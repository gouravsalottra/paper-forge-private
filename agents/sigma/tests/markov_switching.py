from __future__ import annotations

import pandas as pd

from .registry import register


@register
class MarkovSwitchingTest:
    test_name = "markov_switching"
    requires_seeds = True

    def run(self, data: pd.DataFrame, seed: int, params: dict) -> dict:
        series = pd.to_numeric(data.get("returns", pd.Series([], dtype=float)), errors="coerce").dropna()
        stat = float(series.mean()) if not series.empty else 0.0
        pval = 1.0
        return {
            "test_name": self.test_name,
            "seed": seed,
            "statistic": stat,
            "p_value": pval,
            "effect_size": stat,
            "significant": bool(pval < 0.05),
            "conclusion": "placeholder",
            "raw_output": {},
        }
