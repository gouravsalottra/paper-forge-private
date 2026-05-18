from __future__ import annotations

import base64
import hashlib
import json
import os
from typing import Any

try:  # Modal is an optional runtime dependency for local test environments.
    import modal
except Exception:  # pragma: no cover - exercised only when modal is absent.
    modal = None  # type: ignore[assignment]


MODAL_APP_NAME = os.getenv("MODAL_APP_NAME", "thrivarc-compute")
MODAL_FUNCTION_NAME = os.getenv("MODAL_FUNCTION_NAME", "run_analysis_code")
DEFAULT_TIMEOUT_SECONDS = int(os.getenv("MODAL_EXECUTION_TIMEOUT_SECONDS", "900"))
MAX_RETURN_FILE_BYTES = int(os.getenv("MODAL_MAX_RETURN_FILE_BYTES", str(25 * 1024 * 1024)))

if modal is not None:
    app = modal.App(MODAL_APP_NAME)
    image = (
        modal.Image.debian_slim(python_version="3.12")
        .pip_install(
            "pandas==2.2.3",
            "numpy==2.1.3",
            "scipy==1.15.3",
            "statsmodels==0.14.4",
            "linearmodels==7.0",
            "arch==8.0.0",
            "matplotlib==3.10.0",
            "yfinance==0.2.66",
            "seaborn==0.13.2",
        )
    )
else:  # pragma: no cover
    app = None
    image = None


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
        try:
            parsed = json.loads(text[start : end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _minimal_subprocess_env(extra: dict[str, str]) -> dict[str, str]:
    allowed = {
        "PATH",
        "PYTHONPATH",
        "PYTHONUNBUFFERED",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
        "MPLCONFIGDIR",
    }
    env = {key: value for key, value in os.environ.items() if key in allowed and value}
    env["PYTHONUNBUFFERED"] = "1"
    env.update(extra)
    return env


def _collect_files(directory: str, *, kind: str, suffixes: set[str]) -> list[dict[str, Any]]:
    from pathlib import Path

    files: list[dict[str, Any]] = []
    root = Path(directory)
    if not root.exists():
        return files
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        data = path.read_bytes()
        if len(data) > MAX_RETURN_FILE_BYTES:
            files.append(
                {
                    "kind": kind,
                    "filename": path.name,
                    "relative_path": str(path.relative_to(root)),
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "skipped": True,
                    "reason": "file exceeded Modal return size limit",
                }
            )
            continue
        files.append(
            {
                "kind": kind,
                "filename": path.name,
                "relative_path": str(path.relative_to(root)),
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "content_b64": base64.b64encode(data).decode("ascii"),
            }
        )
    return files


if modal is not None:

    @app.function(image=image, timeout=DEFAULT_TIMEOUT_SECONDS, name=MODAL_FUNCTION_NAME)
    def run_analysis_code(payload: dict[str, Any]) -> dict[str, Any]:
        """Execute one generated-code attempt inside Modal and return files to the API."""
        import importlib.metadata
        import platform
        import subprocess
        import sys
        import tempfile
        import time
        from pathlib import Path

        started = time.time()
        session_id = str(payload.get("session_id") or "modal-compute")
        code = str(payload.get("code") or "")
        timeout_seconds = int(payload.get("timeout_seconds") or 120)
        blueprint_json = str(payload.get("blueprint_json") or "{}")

        with tempfile.TemporaryDirectory(prefix="thrivarc-modal-") as tmpdir:
            root = Path(tmpdir)
            data_path = root / "analysis_input.csv"
            event_path = root / "events.csv"
            figures_dir = root / "figures"
            results_dir = root / "results"
            logs_dir = root / "logs"
            figures_dir.mkdir(parents=True, exist_ok=True)
            results_dir.mkdir(parents=True, exist_ok=True)
            logs_dir.mkdir(parents=True, exist_ok=True)

            data_path.write_bytes(base64.b64decode(payload.get("data_csv_b64") or ""))
            event_b64 = payload.get("event_csv_b64") or ""
            if event_b64:
                event_path.write_bytes(base64.b64decode(event_b64))
                event_env = str(event_path)
            else:
                event_env = ""

            code_path = root / "analysis.py"
            code_path.write_text(code, encoding="utf-8")
            env = _minimal_subprocess_env(
                {
                    "DATA_CSV_PATH": str(data_path),
                    "EVENT_CSV_PATH": event_env,
                    "FIGURES_DIR": str(figures_dir),
                    "RESULTS_DIR": str(results_dir),
                    "BLUEPRINT_JSON": blueprint_json,
                    "MPLCONFIGDIR": str(root / "mplconfig"),
                }
            )

            try:
                completed = subprocess.run(
                    [sys.executable, str(code_path)],
                    capture_output=True,
                    text=True,
                    timeout=timeout_seconds,
                    env=env,
                    cwd=str(root),
                )
                timed_out = False
            except subprocess.TimeoutExpired as exc:
                completed = None
                timed_out = True
                stdout = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
                stderr = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            else:
                stdout = completed.stdout or ""
                stderr = completed.stderr or ""

            (logs_dir / "stdout.txt").write_text(stdout, encoding="utf-8", errors="replace")
            (logs_dir / "stderr.txt").write_text(stderr, encoding="utf-8", errors="replace")
            (logs_dir / "analysis_code.py").write_text(code, encoding="utf-8", errors="replace")

            package_names = ["pandas", "numpy", "scipy", "statsmodels", "linearmodels", "arch", "matplotlib", "yfinance"]
            packages: dict[str, str] = {}
            for name in package_names:
                try:
                    packages[name] = importlib.metadata.version(name)
                except Exception:
                    packages[name] = "not installed"

            files = []
            files.extend(_collect_files(str(results_dir), kind="result_csv", suffixes={".csv"}))
            files.extend(_collect_files(str(figures_dir), kind="figure", suffixes={".png", ".pdf"}))
            files.extend(_collect_files(str(logs_dir), kind="log", suffixes={".txt", ".py"}))

            returncode = 124 if timed_out else int(completed.returncode if completed is not None else 1)
            parsed = _extract_json_from_text(stdout)
            runtime_seconds = round(time.time() - started, 3)
            return {
                "success": returncode == 0,
                "backend": "modal",
                "session_id": session_id,
                "returncode": returncode,
                "timed_out": timed_out,
                "stdout": stdout[-12000:],
                "stderr": stderr[-12000:],
                "parsed": parsed,
                "files": files,
                "runtime_seconds": runtime_seconds,
                "environment": {
                    "python": sys.version,
                    "platform": platform.platform(),
                    "packages": packages,
                },
            }


def _modal_function():
    if modal is None:
        raise RuntimeError("Modal SDK is not installed; cannot use Modal compute backend.")
    if os.getenv("MODAL_USE_DEPLOYED", "1").strip().lower() in {"1", "true", "yes"}:
        app_name = os.getenv("MODAL_APP_NAME", MODAL_APP_NAME)
        function_name = os.getenv("MODAL_FUNCTION_NAME", MODAL_FUNCTION_NAME)
        environment_name = os.getenv("MODAL_ENVIRONMENT") or None
        return modal.Function.from_name(app_name, function_name, environment_name=environment_name)
    # This mode is useful only when the module is running under Modal's own app
    # runner. A normal API container should use the deployed lookup above.
    return run_analysis_code


def execute_in_modal(payload: dict[str, Any]) -> dict[str, Any]:
    """Submit one generated-code attempt to Modal.

    The payload intentionally contains data/code only. Production DB, Blob, and
    OpenAI credentials stay in the API container and are not sent to Modal.
    """
    function = _modal_function()
    return function.remote(payload)
