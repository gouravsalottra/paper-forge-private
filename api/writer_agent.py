from __future__ import annotations

import csv
import io
import json
import logging
import re
from typing import Any

from api.llm_caller import call_agent_llm
from api.prompts import WRITER_PROSE_PROMPT, WRITER_TABLES_PROMPT

logger = logging.getLogger(__name__)


def _latex_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _latex_identifier(value: Any, default: str = "id") -> str:
    """Return a LaTeX-safe structural identifier for labels and citation keys."""
    text = "" if value is None else str(value)
    text = text.replace("\\_", "_")
    text = re.sub(r"[^A-Za-z0-9:._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_.:-")
    return text or default


def _humanize_label(value: Any) -> str:
    text = "" if value is None else str(value)
    if not text:
        return ""
    text = text.replace("\\_", "_").replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip()
    replacements = {
        "newey west": "Newey-West",
        "predictive regression hac": "predictive regression with HAC errors",
        "hac se": "HAC standard error",
        "t stat": "t-statistic",
        "p value": "p-value",
        "r2": "R-squared",
        "oos": "out-of-sample",
        "bh correction": "Benjamini-Hochberg correction",
        "bootstrap ci": "bootstrap confidence interval",
        "event study car": "event-study CAR",
    }
    lower = text.lower()
    if lower in replacements:
        text = replacements[lower]
    else:
        for source, target in replacements.items():
            text = re.sub(rf"\b{re.escape(source)}\b", target, text, flags=re.I)
    text = re.sub(r"\b(hac|hc3|car|bh|ols|vix|vix3m|spy|xle|icln)\b", lambda m: m.group(1).upper(), text, flags=re.I)
    return text


def _paper_cell(value: Any, digits: int = 4) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return ""
    return _humanize_label(value)


def _citation_keys(bibliography_bib: str) -> list[str]:
    return re.findall(r"@\w+\{([^,]+),", bibliography_bib or "")


def _json_table_rows(csv_text: str, limit: int = 18) -> list[dict[str, str]]:
    try:
        return list(csv.DictReader(io.StringIO(csv_text)))[:limit]
    except Exception:
        return []


def _all_csv_rows(csv_text: str) -> list[dict[str, str]]:
    try:
        return list(csv.DictReader(io.StringIO(csv_text or "")))
    except Exception:
        return []


def _csv_by_suffix(csv_artifacts: dict[str, str], suffix: str) -> str:
    for path, text in csv_artifacts.items():
        if str(path).endswith(suffix):
            return text
    return ""


def _as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _mean(values: list[float]) -> float | None:
    clean = [value for value in values if value is not None]
    return sum(clean) / len(clean) if clean else None


def _fmt_num(value: Any, digits: int = 3) -> str:
    number = _as_float(value)
    if number is None:
        return "" if value in (None, "") else str(value)
    if abs(number) < 0.001 and number != 0:
        return "<0.001" if number > 0 else ">-0.001"
    return f"{number:.{digits}f}"


def _fmt_p(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return ""
    return "<0.001" if number < 0.001 else f"{number:.3f}"


def _interpret_p(value: Any) -> str:
    p_value = _as_float(value)
    if p_value is None:
        return "p-value not reported"
    if p_value < 0.01:
        return "statistically significant at the 1% level"
    if p_value < 0.05:
        return "statistically significant at the 5% level"
    if p_value < 0.10:
        return "marginally significant at the 10% level"
    return "not statistically significant at conventional levels"


def _truncate_text(value: Any, limit: int = 60) -> str:
    text = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    return text if len(text) <= limit else text[: max(0, limit - 3)].rstrip() + "..."


def _row_has_error(row: dict[str, str]) -> bool:
    text = " ".join(str(value or "") for value in row.values()).lower()
    markers = ["traceback", "exception", "error", "failed:", "must be", "index on the time dimension"]
    return any(marker in text for marker in markers)


def _primary_numbers_from_context(context: dict[str, Any]) -> dict[str, Any]:
    stats_results = context.get("stats_results", {}) if isinstance(context.get("stats_results"), dict) else {}
    primary_numbers = dict(stats_results.get("primary_numbers") or {})
    findings = stats_results.get("findings")
    if isinstance(findings, dict):
        primary_numbers.update(findings.get("primary_numbers") or {})
        assessment = findings.get("economic_significance_assessment")
        if isinstance(assessment, dict):
            primary_numbers.update(assessment.get("primary_numbers") or {})
    return primary_numbers


def _research_design_values(blueprint: dict[str, Any]) -> tuple[str, str, str, str]:
    window = blueprint.get("inferred_window") or {}
    window_start = window.get("start") or blueprint.get("window_start") or "the start of the sample"
    window_end = window.get("end") or blueprint.get("window_end") or "the end of the sample"
    identifiers = blueprint.get("inferred_identifiers") or blueprint.get("identifiers") or []
    identifier_text = ", ".join(map(str, identifiers)) if identifiers else "the study universe"
    return_definition = (
        blueprint.get("return_definition")
        or blueprint.get("overnight_return_definition")
        or blueprint.get("overnight_return")
        or "the pre-specified return definition"
    )
    return str(window_start), str(window_end), identifier_text, str(return_definition)


def _significant_sentence(label: str, stat: Any, p_value: Any) -> str:
    stat_text = _fmt_num(stat)
    p_text = _fmt_p(p_value)
    if not stat_text or not p_text:
        return ""
    return f"{label} yields t={stat_text}, p={p_text}, which is {_interpret_p(p_value)}."


def _series_columns(row: dict[str, Any], suffix: str, *, exclude_prefixes: tuple[str, ...] = ()) -> list[str]:
    columns = []
    for key in row:
        if not str(key).endswith(suffix):
            continue
        if any(str(key).startswith(prefix) for prefix in exclude_prefixes):
            continue
        columns.append(str(key))
    return columns


def _label_from_series_column(column: str, suffix: str) -> str:
    label = str(column)
    if label.endswith(suffix):
        label = label[: -len(suffix)]
    return label.replace("_", " ").upper()


def _directional_summary(csv_artifacts: dict[str, str]) -> dict[str, Any]:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "event_returns.csv"))
    if not rows:
        return {}
    aligned = [_as_float(row.get("direction_aligned_spread")) for row in rows]
    aligned_clean = [value for value in aligned if value is not None]
    positive_count = sum(1 for value in aligned_clean if value > 0)
    aligned_mean = _mean(aligned_clean)
    aligned_std = None
    if len(aligned_clean) > 1 and aligned_mean is not None:
        aligned_std = (sum((value - aligned_mean) ** 2 for value in aligned_clean) / (len(aligned_clean) - 1)) ** 0.5
    summary: dict[str, Any] = {
        "event_count": len(rows),
        "positive_aligned_count": positive_count,
        "mean_aligned_spread": aligned_mean,
        "aligned_spread_std": aligned_std,
    }
    return_cols = _series_columns(rows[0], "_overnight_return", exclude_prefixes=("direction_aligned", "second_minus_first"))
    if len(return_cols) >= 2:
        first_col, second_col = return_cols[:2]
        summary.update(
            {
                "first_series_label": _label_from_series_column(first_col, "_overnight_return"),
                "second_series_label": _label_from_series_column(second_col, "_overnight_return"),
                "first_series_mean": _mean([_as_float(row.get(first_col)) for row in rows]),
                "second_series_mean": _mean([_as_float(row.get(second_col)) for row in rows]),
            }
        )
    return summary


