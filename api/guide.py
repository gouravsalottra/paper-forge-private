from __future__ import annotations

import json
import os
import re
from typing import Any

from fastapi import APIRouter
from openai import AzureOpenAI

router = APIRouter()

AZURE_ENDPOINT = "https://goura-mp4b98bg-eastus2.cognitiveservices.azure.com/"
# MODEL: standardized to gpt-4o per STEP 0 audit
AZURE_DEPLOYMENT = "gpt-4o"
AZURE_API_VERSION = "2024-12-01-preview"


def _client() -> AzureOpenAI:
    return AzureOpenAI(
        azure_endpoint=AZURE_ENDPOINT,
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=AZURE_API_VERSION,
    )


def _json_call(system: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = _client().chat.completions.create(
        model=AZURE_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        response_format={"type": "json_object"},
    )
    content = response.choices[0].message.content or "{}"
    parsed = json.loads(content)
    return parsed if isinstance(parsed, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _blocking_clarifications(clarifications: list[Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in clarifications
        if isinstance(item, dict) and bool(item.get("blocking"))
    ]


def _completion_contract(clarifications: list[Any]) -> dict[str, Any]:
    blockers = _blocking_clarifications(clarifications)
    if blockers:
        return {
            "state": "blocked",
            "ready_for_evidence_preview": False,
            "blockers": [
                {
                    "key": item.get("key") or "clarification",
                    "question": item.get("question") or "Clarify the research design before preview.",
                    "reason": item.get("reason") or "The blueprint cannot safely open the evidence gate yet.",
                }
                for item in blockers
            ],
            "next_step": "Answer the blocking architect clarification.",
        }
    return {
        "state": "ready_for_evidence_preview",
        "ready_for_evidence_preview": True,
        "blockers": [],
        "next_step": "Preview the evidence.",
    }


def _launch_readiness(clarifications: list[Any]) -> dict[str, str]:
    contract = _completion_contract(clarifications)
    if not contract["ready_for_evidence_preview"]:
        return {
            "headline": "Blueprint needs clarification",
            "detail": "Answer the blocking architect clarification before opening the data gate.",
            "next_step": contract["next_step"],
        }
    return {
        "headline": "Blueprint ready for evidence preview",
        "detail": "Review the design before opening the data gate.",
        "next_step": contract["next_step"],
    }


def _normalize_contract(result: dict[str, Any]) -> dict[str, Any]:
    clarifications = _as_list(result.get("clarifications"))
    summary = result.setdefault("blueprint_summary", {})
    if not isinstance(summary, dict):
        summary = {}
        result["blueprint_summary"] = summary
    summary["launch_readiness"] = _launch_readiness(clarifications)
    summary["completion_contract"] = _completion_contract(clarifications)
    if _blocking_clarifications(clarifications):
        result["validated"] = False
        result["error"] = result.get("error") or "Blueprint needs clarification before evidence preview."
    return result


def _payload_text(payload: dict[str, Any]) -> tuple[str, str]:
    raw = " ".join(
        str(payload.get(k) or "")
        for k in (
            "topic",
            "abstract",
            "notes",
            "context",
            "data_instructions",
            "design_instructions",
            "validation_notes",
            "hypothesis",
        )
    )
    return raw.strip(), raw.lower()


def _unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        key = item.strip()
        if not key or key.lower() in seen:
            continue
        seen.add(key.lower())
        out.append(key)
    return out


def _infer_identifiers(raw_text: str, text: str) -> list[str]:
    stop = {
        "AI",
        "API",
        "ETF",
        "ETFS",
        "LLM",
        "NLP",
        "SEC",
        "PAP",
        "VAR",
        "GNN",
        "SRISK",
        "COVAR",
        "WRDS",
        "FRED",
    }
    tickers = [
        token
        for token in re.findall(r"\b[A-Z][A-Z0-9.]{1,5}\b", raw_text)
        if token not in stop and not token.isdigit()
    ]
    named_markets: list[str] = []
    for phrase in [
        "TSX 60",
        "S&P 500",
        "Russell 3000",
        "sector ETFs",
        "ETF holdings",
        "earnings calls",
        "SEC filings",
        "FOMC",
        "Canadian equities",
        "US equities",
    ]:
        if phrase.lower() in text:
            named_markets.append(phrase)
    return _unique(named_markets + tickers)[:12]


def _has_window(text: str) -> bool:
    return bool(
        re.search(r"\b(19|20)\d{2}\b", text)
        or re.search(r"\b\d+\s*(year|years|yr|yrs)\b", text)
        or any(term in text for term in ["pre-2020", "post-2020", "financial crisis", "covid", "dot-com"])
    )


def _infer_window(text: str) -> dict[str, str]:
    years = [int(year) for year in re.findall(r"\b((?:19|20)\d{2})\b", text)]
    if len(years) >= 2:
        return {"start": f"{min(years)}-01-01", "end": f"{max(years)}-12-31"}
    if len(years) == 1:
        year = years[0]
        return {"start": f"{year}-01-01", "end": "2024-12-31"}
    year_span = re.search(r"\b(\d+)\s*(year|years|yr|yrs)\b", text)
    if year_span:
        span = max(1, min(40, int(year_span.group(1))))
        return {"start": f"{2024 - span + 1}-01-01", "end": "2024-12-31"}
    return {"start": "2010-01-01", "end": "2024-12-31"}


def _has_frequency(text: str) -> bool:
    return any(
        term in text
        for term in [
            "intraday",
            "hourly",
            "daily",
            "weekly",
            "monthly",
            "quarterly",
            "annual",
            "rebalance",
            "rebalancing",
            "rotation frequency",
        ]
    )


def _infer_frequency(text: str) -> str:
    if "intraday" in text:
        return "intraday"
    if "hourly" in text:
        return "hourly"
    if "monthly" in text:
        return "monthly"
    if "quarterly" in text:
        return "quarterly"
    if "weekly" in text:
        return "weekly"
    if "annual" in text or "yearly" in text:
        return "annual"
    return "daily"


def _infer_method_style(text: str, confirmatory: bool) -> str:
    if any(term in text for term in ["event study", "event window", "announcement", "fomc", "earnings", "filing"]):
        return "event_study"
    if any(
        term in text
        for term in [
            "backtest",
            "rebalance",
            "rebalancing",
            "rotation",
            "portfolio allocation",
            "trading strategy",
            "outperform benchmark",
            "sharpe",
            "drawdown",
        ]
    ):
        return "backtest"
    if any(term in text for term in ["predict", "regression", "factor", "alpha", "beta", "coefficient", "causal"]):
        return "regression"
    return "regression" if confirmatory else "descriptive"


def _infer_evidence_route(text: str) -> str:
    if any(term in text for term in ["upload", "proprietary", "my dataset", "private", "provided by researcher"]):
        return "upload"
    if "wrds" in text:
        return "public_fallback_or_upload"
    if any(term in text for term in ["edgar", "filing", "earnings call", "transcript"]):
        return "edgar_yfinance"
    if "fred" in text or "macro" in text:
        return "fred_yfinance"
    return "yfinance"


def _blocking_requirements(
    topic: str,
    text: str,
    method: str,
    evidence: str,
    identifiers: list[str],
    explicit_window: bool,
    explicit_frequency: bool,
) -> list[dict[str, Any]]:
    clarifications: list[dict[str, Any]] = []
    if len(topic) < 20:
        clarifications.append({
            "key": "topic",
            "question": "What exact finance question should Thrivarc test?",
            "reason": "The planner needs a concrete market, signal, benchmark, or outcome.",
            "blocking": True,
        })
    if method == "backtest" and not identifiers and not any(term in text for term in ["universe", "index", "market", "sector", "assets"]):
        clarifications.append({
            "key": "universe",
            "question": "What exact universe, benchmark, or investable assets anchor this backtest?",
            "reason": "Backtests are not defensible until the investable universe and comparison set are explicit.",
            "blocking": True,
        })
    if method in {"backtest", "event_study", "regression"} and not explicit_window:
        clarifications.append({
            "key": "time_horizon",
            "question": "What historical window should the study use, or should Thrivarc infer one and ask you to confirm it?",
            "reason": "The data gate needs a visible sample period before it can fingerprint evidence.",
            "blocking": method == "backtest",
        })
    if method == "backtest" and not explicit_frequency:
        clarifications.append({
            "key": "cadence",
            "question": "Should rebalance frequency be fixed, compared across alternatives, or inferred from the strategy logic?",
            "reason": "For allocation studies, cadence is often part of the research design rather than a harmless dropdown.",
            "blocking": True,
        })
    if evidence == "upload" and "schema" not in text and "columns" not in text:
        clarifications.append({
            "key": "upload_schema",
            "question": "What columns, identifiers, timestamp field, and target variable should the uploaded data contain?",
            "reason": "Uploaded data can be previewed only after Thrivarc knows what schema to validate.",
            "blocking": False,
        })
    return clarifications


def _research_package(confirmatory: bool) -> dict[str, Any]:
    if confirmatory:
        return {
            "track": "confirmatory",
            "label": "Confirmatory package",
            "writer_posture": "claims are locked before results and writing stays gated until evidence passes review",
            "includes": [
                "locked Blueprint and PAP",
                "pre-registration certificate",
                "DataPassport",
                "Deviation Register",
                "Code Audit report",
                "Spec Audit report",
                "Reviewer scorecard",
                "Paper-Code verification",
                "paper-ready sections after gate pass",
            ],
            "excludes": ["unstated post-hoc claim upgrades", "paper draft before reviewer clearance"],
            "integrity_statement": "This run can support confirmatory language only for claims locked before evidence execution.",
        }
    return {
        "track": "exploratory",
        "label": "Exploratory package",
        "writer_posture": "findings are hypothesis-generating until upgraded through a locked confirmatory run",
        "includes": [
            "EDA findings",
            "literature gap map",
            "research opportunity map",
            "data quality profile",
            "preliminary evidence table",
            "Reviewer warnings against overclaiming",
        ],
        "excludes": ["pre-registration certificate", "confirmatory causal language", "paper unlock without upgrade"],
        "integrity_statement": "This run can surface research opportunities, not claim proof.",
    }


def _reviewer_gate(confirmatory: bool, method: str) -> dict[str, Any]:
    return {
        "name": "Conditional paper gate",
        "state_before_review": "locked_until_reviewer_passes",
        "paper_unlock_threshold": {"minimum_average": 7.0, "minimum_dimension": 6.0},
        "max_repair_cycles_per_issue": 3,
        "dimensions": [
            {"key": "identification_validity", "label": "Identification validity", "pass_rule": "design answers the stated question without hidden identification leaps"},
            {"key": "data_integrity", "label": "Data integrity", "pass_rule": "coverage, schema, timing, missingness, and provenance are certificate-backed"},
            {"key": "statistical_rigor", "label": "Statistical rigor", "pass_rule": "primary test and robustness burden match the Blueprint"},
            {"key": "economic_significance", "label": "Economic significance", "pass_rule": "effect size matters after costs, frictions, or policy relevance"},
            {"key": "benchmark_fairness", "label": "Benchmark fairness", "pass_rule": "comparison set is investable, timely, and not selected after seeing results"},
            {"key": "robustness_burden", "label": "Robustness burden", "pass_rule": "core finding survives the expected domain-specific stress tests"},
            {"key": "overclaiming_risk", "label": "Overclaiming risk", "pass_rule": "language does not outrun the evidence or research track"},
        ],
        "score_bands": [
            {"range": "8.5-10", "outcome": "paper_unlocked", "researcher_view": "Writer can draft from verified evidence."},
            {"range": "7.0-8.49", "outcome": "conditional_unlock", "researcher_view": "Writer may draft with explicit limitations and reviewer caveats."},
            {"range": "5.0-6.99", "outcome": "repair_required", "researcher_view": "Repair Agent receives issue-scoped contracts before writing is allowed."},
            {"range": "0-4.99", "outcome": "human_escalation", "researcher_view": "Run returns a failure package instead of a paper."},
        ],
        "method_focus": {
            "backtest": ["transaction costs", "turnover", "benchmark fairness", "look-ahead bias", "deflated Sharpe"],
            "event_study": ["event timing", "confounds", "expected return model", "event-window leakage"],
            "regression": ["identification", "standard errors", "controls", "out-of-sample validity"],
            "descriptive": ["coverage", "descriptive limits", "hypothesis-generating language"],
        }.get(method, ["identification", "data integrity", "overclaiming"]),
        "track_rule": "Confirmatory runs require PAP consistency; exploratory runs require hypothesis-generating language.",
        "writer_rule": "Writer is last and never invents numbers.",
        "confirmatory_required": confirmatory,
    }


def _repair_contract_template() -> dict[str, Any]:
    return {
        "name": "Repair Contract",
        "contract_fields": ["trigger", "scope", "pass_criterion", "approval_required", "deviation_register_entry"],
        "trigger_sources": ["Reviewer Agent", "Code Audit Agent", "Spec Audit Agent", "Paper-Code Verifier"],
        "automatic_scope": [
            "rerun a failed parser",
            "regenerate a chart from existing outputs",
            "run a robustness check already named in the Blueprint",
            "fix output formatting that does not change the claim",
        ],
        "requires_researcher_approval": [
            "change the Blueprint",
            "change the data source",
            "change the benchmark or universe",
            "change the method family",
            "upgrade exploratory findings to confirmatory claims",
        ],
        "never_allowed": ["silent p-hacking", "post-hoc benchmark shopping", "claim mutation without Deviation Register entry"],
        "max_cycles_per_issue": 3,
        "exhausted_cycle_outcome": "Escalate to the researcher with a failure package, evidence status, and recommended next design change.",
    }


def _integrity_artifacts(confirmatory: bool) -> dict[str, Any]:
    return {
        "data_passport": {
            "visible_name": "DataPassport",
            "plain_english_summary": [
                "what data was used",
                "where it came from",
                "when it was locked",
                "what the hash proves",
                "what coverage limits remain",
            ],
            "technical_section": ["source parameters", "row counts", "column profile", "missingness", "SHA-256 hashes", "schema fingerprint"],
            "download_format": ["html", "json"],
        },
        "deviation_register": {
            "visible_name": "Deviation Register",
            "ui_location": "Evidence and defense panels",
            "entry_fields": ["timestamp", "trigger", "changed_field", "old_value", "new_value", "reason", "approver"],
            "paper_treatment": "Included as an appendix or reproducibility attachment when any post-lock change occurs.",
        },
        "preregistration_certificate": {
            "enabled": confirmatory,
            "visible_name": "Pre-registration certificate",
            "fields": ["timestamp", "Blueprint hash", "DataPassport hash", "primary hypothesis", "primary test", "alpha", "verification instruction"],
            "compatibility_target": "Export packet shaped for OSF or AEA registry attachment, with journal-verifiable hashes.",
        },
    }


def _clarification_policy(
    topic: str,
    method: str,
    evidence: str,
    identifiers: list[str],
    window: dict[str, str],
    frequency: str,
    confirmatory: bool,
    clarifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    blockers = {str(item.get("key")) for item in _blocking_clarifications(clarifications)}
    question_map = {str(item.get("key")): item for item in clarifications if isinstance(item, dict)}

    def decision(key: str, default: str) -> str:
        if key in blockers:
            return "block"
        if key in question_map:
            return "confirm"
        return default

    rows = [
        ("research_question", "Research question", "infer", topic or "missing", "Natural language is the source of truth for the study."),
        ("research_track", "Exploratory vs confirmatory", "infer", "confirmatory" if confirmatory else "exploratory", "Track controls integrity artifacts and claim language."),
        ("evidence_route", "Evidence route", "confirm", evidence, "Data access controls the preview gate and DataPassport."),
        ("universe", "Universe or identifiers", decision("universe", "confirm"), ", ".join(identifiers) if identifiers else "not explicit", "Finance evidence is not defensible without a visible comparison frame."),
        ("time_horizon", "Historical window", decision("time_horizon", "confirm"), f"{window['start']} to {window['end']}", "Sample period must be visible before evidence fingerprinting."),
        ("cadence", "Cadence role", decision("cadence", "confirm"), frequency, "Cadence may be a design variable, not a one-size-fits-all dropdown."),
        ("upload_schema", "Uploaded schema", decision("upload_schema", "confirm" if evidence == "upload" else "infer"), evidence, "Uploaded data must declare timestamps, identifiers, and target fields."),
        ("validation_burden", "Validation burden", "confirm", method, "Reviewer pressure and tests are selected from the method family."),
    ]
    policy: list[dict[str, Any]] = []
    for key, field, state, value, reason in rows:
        source = question_map.get(key) or {}
        policy.append({
            "key": key,
            "field": field,
            "decision": state,
            "current_value": value,
            "question": source.get("question") or "",
            "reason": source.get("reason") or reason,
        })
    return policy


def _audit_boundary() -> dict[str, Any]:
    return {
        "code_audit_agent": {
            "definition": "Technical correctness check.",
            "checks": ["code executed", "approved libraries used", "edge cases handled", "output files match schema", "errors are resumable"],
            "does_not_check": ["whether the claim is overstated", "whether paper prose matches tables"],
        },
        "spec_audit_agent": {
            "definition": "Research integrity check.",
            "checks": ["outputs match Blueprint", "tests match locked plan", "reported tables exist", "claim stays inside research track"],
            "does_not_check": ["low-level parser exceptions unless they alter the evidence"],
        },
    }


def _paper_code_verifier_policy() -> dict[str, Any]:
    return {
        "trigger": "after review and audit gates pass, and after every repair cycle that changes evidence or reported numbers",
        "final_position": "immediately before Writer export",
        "checks": ["paper claim to output table", "table value to code artifact", "code artifact to DataPassport hash"],
        "on_mismatch": "block Writer, create a Repair Contract, and write a Deviation Register entry if the Blueprint changes.",
    }


def _data_quality_policy(evidence: str) -> dict[str, Any]:
    return {
        "schema_mismatch": {
            "extra_columns": "profile and ignore unless researcher maps them into the Blueprint",
            "missing_required_columns": "block evidence preview",
            "date_range_mismatch": "show coverage delta and ask for approval before launch",
            "frequency_mismatch": "infer resampling options but require approval when cadence affects the claim",
            "missingness_threshold": "warn above 5 percent, block above 20 percent unless the Blueprint justifies it",
        },
        "source_route": evidence,
        "preview_required_before_compute": True,
    }


def _leakage_policy(method: str) -> dict[str, Any]:
    rules = {
        "backtest": "No feature can use information released after the rebalance decision timestamp.",
        "event_study": "Feature windows cannot overlap the event window unless explicitly locked in the Blueprint.",
        "regression": "Right-hand-side timing must be prior or explicitly contemporaneous in the Blueprint.",
        "descriptive": "Descriptive summaries must not be reframed as predictive or causal evidence.",
    }
    return {
        "method": method,
        "primary_rule": rules.get(method, "Timing must match the Blueprint before evidence execution."),
        "failure_action": "block launch for hard leakage; otherwise require researcher-visible caveat and repair scope",
    }


def _statistical_battery(method: str) -> dict[str, Any]:
    batteries = {
        "backtest": ["net_return", "annualized_sharpe", "max_drawdown", "turnover_cost", "deflated_sharpe", "block_bootstrap"],
        "event_study": ["CAR", "BHAR", "market_model_abnormal_return", "cross_sectional_CAR_regression", "bootstrap_inference"],
        "regression": ["newey_west", "fama_macbeth", "factor_regression", "out_of_sample_r2", "multiple_testing_control"],
        "descriptive": ["coverage_profile", "summary_statistics", "correlation_map", "sample_stability"],
    }
    return {"method": method, "tests": batteries.get(method, batteries["descriptive"])}


def _economic_significance(method: str) -> dict[str, str]:
    mapping = {
        "backtest": "Report net-of-cost returns, Sharpe, max drawdown, turnover, and capacity caveats.",
        "event_study": "Report abnormal return magnitude relative to bid-ask spreads and event-window noise.",
        "regression": "Report annualized alpha or basis-point effect size, not just p-values.",
        "descriptive": "Report magnitude and coverage limits without implying decision readiness.",
    }
    return {"method": method, "rule": mapping.get(method, mapping["descriptive"])}


def _data_fallback_policy(evidence: str) -> dict[str, Any]:
    return {
        "wrds_status": "not default in v1 because access is currently paused",
        "preferred_sequence": ["researcher upload", "yfinance", "EDGAR", "FRED", "manual connector request"],
        "selected_route": evidence,
        "when_public_data_incomplete": "show coverage gaps, offer upload merge, and block launch if target variables are missing",
    }


def _architecture_defaults(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    raw_text, text = _payload_text(payload)
    topic = str(payload.get("topic") or "").strip()
    summary = result.setdefault("blueprint_summary", {})
    if not isinstance(summary, dict):
        summary = {}
        result["blueprint_summary"] = summary

    research_state = str(result.get("research_state") or summary.get("research_stance") or "").lower()
    confirmatory = "confirmatory" in research_state or any(
        word in text for word in ["test whether", "hypothesis", "causes", "outperform", "abnormal returns"]
    )
    method = str(summary.get("method_style") or _infer_method_style(text, confirmatory))
    evidence = str(summary.get("evidence_source") or _infer_evidence_route(text))
    identifiers = summary.get("inferred_identifiers")
    if not isinstance(identifiers, list):
        identifiers = _infer_identifiers(raw_text, text)
    window = summary.get("inferred_window")
    if not isinstance(window, dict):
        window = _infer_window(text)
    window = {"start": str(window.get("start") or "2010-01-01"), "end": str(window.get("end") or "2024-12-31")}
    frequency = str(summary.get("recommended_frequency") or _infer_frequency(text))
    clarifications = _as_list(result.get("clarifications"))
    if not clarifications:
        clarifications = _blocking_requirements(topic, text, method, evidence, identifiers, _has_window(text), _has_frequency(text))
        result["clarifications"] = clarifications

    package = _research_package(confirmatory)
    summary.setdefault("architect_summary", f"Thrivarc reads this as a {'confirmatory' if confirmatory else 'exploratory'} empirical finance study.")
    summary.setdefault("research_stance", "confirmatory_pap" if confirmatory else "exploratory")
    summary.setdefault("why_this_stance", "The brief contains a directional testable claim." if confirmatory else "The brief asks to explore evidence before locking a claim.")
    summary.setdefault("evidence_source", evidence)
    summary.setdefault("why_this_evidence_route", "The brief requires uploaded evidence." if evidence == "upload" else "Public or researcher-provided evidence can support the first pass.")
    summary.setdefault("method_style", method)
    summary.setdefault("why_this_method", f"The question maps naturally to {method}.")
    summary.setdefault("recommended_frequency", frequency)
    summary.setdefault("cadence_role", "design_variable" if method == "backtest" else "event_window" if method == "event_study" else "default_market_sampling")
    summary.setdefault("cadence_explanation", "Cadence is inferred from the research design and confirmed at evidence preview.")
    summary.setdefault("decision_problem", "Determine whether the evidence changes the researcher's decision or claim.")
    summary.setdefault("comparison_set", "Use the benchmark, asset universe, or uploaded identifiers from the brief.")
    summary.setdefault("burden_of_proof", "The result must survive validation, audit, and reviewer pressure.")
    summary.setdefault("if_true", "If true, the result should support a narrower defensible finance claim.")
    summary.setdefault("evidence_readiness", "Evidence must be previewed and fingerprinted before launch.")
    summary.setdefault("output_plan", package["label"])
    summary.setdefault("research_package", package)
    summary.setdefault("reviewer_gate", _reviewer_gate(confirmatory, method))
    summary.setdefault("repair_contract_template", _repair_contract_template())
    summary.setdefault("integrity_artifacts", _integrity_artifacts(confirmatory))
    summary["clarification_policy"] = _clarification_policy(topic, method, evidence, identifiers, window, frequency, confirmatory, clarifications)
    summary.setdefault("audit_boundary", _audit_boundary())
    summary.setdefault("paper_code_verifier", _paper_code_verifier_policy())
    summary.setdefault("data_quality_policy", _data_quality_policy(evidence))
    summary.setdefault("leakage_policy", _leakage_policy(method))
    summary.setdefault("statistical_battery", _statistical_battery(method))
    summary.setdefault("economic_significance", _economic_significance(method))
    summary.setdefault("data_fallback_policy", _data_fallback_policy(evidence))
    summary.setdefault("inferred_identifiers", identifiers)
    summary.setdefault("inferred_window", window)
    summary.setdefault("working_assumptions", ["The comparison frame will be finalized before data preview.", "The method must match the approved blueprint."])
    summary.setdefault("reviewer_attack_surface", ["Benchmark choice", "Data coverage", "Robustness", "Claim overreach"])
    summary.setdefault("reviewer_focus", "A hostile reviewer will attack identification, data quality, and interpretation.")

    # Build canonical agent_stack_preview — always uses AZURE_DEPLOYMENT (gpt-4o).
    # This prevents the LLM from hallucinating model names (e.g. gpt-5.5).
    _LLM_AGENT_PHASES = {"LITERATURE", "CODEAUDIT", "REVIEWER"}
    canonical_stack = [
        {"phase": "LITERATURE", "label": "Context scan", "engine": AZURE_DEPLOYMENT, "skill": "Search and synthesize prior evidence", "reads": "research brief", "produces": "literature_map.md", "why_now": "Ground the study before execution."},
        {"phase": "DATAPULL", "label": "Evidence pull", "engine": "Thrivarc evidence connector", "skill": "Fetch or ingest the dataset", "reads": "RunSpec.datapull", "produces": "data preview and certificate", "why_now": "Evidence must be inspected before compute."},
        {"phase": "COMPUTE", "label": "Method engine", "engine": "Thrivarc compute adapter", "skill": f"Run {method}", "reads": "certified data", "produces": "method outputs", "why_now": "Execute the approved design."},
        {"phase": "STATSRUN", "label": "Statistical battery", "engine": "existing stats agents", "skill": "Validate primary findings", "reads": "compute outputs", "produces": "test tables", "why_now": "Quantify evidence strength."},
        {"phase": "CODEAUDIT", "label": "Code audit", "engine": AZURE_DEPLOYMENT, "skill": "Check code/spec alignment", "reads": "RunSpec and outputs", "produces": "audit report", "why_now": "Catch mismatches before review."},
        {"phase": "REVIEWER", "label": "Hostile reviewer", "engine": AZURE_DEPLOYMENT, "skill": "Pressure-test the full study", "reads": "all phase outputs", "produces": "reviewer report", "why_now": "Force defensibility before writing."},
        {"phase": "WRITER", "label": "Paper workspace", "engine": "existing writer", "skill": "Draft verified paper sections", "reads": "approved evidence", "produces": "paper draft", "why_now": "Write only after review passes."},
    ]
    if confirmatory:
        canonical_stack.insert(2, {"phase": "PREREGISTER", "label": "Claim lock", "engine": "existing preregistration agent", "skill": "Lock hypothesis", "reads": "research claim", "produces": "PAP lock", "why_now": "Confirmatory claims must be locked before results."})
    summary.setdefault("agent_stack_preview", canonical_stack)

    # Sanitize: if the LLM returned agent_stack_preview with wrong engine names,
    # force LLM-backed phases back to AZURE_DEPLOYMENT.
    existing_stack = summary.get("agent_stack_preview")
    if isinstance(existing_stack, list):
        for agent_entry in existing_stack:
            if isinstance(agent_entry, dict) and agent_entry.get("phase") in _LLM_AGENT_PHASES:
                agent_entry["engine"] = AZURE_DEPLOYMENT

    if clarifications:
        summary["first_clarification"] = clarifications[0]
    if not summary.get("architect_questions"):
        summary["architect_questions"] = [
            {"dimension": item["key"], "question": item["question"] or f"Confirm {item['field'].lower()}.", "why_it_matters": item["reason"], "owner": "Research architect"}
            for item in summary["clarification_policy"]
            if item["decision"] in {"block", "confirm"}
        ][:5]
    return result


def _fallback_blueprint(payload: dict[str, Any]) -> dict[str, Any]:
    topic = str(payload.get("topic") or "").strip()
    raw_text, text = _payload_text(payload)
    confirmatory = any(word in text for word in ["test whether", "hypothesis", "causes", "outperform", "abnormal returns"])
    method = _infer_method_style(text, confirmatory)
    evidence = _infer_evidence_route(text)
    identifiers = _infer_identifiers(raw_text, text)
    window = _infer_window(text)
    frequency = _infer_frequency(text)
    clarifications = _blocking_requirements(topic, text, method, evidence, identifiers, _has_window(text), _has_frequency(text))
    research_package = _research_package(confirmatory)
    reviewer_gate = _reviewer_gate(confirmatory, method)
    repair_contract = _repair_contract_template()
    stats_policy = _statistical_battery(method)
    agent_stack = [
        {"phase": "LITERATURE", "label": "Context scan", "engine": AZURE_DEPLOYMENT, "skill": "Search and synthesize prior evidence", "reads": "research brief", "produces": "literature_map.md", "why_now": "Ground the study before execution."},
        {"phase": "DATAPULL", "label": "Evidence pull", "engine": "Thrivarc evidence connector", "skill": "Fetch or ingest the dataset", "reads": "RunSpec.datapull", "produces": "data preview and certificate", "why_now": "Evidence must be inspected before compute."},
        {"phase": "COMPUTE", "label": "Method engine", "engine": "Thrivarc compute adapter", "skill": f"Run {method}", "reads": "certified data", "produces": "method outputs", "why_now": "Execute the approved design."},
        {"phase": "STATSRUN", "label": "Statistical battery", "engine": "existing stats agents", "skill": "Validate primary findings", "reads": "compute outputs", "produces": "test tables", "why_now": "Quantify evidence strength."},
        {"phase": "CODEAUDIT", "label": "Code audit", "engine": AZURE_DEPLOYMENT, "skill": "Check code/spec alignment", "reads": "RunSpec and outputs", "produces": "audit report", "why_now": "Catch mismatches before review."},
        {"phase": "REVIEWER", "label": "Hostile reviewer", "engine": AZURE_DEPLOYMENT, "skill": "Pressure-test the full study", "reads": "all phase outputs", "produces": "reviewer report", "why_now": "Force defensibility before writing."},
        {"phase": "WRITER", "label": "Paper workspace", "engine": "existing writer", "skill": "Draft verified paper sections", "reads": "approved evidence", "produces": "paper draft", "why_now": "Write only after review passes."},
    ]
    if confirmatory:
        agent_stack.insert(2, {"phase": "PREREGISTER", "label": "Claim lock", "engine": "existing preregistration agent", "skill": "Lock hypothesis", "reads": "research claim", "produces": "PAP lock", "why_now": "Confirmatory claims must be locked before results."})
    return _normalize_contract({
        "validated": not clarifications,
        "error": None if not clarifications else "Brief is too vague to plan without clarification.",
        "research_state": "confirmatory_pap" if confirmatory else "exploratory",
        "clarifications": clarifications,
        "blueprint_summary": {
            "architect_summary": f"Thrivarc reads this as a {'confirmatory' if confirmatory else 'exploratory'} empirical finance study.",
            "research_stance": "confirmatory_pap" if confirmatory else "exploratory",
            "why_this_stance": "The brief contains a directional testable claim." if confirmatory else "The brief asks to explore evidence before locking a claim.",
            "evidence_source": evidence,
            "why_this_evidence_route": "The brief requires uploaded evidence." if evidence == "upload" else "Public or researcher-provided evidence can support the first pass.",
            "method_style": method,
            "why_this_method": f"The question maps naturally to {method}.",
            "recommended_frequency": frequency,
            "cadence_role": "design_variable" if method == "backtest" else "event_window" if method == "event_study" else "default_market_sampling",
            "cadence_explanation": "Cadence is part of the research design and may need to be fixed or compared." if method == "backtest" else "Timing is driven by the event window." if method == "event_study" else "Sampling frequency is inferred from the research question and confirmed at evidence preview.",
            "decision_problem": "Determine whether the evidence changes the researcher's decision or claim.",
            "comparison_set": "Use the benchmark, asset universe, or uploaded identifiers from the brief.",
            "burden_of_proof": "The result must survive validation, audit, and reviewer pressure.",
            "if_true": "If true, the result should support a narrower defensible finance claim.",
            "evidence_readiness": "Evidence must be previewed and fingerprinted before launch.",
            "output_plan": research_package["label"],
            "research_package": research_package,
            "reviewer_gate": reviewer_gate,
            "repair_contract_template": repair_contract,
            "integrity_artifacts": _integrity_artifacts(confirmatory),
            "clarification_policy": _clarification_policy(topic, method, evidence, identifiers, window, frequency, confirmatory, clarifications),
            "audit_boundary": _audit_boundary(),
            "paper_code_verifier": _paper_code_verifier_policy(),
            "data_quality_policy": _data_quality_policy(evidence),
            "leakage_policy": _leakage_policy(method),
            "statistical_battery": stats_policy,
            "economic_significance": _economic_significance(method),
            "data_fallback_policy": _data_fallback_policy(evidence),
            "inferred_identifiers": identifiers,
            "inferred_window": window,
            "working_assumptions": ["The comparison frame will be finalized before data preview.", "The method must match the approved blueprint."],
            "reviewer_attack_surface": ["Benchmark choice", "Data coverage", "Robustness", "Claim overreach"],
            "reviewer_focus": "A hostile reviewer will attack identification, data quality, and interpretation.",
            "first_clarification": clarifications[0] if clarifications else None,
            "agent_stack_preview": agent_stack,
            "architect_questions": [
                {"dimension": item["key"], "question": item["question"] or f"Confirm {item['field'].lower()}.", "why_it_matters": item["reason"], "owner": "Research architect"}
                for item in _clarification_policy(topic, method, evidence, identifiers, window, frequency, confirmatory, clarifications)
                if item["decision"] in {"block", "confirm"}
            ][:5],
            "revision_policy": {"micro_loops": ["Agents retry bounded failed attempts."], "cross_layer_loops": ["Reviewer routes weaknesses to the weakest phase through Repair Contracts."], "hard_stops": ["Writer waits for reviewer pass.", "Blueprint changes require Deviation Register entries."], "writer_rule": "WRITER drafts only after REVIEWER score average >= 7 and no dimension is below 6", "max_cycles": {"datapull": 2, "compute": 3, "statsrun": 2, "reviewer": 3}},
        },
    })


@router.get("/api/guide")
@router.get("/guide")
def research_guide() -> dict[str, Any]:
    summary = _fallback_blueprint({"topic": "Empirical finance research blueprint"})["blueprint_summary"]
    return {
        "research_package": summary.get("research_package", {}),
        "clarification_policy": summary.get("clarification_policy", []),
        "reviewer_gate": summary.get("reviewer_gate", {}),
        "repair_contract_template": summary.get("repair_contract_template", {}),
        "integrity_artifacts": summary.get("integrity_artifacts", {}),
        "audit_boundary": summary.get("audit_boundary", {}),
        "paper_code_verifier": summary.get("paper_code_verifier", {}),
        "data_quality_policy": summary.get("data_quality_policy", {}),
        "leakage_policy": summary.get("leakage_policy", {}),
        "statistical_battery": summary.get("statistical_battery", {}),
        "economic_significance": summary.get("economic_significance", {}),
        "data_fallback_policy": summary.get("data_fallback_policy", {}),
    }


@router.post("/api/guide/validate")
@router.post("/guide/validate")
def validate(payload: dict[str, Any]) -> dict[str, Any]:
    if not os.getenv("AZURE_OPENAI_API_KEY"):
        return _fallback_blueprint(payload)
    system = (
        "You are a research architect for empirical finance. Return ONLY valid JSON matching the Thrivarc blueprint "
        "shape with validated, research_state, clarifications, and blueprint_summary. Never add prose outside JSON."
    )
    try:
        result = _json_call(system, payload)
    except Exception:
        result = _fallback_blueprint(payload)
    if len(str(payload.get("topic") or "").strip()) < 10:
        result["validated"] = False
        result["error"] = result.get("error") or "Brief is too vague to plan."
        clarifications = _as_list(result.get("clarifications"))
        if not any(isinstance(item, dict) and item.get("key") == "topic" for item in clarifications):
            clarifications.append({
                "key": "topic",
                "question": "What exact finance question should Thrivarc test?",
                "reason": "The planner needs a concrete market, signal, benchmark, or outcome.",
                "blocking": True,
            })
        result["clarifications"] = clarifications
    result = _architecture_defaults(result, payload)
    return _normalize_contract(result)


@router.post("/api/guide/build_runspec")
@router.post("/guide/build_runspec")
def build_runspec(payload: dict[str, Any]) -> dict[str, Any]:
    validated = payload.get("validated_result") if isinstance(payload.get("validated_result"), dict) else validate(payload.get("form_data") or payload)
    form = payload.get("form_data") or {}
    validated = _architecture_defaults(validated, form or payload)
    validated = _normalize_contract(validated)
    summary = validated.get("blueprint_summary", {})
    topic = form.get("topic") or (payload.get("form_data") or {}).get("topic") or "Thrivarc research run"
    runspec = {
        "research": {
            "topic": topic,
            "research_state": validated.get("research_state", "exploratory"),
            "output_format": "research_report",
            "ui_mode": "guided",
            "persona": payload.get("persona") or form.get("persona") or "researcher",
        },
        "datapull": {
            "connector": summary.get("evidence_source", "yfinance"),
            "symbols": summary.get("inferred_identifiers") or [],
            "start_date": (summary.get("inferred_window") or {}).get("start", "2010-01-01"),
            "end_date": (summary.get("inferred_window") or {}).get("end", "2024-12-31"),
            "frequency": summary.get("recommended_frequency", "daily"),
            "fields": ["close", "volume"],
        },
        "compute": {"enabled": summary.get("method_style") not in {"none", "descriptive"}, "type": summary.get("method_style", "descriptive"), "params": {}},
        "statsrun": {"test_battery": (summary.get("statistical_battery") or {}).get("tests", ["coverage_profile"])},
        "blueprint": {
            "agent_stack": summary.get("agent_stack_preview", []),
            "revision_policy": summary.get("revision_policy", {}),
            "architect_questions": summary.get("architect_questions", []),
            "launch_readiness": summary.get("launch_readiness", {}),
            "completion_contract": summary.get("completion_contract", {}),
            "research_package": summary.get("research_package", {}),
            "reviewer_gate": summary.get("reviewer_gate", {}),
            "repair_contract_template": summary.get("repair_contract_template", {}),
            "integrity_artifacts": summary.get("integrity_artifacts", {}),
            "clarification_policy": summary.get("clarification_policy", []),
            "audit_boundary": summary.get("audit_boundary", {}),
            "paper_code_verifier": summary.get("paper_code_verifier", {}),
            "data_quality_policy": summary.get("data_quality_policy", {}),
            "leakage_policy": summary.get("leakage_policy", {}),
            "statistical_battery": summary.get("statistical_battery", {}),
            "economic_significance": summary.get("economic_significance", {}),
            "data_fallback_policy": summary.get("data_fallback_policy", {}),
        },
    }
    return {"runspecs": [{"hypothesis_id": "h1", "runspec": runspec}], "total_estimated_cost": 0.85, "total_estimated_minutes": 12}
