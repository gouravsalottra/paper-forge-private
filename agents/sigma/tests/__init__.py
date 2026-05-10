from .registry import TEST_REGISTRY, get_test, register
from . import (
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

__all__ = ["TEST_REGISTRY", "get_test", "register"]
