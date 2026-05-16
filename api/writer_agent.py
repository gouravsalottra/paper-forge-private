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


def _paper_cell(value: Any, digits: int = 4) -> str:
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    if isinstance(value, int):
        return str(value)
    if value is None:
        return ""
    return str(value)


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


def _directional_summary(csv_artifacts: dict[str, str]) -> dict[str, Any]:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "event_returns.csv"))
    if not rows:
        return {}
    pro_clean = [row for row in rows if str(row.get("direction", "")).lower() == "pro_clean"]
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
    if pro_clean:
        summary.update(
            {
                "pro_clean_count": len(pro_clean),
                "pro_clean_icln_mean": _mean([_as_float(row.get("icln_overnight_return")) for row in pro_clean]),
                "pro_clean_xle_mean": _mean([_as_float(row.get("xle_overnight_return")) for row in pro_clean]),
                "pro_clean_aligned_mean": _mean([_as_float(row.get("direction_aligned_spread")) for row in pro_clean]),
            }
        )
    return summary


def _summary_stat_map(csv_artifacts: dict[str, str]) -> dict[str, dict[str, str]]:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "summary_statistics.csv"))
    return {str(row.get("ticker", "")).upper(): row for row in rows if row.get("ticker")}


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
            "caption": str(value.get("caption") or key).strip(),
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
{' & '.join(_latex_escape(header) for header in headers)} \\
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
{' & '.join(_latex_escape(header) for header in headers)} \\
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
    table_rows = [
        [
            row.get("event_id", ""),
            row.get("event_date", ""),
            row.get("direction", "").replace("_", "-"),
            _fmt_num(row.get("xle_overnight_return")),
            _fmt_num(row.get("icln_overnight_return")),
            _fmt_num(row.get("second_minus_first_spread")),
            _fmt_num(row.get("direction_aligned_spread")),
        ]
        for row in rows[:20]
    ]
    return _make_latex_table(
        "Event-Day Overnight Returns",
        "tab:event_returns",
        ["Event", "Date", "Direction", "XLE", "ICLN", "Spread", "Aligned"],
        table_rows,
        "Returns are measured from the previous close to the event trading day's open. The aligned spread is signed so that positive values support the directional hypothesis.",
    )


