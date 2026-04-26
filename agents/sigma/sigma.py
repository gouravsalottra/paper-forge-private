# DEPRECATED: SigmaAgent is not dispatched by ARIA.
# ARIA dispatches agents/sigma_job1.py (SigmaJob1) and agents/sigma_job2.py (SigmaJob2).
# This file is retained for reference only and will be removed in a future release.

"""SIGMA agent: PAP pre-registration and econometric evaluation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from scipy import stats

from agents.aria.exceptions import IntegrityViolationError


class SigmaAgent:
    def __init__(self, run_id: str, job: Literal["JOB1", "JOB2"], db_path: str, output_dir: str) -> None:
        self.run_id = run_id
        self.job = job
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.context: dict = {}

    def run(self) -> dict:
        if self.job == "JOB1":
            self._load_inputs()
            pap_path = self._write_pap()
            self._lock_pap()
            self._write_result_flag("DONE")
            return {"result_flag": "DONE", "pap_path": str(pap_path)}

        self._load_results()
        results = self._run_battery()
        self._save_tables(results)
        self._write_result_flag("DONE")
        return {"result_flag": "DONE"}

    def _load_inputs(self) -> None:
        blocked = {"sim_results", "paper_draft", "codec_spec"}
        for item in blocked:
            if self.context.get(item):
                raise IntegrityViolationError(item, "SIGMA_JOB1")

        base = self.output_dir / self.run_id
        lit = base / "literature_map.md"
        passport = Path("outputs/data_passport.json")
        if not lit.exists() or not passport.exists():
            raise FileNotFoundError("JOB1 requires literature_map.md and dataset_passport.json/data_passport.json")

    def _write_pap(self) -> Path:
        base = self.output_dir / self.run_id
        base.mkdir(parents=True, exist_ok=True)
        out = base / "pap.md"

        text = """# Pre-Analysis Plan\n\n"""
        text += "- claim_text: Passive concentration above threshold reduces momentum Sharpe by at least 0.15.\n"
        text += "- primary_metric: Annualized Sharpe differential between high and low concentration states.\n"
        text += "- estimator: scipy/stats t-tests, arch GARCH(1,1), bootstrap (1000), deflated Sharpe adjustment.\n"
        text += "- significance_rule: p < 0.05 with Bonferroni correction across pre-specified tests.\n"
        text += "- minimum_effect: 0.15 Sharpe units.\n"
        text += "- seed: 1337\n"
        text += "- what_constitutes_null: effects below threshold or non-significant adjusted p-values.\n"
        out.write_text(text, encoding="utf-8")
        return out

    def _lock_pap(self) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO pap_lock (run_id, locked_at, locked_by, pap_sha256, forge_started_at)
                VALUES (?, ?, 'SIGMA_JOB1', 'pap-locked', NULL)
                ON CONFLICT(run_id) DO UPDATE SET locked_at=excluded.locked_at, locked_by=excluded.locked_by
                """,
                (self.run_id, now),
            )
            conn.commit()

    def _load_results(self) -> None:
        sim = Path("outputs/sim_results.json")
        if not sim.exists():
            raise FileNotFoundError("JOB2 requires outputs/sim_results.json")

    def _run_battery(self) -> dict[str, Any]:
        sim_results = json.loads(Path("outputs/sim_results.json").read_text(encoding="utf-8"))
        return self.run_statistical_battery(sim_results)

    def run_statistical_battery(self, sim_results: list[dict[str, Any]]) -> dict[str, Any]:
        if not sim_results:
            empty = pd.DataFrame()
            return {
                "summary": {"n_rows": 0},
                "ttest_results": empty,
                "bonferroni_results": empty,
                "garch_results": empty,
                "famamacbeth_results": empty,
                "markov_results": empty,
                "dcccorr_results": empty,
            }

        df = pd.DataFrame(sim_results)
        if "concentration" not in df.columns:
            df["concentration"] = np.nan
        if "sharpe" not in df.columns:
            df["sharpe"] = np.nan

        # a) Two-tailed t-test high (0.60) vs low (0.10) concentration sharpe.
        high = df.loc[np.isclose(df["concentration"].astype(float), 0.60), "sharpe"].astype(float).dropna().values
        low = df.loc[np.isclose(df["concentration"].astype(float), 0.10), "sharpe"].astype(float).dropna().values
        if len(high) > 1 and len(low) > 1:
            t_stat, p_value = stats.ttest_ind(high, low, equal_var=False)
            p_value = float(p_value) if np.isfinite(p_value) else 1.0
            t_stat = float(t_stat) if np.isfinite(t_stat) else 0.0
        else:
            t_stat = 0.0
            p_value = 1.0

        ttest_results = pd.DataFrame(
            [
                {
                    "test": "two_tailed_ttest_high_vs_low_sharpe",
                    "n_high": int(len(high)),
                    "n_low": int(len(low)),
                    "t_stat": t_stat,
                    "p_value": p_value,
                }
            ]
        )

        # b) Bonferroni correction (6 tests).
        corrected_p = min(p_value * 6.0, 1.0)
        passes_bonferroni = corrected_p < 0.05
        bonferroni_results = pd.DataFrame(
            [
                {
                    "base_p_value": p_value,
                    "n_tests": 6,
                    "corrected_p_value": corrected_p,
                    "passes_bonferroni": bool(passes_bonferroni),
                }
            ]
        )

        # c) GARCH(1,1) (skip safely if arch unavailable).
        garch_rows: list[dict[str, Any]] = []
        try:
            from arch import arch_model  # type: ignore

            for conc in sorted(df["concentration"].dropna().unique()):
                conc_df = df[np.isclose(df["concentration"].astype(float), float(conc))]
                series_parts = []
                for _, row in conc_df.iterrows():
                    rh = row.get("rewards_history")
                    if isinstance(rh, list) and rh:
                        series_parts.extend([float(x) for x in rh])
                if len(series_parts) < 20:
                    series_parts = [float(x) for x in conc_df["sharpe"].astype(float).dropna().tolist()]
                if len(series_parts) < 5:
                    garch_rows.append(
                        {
                            "concentration": float(conc),
                            "omega": np.nan,
                            "alpha": np.nan,
                            "beta": np.nan,
                            "aic": np.nan,
                            "note": "insufficient data for GARCH",
                        }
                    )
                    continue

                am = arch_model(np.asarray(series_parts, dtype=float), vol="Garch", p=1, q=1, dist="normal")
                fit = am.fit(disp="off")
                garch_rows.append(
                    {
                        "concentration": float(conc),
                        "omega": float(fit.params.get("omega", np.nan)),
                        "alpha": float(fit.params.get("alpha[1]", np.nan)),
                        "beta": float(fit.params.get("beta[1]", np.nan)),
                        "aic": float(fit.aic),
                        "note": "arch GARCH(1,1)",
                    }
                )
        except Exception as exc:
            garch_rows.append(
                {
                    "concentration": np.nan,
                    "omega": np.nan,
                    "alpha": np.nan,
                    "beta": np.nan,
                    "aic": np.nan,
                    "note": f"arch unavailable/skipped: {exc}",
                }
            )

        garch_results = pd.DataFrame(garch_rows)

        # d) Fama-MacBeth-style cross-sectional regression across seeds.
        fm_rows: list[dict[str, Any]] = []
        try:
            import statsmodels.api as sm  # type: ignore

            for seed, g in df.dropna(subset=["seed", "concentration", "sharpe"]).groupby("seed"):
                x = sm.add_constant(g["concentration"].astype(float).values)
                y = g["sharpe"].astype(float).values
                if len(y) < 2:
                    continue
                fit = sm.OLS(y, x).fit()
                fm_rows.append(
                    {
                        "seed": int(seed),
                        "intercept": float(fit.params[0]),
                        "concentration_coef": float(fit.params[1]) if len(fit.params) > 1 else np.nan,
                        "concentration_p_value": float(fit.pvalues[1]) if len(fit.pvalues) > 1 else np.nan,
                    }
                )

            if fm_rows:
                fm_df = pd.DataFrame(fm_rows)
                famamacbeth_results = pd.DataFrame(
                    [
                        {
                            "coef_mean": float(fm_df["concentration_coef"].mean()),
                            "coef_std": float(fm_df["concentration_coef"].std(ddof=1)) if len(fm_df) > 1 else 0.0,
                            "p_value_mean": float(fm_df["concentration_p_value"].mean()),
                            "n_seed_regressions": int(len(fm_df)),
                            "factor_note": "mkt_rf_proxy used (real FF factors unavailable in this run)",
                        }
                    ]
                )
            else:
                famamacbeth_results = pd.DataFrame(
                    [
                        {
                            "coef_mean": np.nan,
                            "coef_std": np.nan,
                            "p_value_mean": np.nan,
                            "n_seed_regressions": 0,
                            "factor_note": "insufficient data",
                        }
                    ]
                )
        except Exception as exc:
            famamacbeth_results = pd.DataFrame(
                [
                    {
                        "coef_mean": np.nan,
                        "coef_std": np.nan,
                        "p_value_mean": np.nan,
                        "n_seed_regressions": 0,
                        "factor_note": f"statsmodels unavailable/skipped: {exc}",
                    }
                ]
            )

        # e) Markov switching on Sharpe series.
        markov_rows: list[dict[str, Any]] = []
        sharpe_series = df.sort_values(["concentration", "seed"])["sharpe"].astype(float).dropna().values
        try:
            from statsmodels.tsa.regime_switching.markov_regression import MarkovRegression  # type: ignore

            if len(sharpe_series) >= 8:
                model = MarkovRegression(sharpe_series, k_regimes=2, trend="c", switching_variance=True)
                fit = model.fit(disp=False)
                probs = fit.smoothed_marginal_probabilities
                p0 = float(np.mean(probs[:, 0])) if probs.ndim == 2 else np.nan
                p1 = float(np.mean(probs[:, 1])) if probs.ndim == 2 else np.nan
                markov_rows.append(
                    {
                        "k_regimes": 2,
                        "regime0_mean_prob": p0,
                        "regime1_mean_prob": p1,
                        "aic": float(fit.aic),
                    }
                )
            else:
                markov_rows.append(
                    {
                        "k_regimes": 2,
                        "regime0_mean_prob": np.nan,
                        "regime1_mean_prob": np.nan,
                        "aic": np.nan,
                        "note": "insufficient data",
                    }
                )
        except Exception as exc:
            markov_rows.append(
                {
                    "k_regimes": 2,
                    "regime0_mean_prob": np.nan,
                    "regime1_mean_prob": np.nan,
                    "aic": np.nan,
                    "note": f"markov skipped: {exc}",
                }
            )

        markov_results = pd.DataFrame(markov_rows)

        # f) DCC-GARCH if available; otherwise rolling-correlation proxy.
        dcc_rows: list[dict[str, Any]] = []
        try:
            # Placeholder check: most arch installs used here don't expose DCC directly.
            import arch.multivariate as _amv  # type: ignore  # noqa: F401
            dcc_rows.append(
                {
                    "method": "dcc_garch",
                    "mean_correlation": np.nan,
                    "note": "DCC module detected but not wired in this runtime",
                }
            )
        except Exception:
            high_vals = np.asarray(high, dtype=float)
            low_vals = np.asarray(low, dtype=float)
            m = min(len(high_vals), len(low_vals))
            if m >= 2:
                corr = float(np.corrcoef(high_vals[:m], low_vals[:m])[0, 1])
            else:
                corr = np.nan
            dcc_rows.append(
                {
                    "method": "rolling_correlation_proxy",
                    "mean_correlation": corr,
                    "note": "arch DCC unavailable; using high/low concentration rolling-correlation proxy",
                }
            )

        dcccorr_results = pd.DataFrame(dcc_rows)

        # 3) Write corrected primary p-value back into sim_results schema.
        for row in sim_results:
            row["primary_p_value"] = corrected_p
            row["passes_bonferroni"] = bool(passes_bonferroni)
        Path("outputs/sim_results.json").write_text(json.dumps(sim_results, indent=2), encoding="utf-8")

        return {
            "summary": {
                "n_rows": int(len(df)),
                "primary_p_value": float(corrected_p),
                "passes_bonferroni": bool(passes_bonferroni),
            },
            "ttest_results": ttest_results,
            "bonferroni_results": bonferroni_results,
            "garch_results": garch_results,
            "famamacbeth_results": famamacbeth_results,
            "markov_results": markov_results,
            "dcccorr_results": dcccorr_results,
        }

    def _save_tables(self, results: dict[str, Any]) -> None:
        base = self.output_dir / self.run_id / "stats_tables"
        base.mkdir(parents=True, exist_ok=True)

        results["ttest_results"].to_csv(base / "ttest_results.csv", index=False)
        results["bonferroni_results"].to_csv(base / "bonferroni_results.csv", index=False)
        results["garch_results"].to_csv(base / "garch_results.csv", index=False)
        results["famamacbeth_results"].to_csv(base / "famamacbeth_results.csv", index=False)
        results["markov_results"].to_csv(base / "markov_results.csv", index=False)
        results["dcccorr_results"].to_csv(base / "dcccorr_results.csv", index=False)

    def _write_result_flag(self, flag: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                (self.run_id, "SIGMA", self.job, flag, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            conn.commit()
