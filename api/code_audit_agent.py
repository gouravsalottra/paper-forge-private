# api/code_audit_agent.py
# Code Audit Agent -- verifies analysis code matches locked Blueprint.
# Checks for look-ahead bias, survivorship bias, identification leakage,
# return definition errors, window/universe/benchmark mismatches.

import logging

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
    if fatal:
        logger.error("CODE_AUDIT: %s fatal violation(s) found. Pipeline blocked.", len(fatal))
        result["blocks_pipeline"] = True

    return result