def _summary_stat_map(csv_artifacts: dict[str, str]) -> dict[str, dict[str, str]]:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "summary_statistics.csv"))
    return {str(row.get("ticker", "")).upper(): row for row in rows if row.get("ticker")}


def _clean_figure_caption(value: Any) -> str:
    text = _humanize_label(value).strip()
    text = re.sub(r"^fig\s*\d+\s*", "", text, flags=re.I).strip()
    text = re.sub(r"\s+", " ", text)
    return text[:1].upper() + text[1:] if text else "Figure"


def _figure_metadata(context: dict[str, Any]) -> dict[str, dict[str, str]]:
    raw = context.get("figure_artifacts", {})
    if not isinstance(raw, dict):
        return {}
    figures: dict[str, dict[str, str]] = {}
    for key, value in raw.items():
        if not isinstance(value, dict):
            continue
        filename = str(value.get("filename") or "").strip()
        path = str(value.get("path") or value.get("blob_path") or "").strip()
        if not filename and path:
            filename = path.rsplit("/", 1)[-1]
        if not filename:
            continue
        figures[str(key)] = {
            "filename": _latex_identifier(filename, "figure.png"),
            "caption": _clean_figure_caption(value.get("caption") or key),
            "label": _latex_identifier(value.get("label") or f"fig:{key}", f"fig:{key}"),
        }
    return figures


def _figure_block(figure: dict[str, str]) -> str:
    if not figure:
        return ""
    return rf"""
\clearpage
\begin{{figure}}[!htbp]
\centering
\includegraphics[width=0.95\textwidth]{{{_latex_identifier(figure.get('filename'), 'figure.png')}}}
\caption{{{_latex_escape(figure.get('caption'))}}}
\label{{{_latex_identifier(figure.get('label'), 'fig:figure')}}}
\end{{figure}}
"""

def _all_figure_blocks(figures: dict[str, dict[str, str]]) -> str:
    if not figures:
        return ""
    return "\n".join(_figure_block(figure) for figure in figures.values() if figure)


def _figure_overview_sentence(figures: dict[str, dict[str, str]]) -> str:
    if not figures:
        return "No figures were generated for this design, so the paper does not reference figures."
    labels = [figure.get("label") for figure in figures.values() if figure.get("label")]
    refs = ", ".join(rf"Figure \ref{{{_latex_identifier(label, 'fig:figure')}}}" for label in labels[:5])
    return f"The figures ({refs}) report the visual diagnostics for this design." if refs else "The figures report the visual diagnostics for this design."


def _method_is_event(blueprint: dict[str, Any], csv_artifacts: dict[str, str]) -> bool:
    method = str(blueprint.get("method_style") or blueprint.get("method_family") or "").lower()
    if method == "event_study":
        return True
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "event_returns.csv"))
    return bool(rows and _series_columns(rows[0], "_overnight_return", exclude_prefixes=("direction_aligned", "second_minus_first")))


def _stat_value(value: Any, fallback: str = "not computed for this design") -> str:
    if value is None or value == "":
        return fallback
    return str(value)


def _make_latex_table(caption: str, label: str, headers: list[str], rows: list[list[Any]], notes: str) -> str:
    if not rows:
        return ""
    columns = "l" * len(headers)
    body_lines = [
        " & ".join(f"{{{_latex_escape(_paper_cell(cell))}}}" for cell in row) + r" \\"
        for row in rows
    ]
    return rf"""
\clearpage
\begin{{table}}[!htbp]
\centering
\caption{{{_latex_escape(caption)}}}
\label{{{_latex_identifier(label, 'tab:table')}}}
\begin{{tabular}}{{{columns}}}
\toprule
{' & '.join(_latex_escape(_paper_cell(header)) for header in headers)} \\
\midrule
{chr(10).join(body_lines)}
\bottomrule
\end{{tabular}}
\begin{{flushleft}}
\small Notes: {_latex_escape(notes)}
\end{{flushleft}}
\end{{table}}
"""


def _make_latex_table_with_spec(
    caption: str,
    label: str,
    headers: list[str],
    rows: list[list[Any]],
    notes: str,
    column_spec: str,
) -> str:
    if not rows:
        return ""
    body_lines = [
        " & ".join(f"{{{_latex_escape(_paper_cell(cell))}}}" for cell in row) + r" \\"
        for row in rows
    ]
    return rf"""
\clearpage
\begin{{table}}[!htbp]
\centering
\caption{{{_latex_escape(caption)}}}
\label{{{_latex_identifier(label, 'tab:table')}}}
\begin{{tabular}}{{{column_spec}}}
\toprule
{' & '.join(_latex_escape(_paper_cell(header)) for header in headers)} \\
\midrule
{chr(10).join(body_lines)}
\bottomrule
\end{{tabular}}
\begin{{flushleft}}
\small Notes: {_latex_escape(notes)}
\end{{flushleft}}
\end{{table}}
"""


def _summary_statistics_table(csv_artifacts: dict[str, str]) -> str:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "summary_statistics.csv"))
    table_rows = [
        [
            row.get("ticker", ""),
            row.get("sample", ""),
            row.get("n", ""),
            _fmt_num(row.get("mean")),
            _fmt_num(row.get("std")),
            _fmt_num(row.get("min")),
            _fmt_num(row.get("median")),
            _fmt_num(row.get("max")),
        ]
        for row in rows
    ]
    return _make_latex_table(
        "Summary Statistics",
        "tab:summary",
        ["Ticker", "Sample", "N", "Mean", "Std.", "Min", "Median", "Max"],
        table_rows,
        "This table reports summary statistics for the primary return series used in the empirical analysis.",
    )


def _event_returns_table(csv_artifacts: dict[str, str]) -> str:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "event_returns.csv"))
    if not rows:
        return ""
    return_cols = _series_columns(rows[0], "_overnight_return", exclude_prefixes=("direction_aligned", "second_minus_first"))
    if not return_cols:
        return ""
    extra_cols = [col for col in ["second_minus_first_spread", "direction_aligned_spread"] if col in rows[0]]
    headers = ["Event", "Date", "Direction"] + [_label_from_series_column(col, "_overnight_return") for col in return_cols] + [
        "Spread" if col == "second_minus_first_spread" else "Aligned" for col in extra_cols
    ]
    table_rows = [
        (
            [
            row.get("event_id", ""),
            row.get("event_date", ""),
            row.get("direction", "").replace("_", "-"),
            ]
            + [_fmt_num(row.get(col)) for col in return_cols]
            + [_fmt_num(row.get(col)) for col in extra_cols]
        )
        for row in rows[:20]
    ]
    return _make_latex_table(
        "Event-Day Overnight Returns",
        "tab:event_returns",
        headers,
        table_rows,
        "Returns are measured from the previous close to the event trading day's open. The aligned spread is signed so that positive values support the directional hypothesis.",
    )


