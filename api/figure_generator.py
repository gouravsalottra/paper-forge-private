from __future__ import annotations

from typing import Any


def generate_figures_for_study(
    session_id: str,
    blueprint: dict[str, Any],
    csv_outputs: dict[str, str],
    results_dict: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Figure generation now belongs to the LLM-authored compute code.

    This compatibility function intentionally does not decide chart types or
    derive figures from CSVs. It only returns figure metadata already produced
    by the compute dispatcher when present in results_dict.
    """
    if isinstance(results_dict, dict):
        figures = results_dict.get("figure_artifacts")
        if isinstance(figures, dict):
            return figures
    return {}
