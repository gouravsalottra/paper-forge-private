from __future__ import annotations

import csv
import base64
import hashlib
import ast
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from openai import AzureOpenAI

from api.model_registry import active_model_name, default_model
from api.stats_executor import _csv_text, load_yfinance_context
from storage.blob import write_artifact

logger = logging.getLogger(__name__)

AZURE_ENDPOINT = "https://thrivarc.openai.azure.com/"
AZURE_DEPLOYMENT = default_model()
AZURE_API_VERSION = "2024-12-01-preview"
EXECUTION_TIMEOUT_SECONDS = 120
MAX_CODE_FIX_ATTEMPTS = int(os.getenv("THRIVARC_CODE_FIX_ATTEMPTS", "5"))
MODAL_ACCOUNT_ALIAS = os.getenv("MODAL_ACCOUNT_ALIAS", "primary")
LLM_CALL_RETRIES = int(os.getenv("THRIVARC_COMPUTE_LLM_RETRIES", "3"))
LLM_CALL_TIMEOUT_SECONDS = float(os.getenv("THRIVARC_COMPUTE_LLM_TIMEOUT_SECONDS", "120"))
LLM_RETRY_DELAY_SECONDS = float(os.getenv("THRIVARC_COMPUTE_LLM_RETRY_DELAY_SECONDS", "2"))


def _method_style(blueprint: dict[str, Any]) -> str:
    return str(blueprint.get("method_style") or blueprint.get("method_family") or "descriptive").strip().lower()


def _topic_text(blueprint: dict[str, Any]) -> str:
    return str(blueprint.get("focus_question") or blueprint.get("topic") or "Thrivarc research question")


def _round(value: Any, digits: int = 6) -> float | None:
    try:
        if value != value:  # NaN
            return None
        return round(float(value), digits)
    except Exception:
        return None


def _slug(value: str, fallback: str = "artifact") -> str:
    clean = re.sub(r"[^a-zA-Z0-9_.-]+", "_", str(value or "").strip()).strip("._-")
    return clean[:90] or fallback


def _extract_json_from_text(text: str) -> dict[str, Any] | None:
    text = str(text or "").strip()
    if not text:
        return None
    for line in reversed([ln.strip() for ln in text.splitlines() if ln.strip()]):
        try:
            parsed = json.loads(line)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            continue
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidate = text[start : end + 1]
        try:
            parsed = json.loads(candidate)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass
        try:
            normalized = re.sub(r"\b(?:np|numpy)\.(?:float|int)(?:16|32|64)?\(([^()]+)\)", r"\1", candidate)
            normalized = re.sub(r"\bnan\b", "None", normalized, flags=re.IGNORECASE)
            parsed = ast.literal_eval(normalized)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            return None
    return None


def _clean_generated_code(code: str) -> str:
    """Normalize LLM-authored code before it reaches a Python executor."""
    text = str(code or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    text = re.sub(r"^\s*python\s*\n", "", text, flags=re.IGNORECASE)
    return text.strip()


def _generated_code_preflight_error(code: str) -> str | None:
    forbidden_imports = ("import sklearn", "from sklearn")
    lowered = code.lower()
    if any(token in lowered for token in forbidden_imports):
        return "scikit-learn/sklearn is not available in the Modal analysis runtime; use numpy, scipy, pandas, or statsmodels instead."
    if code.lstrip().startswith("```"):
        return "Generated code still contains markdown fences; return executable Python only."
    return None


def _compute_backend() -> str:
    requested = str(os.getenv("THRIVARC_COMPUTE_BACKEND") or "").strip().lower()
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("THRIVARC_STORAGE_BACKEND") == "mock":
        return requested or "local"
    if os.getenv("ENVIRONMENT") == "production":
        if requested and requested != "modal":
            raise RuntimeError("Production generated-code execution must use THRIVARC_COMPUTE_BACKEND=modal.")
        return "modal"
    return requested or "local"


def _safe_payload_blueprint(blueprint: dict[str, Any]) -> str:
    """Serialize the locked Blueprint without adding process secrets to Modal payloads."""
    return json.dumps(blueprint, default=str)


def _client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=os.environ["OPENAI_API_KEY"],
        api_version=AZURE_API_VERSION,
        timeout=LLM_CALL_TIMEOUT_SECONDS,
    )


def _call_llm(prompt: str, *, max_tokens: int = 4000, expect_json: bool = False) -> str:
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("THRIVARC_STORAGE_BACKEND") == "mock":
        return _offline_test_llm(prompt, expect_json=expect_json)
    last_error: Exception | None = None
    client = _client()
    for attempt in range(1, LLM_CALL_RETRIES + 1):
        try:
            model_name = active_model_name(AZURE_DEPLOYMENT)
            response = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.1,
                timeout=LLM_CALL_TIMEOUT_SECONDS,
                **({"response_format": {"type": "json_object"}} if expect_json else {}),
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning(
                "Compute LLM call failed on attempt %s/%s: %s",
                attempt,
                LLM_CALL_RETRIES,
                exc,
            )
            if attempt < LLM_CALL_RETRIES:
                time.sleep(LLM_RETRY_DELAY_SECONDS * attempt)
    raise RuntimeError(f"Compute LLM call failed after {LLM_CALL_RETRIES} attempts: {last_error}") from last_error


def _schema_for_csv(data_csv_path: str) -> dict[str, Any]:
    import pandas as pd

    df_sample = pd.read_csv(data_csv_path, nrows=5)
    with open(data_csv_path, "r", encoding="utf-8", errors="ignore") as handle:
        n_rows = max(0, sum(1 for _ in handle) - 1)
    return {
        "columns": list(df_sample.columns),
        "dtypes": df_sample.dtypes.astype(str).to_dict(),
        "n_rows": n_rows,
        "sample": df_sample.head(3).to_dict(orient="records"),
    }