def _car_table(csv_artifacts: dict[str, str]) -> str:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "event_window_car.csv"))
    if not rows:
        return ""
    car_cols = _series_columns(rows[0], "_CAR", exclude_prefixes=("direction_aligned", "second_minus_first"))
    if not car_cols:
        return ""
    extra_cols = [col for col in ["second_minus_first_CAR", "direction_aligned_CAR"] if col in rows[0]]
    headers = ["Window", "Events"] + [_label_from_series_column(col, "_CAR") + " CAR" for col in car_cols] + [
        "Spread CAR" if col == "second_minus_first_CAR" else "Aligned CAR" for col in extra_cols
    ]
    by_window: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        by_window.setdefault(str(row.get("window", "")), []).append(row)
    table_rows: list[list[Any]] = []
    for window in sorted(by_window):
        group = by_window[window]
        table_rows.append(
            [
                window,
                len(group),
            ]
            + [_fmt_num(_mean([_as_float(row.get(col)) for row in group])) for col in car_cols]
            + [_fmt_num(_mean([_as_float(row.get(col)) for row in group])) for col in extra_cols]
        )
    return _make_latex_table(
        "Average Event-Window Cumulative Abnormal Returns",
        "tab:car",
        headers,
        table_rows,
        "CARs are averaged within each event window. The aligned CAR signs each event according to the pre-specified policy direction.",
    )




def _compact_results_table(csv_artifacts: dict[str, str], suffix: str, caption: str, label: str) -> str:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, suffix))
    if not rows:
        return ""
    preferred = [
        "model", "predictor", "outcome", "status", "coefficient", "HAC_se", "HC3_se",
        "t_stat", "p_value", "r2", "oos_r2", "nobs", "reason",
    ]
    headers = [col for col in preferred if col in rows[0]][:8]
    if len(headers) < 2:
        headers = list(rows[0].keys())[:8]
    table_rows = []
    for row in rows[:12]:
        if _row_has_error(row):
            table_rows.append([row.get("model") or row.get("test_name") or "estimator", "skipped", "--", "Insufficient data structure"])
            headers = ["Model", "Status", "p-value", "Interpretation"]
            continue
        table_rows.append([_fmt_num(row.get(col)) if col in {"coefficient", "HAC_se", "HC3_se", "t_stat", "p_value", "r2", "oos_r2"} else row.get(col, "") for col in headers])
    return _make_latex_table_with_spec(
        caption,
        label,
        [header.replace("_", " ").title() for header in headers],
        table_rows,
        "This table reports the primary model output generated for the method family selected in the locked design.",
        "l" * max(1, len(headers)),
    )


def _inference_table(csv_artifacts: dict[str, str]) -> str:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "executed_tests.csv")) or _all_csv_rows(_csv_by_suffix(csv_artifacts, "stats_summary.csv"))
    table_rows: list[list[Any]] = []
    seen: set[str] = set()
    for row in rows:
        test_name = str(row.get("test_name") or "").strip()
        if not test_name or test_name in seen:
            continue
        seen.add(test_name)
        status = str(row.get("status") or "").strip()
        if status == "failed" or _row_has_error(row):
            reason = "Insufficient panel structure" if "panel" in test_name.lower() else "Insufficient data"
            table_rows.append([test_name.replace("_", " "), "skipped", "---", reason])
            continue
        if test_name == "event_study_car":
            statistic = f"t={_fmt_num(row.get('t_stat'))}; mean={_fmt_num(row.get('mean_aligned_effect'))}"
            p_value = _fmt_p(row.get("p_value"))
            interpretation = _interpret_p(row.get("p_value"))
        elif test_name == "newey_west_hac":
            statistic = f"t={_fmt_num(row.get('t_stat'))}; coef={_fmt_num(row.get('coefficient'))}"
            p_value = _fmt_p(row.get("p_value"))
            interpretation = _interpret_p(row.get("p_value"))
        elif test_name == "patell_test":
            statistic = f"Z={_fmt_num(row.get('Z_stat'))}"
            p_value = _fmt_p(row.get("p_value"))
            interpretation = _interpret_p(row.get("p_value"))
        elif test_name == "placebo_test":
            statistic = f"observed={_fmt_num(row.get('observed_stat'))}; draws={row.get('draws') or ''}"
            p_value = _fmt_p(row.get("empirical_p_value"))
            interpretation = "placebo does not reject the observed statistic" if (_as_float(row.get("empirical_p_value")) or 1) > 0.10 else "placebo rejects at conventional levels"
        elif test_name == "bootstrap_ci":
            statistic = f"95% CI [{_fmt_num(row.get('ci_lower'))}, {_fmt_num(row.get('ci_upper'))}]"
            p_value = ""
            interpretation = "confidence interval excludes zero" if (_as_float(row.get("ci_lower")) or 0) > 0 or (_as_float(row.get("ci_upper")) or 0) < 0 else "confidence interval includes zero"
        elif test_name == "subsample_analysis":
            statistic = f"t={_fmt_num(row.get('t_stat'))}; diff={_fmt_num(row.get('difference'))}"
            p_value = _fmt_p(row.get("p_value"))
            interpretation = _interpret_p(row.get("p_value"))
        elif test_name == "bh_correction":
            statistic = f"alpha={_fmt_num(row.get('alpha'))}"
            p_value = ""
            interpretation = "multiple-testing correction applied"
        else:
            statistic = _fmt_num(row.get("t_stat") or row.get("Z_stat") or row.get("coefficient") or row.get("estimate"))
            p_value = _fmt_p(row.get("p_value") or row.get("empirical_p_value"))
            interpretation = _interpret_p(row.get("p_value") or row.get("empirical_p_value")) if p_value else status or "reported"
        table_rows.append([test_name.replace("_", " "), statistic, p_value or "--", _truncate_text(interpretation, 60)])
    return _make_latex_table_with_spec(
        "Statistical Inference and Robustness Tests",
        "tab:inference",
        ["Test", "Statistic", "p-value", "Interpretation"],
        table_rows,
        "This table consolidates the executed inference and robustness tests. Significance stars, where used in coefficient tables, denote *** p<0.01, ** p<0.05, * p<0.10.",
        "llrp{5cm}",
    )


def _deterministic_tables(context: dict[str, Any]) -> tuple[str, list[str]]:
    csv_artifacts = context.get("all_csv_artifacts", {})
    if not isinstance(csv_artifacts, dict):
        return "", []
    blueprint = context.get("blueprint", {}) if isinstance(context.get("blueprint"), dict) else {}
    method = str(blueprint.get("method_style") or blueprint.get("method_family") or "").lower()
    builders: list[tuple[str, Any]] = [("Summary Statistics", _summary_statistics_table)]
    if method == "event_study" or _all_csv_rows(_csv_by_suffix(csv_artifacts, "event_returns.csv")):
        builders.extend([
            ("Event-Day Overnight Returns", _event_returns_table),
            ("Average Event-Window Cumulative Abnormal Returns", _car_table),
        ])
    if method in {"time_series", "var_model", "cointegration"}:
        builders.append(("Time-Series Predictive Regression", lambda csvs: _compact_results_table(csvs, "time_series_regression.csv", "Time-Series Predictive Regression", "tab:time_series_regression")))
    if method in {"regression", "panel_regression", "quantile_regression", "causal_forest"}:
        builders.append(("Regression Results", lambda csvs: _compact_results_table(csvs, "regression_results.csv", "Regression Results", "tab:regression_results")))
    builders.append(("Statistical Inference and Robustness Tests", _inference_table))
    tables: list[str] = []
    captions: list[str] = []
    for caption, builder in builders:
        table = builder(csv_artifacts)
        if table.strip():
            tables.append(table)
            captions.append(caption)
    return "\n".join(tables), captions


