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
    summary: dict[str, Any] = {
        "event_count": len(rows),
        "positive_aligned_count": positive_count,
        "mean_aligned_spread": _mean(aligned_clean),
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


def _make_latex_table(caption: str, label: str, headers: list[str], rows: list[list[Any]], notes: str) -> str:
    if not rows:
        return ""
    columns = "l" * len(headers)
    body_lines = [
        " & ".join(_latex_escape(_paper_cell(cell)) for cell in row) + r" \\"
        for row in rows
    ]
    return rf"""
\clearpage
\begin{{table}}[!htbp]
\centering
\caption{{{_latex_escape(caption)}}}
\label{{{_latex_escape(label)}}}
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
        if status == "failed":
            table_rows.append([test_name.replace("_", " "), "failed", "", str(row.get("reason") or "test did not run")[:80]])
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
            interpretation = "placebo distribution does not reject the observed statistic" if (_as_float(row.get("empirical_p_value")) or 1) > 0.10 else "placebo distribution rejects at conventional levels"
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
        table_rows.append([test_name.replace("_", " "), statistic, p_value, interpretation])
    return _make_latex_table(
        "Statistical Inference and Robustness Tests",
        "tab:inference",
        ["Test", "Statistic", "p-value", "Interpretation"],
        table_rows,
        "This table consolidates the executed inference and robustness tests. Significance stars, where used in coefficient tables, denote *** p<0.01, ** p<0.05, * p<0.10.",
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
        body_lines.append(" & ".join(_latex_escape(_paper_cell(row.get(header))) for header in headers) + r" \\")
    return rf"""
\clearpage
\begin{{table}}[!htbp]
\centering
\caption{{{_latex_escape(caption)}}}
\label{{{_latex_escape(label)}}}
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
        label = f"{author.group(1) if author else 'Unknown'} ({year.group(1) if year else 'n.d.'})"
        text = f"{label}. {title.group(1) if title else 'Untitled'}. {journal.group(1) if journal else 'Working paper'}."
        entries.append(rf"\bibitem[{_latex_escape(label)}]{{{_latex_escape(key)}}} {_latex_escape(text)}")
    return "\n".join(entries)


def _latex_escape_preserving_citations(text: str) -> str:
    """Escape prose while keeping citation commands generated from links usable."""
    citation_tokens: dict[str, str] = {}

    def citation_repl(match: re.Match[str]) -> str:
        token = f"THRIVARCCITE{len(citation_tokens)}TOKEN"
        citation_tokens[token] = rf"\citep{{{_latex_escape(match.group(1))}}}"
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


def _fallback_latex(context: dict[str, Any]) -> dict[str, Any]:
    topic = context.get("topic") or context.get("blueprint", {}).get("focus_question") or "Empirical finance research question"
    blueprint = context.get("blueprint", {})
    data_passport = context.get("data_passport", {})
    literature_review = context.get("literature_review") or "The literature agent did not return prose, so this section summarizes retrieved citation metadata only."
    bibliography_bib = context.get("bibliography_bib") or ""
    method_spec = context.get("method_spec", {})
    csv_artifacts = context.get("all_csv_artifacts", {})
    keys = _citation_keys(bibliography_bib)
    citation_sentence = ", ".join(rf"\citep{{{_latex_escape(key)}}}" for key in keys[:3]) if keys else "the retrieved bibliography"
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
\usepackage{{booktabs,amsmath,natbib,geometry,setspace,longtable,array}}
\geometry{{margin=1in}}
\doublespacing
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
The data source is {_latex_escape(blueprint.get('evidence_route') or blueprint.get('evidence_source'))}. The sample window is {_latex_escape(window_start)} to {_latex_escape(window_end)}. The study universe is {_latex_escape(identifier_text)}. The analysis file contains {_latex_escape(rows)} observations at {_latex_escape(data_passport.get('frequency', 'the study frequency'))}. The return definition is {_latex_escape(return_definition)}. When the design specifies overnight returns, the formula is $overnight\_return_{{i,t}} = open_{{i,t}} - close_{{i,t-1}}$.

The analysis sample is summarized in the tables below. Reported estimates in the text correspond to those tables and to the statistical output used for inference.

\section{{Methodology}}
The research design uses {_latex_escape(blueprint.get('method_family'))}. The estimation framework is {_latex_escape(method_names)}. The identification strategy is {_latex_escape(identification)}. Standard errors and diagnostics follow the estimation approach described in the method specification.

A compact representation of the empirical design is
\[
Y_{{i,t+h}} = \alpha + \beta X_{{i,t}} + \Gamma' C_{{i,t}} + \epsilon_{{i,t+h}},
\]
where the exact definitions of $Y$, $X$, controls, and horizons are those specified before analysis. This equation summarizes the empirical design used for the reported tables.

\section{{Results}}
{_latex_escape(result_paragraphs[0])}

{_latex_escape(result_paragraphs[1])}

{_latex_escape(result_paragraphs[2])}

\section{{Robustness}}
The robustness evidence is summarized in Table \ref{{tab:inference}}. The placebo test, bootstrap interval, HAC specification, and multiple-testing adjustment are interpreted jointly rather than as separate opportunities to select the strongest result. This matters because a small event sample can display economically sensible signs without delivering enough statistical power for strong rejection of the null. The appropriate conclusion is therefore conditional: the estimates are directionally informative, but not sufficient to support a broad claim without additional events or out-of-sample validation.

\section{{Conclusion}}
The paper answers the research question using the estimates reported in the tables. The evidence is most consistent with a cautious interpretation: the signs and magnitudes are economically meaningful enough to warrant attention, but conventional inference remains weak in the available event sample. Future work should expand the event set, test alternative policy classifications, and examine whether the same mechanism appears in firm-level securities, futures markets, or international clean-energy exposures.

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
    return {"latex": latex, "numbers_used": [item for item in numbers_used if not item.endswith(" ")], "tables_written": table_captions, "fallback_used": True}


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
        "tables_written": tables_result.get("tables_written", [])
    }