def _write_context_data(blueprint: dict[str, Any], workdir: str) -> tuple[str, str | None, dict[str, Any]]:
    ctx = load_yfinance_context(blueprint)
    data_csv_path = os.path.join(workdir, "analysis_input.csv")
    ctx.returns.to_csv(data_csv_path, index=False)
    event_csv_path = None
    if ctx.events is not None:
        event_csv_path = os.path.join(workdir, "events.csv")
        ctx.events.to_csv(event_csv_path, index=False)
    context = {
        "identifiers": ctx.identifiers,
        "window": ctx.window,
        "topic": ctx.topic,
        "method_family": _method_style(blueprint),
        "data_row_count": int(len(ctx.returns)),
    }
    return data_csv_path, event_csv_path, context


def _llm_write_analysis_code(blueprint: dict[str, Any], schema: dict[str, Any], session_id: str | None, event_schema: dict[str, Any] | None = None) -> str:
    prompt = f"""
You are the best quantitative analyst in empirical finance.
You have been given a locked research Blueprint and a dataset schema.
Your job is to write complete, executable Python analysis code for THIS study.

RESEARCH BLUEPRINT:
{json.dumps(blueprint, indent=2, default=str)}

DATA SCHEMA:
{json.dumps(schema, indent=2, default=str)}

EVENT SCHEMA, IF PROVIDED:
{json.dumps(event_schema or {}, indent=2, default=str)}

RUNTIME PATHS ARE PROVIDED AS ENVIRONMENT VARIABLES:
DATA_CSV_PATH: path to the verified input CSV
EVENT_CSV_PATH: optional event CSV path, may be empty
FIGURES_DIR: directory where all PNG/PDF figures must be written
RESULTS_DIR: directory where all result CSV files must be written
BLUEPRINT_JSON: JSON string of the locked Blueprint

AVAILABLE LIBRARIES:
pandas, numpy, scipy, statsmodels, linearmodels, arch, matplotlib.
scikit-learn/sklearn is NOT installed. Do not import it.

HOW TO THINK:
Read the Blueprint and the data schema. Decide what analysis this study needs.
Do not apply a fixed template. If the Blueprint is a time-series predictive
question, identify predictors and outcomes from the available columns and run a
predictive analysis appropriate to the claim. If it is an event study and an
event file is present, align events and compute event-window evidence. If it is
a regression or panel study, construct pre-measured predictors and subsequent
outcomes from the available columns, then estimate the appropriate model.

REQUIREMENTS:
1. Load data from os.environ["DATA_CSV_PATH"].
2. Use EVENT_CSV_PATH only if it exists and is relevant to the Blueprint.
3. Compute variables, transformations, tests, and figures required by the study.
4. Use matplotlib with matplotlib.use("Agg") before importing pyplot.
5. Save figures to FIGURES_DIR. Every figure needs title, axis labels, and legend when useful.
6. Save human-readable CSVs to RESULTS_DIR. CSV headers must be proper English, not snake_case.
7. At the end, print exactly one JSON object on its own final line with this shape:
{{
  "primary_result": {{
    "label": "human readable primary test name",
    "coefficient": number or null,
    "t_statistic": number or null,
    "p_value": number or null,
    "interpretation": "plain-English interpretation with numbers"
  }},
  "additional_results": [
    {{"label": "human readable result", "statistic": number or null, "p_value": number or null, "interpretation": "plain English"}}
  ],
  "figures": ["absolute/path/to/figure.png"],
  "result_csvs": ["absolute/path/to/results.csv"],
  "evidence_conclusion": "hypothesis_supported | hypothesis_not_supported_or_exploratory | analysis_incomplete",
  "economic_interpretation": "one paragraph in plain English"
}}

ECONOMETRIC CORRECTNESS RULES:
- For VIX term-structure studies, compute the spread as the difference in
  closing PRICE LEVELS of the two volatility index series, e.g.
  VIX close level minus VIX3M close level. Do not compute the term-structure
  spread from overnight returns or percentage returns. VIX and VIX3M are
  volatility indices measured in percentage points, not return series.
- If you report a bootstrap confidence interval for a regression coefficient,
  bootstrap that same coefficient from the same regression. Resample rows with
  replacement, refit the identical regression in each draw, collect the same
  coefficient, and report the 2.5th and 97.5th percentiles. The confidence
  interval must correspond to, and normally contain, the reported point
  estimate unless the bootstrap distribution itself is degenerate or invalid.
- If an out-of-sample R-squared is computed, write the numeric value to the
  CSV and JSON summary. Do not report only that the check completed.
- If a method is inapplicable to the available schema, skip it with a
  plain-English reason instead of printing Python exceptions into results.

STRICT RULES:
- Write only Python code. No markdown fences. No explanation.
- Do not hardcode research-topic-specific content. Read the Blueprint and schema.
- Do not write snake_case labels into CSV headers or interpretations.
- Do not import sklearn or any package not listed above.
- If a test is not applicable, skip it and include a plain-English reason.
- Every number must be computed from the data loaded from DATA_CSV_PATH or EVENT_CSV_PATH.
"""
    return _clean_generated_code(_call_llm(prompt, max_tokens=5000))