def _executed_test_labels(csv_artifacts: dict[str, str]) -> list[str]:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "executed_tests.csv"))
    labels: list[str] = []
    for row in rows:
        test_name = str(row.get("test_name") or "").strip()
        status = str(row.get("status") or "").strip().lower()
        if not test_name or status == "failed" or _row_has_error(row):
            continue
        labels.append(_humanize_label(test_name))
    return labels


def _clean_topic_fragment(topic: str) -> str:
    fragment = re.sub(r"\s+", " ", str(topic or "")).strip().rstrip("?")
    fragment = re.sub(r"^(does|do|can|will|is|are|when|what is|what are)\s+", "", fragment, flags=re.I)
    return fragment[:1].upper() + fragment[1:] if fragment else "The empirical relation under study"


def _subject_without_leading_article(text: str) -> str:
    subject = re.sub(r"\s+", " ", str(text or "")).strip()
    subject = re.sub(r"^(the|a|an)\s+", "", subject, flags=re.I)
    subject = re.sub(r"\bterm structure\b", "term-structure", subject, flags=re.I)
    return subject[:1].upper() + subject[1:] if subject else "The measured signal"


def _predictive_hook_subject(text: str) -> str:
    subject = _subject_without_leading_article(text)
    mass_nouns = ("activity", "pressure", "flow", "sentiment", "risk", "volatility", "liquidity")
    if subject.lower().endswith(mass_nouns):
        return subject
    return f"A {subject}"


def _infer_mechanism_terms(topic: str, predictor_text: str, outcome: str) -> tuple[str, str, str]:
    text = re.sub(r"\s+", " ", str(topic or "")).strip().rstrip("?")
    patterns = [
        r"^(?:does|do)\s+(.+?)\s+predict\s+(.+)$",
        r"^(?:does|do)\s+(.+?)\s+produce\s+(.+?)(?:,\s+and\s+.+)?$",
        r"^(?:does|do)\s+(.+?)\s+allow\s+.+?\s+to\s+(.+?)(?:,\s+and\s+.+)?$",
        r"^when\s+(.+?),\s*does\s+.+?\s+(.+)$",
    ]
    inferred_x = ""
    inferred_y = ""
    for pattern in patterns:
        match = re.match(pattern, text, flags=re.I)
        if match:
            inferred_x = match.group(1).strip()
            inferred_y = match.group(2).strip()
            break

    generic_predictors = {"the primary explanatory variation", "primary explanatory variation", ""}
    generic_outcomes = {"the outcome variable", "outcome variable", ""}
    x_term = inferred_x or ("" if predictor_text in generic_predictors else predictor_text) or _clean_topic_fragment(topic)
    y_term = inferred_y or ("" if outcome in generic_outcomes else outcome) or "the measured financial outcome"
    phenomenon = f"the relation between {x_term} and {y_term}" if inferred_x and inferred_y else _clean_topic_fragment(topic)
    phenomenon = phenomenon[:1].upper() + phenomenon[1:] if phenomenon else phenomenon
    return phenomenon, x_term, y_term


def _latex_table(caption: str, label: str, rows: list[dict[str, Any]], max_rows: int = 18) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())[:8]
    columns = "l" * len(headers)
    body_lines = []
    for row in rows[:max_rows]:
        body_lines.append(" & ".join(f"{{{_latex_escape(_paper_cell(row.get(header)))}}}" for header in headers) + r" \\")
    return rf"""
\clearpage
\begin{{table}}[!htbp]
\centering
\caption{{{_latex_escape(caption)}}}
\label{{{_latex_identifier(label, 'tab:table')}}}
\begin{{tabular}}{{{columns}}}
\toprule
{' & '.join(_latex_escape(h) for h in headers)} \\
\midrule
{chr(10).join(body_lines)}
\bottomrule
\end{{tabular}}
\begin{{flushleft}}
\small Notes: Values are computed from the study data. Significance stars, when present, follow *** p<0.01, ** p<0.05, * p<0.10.
\end{{flushleft}}
\end{{table}}
"""


def _bibitems(bibliography_bib: str) -> str:
    entries = []
    for match in re.finditer(r"@\w+\{([^,]+),(.*?)\n\}", bibliography_bib or "", flags=re.S):
        key, body = match.group(1), match.group(2)
        title = re.search(r"title\s*=\s*\{([^}]*)\}", body, flags=re.I)
        author = re.search(r"author\s*=\s*\{([^}]*)\}", body, flags=re.I)
        journal = re.search(r"journal\s*=\s*\{([^}]*)\}", body, flags=re.I)
        year = re.search(r"year\s*=\s*\{([^}]*)\}", body, flags=re.I)
        raw_author = author.group(1) if author else "Unknown"
        raw_year = year.group(1) if year else "n.d."
        label = _natbib_label(raw_author, raw_year)
        text = f"{raw_author} ({raw_year}). {title.group(1) if title else 'Untitled'}. {journal.group(1) if journal else 'Working paper'}."
        entries.append(rf"\bibitem[{_latex_escape(label)}]{{{_latex_identifier(key, 'ref')}}} {_latex_escape(text)}")
    return "\n".join(entries)


def _author_last_name(author: str) -> str:
    author = re.sub(r"\s+", " ", str(author or "")).strip()
    if not author:
        return "Unknown"
    if "," in author:
        return author.split(",", 1)[0].strip() or "Unknown"
    particles = {"de", "del", "de la", "van", "von"}
    words = author.split()
    if len(words) >= 2 and " ".join(words[-2:]).lower() in particles:
        return " ".join(words[-2:])
    return words[-1].strip(".,") or "Unknown"


def _natbib_label(author_field: str, year: str) -> str:
    authors = [item.strip() for item in re.split(r"\s+and\s+", str(author_field or ""), flags=re.I) if item.strip()]
    clean_year = str(year or "n.d.").strip()
    if not authors:
        return f"Unknown({clean_year})"
    if len(authors) == 1:
        short = _author_last_name(authors[0])
    elif len(authors) == 2:
        short = f"{_author_last_name(authors[0])} and {_author_last_name(authors[1])}"
    else:
        short = f"{_author_last_name(authors[0])} et al."
    return f"{short}({clean_year})"


