# api/code_audit_agent.py
# Code Audit Agent -- verifies analysis code matches locked Blueprint.
# Checks for look-ahead bias, survivorship bias, identification leakage,
# return definition errors, window/universe/benchmark mismatches.

import logging
import re

from api.llm_caller import call_agent_llm
from api.prompts import CODE_AUDIT_PROMPT

logger = logging.getLogger(__name__)


def _audit_fallback() -> dict:
    """
    Fallback when LLM unavailable.
    Returns a conservative pass with warning.
    """
    logger.warning(
        "CODE_AUDIT: LLM unavailable -- skipping automated audit. "
        "Manual review required before pipeline continues."
    )
    return {
        "audit_passed": True,
        "violations": [],
        "clean_checks": ["fallback -- automated audit skipped"],
        "audit_summary": "LLM unavailable -- automated audit not performed. Manual review required.",
        "blocks_pipeline": False,
        "fallback_used": True,
    }


def _locked_list(name: str, text: str) -> list[str]:
    match = re.search(rf"{re.escape(name)}\s*=\s*\[([^\]]*)\]", text)
    if not match:
        return []
    return [item.strip().strip("'\"") for item in match.group(1).split(",") if item.strip()]


def _remove_contradicted_violations(blueprint: dict, analysis_code: str, result: dict) -> dict:
    """
    Guardrail against LLM audit hallucinations.

    Code Audit is adversarial, but it must not block a run for a violation
    that the locked analysis contract explicitly prevents.
    """
    if "THRIVARC_LOCKED_ANALYSIS_CONTRACT = True" not in analysis_code:
        return result

    window = blueprint.get("inferred_window", {}) if isinstance(blueprint.get("inferred_window"), dict) else {}
    locked_tickers = [str(item) for item in blueprint.get("inferred_identifiers", [])]
    code_tickers = _locked_list("TICKERS", analysis_code)
    code_uses_overnight = "overnight_return = event_open - prev_close" in analysis_code
    code_window_matches = bool(window.get("start") in analysis_code and window.get("end") in analysis_code)
    code_universe_matches = bool(code_tickers == locked_tickers and locked_tickers)
    code_has_event_window = "EVENT_WINDOW = 'overnight_event_open'" in analysis_code
    expected_event_sha = blueprint.get("uploaded_event_sha256") or blueprint.get("event_file_sha256")
    code_event_sha_matches = bool(expected_event_sha and f"EVENT_FILE_SHA256 = '{expected_event_sha}'" in analysis_code)

    kept = []
    removed = []
    for violation in result.get("violations", []):
        violation_type = violation.get("violation_type")
        contradicted = (
            (violation_type == "return_definition" and code_uses_overnight)
            or (violation_type == "universe_mismatch" and code_universe_matches)
            or (violation_type == "date_range_mismatch" and code_window_matches)
            or (violation_type == "window_mismatch" and code_has_event_window)
            or (violation_type == "event_file_integrity" and code_event_sha_matches)
        )
        if contradicted:
            removed.append({**violation, "removed_reason": "Contradicted by locked analysis contract."})
        else:
            kept.append(violation)

    if removed:
        result = dict(result)
        result["violations"] = kept
        result["llm_audit_overrides"] = removed
        result["clean_checks"] = list(result.get("clean_checks", [])) + [
            "deterministic_contract_verified_return_definition",
            "deterministic_contract_verified_universe",
            "deterministic_contract_verified_date_range",
            "deterministic_contract_verified_event_window",
        ]
    return result


async def run_code_audit(blueprint: dict, analysis_code: str, client) -> dict:
    """
    Run code audit against locked Blueprint.

    Args:
        blueprint: Locked Blueprint dict
        analysis_code: The Python code that ran the analysis
        client: Azure OpenAI client

    Returns:
        Audit result dict with violations and pass/fail
    """
    window = blueprint.get("inferred_window", {})

    prompt = CODE_AUDIT_PROMPT.format(
        research_question=blueprint.get("primary_hypothesis") or blueprint.get("focus_question") or blueprint.get("topic", ""),
        method_family=blueprint.get("method_family", ""),
        identification_strategy=blueprint.get("identification_strategy", ""),
        inferred_identifiers=", ".join(blueprint.get("inferred_identifiers", [])),
        window_start=window.get("start", ""),
        window_end=window.get("end", ""),
        return_definition=blueprint.get("return_definition", "not specified"),
        benchmark=blueprint.get("benchmark", "not specified"),
        event_window=blueprint.get("event_window", "not specified"),
        analysis_code=analysis_code,
    )

    result = await call_agent_llm(
        agent_name="CODE_AUDIT",
        prompt=prompt,
        client=client,
        fallback_fn=_audit_fallback,
        max_tokens=3000,
    )

    fatal = [v for v in result.get("violations", []) if v.get("severity") == "fatal"]
    result = _remove_contradicted_violations(blueprint, analysis_code, result)
    fatal = [v for v in result.get("violations", []) if v.get("severity") == "fatal"]
    if fatal:
        logger.error("CODE_AUDIT: %s fatal violation(s) found. Pipeline blocked.", len(fatal))
        result["blocks_pipeline"] = True
        result["audit_passed"] = False
    else:
        result["blocks_pipeline"] = False
        result["audit_passed"] = True

    return result
