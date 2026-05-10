"""Compatibility shim for legacy compute entrypoint.

This module remains importable for backward compatibility with tests and
existing integrations that import ``agents.forge.full_run``.
"""

from __future__ import annotations

from typing import Any


def run_full_sweep(n_episodes: int | None = None) -> dict[str, Any]:
    """Legacy shim.

    The production RL implementation was moved under examples/. Core runtime
    should dispatch through compute adapters instead.
    """
    if n_episodes is None:
        raise ValueError(
            "compute.episodes must be specified in PROTOCOL.md "
            "when using rl or abm compute type. "
            "Example: episodes: 5e5"
        )
    return {
        "result_flag": "SKIPPED",
        "backend": "legacy-shim",
        "n_episodes": int(n_episodes),
        "note": "Legacy agents.forge.full_run shim. Use agents.compute adapters.",
    }