def _latex_escape_preserving_citations(text: str) -> str:
    """Escape prose while keeping citation commands generated from links usable."""
    citation_tokens: dict[str, str] = {}

    def citation_repl(match: re.Match[str]) -> str:
        token = f"THRIVARCCITE{len(citation_tokens)}TOKEN"
        citation_tokens[token] = rf"\citep{{{_latex_identifier(match.group(1), 'ref')}}}"
        return token

    text = re.sub(r"\(\[([A-Za-z0-9:_-]+)\]\([^)]+\)\)", citation_repl, text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("__", "")
    escaped = _latex_escape(text)
    for token, citation in citation_tokens.items():
        escaped = escaped.replace(_latex_escape(token), citation)
    return escaped


def _markdown_to_latex(text: str) -> str:
    """Convert retrieved Markdown prose into conservative LaTeX paragraphs."""
    if not text:
        return ""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(text))
    lines: list[str] = []
    in_fence = False
    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading:
            title = heading.group(2).strip().strip("#").strip()
            if title:
                command = "subsection" if len(heading.group(1)) <= 3 else "subsubsection"
                lines.append(rf"\{command}*{{{_latex_escape(title)}}}")
            continue
        if not stripped:
            lines.append("")
            continue
        list_item = re.match(r"^(\d+\.|-|\*)\s+(.+)$", stripped)
        if list_item:
            lines.append(r"\noindent " + _latex_escape_preserving_citations(list_item.group(2)) + r"\\")
            continue
        lines.append(_latex_escape_preserving_citations(stripped))
    return "\n".join(lines)


def _prose_needs_deterministic_fallback(prose_latex: str, context: dict[str, Any]) -> bool:
    if not prose_latex or "\\documentclass" not in prose_latex:
        return True
    if "\\doublespacing" in prose_latex or "Figure ??" in prose_latex:
        return True
    if re.search(r"\b[a-zA-Z][a-zA-Z0-9_]*\\?_[a-zA-Z0-9_]*\s*=\s*-?\d", prose_latex):
        return True
    if "is the economic phenomenon studied" in prose_latex or "The main results are" in prose_latex:
        return True
    figures = _figure_metadata(context)
    if figures and "\\includegraphics" not in prose_latex:
        return True
    available_labels = {figure.get("label") for figure in figures.values() if figure.get("label")}
    for label in re.findall(r"\\ref\{(fig:[^}]+)\}", prose_latex):
        if label not in available_labels:
            return True
    return False


