# api/stats_agent.py
# Statistics Agent -- determines the complete test battery for a study.
# THIS IS THE FILE THAT REPLACES THE HARDCODED REGISTRY LOOKUP.
# Primary path: LLM via STATISTICS_AGENT_PROMPT
# Fallback: econometric_inventory.py + method_registry.py (logs warning)
#
# The LLM generates a study-specific, complete test battery.
# The registry was a 5-8 test hardcoded list.
# The LLM generates 15-30 tests specific to the design.

import logging
from typing import Any

from api.llm_caller import call_agent_llm
from api.prompts import STATISTICS_AGENT_PROMPT

logger = logging.getLogger(__name__)


def _as_test_rows(tests: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "test_name": test,
            "purpose": "fallback from econometric inventory and method registry",
            "required": True,
            "fallback_used": True,
        }
        for test in tests
    ]


def _stats_fallback(method_family: str) -> dict[str, Any]:
    """
    Fallback when LLM unavailable.
    Merges econometric_inventory + method_registry.
    Always logs a warning -- this path produces inferior results.
    """
    logger.warning(
        "STATS_AGENT: LLM unavailable -- using fallback registry for method_family=%s. "
        "Test battery will be generic, not study-specific.",
        method_family,
    )
    try:
        from api.method_registry import method_definition

        registry = method_definition(method_family)
        pre = list(registry.get("diagnostic_tests", []))
        inference = list(registry.get("inference_tests", []))
        evaluation = list(registry.get("evaluation_tests", []))
        registered = list(registry.get("registered_checks", []))
        return {
            "pre_estimation_diagnostics": _as_test_rows(pre[: max(3, min(len(pre), 5))]),
            "post_estimation_diagnostics": _as_test_rows((pre[5:] or registered[:3])),
            "inference_tests": _as_test_rows(inference + evaluation),
            "identification_validity_tests": _as_test_rows(inference[:2]),
            "robustness_checks": [
                {
                    "check_name": check,
                    "purpose": "fallback registered robustness check",
                    "implementation": "run registered pipeline check",
                    "required": True,
                    "reviewer_exact_language": "Show the result survives this robustness check.",
                    "fallback_used": True,
                }
                for check in registered[:6]
            ],
            "multiple_testing_correction": {
                "required": len(inference + evaluation + registered) > 5,
                "method": "BH" if len(inference + evaluation + registered) > 5 else "none",
                "justification": "fallback default based on number of registered checks",
            },
            "forbidden_mistakes": [registry.get("leakage_rule", "No timing leakage.")],
            "desk_rejection_risks": registry.get("reviewer_focus", []),
            "fallback_used": True,
            "fallback_reason": "LLM unavailable",
        }
    except Exception as exc:
        logger.warning("STATS_AGENT: all fallback sources unavailable: %s", exc)
        return {
            "pre_estimation_diagnostics": [],
            "post_estimation_diagnostics": [],
            "inference_tests": [],
            "identification_validity_tests": [],
            "robustness_checks": [],
            "fallback_used": True,
            "fallback_reason": "all sources unavailable",
        }


async def get_stats_spec(blueprint: dict, method_spec: dict, client) -> dict:
    """
    Primary entry point for Statistics Agent.

    Calls LLM with full blueprint + method spec context.
    Falls back to registry if LLM fails.

    This function replaces any direct registry call for test batteries
    in sessions.py or runs.py.

    Args:
        blueprint: Locked Blueprint dict
        method_spec: Output of get_method_spec()
        client: Azure OpenAI client

    Returns:
        Complete test battery dict
    """
    identifiers = blueprint.get("inferred_identifiers", [])
    window = blueprint.get("inferred_window", {})
    sample_desc = f"{', '.join(identifiers)} from {window.get('start', 'unknown')} to {window.get('end', 'unknown')}"

    frameworks = method_spec.get("modeling_frameworks", [{}])
    first_framework = frameworks[0] if frameworks else {}
    if isinstance(first_framework, dict):
        primary_model = first_framework.get("name", "OLS regression")
    else:
        primary_model = str(first_framework or "OLS regression")

    prompt = STATISTICS_AGENT_PROMPT.format(
        method_family=blueprint.get("method_family", ""),
        data_structure=blueprint.get("data_structure", ""),
        identification_strategy=blueprint.get("identification_strategy", ""),
        primary_model=primary_model,
        primary_coefficient=method_spec.get("primary_coefficient", ""),
        standard_error_approach=method_spec.get("standard_error_approach", ""),
        known_threats=", ".join(blueprint.get("known_threats", [])),
        sample_description=sample_desc,
        window_start=window.get("start", ""),
        window_end=window.get("end", ""),
    )

    return await call_agent_llm(
        agent_name="STATS_AGENT",
        prompt=prompt,
        client=client,
        fallback_fn=_stats_fallback,
        fallback_args={"method_family": blueprint.get("method_family", "descriptive")},
        max_tokens=4000,
    )
