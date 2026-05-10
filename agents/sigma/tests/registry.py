from __future__ import annotations

from .base import StatTest

TEST_REGISTRY: dict[str, type[StatTest]] = {}


def register(cls):
    TEST_REGISTRY[cls.test_name] = cls
    return cls


def get_test(name: str) -> StatTest:
    _bootstrap_registry()
    if name not in TEST_REGISTRY:
        raise ValueError(
            f"Unknown statistical test: '{name}'\n"
            f"Available: {sorted(TEST_REGISTRY.keys())}"
        )
    return TEST_REGISTRY[name]()


def _bootstrap_registry() -> None:
    if TEST_REGISTRY:
        return
    from . import (  # noqa: F401
        newey_west_hac,
        garch_11,
        bootstrap_ci,
        deflated_sharpe,
        fama_macbeth,
        regime_switching,
        markov_switching,
        descriptive_stats,
        placebo_test,
        out_of_sample_r2,
    )


_bootstrap_registry()