def _fallback_latex(context: dict[str, Any]) -> dict[str, Any]:
    topic = context.get("topic") or context.get("blueprint", {}).get("focus_question") or "Empirical finance research question"
    blueprint = context.get("blueprint", {})
    data_passport = context.get("data_passport", {})
    literature_review = context.get("literature_review") or "The literature agent did not return prose, so this section summarizes retrieved citation metadata only."
    bibliography_bib = context.get("bibliography_bib") or ""
    method_spec = context.get("method_spec", {})
    csv_artifacts = context.get("all_csv_artifacts", {})
    keys = _citation_keys(bibliography_bib)
    citation_sentence = ", ".join(rf"\citep{{{_latex_identifier(key, 'ref')}}}" for key in keys[:3]) if keys else "the retrieved bibliography"
    primary_numbers = _primary_numbers_from_context(context)
    method_frameworks = method_spec.get("modeling_frameworks") or []
    method_names = ", ".join(str(item.get("name") if isinstance(item, dict) else item) for item in method_frameworks[:4]) or blueprint.get("method_family", "empirical design")
    window_start, window_end, identifier_text, return_definition = _research_design_values(blueprint)
    lit_section = _markdown_to_latex(literature_review)
    outcome = blueprint.get("outcome_variable") or "the outcome variable"
    predictors = blueprint.get("key_predictors") or []
    predictor_text = ", ".join(map(str, predictors)) if predictors else "the primary explanatory variation"
    _, x_term, y_term = _infer_mechanism_terms(topic, predictor_text, outcome)
    identification = blueprint.get("identification_strategy") or "the empirical design"
    directional = _directional_summary(csv_artifacts if isinstance(csv_artifacts, dict) else {})
    event_count = primary_numbers.get("event_count") or directional.get("event_count")
    aligned_effect = primary_numbers.get("mean_aligned_effect") or directional.get("mean_aligned_spread")
    event_t = primary_numbers.get("event_t_stat")
    event_p = primary_numbers.get("event_p_value")
    nw_coef = primary_numbers.get("newey_west_coefficient")
    nw_t = primary_numbers.get("newey_west_t_stat")
    nw_p = primary_numbers.get("newey_west_p_value")
    placebo_p = primary_numbers.get("placebo_empirical_p_value")
    ci_lower = primary_numbers.get("bootstrap_ci_lower")
    ci_upper = primary_numbers.get("bootstrap_ci_upper")
    rows = primary_numbers.get("row_count") or data_passport.get("rows")
    executed_test_labels = _executed_test_labels(csv_artifacts if isinstance(csv_artifacts, dict) else {})
    executed_test_text = ", ".join(executed_test_labels[:6]) if executed_test_labels else "the executed inference checks"

    if re.search(r"\bpredict(?:s|ed|ing)?\b|\bforecast(?:s|ed|ing)?\b", str(topic or ""), flags=re.I):
        hook = (
            f"{_predictive_hook_subject(x_term)} is a compact warning signal because it condenses information that may arrive before "
            f"{y_term} is fully reflected in prices. The empirical question is whether that signal moves ahead of the "
            "outcome with enough regularity to be economically useful, not merely whether the sign is intuitive in hindsight."
        )
    else:
        hook = (
            f"{_clean_topic_fragment(topic)} matters because it links an observable financial signal, shock, or institutional mechanism "
            "to a measurable market outcome. The empirical question is whether the outcome moves in the direction implied by the mechanism, "
            "whether the magnitude is economically meaningful, and whether the evidence survives standard inference rather than narrative appeal."
        )

    comparison_sentence = ""
    if directional.get("first_series_label") and directional.get("second_series_label"):
        comparison_sentence = (
            f"Across the primary event observations, {directional.get('second_series_label')} averages "
            f"{_fmt_num(directional.get('second_series_mean'))} while {directional.get('first_series_label')} averages "
            f"{_fmt_num(directional.get('first_series_mean'))} in the reported return units."
        )
    direction_sentence = ""
    if directional:
        direction_sentence = (
            f"The direction-aligned spread is positive in {directional.get('positive_aligned_count')} of "
            f"{directional.get('event_count')} events, with an average aligned response of "
            f"{_fmt_num(directional.get('mean_aligned_spread'))}."
        )
    event_sentence = _significant_sentence("The event-day test", event_t, event_p)
    nw_sentence = _significant_sentence("The dependence-robust specification", nw_t, nw_p)
    if nw_sentence and nw_coef not in (None, ""):
        nw_sentence = nw_sentence[:-1] + f" and an estimated coefficient of {_fmt_num(nw_coef)}."
    placebo_sentence = (
        f"The randomization check reports an empirical p-value of {_fmt_p(placebo_p)}, so the observed statistic is not unusual relative to its comparison distribution."
        if placebo_p not in (None, "")
        else "The randomization check is reported in the inference table."
    )
    ci_sentence = (
        f"The resampling interval ranges from {_fmt_num(ci_lower)} to {_fmt_num(ci_upper)}, which keeps the estimated direction positive but should be interpreted alongside the primary test."
        if ci_lower not in (None, "") and ci_upper not in (None, "")
        else "The resampling interval is reported in the inference table."
    )
    figures = _figure_metadata(context)
    figure_blocks = _all_figure_blocks(figures)
    figure_overview = _figure_overview_sentence(figures)
    is_event_design = _method_is_event(blueprint, csv_artifacts if isinstance(csv_artifacts, dict) else {})
    if is_event_design and aligned_effect not in (None, ""):
        main_finding = (
            f"Using {event_count or 'the'} events from {window_start} to {window_end}, the mean direction-aligned response is "
            f"{_fmt_num(aligned_effect)}. {event_sentence or 'The event-day test is reported in the inference table.'} "
            f"{comparison_sentence} {direction_sentence}"
        ).strip()
        abstract_numbers = (
            f"mean aligned response {_fmt_num(aligned_effect)}, event-day t-statistic {_fmt_num(event_t)}, and p-value {_fmt_p(event_p)}"
            if event_t not in (None, "") and event_p not in (None, "")
            else "the reported event-study estimates in the tables"
        )
    elif nw_coef not in (None, "") or nw_t not in (None, ""):
        main_finding = (
            f"The primary predictive specification estimates a coefficient of {_fmt_num(nw_coef)} with "
            f"t={_fmt_num(nw_t)} and p={_fmt_p(nw_p)} over {rows or 'the verified'} observations. "
            f"This is {_interpret_p(nw_p)} and should be read with the reported holdout and robustness evidence."
        )
        abstract_numbers = f"coefficient {_fmt_num(nw_coef)}, t-statistic {_fmt_num(nw_t)}, and p-value {_fmt_p(nw_p)}"
    else:
        main_finding = "The primary estimates are reported in the model and inference tables; the available outputs do not support a stronger numerical summary than the verified tables provide."
        abstract_numbers = "the reported estimates in the tables"
    tables_latex, table_captions = _deterministic_tables(context)
    if not tables_latex:
        tables_latex = _latex_table("Primary estimates", "tab:primary", [{"metric": k, "value": v} for k, v in primary_numbers.items()])
        table_captions = ["Primary estimates"] if tables_latex else []
    summary_stats = _summary_stat_map(csv_artifacts if isinstance(csv_artifacts, dict) else {})
    identifiers = list(blueprint.get("inferred_identifiers") or blueprint.get("identifiers") or [])
    first_identifier = str(identifiers[0]) if identifiers else "the first series"
    second_identifier = str(identifiers[1]) if len(identifiers) > 1 else "the comparison series"
    first_stats = summary_stats.get(first_identifier.upper(), {})
    second_stats = summary_stats.get(second_identifier.upper(), {})
    event_file = blueprint.get("event_file") or blueprint.get("uploaded_event_file") or "the locked event file"
    event_sha = blueprint.get("event_file_sha256") or blueprint.get("uploaded_event_sha256") or data_passport.get("event_file_sha256") or "not reported in the current data record"
    aligned_std = directional.get("aligned_spread_std")
    mde = None
    if aligned_std is not None and str(event_count or "").replace(".", "", 1).isdigit():
        mde = 2.262 * float(aligned_std) / (float(event_count) ** 0.5)
    if is_event_design:
        method_stat_paragraph = (
            "The primary statistic is the event-level contrast that answers the locked hypothesis. "
            "When the design compares two measured series around events, let $R^{(1)}_e$ and $R^{(2)}_e$ denote the two event-level outcomes. "
            "The aligned spread signs the contrast so that positive values indicate movement in the hypothesized direction. The null hypothesis is that the mean aligned contrast equals zero.\n\n"
            "Formally, the event-level statistic is\n"
            "\\[\nA_e = s_e \\left(R^{(2)}_e - R^{(1)}_e\\right),\n\\]\n"
            "where $s_e$ is the ex ante sign implied by the locked design. The reported test evaluates whether $\\bar{A}$ differs from zero. The same signing convention is applied to any cumulative or multi-period outcome reported in Table \\ref{tab:car}."
        )
        power_sentence = (
            f"Power is a binding limitation whenever the effective sample is small. With {_latex_escape(event_count)} primary observations and an aligned-spread standard deviation of {_latex_escape(_fmt_num(aligned_std))}, "
            f"a two-sided 5 percent test would require an approximate mean effect near {_latex_escape(_fmt_num(mde))} in the same units to reject the null using the observed dispersion. "
            f"The detected mean aligned response of {_latex_escape(_fmt_num(aligned_effect))} is read against that benchmark rather than interpreted in isolation."
        )
    else:
        method_stat_paragraph = (
            "The primary statistic is the coefficient or predictive contrast that answers the locked hypothesis. "
            "For predictive and regression designs, the empirical object can be written as\n"
            "\\[\nY_{i,t+h} = \\alpha + \\beta X_{i,t} + \\Gamma' C_{i,t} + \\epsilon_{i,t+h},\n\\]\n"
            "where $Y_{i,t+h}$ is the subsequent outcome, $X_{i,t}$ is the pre-measured predictor, and $C_{i,t}$ contains controls or fixed-effect structure when the verified data support them. "
            "The null hypothesis is that the primary coefficient is zero after applying the standard-error correction appropriate for the design."
        )
        power_sentence = (
            "Power is assessed through the number of verified observations, coefficient uncertainty, and the holdout or robustness diagnostics reported in Table \\ref{tab:inference}. "
            "An event-count power calculation is not applicable because this design is not an event study."
        )
    design_descriptor = "pre-specified event return definition" if is_event_design else "pre-specified measurement design"
    gap_statement = (
        f"Despite this literature, existing work leaves open whether {_latex_escape(x_term)} produces the specific response in "
        f"{_latex_escape(y_term)} over the measurement horizon used here. This paper fills that gap by studying "
        f"{_latex_escape(identifier_text)} from {_latex_escape(window_start)} to {_latex_escape(window_end)} with "
        f"{_latex_escape(method_names)} and the {design_descriptor}."
    )
    if is_event_design:
        diagnostic_sentence = (
            f"{placebo_sentence} {ci_sentence} Together, these diagnostics support a cautious reading: the signs are economically interpretable, "
            "but the sample is small and the conventional event-day test does not reject the null at standard levels."
        )
    else:
        diagnostic_sentence = (
            f"{placebo_sentence} {ci_sentence} Together, these diagnostics support a cautious reading: the predictive sign is interpretable, "
            "but the estimated coefficient is not precise enough to support a strong forecasting claim at conventional thresholds."
        )
    result_paragraphs = [
        main_finding,
        (
            f"The dependence-robust specification is the main precision check where the design requires it. {nw_sentence or 'The dependence-robust result is reported in the inference table.'} "
            "This matters because untreated dependence or heteroskedasticity can make an empirical contrast look more precise than it is."
        ),
        diagnostic_sentence,
    ]
    if is_event_design:
        design_use_sentence = f"It uses {_latex_escape(method_names)} and {_latex_escape(return_definition)} for {_latex_escape(identifier_text)} over {_latex_escape(window_start)} through {_latex_escape(window_end)}."
        variable_sentence = (
            "The main variable follows the locked return definition. When the design uses overnight returns, the paper computes "
            "$overnight\\_return_{i,t} = open_{i,t} - close_{i,t-1}$. The previous close is the last available trading observation before the measurement date, not a calendar placeholder. "
            "This timing rule matters because using information from the wrong trading day would mechanically contaminate the result."
        )
        sample_record_sentence = (
            f"The sample-construction record is {_latex_escape(event_file)} when the design uses an external event or classification file. "
            f"The recorded SHA-256 is {_latex_escape(event_sha)} when available. Directional signing is applied only for designs that explicitly require it."
        )
        summary_sentence = (
            f"Table \\ref{{tab:summary}} reports summary statistics for the daily event-measurement series. In the verified sample, {_latex_escape(second_identifier)} has mean {_latex_escape(_fmt_num(second_stats.get('mean')))} and standard deviation {_latex_escape(_fmt_num(second_stats.get('std')))}, while {_latex_escape(first_identifier)} has mean {_latex_escape(_fmt_num(first_stats.get('mean')))} and standard deviation {_latex_escape(_fmt_num(first_stats.get('std')))}. The volatility difference matters because weak inference around event dates can reflect genuine absence of a response or the difficulty of detecting small announcement effects against noisy returns."
        )
        conclusion_sentence = (
            "The paper finds evidence that is best interpreted within the limits of the locked event-study design. The mean aligned statistic is positive when reported, and some observations move in the hypothesized direction, but the primary test does not necessarily reject the null at conventional levels."
        )
    else:
        design_use_sentence = f"It uses {_latex_escape(method_names)} for {_latex_escape(identifier_text)} over {_latex_escape(window_start)} through {_latex_escape(window_end)}."
        variable_sentence = (
            "The main variables follow the locked predictive design. Predictors are measured before the outcome window, transformed only with information available at the measurement date, and aligned to subsequent outcomes before estimation. This timing rule matters because predictive evidence is only meaningful when the signal is observable before the return or crash outcome it is meant to forecast."
        )
        sample_record_sentence = (
            "The sample is constructed directly from the verified market-data panel. No external event calendar is used for this design. Predictive and regression designs report coefficients, confidence intervals, and model diagnostics rather than directionally signed event responses."
        )
        summary_sentence = (
            f"Table \\ref{{tab:summary}} reports summary statistics for the analysis series used in the predictive design. In the verified sample, {_latex_escape(second_identifier)} has mean {_latex_escape(_fmt_num(second_stats.get('mean')))} and standard deviation {_latex_escape(_fmt_num(second_stats.get('std')))}, while {_latex_escape(first_identifier)} has mean {_latex_escape(_fmt_num(first_stats.get('mean')))} and standard deviation {_latex_escape(_fmt_num(first_stats.get('std')))}. The dispersion matters because noisy predictors and outcomes can produce economically suggestive but statistically weak forecasting estimates."
        )
        conclusion_sentence = (
            "The paper finds evidence that is best interpreted within the limits of the locked predictive design. The estimated predictive coefficient is reported directly, but the primary test does not reject the null at conventional levels, so the paper treats the signal as suggestive rather than tradable forecasting evidence."
        )

    latex = rf"""\documentclass[12pt]{{article}}
\usepackage{{booktabs,amsmath,natbib,geometry,setspace,longtable,array,graphicx}}
\geometry{{margin=1in}}
\onehalfspacing
\title{{{_latex_escape(topic)}}}
\author{{Research Team}}
\date{{\today}}
\begin{{document}}
\maketitle

\begin{{abstract}}
This paper examines {_latex_escape(topic)}. The study uses {_latex_escape(method_names)} on {_latex_escape(identifier_text)} from {_latex_escape(window_start)} to {_latex_escape(window_end)}. The analysis links {_latex_escape(x_term)} to {_latex_escape(y_term)} through {_latex_escape(identification)}. The central estimates are {_latex_escape(abstract_numbers)}. The evidence points to an economically interpretable pattern, but statistical support is limited where p-values remain above conventional thresholds.
\end{{abstract}}

\section{{Introduction}}
{_latex_escape(hook)}

The closest literature shows why this setting is empirically interesting. The most relevant retrieved studies include {citation_sentence}. Read together, these papers establish the empirical and methodological boundary conditions for the question, but they do not by themselves answer the narrower claim tested here.

The remaining gap is the specific mechanism and measurement window. Prior work often studies related outcomes, broader horizons, or adjacent mechanisms; it less often asks whether {_latex_escape(x_term)} maps into {_latex_escape(y_term)} under the exact design used here. That gap matters because a credible empirical design must match the timing, comparison group, and outcome to the economic mechanism.

This paper examines the gap directly. {design_use_sentence} { _latex_escape(main_finding) }

The contribution is threefold. First, the paper translates the research question into a locked empirical contrast rather than a post hoc narrative. Second, it reports both economic magnitudes and inference tests, keeping interpretation tied to measured evidence. Third, it exposes limitations directly, so weak or null evidence narrows the conclusion instead of being converted into an overclaim.

The rest of the paper proceeds as follows. Section 2 reviews the related literature. Section 3 describes the data and variable construction. Section 4 presents the methodology. Section 5 reports the main results. Section 6 discusses robustness and limitations. Section 7 concludes. Tables appear after the references.

\section{{Literature Review}}
{lit_section}

\paragraph{{Gap and contribution.}} {gap_statement}

\section{{Data}}
The empirical sample is built from {_latex_escape(blueprint.get('evidence_route') or blueprint.get('evidence_source'))} observations for {_latex_escape(identifier_text)} over {_latex_escape(window_start)} through {_latex_escape(window_end)}. The verified data table contains {_latex_escape(rows)} observations after aligning the analysis unit and removing rows without the required measurement inputs. {figure_overview}

{variable_sentence}

{sample_record_sentence}

{summary_sentence}

All results below use the locked data definitions described in this section. The paper does not change the sample universe after computing outcomes and does not reinterpret the method family after observing the estimates.

The unit of observation is intentionally conservative. The design favors measurements that are observable, reproducible, and aligned with the claim over richer specifications that the available data cannot support. This choice can reduce cross-sectional detail, but it makes the reported estimates easier to audit and interpret.

\section{{Methodology}}
The empirical design follows the method specified before execution. It asks whether {_latex_escape(x_term)} is associated with the predicted movement in {_latex_escape(y_term)} over the locked measurement window. The identifying assumption is not stronger than the design allows: the analysis can support a causal interpretation only if the research design explains why the key variation is plausibly exogenous. Otherwise, the evidence is interpreted as predictive or associational.

{method_stat_paragraph}

The inference strategy deliberately separates economic direction from statistical significance. The executed checks in Table \ref{{tab:inference}} include {_latex_escape(executed_test_text)}. Each check is interpreted for the threat it addresses rather than treated as a mechanical hurdle. The point estimate answers the economic question; the surrounding inference asks whether the observed pattern is large relative to the uncertainty, dependence, and counterfactual variation in the available data.

The design has important limitations. The effective sample size and measurement granularity determine how much the paper can claim even when signs are economically intuitive. The analysis also inherits the limits of the available measurement units and controls. These limits mean the paper can speak to the locked claim and sample, but it should not be read as a broader causal estimate unless the identification strategy explicitly supports that conclusion.

The empirical strategy fixes the burden of proof before interpreting the signs. A favorable point estimate is not sufficient evidence by itself; it must be read alongside the inference, robustness, and uncertainty estimates reported below. This sequencing prevents a visually intuitive pattern from becoming a claim stronger than the evidence.

\section{{Results}}
{_latex_escape(result_paragraphs[0])}

The visual evidence appears below when the empirical analysis produces figures for this design. Each figure is referenced only if it exists in the compiled paper.

{figure_blocks}

{_latex_escape(result_paragraphs[1])}

{_latex_escape(result_paragraphs[2])}

\section{{Robustness}}
The robustness evidence is summarized in Table \ref{{tab:inference}}. The dependence-robust specification yields t={_latex_escape(_fmt_num(nw_t))}, p={_latex_escape(_fmt_p(nw_p))} when that statistic is available. This comparison is informative because allowing for dependence or heteroskedasticity can change apparent precision even when it does not change the economic sign.

The randomization evidence reports an empirical p-value of {_latex_escape(_fmt_p(placebo_p))}. Interpreted literally, the observed aligned spread is not extreme relative to draws from the relevant comparison environment. Distributional figures are included only when they are available for this design.

The resampling interval runs from {_latex_escape(_fmt_num(ci_lower))} to {_latex_escape(_fmt_num(ci_upper))}. This interval keeps the estimated average response positive where the endpoints are both above zero, but the economic magnitude must be read relative to the volatility of the measured outcome. The interval therefore supports the directional interpretation while also cautioning against describing the result as large or precisely estimated when the sample is limited.

{power_sentence}

Skipped tests in Table \ref{{tab:inference}} are also informative. When a requested estimator does not match the data structure, forcing it would create a false sense of sophistication. The paper therefore reports the skipped test as a design limitation rather than printing the underlying software exception or treating the failed estimator as evidence.

\section{{Conclusion}}
{conclusion_sentence}

The economic interpretation is therefore cautious. The data may contain the mechanism described in the research question, but the available sample and uncertainty determine how strongly the paper can speak. A weak or null result is still informative when it narrows what the evidence supports.

Future work should increase statistical power, improve measurement, and test the mechanism in additional samples. The most useful extension is not necessarily a more complicated model; it is the design change that most directly addresses the largest remaining identification or power concern surfaced by the evidence.

\bibliographystyle{{plainnat}}
\begin{{thebibliography}}{{99}}
{_bibitems(bibliography_bib)}
\end{{thebibliography}}

{tables_latex}
\end{{document}}
"""
    numbers_used = [
        f"mean aligned response {_fmt_num(aligned_effect)}",
        f"event t-statistic {_fmt_num(event_t)}",
        f"event p-value {_fmt_p(event_p)}",
        f"dependence-robust coefficient {_fmt_num(nw_coef)}",
        f"dependence-robust p-value {_fmt_p(nw_p)}",
        f"placebo p-value {_fmt_p(placebo_p)}",
        f"bootstrap interval [{_fmt_num(ci_lower)}, {_fmt_num(ci_upper)}]",
    ]
    return {
        "latex": latex,
        "numbers_used": [item for item in numbers_used if not item.endswith(" ")],
        "tables_written": table_captions,
        "figure_artifacts": context.get("figure_artifacts", {}),
        "fallback_used": True,
    }