def _llm_fix_code(code: str, error: str, blueprint: dict[str, Any], schema: dict[str, Any]) -> str:
    prompt = f"""
This Python analysis code failed. Fix it so it runs successfully.

BLUEPRINT:
{json.dumps(blueprint, indent=2, default=str)}

DATA SCHEMA:
{json.dumps(schema, indent=2, default=str)}

BROKEN CODE:
{code}

ERROR:
{error[-3000:]}

Preserve econometric intent while fixing the code:
- VIX term-structure spread means close-level VIX minus close-level VIX3M, not
  a return spread.
- Bootstrap confidence intervals for regression coefficients must resample and
  refit the same regression coefficient being reported.
- Failed or inapplicable tests should be skipped with plain-English reasons,
  not written as Python exception text.
- Do not import sklearn/scikit-learn or any package outside pandas, numpy,
  scipy, statsmodels, linearmodels, arch, and matplotlib.
- Return executable Python only, without markdown fences.

Return only fixed Python code. No markdown fences. No explanation.
"""
    return _clean_generated_code(_call_llm(prompt, max_tokens=5000))


def _run_local_analysis_attempt(
    current_code: str,
    data_csv_path: str,
    event_csv_path: str | None,
    figures_dir: str,
    results_dir: str,
    blueprint: dict[str, Any],
) -> dict[str, Any]:
    env = os.environ.copy()
    env.update(
        {
            "DATA_CSV_PATH": data_csv_path,
            "EVENT_CSV_PATH": event_csv_path or "",
            "FIGURES_DIR": figures_dir,
            "RESULTS_DIR": results_dir,
            "BLUEPRINT_JSON": _safe_payload_blueprint(blueprint),
        }
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as handle:
        handle.write(current_code)
        code_path = handle.name
    try:
        result = subprocess.run(
            [sys.executable, code_path],
            capture_output=True,
            text=True,
            timeout=EXECUTION_TIMEOUT_SECONDS,
            env=env,
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "parsed": _extract_json_from_text(result.stdout),
            "backend": "local",
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "success": False,
            "returncode": 124,
            "stdout": str(exc.stdout or ""),
            "stderr": f"analysis code timed out after {EXECUTION_TIMEOUT_SECONDS}s: {exc}",
            "parsed": None,
            "backend": "local",
        }
    finally:
        try:
            os.unlink(code_path)
        except OSError:
            pass


def _modal_payload(
    current_code: str,
    data_csv_path: str,
    event_csv_path: str | None,
    session_id: str | None,
    blueprint: dict[str, Any],
) -> dict[str, Any]:
    payload = {
        "session_id": session_id or "local-compute",
        "code": current_code,
        "data_csv_b64": base64.b64encode(Path(data_csv_path).read_bytes()).decode("ascii"),
        "event_csv_b64": base64.b64encode(Path(event_csv_path).read_bytes()).decode("ascii") if event_csv_path else "",
        "blueprint_json": _safe_payload_blueprint(blueprint),
        "timeout_seconds": int(os.getenv("MODAL_ANALYSIS_ATTEMPT_TIMEOUT_SECONDS", str(EXECUTION_TIMEOUT_SECONDS))),
        "modal_account_alias": os.getenv("MODAL_ACCOUNT_ALIAS", MODAL_ACCOUNT_ALIAS),
    }
    forbidden_keys = {"OPENAI_API_KEY", "DATABASE_URL", "AZURE_STORAGE_CONNECTION_STRING", "MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"}
    leaked = forbidden_keys.intersection(payload)
    if leaked:
        raise RuntimeError(f"Modal payload unexpectedly included secret keys: {sorted(leaked)}")
    return payload


def _materialize_modal_files(modal_result: dict[str, Any], figures_dir: str, results_dir: str, work_root: str) -> dict[str, Any]:
    parsed = modal_result.get("parsed") if isinstance(modal_result.get("parsed"), dict) else None
    if not isinstance(parsed, dict) or ("primary_result" not in parsed and "additional_results" not in parsed):
        parsed = _extract_json_from_text(modal_result.get("stdout", ""))
    if not isinstance(parsed, dict):
        parsed = {"raw_output": str(modal_result.get("stdout") or "").strip()}
    figures: list[str] = []
    result_csvs: list[str] = []
    logs_dir = os.path.join(work_root, "modal_logs")
    os.makedirs(logs_dir, exist_ok=True)
    for file_info in modal_result.get("files") or []:
        if not isinstance(file_info, dict) or file_info.get("skipped"):
            continue
        content_b64 = file_info.get("content_b64")
        if not content_b64:
            continue
        filename = _slug(file_info.get("filename") or "modal_output", "modal_output")
        kind = str(file_info.get("kind") or "").lower()
        if kind == "figure":
            target_dir = figures_dir
        elif kind == "result_csv":
            target_dir = results_dir
        else:
            target_dir = logs_dir
        os.makedirs(target_dir, exist_ok=True)
        local_path = os.path.join(target_dir, filename)
        with open(local_path, "wb") as handle:
            handle.write(base64.b64decode(content_b64))
        if kind == "figure":
            figures.append(local_path)
        elif kind == "result_csv":
            result_csvs.append(local_path)
    if figures:
        parsed["figures"] = figures
    if result_csvs:
        parsed["result_csvs"] = result_csvs
    parsed["figures_dir"] = figures_dir
    parsed["results_dir"] = results_dir
    parsed["modal_logs_dir"] = logs_dir
    parsed["modal_execution"] = {
        "backend": "modal",
        "modal_account_alias": modal_result.get("modal_account_alias") or os.getenv("MODAL_ACCOUNT_ALIAS", MODAL_ACCOUNT_ALIAS),
        "returncode": modal_result.get("returncode"),
        "runtime_seconds": modal_result.get("runtime_seconds"),
        "environment": modal_result.get("environment", {}),
        "routing": modal_result.get("routing", {}),
    }
    parsed["stderr"] = str(modal_result.get("stderr") or "")[-2000:]
    return parsed


def _run_modal_analysis_attempt(
    current_code: str,
    data_csv_path: str,
    event_csv_path: str | None,
    figures_dir: str,
    results_dir: str,
    work_root: str,
    session_id: str | None,
    blueprint: dict[str, Any],
) -> dict[str, Any]:
    from api.modal_compute import execute_in_modal

    modal_result = execute_in_modal(_modal_payload(current_code, data_csv_path, event_csv_path, session_id, blueprint))
    parsed = _materialize_modal_files(modal_result, figures_dir, results_dir, work_root)
    return {
        "success": bool(modal_result.get("success")),
        "returncode": modal_result.get("returncode"),
        "stdout": str(modal_result.get("stdout") or ""),
        "stderr": str(modal_result.get("stderr") or ""),
        "parsed": parsed,
        "backend": "modal",
        "runtime_seconds": modal_result.get("runtime_seconds"),
    }


def _execute_analysis_code(code: str, data_csv_path: str, session_id: str | None, blueprint: dict[str, Any], schema: dict[str, Any], event_csv_path: str | None = None) -> dict[str, Any]:
    run_id = session_id or "local-compute"
    work_root = tempfile.mkdtemp(prefix=f"thrivarc-{_slug(run_id)}-")
    figures_dir = os.path.join(work_root, "figures")
    results_dir = os.path.join(work_root, "results")
    os.makedirs(figures_dir, exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)
    current_code = code
    last_error = ""
    backend = _compute_backend()
    for attempt in range(1, MAX_CODE_FIX_ATTEMPTS + 1):
        try:
            current_code = _clean_generated_code(current_code)
            preflight_error = _generated_code_preflight_error(current_code)
            if preflight_error:
                last_error = preflight_error
                logger.warning("LLM analysis code failed preflight on attempt %s: %s", attempt, preflight_error)
                current_code = _llm_fix_code(current_code, preflight_error, blueprint, schema)
                continue
            if backend == "modal":
                result = _run_modal_analysis_attempt(current_code, data_csv_path, event_csv_path, figures_dir, results_dir, work_root, session_id, blueprint)
            else:
                result = _run_local_analysis_attempt(current_code, data_csv_path, event_csv_path, figures_dir, results_dir, blueprint)
            if result.get("success"):
                parsed = result.get("parsed") if isinstance(result.get("parsed"), dict) else _extract_json_from_text(result.get("stdout", ""))
                if not isinstance(parsed, dict):
                    parsed = {"raw_output": str(result.get("stdout") or "").strip()}
                parsed["figures_dir"] = figures_dir
                parsed["results_dir"] = results_dir
                parsed["analysis_code"] = current_code
                parsed["stderr"] = str(result.get("stderr") or "")[-2000:]
                parsed["compute_backend"] = backend
                modal_execution = parsed.get("modal_execution") if isinstance(parsed.get("modal_execution"), dict) else {}
                parsed["modal_account_alias"] = modal_execution.get("modal_account_alias") if backend == "modal" else None
                parsed["modal_routing"] = modal_execution.get("routing", {}) if backend == "modal" else {}
                parsed["execution_attempts"] = attempt
                if result.get("runtime_seconds") is not None:
                    parsed["runtime_seconds"] = result.get("runtime_seconds")
                return parsed
            last_error = str(result.get("stderr") or result.get("stdout") or "")[-4000:]
            logger.warning("LLM analysis code failed on attempt %s: %s", attempt, last_error[-500:])
            current_code = _llm_fix_code(current_code, last_error, blueprint, schema)
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            logger.warning("Analysis execution backend %s failed on attempt %s: %s", backend, attempt, last_error[-500:])
            current_code = _llm_fix_code(current_code, last_error, blueprint, schema)
    return {"error": f"Analysis failed after {MAX_CODE_FIX_ATTEMPTS} attempts", "last_error": last_error, "figures_dir": figures_dir, "results_dir": results_dir, "analysis_code": current_code, "compute_backend": backend, "modal_account_alias": os.getenv("MODAL_ACCOUNT_ALIAS", MODAL_ACCOUNT_ALIAS) if backend == "modal" else None, "execution_attempts": MAX_CODE_FIX_ATTEMPTS}


def _llm_format_results(blueprint: dict[str, Any], raw_results: dict[str, Any], session_id: str | None) -> dict[str, Any]:
    prompt = f"""
You are formatting statistical results for an academic finance paper.
Convert raw code execution results into clean, human-readable JSON.

BLUEPRINT:
{json.dumps(blueprint, indent=2, default=str)}

RAW RESULTS:
{json.dumps(raw_results, indent=2, default=str)}

Return ONLY valid JSON with this shape:
{{
  "primary_finding": "one paragraph in plain English with actual numbers",
  "tables": [
    {{
      "title": "Human-readable table title",
      "headers": ["Column 1", "Column 2"],
      "rows": [["cell", "cell"]],
      "notes": "table notes"
    }}
  ],
  "figure_paths": ["path1.png"],
  "stats_summary": {{
    "primary_test": {{"label": "...", "statistic": null, "p_value": null, "interpretation": "..."}}
  }},
  "evidence_conclusion": "hypothesis_supported | hypothesis_not_supported_or_exploratory | analysis_incomplete",
  "economic_interpretation": "one paragraph"
}}

RULES:
- No snake_case in labels, table headers, notes, or prose.
- Every number must come from RAW RESULTS.
- Missing values must be null, never an empty string.
"""
    response = _call_llm(prompt, max_tokens=2500, expect_json=True)
    parsed = _extract_json_from_text(response)
    return parsed if isinstance(parsed, dict) else raw_results


def _read_csv_rows(path: str) -> list[dict[str, Any]]:
    try:
        with open(path, newline="", encoding="utf-8", errors="replace") as handle:
            return list(csv.DictReader(handle))
    except Exception:
        return []


def _csv_text_from_file(path: str) -> str:
    try:
        return Path(path).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _stats_rows_from_summary(summary: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    primary = summary.get("primary_result") if isinstance(summary.get("primary_result"), dict) else {}
    if primary:
        rows.append(
            {
                "Test": primary.get("label") or "Primary test",
                "Statistic": primary.get("t_statistic") if primary.get("t_statistic") is not None else primary.get("coefficient"),
                "P Value": primary.get("p_value"),
                "Interpretation": primary.get("interpretation"),
                "Status": "Complete" if not summary.get("error") else "Failed",
            }
        )
    for item in summary.get("additional_results") or []:
        if isinstance(item, dict):
            rows.append(
                {
                    "Test": item.get("label") or "Additional result",
                    "Statistic": item.get("statistic"),
                    "P Value": item.get("p_value"),
                    "Interpretation": item.get("interpretation"),
                    "Status": item.get("status") or "Complete",
                }
            )
    if not rows and summary.get("error"):
        rows.append({"Test": "LLM-authored analysis", "Status": "Failed", "Interpretation": summary.get("last_error") or summary.get("error")})
    return rows


def _stats_csv(rows: list[dict[str, Any]]) -> str:
    fields = ["Test", "Statistic", "P Value", "Interpretation", "Status"]
    expanded = list(dict.fromkeys(fields + [key for row in rows for key in row.keys()]))
    return _csv_text(rows or [{"Test": "Analysis", "Status": "Not computed", "Interpretation": "No result rows were produced."}], expanded)


def _artifact_path_for_result_csv(filename: str, index: int) -> str:
    lower = filename.lower()
    if any(token in lower for token in ["summary", "test", "inference", "stat", "result"]):
        return f"07_statistics/results_tables/{_slug(filename, f'result_{index}.csv')}"
    return f"06_compute/method_outputs/{_slug(filename, f'output_{index}.csv')}"


def _upload_outputs(session_id: str | None, raw_results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    figures: dict[str, dict[str, Any]] = {}
    if not session_id:
        return figures
    figure_paths = list(raw_results.get("figures") or [])
    figures_dir = raw_results.get("figures_dir")
    if figures_dir and os.path.isdir(figures_dir):
        for path in Path(figures_dir).iterdir():
            if path.suffix.lower() in {".png", ".pdf"} and str(path) not in figure_paths:
                figure_paths.append(str(path))
    for idx, local in enumerate(figure_paths, start=1):
        path = Path(str(local))
        if not path.exists() or path.suffix.lower() not in {".png", ".pdf"}:
            continue
        filename = _slug(path.name, f"figure_{idx}{path.suffix.lower()}")
        artifact_ref = write_artifact(session_id, f"figures/{filename}", path.read_bytes())
        key = f"fig{idx}_{Path(filename).stem}"
        figures[key] = {
            "key": key,
            "path": f"figures/{filename}",
            "blob_path": artifact_ref.get("blob_path"),
            "filename": filename,
            "caption": raw_results.get("figure_captions", {}).get(str(local), Path(filename).stem.replace("_", " ").title()) if isinstance(raw_results.get("figure_captions"), dict) else Path(filename).stem.replace("_", " ").title(),
            "label": f"fig:{Path(filename).stem}",
            "sha256": artifact_ref.get("sha256"),
            "bytes": artifact_ref.get("bytes"),
        }
    return figures


def _upload_execution_artifacts(session_id: str | None, raw_results: dict[str, Any]) -> dict[str, dict[str, Any]]:
    artifacts: dict[str, dict[str, Any]] = {}
    if not session_id:
        return artifacts
    analysis_code = raw_results.get("analysis_code")
    if isinstance(analysis_code, str) and analysis_code.strip():
        artifacts["analysis_code"] = write_artifact(session_id, "06_compute/generated_code/analysis_code.py", analysis_code)
    stderr = raw_results.get("stderr")
    if isinstance(stderr, str) and stderr.strip():
        artifacts["stderr"] = write_artifact(session_id, "06_compute/logs/stderr.txt", stderr)
    logs_dir = raw_results.get("modal_logs_dir")
    if logs_dir and os.path.isdir(logs_dir):
        for path in sorted(Path(logs_dir).iterdir()):
            if path.is_file():
                key = f"modal_log_{path.stem}"
                artifacts[key] = write_artifact(session_id, f"06_compute/logs/{_slug(path.name, 'modal_log.txt')}", path.read_bytes())
    manifest = {
        "backend": raw_results.get("compute_backend"),
        "modal_account_alias": raw_results.get("modal_account_alias"),
        "execution_attempts": raw_results.get("execution_attempts"),
        "runtime_seconds": raw_results.get("runtime_seconds"),
        "modal_execution": raw_results.get("modal_execution", {}),
        "modal_routing": raw_results.get("modal_routing", {}),
        "error": raw_results.get("error"),
        "last_error": raw_results.get("last_error"),
    }
    artifacts["execution_manifest"] = write_artifact(session_id, "06_compute/manifests/execution_manifest.json", json.dumps(manifest, indent=2, default=str))
    return artifacts


def _collect_csv_outputs(data_csv_path: str, raw_results: dict[str, Any], stats_rows: list[dict[str, Any]]) -> dict[str, str]:
    outputs: dict[str, str] = {"03_data/overnight_returns.csv": _csv_text_from_file(data_csv_path)}
    seen: set[str] = set()
    for idx, local in enumerate(raw_results.get("result_csvs") or [], start=1):
        path = Path(str(local))
        if not path.exists() or path.suffix.lower() != ".csv":
            continue
        artifact_path = _artifact_path_for_result_csv(path.name, idx)
        outputs[artifact_path] = _csv_text_from_file(str(path))
        seen.add(str(path.resolve()))
    results_dir = raw_results.get("results_dir")
    if results_dir and os.path.isdir(results_dir):
        for idx, path in enumerate(sorted(Path(results_dir).glob("*.csv")), start=1):
            if str(path.resolve()) in seen:
                continue
            outputs[_artifact_path_for_result_csv(path.name, idx)] = _csv_text_from_file(str(path))
    stats_text = _stats_csv(stats_rows)
    outputs.setdefault("07_statistics/results_tables/executed_tests.csv", stats_text)
    outputs.setdefault("08_stats/stats_summary.csv", stats_text)
    return outputs


def _primary_numbers(raw_results: dict[str, Any], formatted: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    primary = raw_results.get("primary_result") if isinstance(raw_results.get("primary_result"), dict) else {}
    primary_test = (formatted.get("stats_summary") or {}).get("primary_test") if isinstance(formatted.get("stats_summary"), dict) else {}
    if not isinstance(primary_test, dict):
        primary_test = {}
    t_stat = primary.get("t_statistic") if primary.get("t_statistic") is not None else primary_test.get("statistic")
    p_value = primary.get("p_value") if primary.get("p_value") is not None else primary_test.get("p_value")
    return {
        "row_count": context.get("data_row_count"),
        "identifier_count": len(context.get("identifiers") or []),
        "primary_analysis_type": context.get("method_family"),
        "primary_label": primary.get("label") or primary_test.get("label"),
        "coefficient": primary.get("coefficient"),
        "primary_t_stat": t_stat,
        "primary_p_value": p_value,
        "primary_finding": formatted.get("primary_finding") or primary.get("interpretation"),
        "return_definition": raw_results.get("return_definition"),
    }


def _result_hash(primary_numbers: dict[str, Any], raw_results: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps({"primary_numbers": primary_numbers, "results": raw_results}, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def dispatch_compute(session_id: str | None, blueprint: dict[str, Any], data_csv_path: str | None = None, conn: Any | None = None) -> dict[str, Any]:
    """LLM-first compute dispatcher: the LLM writes analysis code; Python executes it."""
    workdir_obj = tempfile.TemporaryDirectory(prefix=f"thrivarc-compute-{_slug(session_id or 'local')}-")
    workdir = workdir_obj.name
    try:
        event_csv_path = None
        context: dict[str, Any]
        if data_csv_path:
            context = {"identifiers": [], "window": {}, "topic": _topic_text(blueprint), "method_family": _method_style(blueprint), "data_row_count": None}
        else:
            data_csv_path, event_csv_path, context = _write_context_data(blueprint, workdir)
        schema = _schema_for_csv(data_csv_path)
        event_schema = _schema_for_csv(event_csv_path) if event_csv_path else None
        context["data_row_count"] = schema.get("n_rows", context.get("data_row_count"))
        code = _llm_write_analysis_code(blueprint, schema, session_id, event_schema)
        raw_results = _execute_analysis_code(code, data_csv_path, session_id, blueprint, schema, event_csv_path)
        formatted = _llm_format_results(blueprint, raw_results, session_id)
        stats_rows = _stats_rows_from_summary(raw_results)
        csv_outputs = _collect_csv_outputs(data_csv_path, raw_results, stats_rows)
        figure_artifacts = _upload_outputs(session_id, raw_results)
        execution_artifacts = _upload_execution_artifacts(session_id, raw_results)
        primary_numbers = _primary_numbers(raw_results, formatted, context)
        if not primary_numbers.get("return_definition"):
            primary_numbers["return_definition"] = blueprint.get("return_definition") or blueprint.get("overnight_return_definition")
        executed_tests = [row.get("Test") for row in stats_rows if str(row.get("Status", "")).lower() in {"complete", "completed"}]
        skipped_tests = {row.get("Test"): row.get("Interpretation") for row in stats_rows if str(row.get("Status", "")).lower() not in {"complete", "completed"} and row.get("Test")}
        return {
            "context": {"identifiers": context.get("identifiers", []), "window": context.get("window", {}), "method_family": context.get("method_family"), "topic": context.get("topic")},
            "event_rows": [],
            "car_rows": [],
            "summary_statistics_rows": [],
            "executed_test_rows": stats_rows,
            "csv_outputs": csv_outputs,
            "figure_artifacts": figure_artifacts,
            "execution_artifacts": execution_artifacts,
            "primary_numbers": primary_numbers,
            "robustness_results": {
                "raw_execution_summary": raw_results,
                "formatted_results": formatted,
                "result_tables": formatted.get("tables", []) if isinstance(formatted, dict) else [],
            },
            "stats_summary": {
                "executed_tests": executed_tests,
                "skipped_tests": skipped_tests,
                "formatted": formatted.get("stats_summary", {}) if isinstance(formatted, dict) else {},
                "primary_finding": formatted.get("primary_finding") if isinstance(formatted, dict) else None,
            },
            "evidence_conclusion": formatted.get("evidence_conclusion") or raw_results.get("evidence_conclusion") or ("analysis_incomplete" if raw_results.get("error") else "hypothesis_not_supported_or_exploratory"),
            "economic_interpretation": formatted.get("economic_interpretation") or raw_results.get("economic_interpretation") or primary_numbers.get("primary_finding") or "The LLM-authored analysis executed and produced verified results.",
            "price_result_sha256": _result_hash(primary_numbers, raw_results),
            "price_window": context.get("window", {}),
            "data_row_count": schema.get("n_rows", 0),
            "analysis_code": raw_results.get("analysis_code", code),
            "execution_metadata": {
                "backend": raw_results.get("compute_backend") or _compute_backend(),
                "modal_account_alias": raw_results.get("modal_account_alias"),
                "attempts": raw_results.get("execution_attempts"),
                "runtime_seconds": raw_results.get("runtime_seconds"),
                "modal_execution": raw_results.get("modal_execution", {}),
                "modal_routing": raw_results.get("modal_routing", {}),
                "stderr": raw_results.get("stderr"),
                "error": raw_results.get("error"),
                "last_error": raw_results.get("last_error"),
            },
        }
    finally:
        # Temporary execution outputs are copied into the returned CSV strings and
        # uploaded Blob artifacts before cleanup.
        try:
            workdir_obj.cleanup()
        except Exception:
            pass


def execute_custom_analysis_code(session_id: str | None, blueprint: dict[str, Any], code: str) -> dict[str, Any]:
    """Execute researcher-visible cockpit cell code through the normal backend.

    Production still routes through Modal via _execute_analysis_code(); this
    helper only lets the cockpit provide the code instead of asking the LLM to
    generate a fresh monolithic script.
    """
    workdir_obj = tempfile.TemporaryDirectory(prefix=f"thrivarc-cells-{_slug(session_id or 'local')}-")
    workdir = workdir_obj.name
    try:
        data_csv_path, event_csv_path, context = _write_context_data(blueprint, workdir)
        schema = _schema_for_csv(data_csv_path)
        raw_results = _execute_analysis_code(code, data_csv_path, session_id, blueprint, schema, event_csv_path)
        stats_rows = _stats_rows_from_summary(raw_results)
        csv_outputs = _collect_csv_outputs(data_csv_path, raw_results, stats_rows)
        figure_artifacts = _upload_outputs(session_id, raw_results)
        execution_artifacts = _upload_execution_artifacts(session_id, raw_results)
        return {
            "context": context,
            "success": not raw_results.get("error"),
            "raw_results": raw_results,
            "csv_outputs": csv_outputs,
            "figure_artifacts": figure_artifacts,
            "execution_artifacts": execution_artifacts,
            "stats_rows": stats_rows,
            "analysis_code": raw_results.get("analysis_code", code),
            "execution_metadata": {
                "backend": raw_results.get("compute_backend") or _compute_backend(),
                "modal_account_alias": raw_results.get("modal_account_alias"),
                "attempts": raw_results.get("execution_attempts"),
                "runtime_seconds": raw_results.get("runtime_seconds"),
                "modal_execution": raw_results.get("modal_execution", {}),
                "modal_routing": raw_results.get("modal_routing", {}),
                "stderr": raw_results.get("stderr"),
                "error": raw_results.get("error"),
                "last_error": raw_results.get("last_error"),
            },
        }
    finally:
        try:
            workdir_obj.cleanup()
        except Exception:
            pass


def execute_research_plan(blueprint: dict[str, Any], stats_spec: dict[str, Any] | None = None, session_id: str | None = None) -> dict[str, Any]:
    """Compatibility entrypoint used by session orchestration and tests."""
    result = dispatch_compute(session_id, blueprint)
    
    from api.artifact_contract import ComputeArtifacts, validate_or_raise
    
    primary = result.get('primary_numbers', {})
    mapped_primary = {
        'label': primary.get('primary_label'),
        'statistic': primary.get('primary_t_stat'),
        'p_value': primary.get('primary_p_value'),
        'coefficient': primary.get('coefficient')
    }
    
    stats_data = result.get('stats_summary', {}).get('formatted', {})
    if not isinstance(stats_data, dict):
        stats_data = {}
    normalized_stats: dict[str, dict[str, Any]] = {}
    for k, v in stats_data.items():
        if isinstance(v, dict):
            row = dict(v)
            if 'status' not in row:
                row['status'] = 'complete' if row.get('statistic') is not None or row.get('p_value') is not None else 'failed'
                if row['status'] == 'failed' and not row.get('interpretation'):
                    row['interpretation'] = 'Test failed to produce valid statistics.'
            normalized_stats[str(k)] = row
    for row in result.get("executed_test_rows", []):
        if not isinstance(row, dict):
            continue
        test_name = str(row.get("Test") or row.get("test") or "Executed test")
        if test_name in normalized_stats:
            continue
        status = str(row.get("Status") or row.get("status") or "complete").lower()
        if status == "completed":
            status = "complete"
        if status not in {"complete", "skipped", "failed"}:
            status = "complete" if row.get("Statistic") not in (None, "") or row.get("P Value") not in (None, "") else "skipped"
        normalized_stats[test_name] = {
            "label": test_name,
            "statistic": row.get("Statistic"),
            "p_value": row.get("P Value"),
            "interpretation": row.get("Interpretation") or ("Test completed." if status == "complete" else "Test did not produce a statistic."),
            "status": status,
        }
        
    artifacts = ComputeArtifacts(
        session_id=session_id or 'local',
        data_csv_paths=list(result.get('csv_outputs', {}).keys()),
        primary_result=mapped_primary,
        stats_summary=normalized_stats,
        figure_blob_paths=[f.get('blob_path', '') for f in result.get('figure_artifacts', {}).values()]
    )
    validate_or_raise(artifacts, "Compute phase")
    
    return result


# Test-only stand-in for LLM responses. Production requires OPENAI_API_KEY and
# uses Azure OpenAI gpt-4o through _call_llm().
def _offline_test_llm(prompt: str, *, expect_json: bool = False) -> str:
    if expect_json:
        return json.dumps(
            {
                "primary_finding": "The generated analysis code produced verified results with human-readable labels.",
                "tables": [],
                "figure_paths": [],
                "stats_summary": {
                    "primary_test": {
                        "label": "Generated analysis",
                        "statistic": None,
                        "p_value": None,
                        "interpretation": "See generated result files and figures.",
                    }
                },
                "evidence_conclusion": "hypothesis_not_supported_or_exploratory",
                "economic_interpretation": "The compute dispatcher executed LLM-authored code rather than a method-specific Python branch.",
            }
        )
    return r'''
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

DATA_CSV_PATH = os.environ["DATA_CSV_PATH"]
FIGURES_DIR = os.environ["FIGURES_DIR"]
RESULTS_DIR = os.environ["RESULTS_DIR"]


def safe_float(value):
    try:
        if pd.isna(value):
            return None
        return round(float(value), 6)
    except Exception:
        return None


def save_figure(name):
    path = os.path.join(FIGURES_DIR, name)
    plt.tight_layout()
    plt.savefig(path, dpi=120, bbox_inches="tight")
    plt.close()
    return path


df = pd.read_csv(DATA_CSV_PATH)
if "date" in df.columns:
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

figures = []
result_csvs = []
primary = {
    "label": "Generated data analysis",
    "coefficient": None,
    "t_statistic": None,
    "p_value": None,
    "interpretation": "Generated analysis completed using available columns.",
}

summary = (
    df.describe(include="all")
    .transpose()
    .reset_index()
    .rename(
        columns={
            "index": "Variable",
            "count": "Observations",
            "mean": "Mean",
            "std": "Standard Deviation",
            "min": "Minimum",
            "max": "Maximum",
        }
    )
)
summary_path = os.path.join(RESULTS_DIR, "Summary Statistics.csv")
summary.to_csv(summary_path, index=False)
result_csvs.append(summary_path)

numeric_cols = [column for column in df.columns if pd.api.types.is_numeric_dtype(df[column])]
if numeric_cols:
    first = numeric_cols[0]
    series = pd.to_numeric(df[first], errors="coerce").dropna()
    if len(series) > 1:
        t_stat, p_value = stats.ttest_1samp(series, 0.0)
        primary = {
            "label": f"Mean test for {first}",
            "coefficient": safe_float(series.mean()),
            "t_statistic": safe_float(t_stat),
            "p_value": safe_float(p_value),
            "interpretation": f"The mean of {first} is {series.mean():.4f} with p={p_value:.3f}.",
        }
        mean_path = os.path.join(RESULTS_DIR, "Primary Mean Test.csv")
        pd.DataFrame(
            [
                {
                    "Test": f"Mean test for {first}",
                    "Estimate": safe_float(series.mean()),
                    "T Statistic": safe_float(t_stat),
                    "P Value": safe_float(p_value),
                    "Observations": int(len(series)),
                }
            ]
        ).to_csv(mean_path, index=False)
        result_csvs.append(mean_path)

if "date" in df.columns and numeric_cols:
    plt.figure(figsize=(9, 4))
    if "ticker" in df.columns:
        for ticker, group in df.groupby("ticker"):
            group = group.sort_values("date")
            plt.plot(group["date"], pd.to_numeric(group[numeric_cols[0]], errors="coerce"), label=str(ticker), linewidth=0.9)
        plt.legend(fontsize=8)
    else:
        ordered = df.sort_values("date")
        plt.plot(ordered["date"], pd.to_numeric(ordered[numeric_cols[0]], errors="coerce"), linewidth=0.9)
    plt.title(f"{numeric_cols[0]} Over Time")
    plt.xlabel("Date")
    plt.ylabel(numeric_cols[0])
    plt.grid(True, alpha=0.3)
    figures.append(save_figure("Time Series Overview.png"))

if len(numeric_cols) >= 2:
    x_col, y_col = numeric_cols[0], numeric_cols[1]
    design = df[[x_col, y_col]].apply(pd.to_numeric, errors="coerce").dropna()
    regression_path = os.path.join(RESULTS_DIR, "Bivariate Relationship.csv")
    if len(design) > 2:
        slope, intercept, r_value, p_value, se = stats.linregress(design[x_col], design[y_col])
        t_stat = slope / se if se else None
        pd.DataFrame(
            [
                {
                    "Relationship": f"{y_col} on {x_col}",
                    "Coefficient": safe_float(slope),
                    "Standard Error": safe_float(se),
                    "T Statistic": safe_float(t_stat),
                    "P Value": safe_float(p_value),
                    "R Squared": safe_float(r_value ** 2),
                    "Observations": int(len(design)),
                }
            ]
        ).to_csv(regression_path, index=False)
        result_csvs.append(regression_path)
        plt.figure(figsize=(7, 5))
        plt.scatter(design[x_col], design[y_col], s=10, alpha=0.45, label="Observations")
        xs = np.linspace(design[x_col].min(), design[x_col].max(), 100)
        plt.plot(xs, intercept + slope * xs, color="red", label="Fitted line")
        plt.title(f"{y_col} Versus {x_col}")
        plt.xlabel(x_col)
        plt.ylabel(y_col)
        plt.legend()
        plt.grid(True, alpha=0.3)
        figures.append(save_figure("Bivariate Relationship.png"))

print(
    json.dumps(
        {
            "primary_result": primary,
            "additional_results": [],
            "figures": figures,
            "result_csvs": result_csvs,
            "evidence_conclusion": "hypothesis_not_supported_or_exploratory",
            "economic_interpretation": primary.get("interpretation"),
        }
    )
)
'''