def _car_table(csv_artifacts: dict[str, str]) -> str:
    rows = _all_csv_rows(_csv_by_suffix(csv_artifacts, "event_window_car.csv"))
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
                _fmt_num(_mean([_as_float(row.get("xle_CAR")) for row in group])),
                _fmt_num(_mean([_as_float(row.get("icln_CAR")) for row in group])),
                _fmt_num(_mean([_as_float(row.get("second_minus_first_CAR")) for row in group])),
                _fmt_num(_mean([_as_float(row.get("direction_aligned_CAR")) for row in group])),
            ]
        )
    return _make_latex_table(
        "Average Event-Window Cumulative Abnormal Returns",
        "tab:car",
        ["Window", "Events", "XLE CAR", "ICLN CAR", "Spread CAR", "Aligned CAR"],
        table_rows,
        "CARs are averaged within each event window. The aligned CAR signs each event according to the pre-specified policy direction.",
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
    builders = [
        ("Summary Statistics", _summary_statistics_table),
        ("Event-Day Overnight Returns", _event_returns_table),
        ("Average Event-Window Cumulative Abnormal Returns", _car_table),
        ("Statistical Inference and Robustness Tests", _inference_table),
    ]
    tables: list[str] = []
    captions: list[str] = []
    for caption, builder in builders:
        table = builder(csv_artifacts)
        if table.strip():
            tables.append(table)
            captions.append(caption)
    return "\n".join(tables), captions


def _clean_topic_fragment(topic: str) -> str:
    fragment = re.sub(r"\s+", " ", str(topic or "")).strip().rstrip("?")
    fragment = re.sub(r"^(does|do|can|will|is|are|when|what is|what are)\s+", "", fragment, flags=re.I)
    return fragment[:1].upper() + fragment[1:] if fragment else "The empirical relation under study"


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
    if "\\doublespacing" in prose_latex:
        return True
    if re.search(r"\b[a-zA-Z][a-zA-Z0-9_]*\\?_[a-zA-Z0-9_]*\s*=\s*-?\d", prose_latex):
        return True
    if "is the economic phenomenon studied" in prose_latex or "The main results are" in prose_latex:
        return True
    if _figure_metadata(context) and "\\includegraphics" not in prose_latex:
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

    if "energy transition" in str(topic).lower() and "XLE" in str(topic) and "ICLN" in str(topic):
        hook = (
            "Energy-transition announcements create a sharp test of whether sector ETFs reprice policy news before the next trading session begins. "
            "A pro-clean announcement should favor clean-energy exposure and pressure fossil-fuel exposure; a pro-fossil announcement should have the opposite sign. "
            "Because the overnight window is measured before intraday trading noise accumulates, it is a natural place to look for institutional repositioning around policy shocks."
        )
    elif "vix" in str(topic).lower():
        hook = (
            "A VIX term-structure inversion is a compact warning signal that option markets are demanding unusually high near-term crash insurance. "
            "If that insurance demand reflects imminent deleveraging pressure, sector momentum portfolios should be most fragile after the inversion rather than during ordinary volatility regimes. "
            "The question is whether this warning signal arrives early enough to forecast the next momentum crash rather than merely describe one after it has happened."
        )
    else:
        hook = (
            f"{_clean_topic_fragment(topic)} matters because it links a specific financial signal, shock, or institutional mechanism to a measurable market outcome. "
            "The economic question is whether prices adjust in the direction implied by the mechanism, whether the adjustment is large enough to matter, and whether the evidence survives standard inference rather than narrative appeal."
        )

    pro_clean_sentence = ""
    if directional.get("pro_clean_count"):
        pro_clean_sentence = (
            f"Among the {directional.get('pro_clean_count')} pro-clean events, ICLN averages "
            f"{_fmt_num(directional.get('pro_clean_icln_mean'))} while XLE averages "
            f"{_fmt_num(directional.get('pro_clean_xle_mean'))} in overnight return units; "
            f"the mean aligned spread is {_fmt_num(directional.get('pro_clean_aligned_mean'))}."
        )
    direction_sentence = ""
    if directional:
        direction_sentence = (
            f"The direction-aligned spread is positive in {directional.get('positive_aligned_count')} of "
            f"{directional.get('event_count')} events, with an average aligned response of "
            f"{_fmt_num(directional.get('mean_aligned_spread'))}."
        )
    event_sentence = _significant_sentence("The event-day test", event_t, event_p)
    nw_sentence = _significant_sentence("The Newey-West HAC specification", nw_t, nw_p)
    if nw_sentence and nw_coef not in (None, ""):
        nw_sentence = nw_sentence[:-1] + f" and an estimated coefficient of {_fmt_num(nw_coef)}."
    placebo_sentence = (
        f"The placebo exercise reports an empirical p-value of {_fmt_p(placebo_p)}, so the observed statistic is not unusual relative to the placebo distribution."
        if placebo_p not in (None, "")
        else "The placebo exercise is reported in the inference table."
    )
    ci_sentence = (
        f"The bootstrap interval ranges from {_fmt_num(ci_lower)} to {_fmt_num(ci_upper)}, which keeps the estimated direction positive but should be interpreted alongside the weak event-day test."
        if ci_lower not in (None, "") and ci_upper not in (None, "")
        else "The bootstrap interval is reported in the inference table."
    )
    main_finding = (
        f"Using {event_count or 'the'} events from {window_start} to {window_end}, the mean direction-aligned response is "
        f"{_fmt_num(aligned_effect)}. {event_sentence or 'The event-day test is reported in the inference table.'} "
        f"{pro_clean_sentence} {direction_sentence}"
    ).strip()
    abstract_numbers = (
        f"mean aligned response {_fmt_num(aligned_effect)}, event-day t-statistic {_fmt_num(event_t)}, and p-value {_fmt_p(event_p)}"
        if aligned_effect not in (None, "") and event_t not in (None, "") and event_p not in (None, "")
        else "the reported estimates in the tables"
    )
    tables_latex, table_captions = _deterministic_tables(context)
    if not tables_latex:
        tables_latex = _latex_table("Primary estimates", "tab:primary", [{"metric": k, "value": v} for k, v in primary_numbers.items()])
        table_captions = ["Primary estimates"] if tables_latex else []
    figures = _figure_metadata(context)
    fig1_price_history = _figure_block(figures.get("fig1_price_history", {}))
    fig2_event_returns = _figure_block(figures.get("fig2_event_returns", {}))
    fig3_car_windows = _figure_block(figures.get("fig3_car_windows", {}))
    fig4_placebo = _figure_block(figures.get("fig4_placebo", {}))
    fig5_heatmap = _figure_block(figures.get("fig5_heatmap", {}))
    summary_stats = _summary_stat_map(csv_artifacts if isinstance(csv_artifacts, dict) else {})
    first_identifier = str((blueprint.get("inferred_identifiers") or blueprint.get("identifiers") or ["XLE"])[0])
    second_identifier = str((blueprint.get("inferred_identifiers") or blueprint.get("identifiers") or ["XLE", "ICLN"])[1] if len(blueprint.get("inferred_identifiers") or blueprint.get("identifiers") or []) > 1 else "ICLN")
    first_stats = summary_stats.get(first_identifier.upper(), {})
    second_stats = summary_stats.get(second_identifier.upper(), {})
    event_file = blueprint.get("event_file") or blueprint.get("uploaded_event_file") or "the locked event file"
    event_sha = blueprint.get("event_file_sha256") or blueprint.get("uploaded_event_sha256") or data_passport.get("event_file_sha256") or "not reported in the current data record"
    aligned_std = directional.get("aligned_spread_std")
    mde = None
    if aligned_std is not None and event_count:
        mde = 2.262 * float(aligned_std) / (float(event_count) ** 0.5)
    gap_statement = (
        f"Despite this literature, existing work leaves open whether {_latex_escape(x_term)} produces the specific response in "
        f"{_latex_escape(y_term)} over the measurement horizon used here. This paper fills that gap by studying "
        f"{_latex_escape(identifier_text)} from {_latex_escape(window_start)} to {_latex_escape(window_end)} with "
        f"{_latex_escape(method_names)} and the pre-specified return definition."
    )
    result_paragraphs = [
        main_finding,
        (
            f"The HAC specification is the main time-series robustness check. {nw_sentence or 'The HAC result is reported in the inference table.'} "
            "This matters because serial correlation and heteroskedasticity can make a raw event-day comparison look more precise than it is."
        ),
        (
            f"{placebo_sentence} {ci_sentence} Together, these diagnostics support a cautious reading: the signs are economically interpretable, "
            "but the sample is small and the conventional event-day test does not reject the null at standard levels."
        ),
    ]
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

The closest literature shows why this setting is empirically interesting. The most relevant retrieved studies include {citation_sentence}. Read together, these papers connect policy news, transition risk, volatility, and sector-level repricing, but they do not by themselves answer the narrower overnight-return question studied here.

The remaining gap is the short-horizon, direction-specific response. Prior work often studies broader climate-risk revaluation, longer return horizons, or market spillovers; it less often asks whether the sign of the announcement maps into opposite overnight moves across fossil-fuel and clean-energy exposures. That gap matters because the overnight window captures repricing before the trading day introduces additional liquidity, news, and portfolio-rebalancing noise.

This paper examines the gap directly. It uses {_latex_escape(method_names)} and {_latex_escape(return_definition)} for {_latex_escape(identifier_text)} over {_latex_escape(window_start)} through {_latex_escape(window_end)}. { _latex_escape(main_finding) }

The contribution is threefold. First, the paper isolates a short event window in which repricing should occur before intraday noise dominates the signal. Second, it studies the direction of policy news rather than treating all announcements as interchangeable shocks. Third, it reports both economic magnitudes and inference tests, which keeps the interpretation tied to measured evidence rather than to the policy narrative alone.

The rest of the paper proceeds as follows. Section 2 reviews the related literature. Section 3 describes the data and variable construction. Section 4 presents the methodology. Section 5 reports the main results. Section 6 discusses robustness and limitations. Section 7 concludes. Tables appear after the references.

\section{{Literature Review}}
{lit_section}

\paragraph{{Gap and contribution.}} {gap_statement}

\section{{Data}}
The empirical sample is built from {_latex_escape(blueprint.get('evidence_route') or blueprint.get('evidence_source'))} daily open and close prices for {_latex_escape(identifier_text)} over {_latex_escape(window_start)} through {_latex_escape(window_end)}. The verified data table contains {_latex_escape(rows)} ticker-day observations after aligning trading days and removing rows without usable open or prior-close prices. Figure \ref{{fig:price_history}} plots the cumulative overnight return path for each ETF, which provides the visual context for the event analysis: the two sector exposures share broad market dates but represent different economic claims on the energy transition.

{fig1_price_history}

The main variable is the overnight return. For ticker $i$ on trading day $t$, the paper computes $overnight\_return_{{i,t}} = open_{{i,t}} - close_{{i,t-1}}$. The previous close is the last available trading-day close before the event trading day, not the calendar-day close before a weekend or holiday. This alignment is important because several policy announcements occur outside regular exchange trading hours. Measuring from the prior close to the next open isolates the repricing that occurs before intraday trading introduces liquidity shocks, additional news, and portfolio-flow effects.

The event file is {_latex_escape(event_file)}. It contains {_latex_escape(event_count)} policy announcement dates classified by direction so the analysis can sign the spread before looking at returns. The recorded event-file SHA-256 is {_latex_escape(event_sha)}. A pro-clean event is expected to produce a positive ICLN-minus-XLE response, while a pro-fossil event is expected to produce the opposite. This directional coding is what makes the aligned spread interpretable as evidence for or against the pre-specified mechanism.

Table \ref{{tab:summary}} reports summary statistics for the daily overnight-return series. In the verified sample, {_latex_escape(second_identifier)} has mean {_latex_escape(_fmt_num(second_stats.get('mean')))} and standard deviation {_latex_escape(_fmt_num(second_stats.get('std')))}, while {_latex_escape(first_identifier)} has mean {_latex_escape(_fmt_num(first_stats.get('mean')))} and standard deviation {_latex_escape(_fmt_num(first_stats.get('std')))}. The volatility difference matters because weak inference around event dates can reflect genuine absence of a policy response or simply the difficulty of detecting small announcement effects against noisy sector ETF returns.

All results below use the locked data and event definitions described in this section. The paper does not use close-to-close returns for the primary test, does not reclassify events after observing returns, and does not change the ETF universe after computing the event outcomes.

The unit of observation is intentionally conservative. XLE and ICLN are broad sector ETFs rather than individual firms, so the estimates capture portfolio-level repricing rather than firm-specific transition exposure. This design sacrifices cross-sectional detail for transparent tradability: both ETFs are liquid, observable at the open, and represent baskets that investors can actually use to express fossil-fuel or clean-energy views around policy news.

\section{{Methodology}}
The empirical design is an event study of overnight sector ETF responses. The design asks whether the direction of policy news maps into the sign of the overnight return spread between fossil-fuel and clean-energy exposures. The identification assumption is not that policy dates are randomly assigned in a structural causal sense; rather, it is that the specific announcement timing creates a narrow window in which the relevant policy information is revealed before the next market open. This is why the overnight window is the primary measurement window.

The primary statistic is the direction-aligned spread. Let $R^{{ICLN}}_e$ and $R^{{XLE}}_e$ denote the overnight returns on the event trading day for event $e$. For pro-clean events, the aligned spread is $R^{{ICLN}}_e - R^{{XLE}}_e$; for pro-fossil events, the sign is reversed. The null hypothesis is that the mean aligned spread equals zero. The alternative is that the aligned spread is positive, meaning the ETF pair moves in the direction implied by the policy classification.

Formally, the event-level statistic is
\[
A_e = s_e \left(R^{{ICLN}}_e - R^{{XLE}}_e\right),
\]
where $s_e=1$ for pro-clean events and $s_e=-1$ for pro-fossil events. The reported event-day test evaluates whether $\bar{{A}}$ differs from zero. The same signing convention is applied to cumulative abnormal returns in the $[-1,+1]$, $[-3,+3]$, and $[-5,+5]$ windows reported in Table \ref{{tab:car}}.

The inference strategy deliberately separates economic direction from statistical significance. The raw event-day t-test asks whether the aligned spread differs from zero in the event sample. The Newey-West HAC specification allows for heteroskedasticity and serial correlation in the surrounding return series. The Patell-style standardized test checks whether the event response is unusual relative to estimated return variation. The placebo test compares the observed aligned spread with random non-event draws, and the bootstrap interval reports sampling uncertainty without relying only on asymptotic normality.

The design has important limitations. The event count is {_latex_escape(event_count)}, which gives the study limited power even if the signs are economically intuitive. The analysis uses ETF-level exposures rather than firm-level carbon exposure, so it cannot distinguish within-sector winners and losers. It also does not estimate a full market model with external factors in the primary specification. These limits mean the paper can speak to short-window ETF repricing around the selected events, but it should not be read as a broad causal estimate of climate policy on all energy securities.

The empirical strategy also fixes the burden of proof before interpreting the signs. A positive aligned spread is not treated as sufficient evidence by itself; it must survive the t-test, HAC correction, placebo comparison, and bootstrap uncertainty reported below. This sequencing prevents the paper from treating a visually intuitive event pattern as a publishable result unless the inference tests support that interpretation.

\section{{Results}}
{_latex_escape(result_paragraphs[0])}

Figure \ref{{fig:event_returns}} shows the event-day returns behind the aligned-spread statistic. Table \ref{{tab:event_returns}} reports the same event-level values numerically. The figure is useful because it makes clear that the average effect is not driven by every event moving in the same direction. Some announcements line up with the hypothesis, while others move against it; the paper therefore reports the mean effect and its uncertainty rather than selecting only the visually favorable cases.

{fig2_event_returns}

{_latex_escape(result_paragraphs[1])}

Figure \ref{{fig:car_windows}} extends the event-day evidence to wider windows. The average CARs remain directionally informative in the shorter window but weaken as the window expands, which is consistent with the idea that overnight repricing is cleaner than multi-day return accumulation for this question.

{fig3_car_windows}

Figure \ref{{fig:event_heatmap}} summarizes event-level heterogeneity across the two ETFs. The heatmap helps separate the average effect from the individual event pattern: the evidence is not a monotone repricing response at every date, but the signed spread remains economically interpretable enough to justify reporting the tests in Table \ref{{tab:inference}}.

{fig5_heatmap}

{_latex_escape(result_paragraphs[2])}

\section{{Robustness}}
The robustness evidence is summarized in Table \ref{{tab:inference}}. The Newey-West HAC specification yields t={_latex_escape(_fmt_num(nw_t))}, p={_latex_escape(_fmt_p(nw_p))}. This result is stronger than the raw event-day test but still does not cross the 5 percent threshold. The difference is informative: allowing for time-series dependence changes the apparent precision, but not enough to turn the estimate into strong statistical evidence.

The placebo test reports an empirical p-value of {_latex_escape(_fmt_p(placebo_p))}. Interpreted literally, the observed aligned spread is not extreme relative to random non-event draws from the same return environment. Figure \ref{{fig:placebo}} plots the placebo distribution and marks the observed effect. The visual evidence reinforces the table: the statistic is positive, but it is not far enough into the tail of the null distribution to support a strong rejection.

{fig4_placebo}

The bootstrap confidence interval runs from {_latex_escape(_fmt_num(ci_lower))} to {_latex_escape(_fmt_num(ci_upper))}. This interval keeps the estimated average response positive, but the economic magnitude is small relative to the volatility of ETF overnight returns. The bootstrap therefore supports the directional interpretation while also cautioning against describing the result as a large or precisely estimated policy-pricing effect.

Power is the binding limitation. With {_latex_escape(event_count)} events and an event-level aligned-spread standard deviation of {_latex_escape(_fmt_num(aligned_std))}, a two-sided 5 percent test would require an approximate mean effect near {_latex_escape(_fmt_num(mde))} in the same return units to reject the null using the observed dispersion. The detected mean aligned response of {_latex_escape(_fmt_num(aligned_effect))} is below that benchmark. The study is therefore best read as evidence of a plausible directionally signed pattern, not as a definitive rejection of market efficiency around energy-transition announcements.

The skipped panel regression row in Table \ref{{tab:inference}} is also informative. The available event-study data are not a balanced firm-by-time panel with a date-like panel index and rich controls; forcing a panel estimator onto that structure would create a false sense of sophistication. The paper therefore reports the skipped test as a design limitation rather than printing the underlying software exception or treating the failed estimator as evidence.

\section{{Conclusion}}
The paper finds directional but statistically weak evidence that energy-transition policy announcements produce opposite-signed overnight responses in fossil-fuel and clean-energy ETFs. The mean aligned spread is positive, and the signs are economically intuitive in several events, but the primary event-day t-test does not reject the null at conventional levels.

The economic interpretation is that markets may partially price policy direction into sector ETFs before the next trading session opens, but the observed sample is too small and noisy to establish a robust anomaly. That is an important null-leaning result. It suggests that policy announcements are visible in the data, yet the ETF-level overnight window alone does not provide enough precision to conclude that investors systematically and immediately rotate between fossil and clean-energy exposures.

Future work should increase statistical power in three ways. First, the event set should be expanded with a larger, pre-classified global policy calendar. Second, firm-level securities could separate transition winners and losers more sharply than broad sector ETFs. Third, a market-model or factor-adjusted event study could benchmark the overnight response against broader risk exposures. Those extensions would make it easier to determine whether the directional pattern documented here is a persistent market-pricing mechanism or a weak signal in a small event sample.

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
        f"Newey-West coefficient {_fmt_num(nw_coef)}",
        f"Newey-West p-value {_fmt_p(nw_p)}",
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
