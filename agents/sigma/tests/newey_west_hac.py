from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from .registry import register


@register
class NeweyWestHAC:
    test_name = "newey_west_hac"
    requires_seeds = True

    def run(self, data: pd.DataFrame, seed: int, params: dict) -> dict:
        series = pd.to_numeric(data.get("returns", pd.Series([], dtype=float)), errors="coerce").dropna()
        if len(series) < 3:
            return {
                "test_name": self.test_name,
                "seed": seed,
                "statistic": 0.0,
                "p_value": 1.0,
                "effect_size": 0.0,
                "significant": False,
                "conclusion": "insufficient data",
                "raw_output": {},
            }

        y = np.asarray(series, dtype=float)
        X = np.ones((len(y), 1), dtype=float)
        fit = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": min(4, len(y) - 1)})
        stat = float(fit.tvalues[0])
        pval = float(fit.pvalues[0])
        return {
            "test_name": self.test_name,
            "seed": seed,
            "statistic": stat,
            "p_value": pval,
            "effect_size": float(series.mean()),
            "significant": bool(pval < 0.05),
            "conclusion": "Significant" if pval < 0.05 else "Not significant",
            "raw_output": {"coef": float(fit.params[0])},
        }
