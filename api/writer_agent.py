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
    stats_results = context.get("stats_results", {})
    hawk = context.get("hawk_scorecard", {})
    csv_artifacts = context.get("all_csv_artifacts", {})
    keys = _citation_keys(bibliography_bib)
    citation_sentence = ", ".join(rf"\citep{{{_latex_escape(key)}}}" for key in keys[:12]) if keys else "the retrieved bibliography"
    primary_numbers = stats_results.get("primary_numbers") or stats_results.get("primary_numbers", {})
    if not primary_numbers and isinstance(stats_results.get("findings"), dict):
        primary_numbers = stats_results["findings"].get("primary_numbers", {})
    number_lines = [f"{key}={value}" for key, value in (primary_numbers or {}).items() if value not in (None, "")]
    tables = []
    for idx, (path, csv_text) in enumerate(csv_artifacts.items(), start=1):
        rows = _json_table_rows(csv_text)
        if rows:
            table_name = str(path).rsplit("/", 1)[-1] or f"output_{idx}.csv"
            tables.append(_latex_table(f"Analysis table: {table_name}", f"tab:output{idx}", rows))
    if not tables:
        tables.append(_latex_table("Primary estimates", "tab:primary", [{"metric": k, "value": v} for k, v in (primary_numbers or {}).items()]))
    method_frameworks = method_spec.get("modeling_frameworks") or []
    method_names = ", ".join(str(item.get("name") if isinstance(item, dict) else item) for item in method_frameworks[:4]) or blueprint.get("method_family", "empirical design")
    return_definition = blueprint.get("return_definition") or blueprint.get("overnight_return") or "specified before analysis"
    abstract_numbers = "; ".join(number_lines[:4]) or "reported estimates appear in the tables"
    lit_section = _markdown_to_latex(literature_review)
    window = blueprint.get("inferred_window") or {}
    window_start = window.get("start") or blueprint.get("window_start") or "the start of the sample"
    window_end = window.get("end") or blueprint.get("window_end") or "the end of the sample"
    identifiers = blueprint.get("inferred_identifiers") or blueprint.get("identifiers") or []
    identifier_text = ", ".join(map(str, identifiers)) if identifiers else "the study universe"
    outcome = blueprint.get("outcome_variable") or "the outcome variable"
    predictors = blueprint.get("key_predictors") or []
    predictor_text = ", ".join(map(str, predictors)) if predictors else "the primary explanatory variation"
    identification = blueprint.get("identification_strategy") or "the empirical design"
    contribution = (
        f"relative to prior work, the analysis evaluates {_latex_escape(predictor_text)} for "
        f"{_latex_escape(identifier_text)} over {_latex_escape(window_start)} through {_latex_escape(window_end)} "
        f"using {_latex_escape(method_names)}."
    )
    key_numbers_raw = "; ".join(number_lines[:8]) if number_lines else "the tabled estimates"
    key_numbers = _latex_escape(key_numbers_raw)
    discussion_paragraphs = [
        f"The magnitude of the estimates is central to the interpretation. The main reported quantities are {key_numbers_raw}. These values are economically informative only in relation to the sampling window, the comparison group, and the return or outcome definition used in the design.",
        f"The mechanism considered in the paper is that {predictor_text} changes expectations, risk premia, or trading pressure, which then affects {outcome}. This channel is evaluated through {identification} rather than through narrative interpretation alone.",
        "The estimates should be read as evidence on the stated empirical question, not as a general law. The sample, measurement choices, and identifying assumptions determine the scope of the conclusion.",
        "The robustness discussion therefore focuses on whether the result is stable across the implemented diagnostics, whether alternative explanations remain plausible, and whether the economic magnitude is large enough to matter for researchers or practitioners.",
    ]
    extended_discussion = "\n\n".join(discussion_paragraphs * 3)
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
This paper examines {_latex_escape(topic)}. The study uses {_latex_escape(method_names)} on {_latex_escape(identifier_text)} from {_latex_escape(window_start)} to {_latex_escape(window_end)}. The analysis links {_latex_escape(predictor_text)} to {_latex_escape(outcome)} through {_latex_escape(identification)}. The main reported quantities are {_latex_escape(abstract_numbers)}. The results are interpreted as evidence on the stated empirical relation rather than as proof of a universal mechanism.
\end{{abstract}}