async def write_paper_latex(context: dict[str, Any], client=None) -> dict[str, Any]:
    if client is None:
        return _fallback_latex(context)
    
    prose_prompt = WRITER_PROSE_PROMPT.format(
        topic=context.get("topic", ""),
        blueprint_json=json.dumps(context.get("blueprint", {}), indent=2, sort_keys=True),
        data_passport_json=json.dumps(context.get("data_passport", {}), indent=2, sort_keys=True),
        literature_review=context.get("literature_review", ""),
        bibliography_bib=context.get("bibliography_bib", ""),
        method_spec_json=json.dumps(context.get("method_spec", {}), indent=2, sort_keys=True),
        stats_results_json=json.dumps(context.get("stats_results", {}), indent=2, sort_keys=True),
        hawk_scorecard_json=json.dumps(context.get("hawk_scorecard", {}), indent=2, sort_keys=True),
        all_csv_artifacts_json=json.dumps(context.get("all_csv_artifacts", {}), indent=2, sort_keys=True),
        figure_artifacts_json=json.dumps(context.get("figure_artifacts", {}), indent=2, sort_keys=True),
    )
    
    prose_result = await call_agent_llm(
        agent_name="WRITER_AGENT_PROSE",
        prompt=prose_prompt,
        client=client,
        fallback_fn=_fallback_latex,
        fallback_args={"context": context},
        max_tokens=10000,
    )

    if prose_result.get("fallback_used"):
        return prose_result

    tables_latex, deterministic_captions = _deterministic_tables(context)
    tables_result: dict[str, Any] = {"latex": tables_latex, "tables_written": deterministic_captions}
    if not tables_latex.strip():
        tables_prompt = WRITER_TABLES_PROMPT.format(
            topic=context.get("topic", ""),
            all_csv_artifacts_json=json.dumps(context.get("all_csv_artifacts", {}), indent=2, sort_keys=True),
            stats_results_json=json.dumps(context.get("stats_results", {}), indent=2, sort_keys=True),
        )
        tables_result = await call_agent_llm(
            agent_name="WRITER_AGENT_TABLES",
            prompt=tables_prompt,
            client=client,
            fallback_fn=lambda: {"latex": "", "tables_written": []},
            max_tokens=6000,
        )
    
    prose_latex = prose_result.get("latex") or prose_result.get("final_latex") or ""
    if "%%%END_PROSE%%%" in prose_latex:
        prose_latex = prose_latex.split("%%%END_PROSE%%%")[0]
    if _prose_needs_deterministic_fallback(prose_latex, context):
        fallback = _fallback_latex(context)
        fallback["llm_result_rejected"] = True
        return fallback
        
    tables_latex = tables_result.get("latex") or tables_result.get("final_latex") or ""
    if "%%%END_TABLES%%%" in tables_latex:
        tables_latex = tables_latex.split("%%%END_TABLES%%%")[0]
        
    # Remove \end{document} from prose if the LLM output it early
    prose_latex = prose_latex.replace("\\end{document}", "")
    
    latex = f"{prose_latex.strip()}\n\n{tables_latex.strip()}\n\\end{document}\n"
    
    if not prose_latex or "\\documentclass" not in prose_latex:
        fallback = _fallback_latex(context)
        fallback["llm_result_without_latex"] = prose_result
        return fallback
        
    return {
        **prose_result,
        "latex": latex,
        "tables_written": tables_result.get("tables_written", []),
        "figure_artifacts": context.get("figure_artifacts", {}),
    }
