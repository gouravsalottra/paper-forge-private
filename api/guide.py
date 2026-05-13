from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter
from openai import AzureOpenAI

router = APIRouter()

AZURE_ENDPOINT = "https://goura-mp4b98bg-eastus2.cognitiveservices.azure.com/"
AZURE_DEPLOYMENT = "gpt-5.5"
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


def _fallback_blueprint(payload: dict[str, Any]) -> dict[str, Any]:
    topic = str(payload.get("topic") or "").strip()
    text = " ".join(str(payload.get(k) or "") for k in ("topic", "abstract", "notes", "data_instructions", "design_instructions", "validation_notes", "hypothesis")).lower()
    confirmatory = any(word in text for word in ["test whether", "hypothesis", "causes", "outperform", "abnormal returns"])
    upload = any(word in text for word in ["upload", "proprietary", "my dataset", "private"])
    event = any(word in text for word in ["event", "announcement", "fomc", "earnings", "filing"])
    method = "event_study" if event else "regression" if confirmatory else "descriptive"
    evidence = "upload" if upload else "yfinance"
    clarifications = []
    if len(topic) < 20:
        clarifications.append({"key": "topic", "question": "What exact finance question should Thrivarc test?", "reason": "The planner needs a concrete market, signal, benchmark, or outcome.", "blocking": True})
    agent_stack = [
        {"phase": "LITERATURE", "label": "Context scan", "engine": AZURE_DEPLOYMENT, "skill": "Search and synthesize prior evidence", "reads": "research brief", "produces": "literature_map.md", "why_now": "Ground the study before execution."},
        {"phase": "DATAPULL", "label": "Evidence pull", "engine": "existing Paper Forge connector", "skill": "Fetch or ingest the dataset", "reads": "RunSpec.datapull", "produces": "data preview and certificate", "why_now": "Evidence must be inspected before compute."},
        {"phase": "COMPUTE", "label": "Method engine", "engine": "existing Paper Forge compute", "skill": f"Run {method}", "reads": "certified data", "produces": "method outputs", "why_now": "Execute the approved design."},
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
            "why_this_evidence_route": "The brief requires uploaded evidence." if upload else "Public market data is sufficient for the first pass.",
            "method_style": method,
            "why_this_method": f"The question maps naturally to {method}.",
            "recommended_frequency": "daily",
            "cadence_role": "event_window" if event else "default_market_sampling",
            "cadence_explanation": "Timing is driven by the event window." if event else "Daily sampling is a starting point until the evidence preview says otherwise.",
            "decision_problem": "Determine whether the evidence changes the researcher's decision or claim.",
            "comparison_set": "Use the benchmark, asset universe, or uploaded identifiers from the brief.",
            "burden_of_proof": "The result must survive validation, audit, and reviewer pressure.",
            "if_true": "If true, the result should support a narrower defensible finance claim.",
            "evidence_readiness": "Evidence must be previewed and fingerprinted before launch.",
            "output_plan": "Research report with reviewer-backed paper workspace.",
            "inferred_identifiers": [],
            "inferred_window": {"start": "2010-01-01", "end": "2024-12-31"},
            "working_assumptions": ["The comparison frame will be finalized before data preview.", "The method must match the approved blueprint."],
            "reviewer_attack_surface": ["Benchmark choice", "Data coverage", "Robustness", "Claim overreach"],
            "reviewer_focus": "A hostile reviewer will attack identification, data quality, and interpretation.",
            "first_clarification": clarifications[0] if clarifications else None,
            "agent_stack_preview": agent_stack,
            "architect_questions": [{"dimension": "evidence", "question": "What universe, benchmark, or uploaded schema should anchor this study?", "why_it_matters": "The evidence route controls every downstream phase.", "owner": "Research architect"}],
            "revision_policy": {"micro_loops": ["Agents retry bounded failed attempts."], "cross_layer_loops": ["Reviewer routes weaknesses to the weakest phase."], "hard_stops": ["Writer waits for reviewer pass."], "writer_rule": "WRITER drafts only after REVIEWER scores >= 7", "max_cycles": {"datapull": 2, "compute": 3, "statsrun": 2, "reviewer": 3}},
        },
    })


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
    return _normalize_contract(result)


@router.post("/guide/build_runspec")
def build_runspec(payload: dict[str, Any]) -> dict[str, Any]:
    validated = payload.get("validated_result") if isinstance(payload.get("validated_result"), dict) else validate(payload.get("form_data") or payload)
    validated = _normalize_contract(validated)
    form = payload.get("form_data") or {}
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
        "statsrun": {"test_battery": ["t_test", "newey_west", "bonferroni"]},
        "blueprint": {
            "agent_stack": summary.get("agent_stack_preview", []),
            "revision_policy": summary.get("revision_policy", {}),
            "architect_questions": summary.get("architect_questions", []),
            "launch_readiness": summary.get("launch_readiness", {}),
            "completion_contract": summary.get("completion_contract", {}),
        },
    }
    return {"runspecs": [{"hypothesis_id": "h1", "runspec": runspec}], "total_estimated_cost": 0.85, "total_estimated_minutes": 12}
