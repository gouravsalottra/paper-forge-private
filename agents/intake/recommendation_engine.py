from __future__ import annotations


class RecommendationEngine:
    MAP = {
        "predictability": ["fama_macbeth", "out_of_sample_r2", "placebo_test", "newey_west_hac"],
        "performance": ["newey_west_hac", "deflated_sharpe", "bootstrap_ci", "regime_switching"],
        "causal": ["event_study_car", "placebo_test", "newey_west_hac", "granger_causality"],
        "descriptive": ["descriptive_stats", "regime_switching", "markov_switching"],
        "exploratory": ["descriptive_stats"],
    }

    def recommend_tests(self, claim_type: str) -> list[str]:
        return list(self.MAP.get((claim_type or "").lower(), ["descriptive_stats"]))
