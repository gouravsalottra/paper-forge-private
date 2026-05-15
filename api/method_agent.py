# api/method_agent.py
# Method/Compute Agent -- specifies what to estimate for a given Blueprint.
# Primary path: LLM via METHOD_AGENT_PROMPT
# Fallback: method_registry.py (logs warning when used)

import logging
from typing import Any

from api.llm_caller import call_agent_llm
from api.prompts import METHOD_AGENT_PROMPT

logger = logging.getLogger(__name__)


def _method_fallback(method_family: str) -> dict[str, Any]:
    """
    Fallback when LLM unavailable.
    Uses method_registry -- always logs a warning.
    """
    try:
        from api.method_registry import method_definition

        registry = method_definition(method_family)
        logger.warning(
            "METHOD_AGENT: LLM unavailable -- using fallback registry for method_family=%s. "
            "Results will be less specific than LLM-generated spec.",
            method_family,
        )
        frameworks = [
            {
                "name": name,
                "purpose": "Fallback framework selected from method registry.",
                "primary": idx == 0,
                "specification": registry.get("primary_test", "registry fallback specification"),
                "software_library": "statsmodels",
                "software_function": "registry_selected_adapter",
                "required_inputs": registry.get("features", []),
                "expected_output": registry.get("claim_scope", "method output"),
            }
            for idx, name in enumerate(registry.get("modeling_frameworks", []))
        ]
        if not frameworks:
            frameworks = [
                {
                    "name": registry.get("label", method_family),
                    "purpose": "Fallback descriptive or registry-selected model.",
                    "primary": True,
                    "specification": registry.get("primary_test", "registry fallback specification"),
                    "software_library": "statsmodels",
                    "software_function": "registry_selected_adapter",
                    "required_inputs": registry.get("features", []),
                    "expected_output": registry.get("claim_scope", "method output"),
                }
            ]
        return {
            "modeling_frameworks": frameworks,
            "estimation_sequence": ["Run primary model", "Run registered robustness checks"],
            "fixed_effects_structure": "none",
            "standard_error_approach": "OLS or registry default",
            "why_this_se_approach": "fallback default from method registry",
            "primary_coefficient": "primary predictor",
            "expected_sign": "ambiguous",
            "expected_magnitude_range": "unknown",
            "economic_significance_benchmark": registry.get("economic_rule", "unknown"),
            "compute_artifacts": [registry.get("compute_path", "06_compute/method_outputs/results.json")],
            "python_code_scaffold": "# fallback -- no LLM scaffold available",
            "forbidden_in_code": [registry.get("leakage_rule", "No post-hoc leakage.")],
            "fallback_used": True,
            "fallback_reason": "LLM unavailable",
        }
    except Exception as exc:
        logger.error("METHOD_AGENT: both LLM and registry unavailable: %s", exc)
        return {"fallback_used": True, "fallback_reason": "all sources unavailable", "modeling_frameworks": []}


async def get_method_spec(blueprint: dict, client) -> dict:
    """
    Primary entry point for Method Agent.
    Calls LLM with full blueprint context.
    Falls back to registry if LLM fails.

    Args:
        blueprint: Locked Blueprint dict from Research Architect
        client: Azure OpenAI client

    Returns:
        Method specification dict
    """
    prompt = METHOD_AGENT_PROMPT.format(
        research_question=blueprint.get("primary_hypothesis") or blueprint.get("focus_question") or blueprint.get("topic", ""),
        method_family=blueprint.get("method_family", ""),
        data_structure=blueprint.get("data_structure", ""),
        identification_strategy=blueprint.get("identification_strategy", ""),
        outcome_variable=blueprint.get("outcome_variable", ""),
        key_predictors=", ".join(blueprint.get("key_predictors", [])),
        control_variables=", ".join(blueprint.get("control_variables", [])),
        inferred_identifiers=", ".join(blueprint.get("inferred_identifiers", [])),
        window_start=blueprint.get("inferred_window", {}).get("start", ""),
        window_end=blueprint.get("inferred_window", {}).get("end", ""),
        known_threats=", ".join(blueprint.get("known_threats", [])),
        economic_significance_definition=blueprint.get("economic_significance_definition", ""),
    )

    return await call_agent_llm(
        agent_name="METHOD_AGENT",
        prompt=prompt,
        client=client,
        fallback_fn=_method_fallback,
        fallback_args={"method_family": blueprint.get("method_family", "descriptive")},
        max_tokens=4000,
    )