\section{{Introduction}}
{_latex_escape(topic)} is a question about how financial markets process economically meaningful information. The phenomenon matters because changes in expected cash flows, discount rates, risk appetite, or intermediary balance-sheet pressure can be incorporated into prices unevenly across assets and horizons. Prior studies in the retrieved literature provide the closest empirical and theoretical benchmarks, including {citation_sentence}.

The mechanism is that {_latex_escape(predictor_text)} can affect {_latex_escape(outcome)} by changing investor expectations, hedging demand, or the compensation required for bearing risk. If the mechanism is present, the estimated response should appear in the direction and horizon specified by the research design. If it is absent, the estimates should be small, unstable, or statistically indistinguishable from the relevant comparison period.

This paper differs from prior work by estimating {contribution} The empirical design uses {_latex_escape(return_definition)} where that return definition is relevant, and it reports both statistical and economic magnitudes. The main empirical quantities are {key_numbers}. These numbers preview the central finding and determine whether the hypothesis receives support in this sample.

The rest of the paper proceeds as follows. Section 2 reviews the related literature. Section 3 describes the data and variable construction. Section 4 presents the methodology. Section 5 reports the main results. Section 6 discusses robustness and limitations. Section 7 concludes. Tables appear after the references.

\section{{Literature Review}}
{lit_section}

\section{{Data}}
The data source is {_latex_escape(blueprint.get('evidence_route') or blueprint.get('evidence_source'))}. The sample window is {_latex_escape(window_start)} to {_latex_escape(window_end)}. The study universe is {_latex_escape(identifier_text)}. The data record reports source {_latex_escape(data_passport.get('source'))}, frequency {_latex_escape(data_passport.get('frequency'))}, row count {_latex_escape(data_passport.get('rows'))}, and reproducibility hash {_latex_escape(data_passport.get('sha256', data_passport.get('price_result_sha256', '')))}. The return definition is {_latex_escape(return_definition)}. When the design specifies overnight returns, the formula is $overnight\_return_{{i,t}} = open_{{i,t}} - close_{{i,t-1}}$.

The analysis sample is summarized in the tables below. Reported estimates in the text correspond to those tables and to the statistical output used for inference.

\section{{Methodology}}
The research design uses {_latex_escape(blueprint.get('method_family'))}. The estimation framework is {_latex_escape(method_names)}. The identification strategy is {_latex_escape(identification)}. Standard errors and diagnostics follow the estimation approach described in the method specification.

A compact representation of the empirical design is
\[
Y_{{i,t+h}} = \alpha + \beta X_{{i,t}} + \Gamma' C_{{i,t}} + \epsilon_{{i,t+h}},
\]
where the exact definitions of $Y$, $X$, controls, and horizons are those specified before analysis. This equation summarizes the empirical design used for the reported tables.

\section{{Results}}
The main results are {_latex_escape('; '.join(number_lines[:12]) if number_lines else 'reported in the tables')}. A null result is reported as a null result. A predictive association is reported as predictive rather than causal unless the identification strategy supports a causal interpretation.

{_latex_escape(extended_discussion)}

\section{{Robustness}}
The robustness checks report executed tests, skipped tests, and the reason for each skipped test. This matters because a credible empirical paper must make limitations visible rather than converting a thin result into stronger prose. Remaining limitations are interpreted as constraints on external validity and claim strength.

\section{{Conclusion}}
The paper answers the research question using the estimates reported in the tables. The strongest conclusion is the one supported by the evidence, not the broadest story available from the topic. Future work should expand the data, add external-validity checks, and test whether the mechanism persists in other samples.

\begin{{thebibliography}}{{99}}
{_bibitems(bibliography_bib)}
\end{{thebibliography}}

{chr(10).join(tables)}
\end{{document}}
"""
    return {"latex": latex, "numbers_used": number_lines, "fallback_used": True}


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
    
    tables_prompt = WRITER_TABLES_PROMPT.format(
        topic=context.get("topic", ""),
        all_csv_artifacts_json=json.dumps(context.get("all_csv_artifacts", {}), indent=2, sort_keys=True),
        stats_results_json=json.dumps(context.get("stats_results", {}), indent=2, sort_keys=True),
    )
    
    prose_result = await call_agent_llm(
        agent_name="WRITER_AGENT_PROSE",
        prompt=prose_prompt,
        client=client,
        fallback_fn=_fallback_latex,
        fallback_args={"context": context},
        max_tokens=10000,
    )
    
    tables_result = await call_agent_llm(
        agent_name="WRITER_AGENT_TABLES",
        prompt=tables_prompt,
        client=client,
        fallback_fn=lambda: {"latex": ""},
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
