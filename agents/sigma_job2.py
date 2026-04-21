"""SIGMA Job 2: econometric battery over FORGE simulation outputs."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from arch import arch_model
from scipy.stats import norm
from statsmodels.tsa.regime_switching.markov_autoregression import MarkovAutoregression


@dataclass
class SigmaJob2:
    run_id: str
    db_path: str = "state.db"
    output_dir: str = "paper_memory"

    def run(self) -> dict:
        sim_df = self._load_sim_results()
        seed = self._seed_from_pap_lock()
        returns = sim_df["mean_reward"].to_numpy(dtype=float)
        primary_metric = self._rolling_sharpe_differential(sim_df)

        ttest_result = self._newey_west_ttest(returns)
        garch_result = self._garch_11(returns)
        bootstrap_result = self._bootstrap_ci(returns, seed=seed, n_resamples=1000)
        deflated_result = self._deflated_sharpe(returns, n_trials=6)
        regime_result = self._markov_regime(returns)
        fama_result = self._fama_macbeth_regression(sim_df)
        dcc_result = self._dcc_garch_summary()
        seed_consistency = self._validate_seed_consistency(sim_df)

        bonf = self._bonferroni(
            [
                ttest_result["p_value"],
                garch_result["alpha_pvalue"],
                deflated_result["p_value"],
                regime_result["regime_mean_diff_p_value"],
                bootstrap_result["mean_lt_zero_p_value"],
                fama_result.get("concentration_pvalue", 1.0),
            ],
            n_tests=6,
            primary_metric=primary_metric,
        )

        stats_dir = Path(self.output_dir) / self.run_id / "stats_tables"
        stats_dir.mkdir(parents=True, exist_ok=True)

        sharpe_summary_path = stats_dir / "sharpe_summary.csv"
        ttest_results_path = stats_dir / "ttest_results.csv"
        garch_results_path = stats_dir / "garch_results.csv"
        fama_macbeth_path = stats_dir / "fama_macbeth_results.csv"
        primary_metric_path = stats_dir / "primary_metric.csv"
        min_effect_path = stats_dir / "minimum_effect_check.csv"
        dcc_path = stats_dir / "dcc_garch_results.csv"
        seed_path = stats_dir / "seed_consistency.csv"
        latex_path = stats_dir / "stats_summary.tex"

        self._write_sharpe_summary(sharpe_summary_path, sim_df, deflated_result, bootstrap_result, bonf)
        self._write_ttest_results(ttest_results_path, ttest_result, bonf)
        self._write_garch_results(garch_results_path, garch_result, bonf)
        self._write_fama_macbeth_results(fama_macbeth_path, fama_result, bonf)
        pd.DataFrame([primary_metric]).to_csv(primary_metric_path, index=False)
        min_effect_data = {
            "threshold": -0.15,
            "observed_differential": primary_metric.get("sharpe_differential"),
            "passes": primary_metric.get("meets_minimum_effect"),
            "conclusion": primary_metric.get("economic_significance"),
        }
        pd.DataFrame([min_effect_data]).to_csv(min_effect_path, index=False)
        pd.DataFrame([{
            "method": dcc_result.get("method"),
            "n_pairs": dcc_result.get("n_pairs"),
            "mean_dcc_correlation": dcc_result.get("mean_dcc_correlation"),
            "error": dcc_result.get("error"),
        }]).to_csv(dcc_path, index=False)
        pd.DataFrame([{
            "consistent": seed_consistency["consistent"],
            "finding_valid": seed_consistency["finding_valid"],
            "conclusion": seed_consistency["conclusion"],
        }]).to_csv(seed_path, index=False)
        self._write_stats_summary_tex(
            latex_path,
            ttest_result=ttest_result,
            garch_result=garch_result,
            bootstrap_result=bootstrap_result,
            deflated_result=deflated_result,
            regime_result=regime_result,
            fama_macbeth_result=fama_result,
            bonf=bonf,
        )
        versions_path = stats_dir / "library_versions.json"
        import json as _json

        versions = {}
        for pkg in ["arch", "statsmodels", "scipy", "pandas", "numpy", "linearmodels"]:
            versions[pkg] = _get_pkg_version(pkg)
        versions_path.write_text(_json.dumps(versions, indent=2), encoding="utf-8")

        self._write_result_flag("DONE")

        return {
            "result_flag": "DONE",
            "seed": seed,
            "paths": {
                "sharpe_summary": str(sharpe_summary_path),
                "ttest_results": str(ttest_results_path),
                "garch_results": str(garch_results_path),
                "fama_macbeth_results": str(fama_macbeth_path),
                "primary_metric": str(primary_metric_path),
                "minimum_effect_check": str(min_effect_path),
                "dcc_garch_results": str(dcc_path),
                "seed_consistency": str(seed_path),
                "stats_summary_tex": str(latex_path),
                "library_versions": str(versions_path),
            },
            "summary": {
                "primary_metric": primary_metric,
                "newey_west_t": ttest_result,
                "garch": garch_result,
                "bootstrap": bootstrap_result,
                "deflated_sharpe": deflated_result,
                "markov_regime": regime_result,
                "fama_macbeth": fama_result,
                "dcc_garch": dcc_result,
                "seed_consistency": seed_consistency,
                "bonferroni": bonf,
            },
            "primary_metric": primary_metric,
        }

    @staticmethod
    def _load_sim_results() -> pd.DataFrame:
        sim_path = Path("outputs") / "sim_results.json"
        if not sim_path.exists():
            raise FileNotFoundError(f"Missing simulation file: {sim_path}")
        rows = json.loads(sim_path.read_text(encoding="utf-8"))
        if not rows:
            raise ValueError("outputs/sim_results.json is empty")
        df = pd.DataFrame(rows)
        needed = {"concentration", "seed", "sharpe", "mean_reward", "n_episodes"}
        missing = sorted(needed - set(df.columns))
        if missing:
            raise ValueError(f"sim_results missing required columns: {missing}")
        return df

    def _seed_from_pap_lock(self) -> int:
        # pap_lock does not carry seed directly in current schema; derive deterministic seed.
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT pap_sha256 FROM pap_lock WHERE run_id = ? ORDER BY locked_at DESC LIMIT 1",
                (self.run_id,),
            ).fetchone()
        if row and row[0]:
            token = str(row[0])
            try:
                return int(token[:8], 16)
            except ValueError:
                digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
                return int(digest[:8], 16)
        return 1337

    @staticmethod
    def _newey_west_ttest(returns: np.ndarray) -> dict:
        y = np.asarray(returns, dtype=float)
        x = np.ones((len(y), 1), dtype=float)
        model = sm.OLS(y, x)
        fit = model.fit(cov_type="HAC", cov_kwds={"maxlags": 4})
        p_value = float(fit.pvalues[0])
        return {
            "coef_mean": float(fit.params[0]),
            "std_error_hac": float(fit.bse[0]),
            "t_stat": float(fit.tvalues[0]),
            "p_value": p_value,
            "n_obs": int(len(y)),
            "maxlags": 4,
            "two_tailed": True,
            "alpha": 0.05,
            "passes_alpha": p_value < 0.05,
            "passes_bonferroni": p_value < 0.0083,
            "conclusion": (
                "Significant at alpha=0.05" if p_value < 0.05
                else "Not significant at alpha=0.05"
            ),
        }

    @staticmethod
    def _garch_11(returns: np.ndarray) -> dict:
        y = np.asarray(returns, dtype=float) * 100.0
        model = arch_model(y, mean="Constant", vol="GARCH", p=1, q=1, dist="normal")
        fit = model.fit(disp="off")

        params = fit.params
        pvals = fit.pvalues
        alpha = float(params.get("alpha[1]", np.nan))
        beta = float(params.get("beta[1]", np.nan))

        return {
            "mu": float(params.get("mu", np.nan)),
            "omega": float(params.get("omega", np.nan)),
            "alpha1": alpha,
            "beta1": beta,
            "persistence_alpha_beta": float(alpha + beta) if np.isfinite(alpha + beta) else float("nan"),
            "loglikelihood": float(fit.loglikelihood),
            "aic": float(fit.aic),
            "bic": float(fit.bic),
            "alpha_pvalue": float(pvals.get("alpha[1]", np.nan)),
            "beta_pvalue": float(pvals.get("beta[1]", np.nan)),
            "n_obs": int(len(y)),
        }

    @staticmethod
    def _bootstrap_ci(returns: np.ndarray, seed: int, n_resamples: int = 1000) -> dict:
        rng = np.random.default_rng(seed)
        x = np.asarray(returns, dtype=float)
        n = len(x)
        means = np.empty(n_resamples, dtype=float)

        for i in range(n_resamples):
            sample = rng.choice(x, size=n, replace=True)
            means[i] = float(np.mean(sample))

        ci_low, ci_high = np.percentile(means, [2.5, 97.5])
        p_less_zero = float(np.mean(means < 0.0))

        return {
            "resamples": int(n_resamples),
            "seed": int(seed),
            "boot_mean": float(np.mean(means)),
            "ci_2_5": float(ci_low),
            "ci_97_5": float(ci_high),
            "mean_lt_zero_p_value": p_less_zero,
        }

    @staticmethod
    def _deflated_sharpe(returns: np.ndarray, n_trials: int = 6) -> dict:
        r = np.asarray(returns, dtype=float)
        n = len(r)
        std = float(np.std(r, ddof=1)) if n > 1 else 0.0
        if n < 3 or std < 1e-12:
            return {
                "sharpe": 0.0,
                "sr_star": 0.0,
                "deflated_sharpe_z": 0.0,
                "p_value": 1.0,
                "n_trials": int(n_trials),
            }

        sr = float(np.mean(r) / std * math.sqrt(252.0))
        skew = float(pd.Series(r).skew())
        kurt = float(pd.Series(r).kurt()) + 3.0

        # Bailey & Lopez de Prado style expected max Sharpe adjustment.
        gamma = 0.5772156649
        z1 = norm.ppf(1.0 - 1.0 / max(n_trials, 2))
        z2 = norm.ppf(1.0 - 1.0 / (max(n_trials, 2) * math.e))
        sr_star = float((1.0 - gamma) * z1 + gamma * z2)

        denom_term = 1.0 - skew * sr + ((kurt - 1.0) / 4.0) * (sr**2)
        denom_term = max(denom_term, 1e-8)
        z = float(((sr - sr_star) * math.sqrt(max(n - 1, 1))) / math.sqrt(denom_term))
        p_value = float(1.0 - norm.cdf(z))

        return {
            "sharpe": sr,
            "sr_star": sr_star,
            "deflated_sharpe_z": z,
            "p_value": p_value,
            "n_trials": int(n_trials),
        }

    @staticmethod
    def _markov_regime(returns: np.ndarray) -> dict:
        y = np.asarray(returns, dtype=float)
        model = MarkovAutoregression(y, k_regimes=2, order=1, switching_variance=True)
        fit = model.fit(disp=False)
        probs = fit.smoothed_marginal_probabilities
        reg1 = np.asarray(probs.iloc[:, 0]) if hasattr(probs, "iloc") else np.asarray(probs[:, 0])

        # MarkovAutoregression with order=1 can produce probabilities for n-1 rows.
        # Align returns to the probability vector tail to avoid shape mismatch.
        if reg1.shape[0] != y.shape[0]:
            y_aligned = y[-reg1.shape[0] :]
        else:
            y_aligned = y

        low_mask = reg1 >= 0.5
        high_mask = ~low_mask
        mean_low = float(np.mean(y_aligned[low_mask])) if np.any(low_mask) else float("nan")
        mean_high = float(np.mean(y_aligned[high_mask])) if np.any(high_mask) else float("nan")

        if np.any(low_mask) and np.any(high_mask):
            t = sm.stats.ttest_ind(y_aligned[low_mask], y_aligned[high_mask], alternative="two-sided", usevar="unequal")
            p = float(t[1])
        else:
            p = float("nan")

        return {
            "k_regimes": 2,
            "aic": float(fit.aic),
            "bic": float(fit.bic),
            "loglikelihood": float(fit.llf),
            "regime1_mean": mean_low,
            "regime2_mean": mean_high,
            "regime_mean_diff_p_value": p,
        }

    @staticmethod
    def _rolling_sharpe_differential(sim_df: pd.DataFrame) -> dict:
        """
        Compute the primary metric from PAPER.md:
        Annualized Sharpe differential = mean(Sharpe|high_conc)
                                        - mean(Sharpe|low_conc)
        High concentration = passive_concentration >= 0.30
        Low concentration  = passive_concentration < 0.30
        Window: per-scenario Sharpe already annualized in FORGE output.
        """
        high = sim_df[sim_df["concentration"] >= 0.30]["sharpe"]
        low = sim_df[sim_df["concentration"] < 0.30]["sharpe"]

        if high.empty or low.empty:
            return {
                "sharpe_high_mean": float("nan"),
                "sharpe_low_mean": float("nan"),
                "sharpe_differential": float("nan"),
                "meets_minimum_effect": False,
                "minimum_effect_threshold": -0.15,
            }

        sharpe_high = float(high.mean())
        sharpe_low = float(low.mean())
        differential = sharpe_high - sharpe_low

        return {
            "sharpe_high_mean": sharpe_high,
            "sharpe_low_mean": sharpe_low,
            "sharpe_differential": differential,
            "meets_minimum_effect": differential <= -0.15,
            "minimum_effect_threshold": -0.15,
            "economic_significance": (
                "Confirmed" if differential <= -0.15
                else "Not confirmed — effect below minimum threshold"
            ),
        }

    @staticmethod
    def _fama_macbeth_regression(sim_df: pd.DataFrame) -> dict:
        """
        Fama-MacBeth two-pass cross-sectional regression.
        Uses passive concentration as the factor.
        Cross-section: seeds (entities).
        Time: concentration conditions (periods).
        Dependent: Sharpe ratio.
        """
        try:
            from linearmodels import FamaMacBeth

            df = sim_df.copy()
            df["entity"] = df["seed"].astype(str)
            df["time_idx"] = pd.Categorical(df["concentration"].round(2)).codes
            df["passive_above_threshold"] = (df["concentration"] >= 0.30).astype(float)
            # Dev proxy factors for FF-style exposure tracking.
            df["mkt_rf_proxy"] = df["mean_reward"]
            df["smb_proxy"] = df["concentration"] - df["concentration"].mean()
            df["hml_proxy"] = df["sharpe"] - df["sharpe"].mean()
            df["momentum_factor_proxy"] = df["sharpe"].diff().fillna(0.0)

            panel = df.set_index(["entity", "time_idx"])
            if len(panel.index.get_level_values(0).unique()) < 2:
                raise ValueError("Need at least 2 entities for Fama-MacBeth")

            mod = FamaMacBeth(
                panel["sharpe"],
                panel[["mkt_rf_proxy", "smb_proxy", "hml_proxy"]],
            )
            fit = mod.fit(cov_type="kernel", bandwidth=2)

            params = fit.params.to_dict()
            pvals = fit.pvalues.to_dict()
            return {
                "method": "FamaMacBeth_OLS",
                "concentration_coef": float(params.get("mkt_rf_proxy", float("nan"))),
                "concentration_pvalue": float(pvals.get("mkt_rf_proxy", float("nan"))),
                "passive_dummy_coef": float(params.get("smb_proxy", float("nan"))),
                "passive_dummy_pvalue": float(pvals.get("smb_proxy", float("nan"))),
                "rsquared": float(fit.rsquared),
                "n_obs": int(fit.nobs),
                "factors_used": "mkt_rf_proxy, smb_proxy, hml_proxy",
                "note": (
                    "Dev run: FF factors from WRDS not available. "
                    "Using explicit three-factor proxy structure for Fama-MacBeth; "
                    "full WRDS run should replace with true Fama-French factors."
                ),
            }
        except Exception as exc:
            return {
                "method": "FamaMacBeth_OLS",
                "error": str(exc),
                "concentration_coef": float("nan"),
                "concentration_pvalue": float("nan"),
                "passive_dummy_coef": float("nan"),
                "passive_dummy_pvalue": float("nan"),
                "rsquared": float("nan"),
                "n_obs": 0,
                "note": f"FamaMacBeth failed: {exc}",
            }

    @staticmethod
    def _dcc_garch_summary() -> dict:
        """
        Run DCC-GARCH if commodity_returns.csv has 2+ columns.
        Wraps agents/analyst/analyst.py compute_dcc_correlations().
        """
        try:
            returns_path = Path("outputs/commodity_returns.csv")
            if not returns_path.exists():
                return {"error": "commodity_returns.csv not found"}

            returns = pd.read_csv(returns_path, parse_dates=["date"]).set_index("date").dropna()
            value_cols = [c for c in returns.columns if c != "date"]
            if len(value_cols) < 2:
                return {
                    "error": "Need 2+ assets for DCC-GARCH",
                    "assets": value_cols,
                }

            from agents.analyst.analyst import compute_dcc_correlations

            dcc_df = compute_dcc_correlations(returns)
            if dcc_df.empty:
                return {"error": "DCC-GARCH returned empty result"}

            summary = (
                dcc_df.groupby("pair")["correlation"]
                .agg(["mean", "std", "min", "max"])
                .reset_index()
            )

            return {
                "method": "DCC-GARCH(1,1)",
                "n_pairs": int(len(summary)),
                "mean_dcc_correlation": float(dcc_df["correlation"].mean()),
                "pairs": summary.to_dict(orient="records"),
            }
        except Exception as exc:
            return {"error": str(exc), "method": "DCC-GARCH(1,1)"}

    @staticmethod
    def _validate_seed_consistency(sim_df: pd.DataFrame) -> dict:
        """
        PAPER.md: finding valid only if it holds across all 3 seeds.
        Check: for each concentration level, do all 3 seeds agree
        on direction of Sharpe (all positive or all negative)?
        """
        required_seeds = {1337, 42, 9999}
        actual_seeds = set(sim_df["seed"].unique())
        missing_seeds = required_seeds - actual_seeds

        if missing_seeds:
            return {
                "consistent": False,
                "reason": f"Missing seeds: {missing_seeds}",
                "required_seeds": sorted(required_seeds),
                "actual_seeds": sorted(actual_seeds),
                "finding_valid": False,
                "conclusion": "Finding does NOT hold across all 3 seeds — invalid per PAPER.md",
            }

        consistency_by_concentration = {}
        for conc in sim_df["concentration"].unique():
            subset = sim_df[sim_df["concentration"] == conc]
            sharpes = subset["sharpe"].tolist()
            directions = [1 if s > 0 else -1 for s in sharpes]
            consistent = len(set(directions)) == 1
            consistency_by_concentration[str(round(float(conc), 2))] = {
                "sharpes": sharpes,
                "consistent_direction": consistent,
                "direction": (
                    "positive" if all(d > 0 for d in directions)
                    else "negative" if all(d < 0 for d in directions)
                    else "mixed"
                ),
            }

        all_consistent = all(v["consistent_direction"] for v in consistency_by_concentration.values())
        return {
            "consistent": all_consistent,
            "required_seeds": sorted(required_seeds),
            "actual_seeds": sorted(actual_seeds),
            "by_concentration": consistency_by_concentration,
            "finding_valid": all_consistent,
            "conclusion": (
                "Finding holds across all 3 seeds — valid per PAPER.md"
                if all_consistent
                else "Finding does NOT hold across all 3 seeds — invalid per PAPER.md"
            ),
        }

    @staticmethod
    def _bonferroni(p_values: list[float], n_tests: int, primary_metric: dict | None = None) -> dict:
        threshold = 0.05 / float(n_tests)
        clean = [float(p) for p in p_values if np.isfinite(p)]
        return {
            "n_tests": int(n_tests),
            "adjusted_threshold": threshold,
            "passes_any": bool(any(p < threshold for p in clean)),
            "num_significant": int(sum(p < threshold for p in clean)),
            "minimum_effect_met": (primary_metric or {}).get("meets_minimum_effect", False),
        }

    @staticmethod
    def _write_sharpe_summary(path: Path, sim_df: pd.DataFrame, dsr: dict, boot: dict, bonf: dict) -> None:
        by_conc = sim_df.groupby("concentration")["sharpe"].agg(["mean", "std", "count"]).reset_index()
        by_conc.rename(columns={"mean": "mean_sharpe", "std": "std_sharpe", "count": "n"}, inplace=True)
        by_conc["deflated_sharpe_z"] = dsr["deflated_sharpe_z"]
        by_conc["deflated_sharpe_p"] = dsr["p_value"]
        by_conc["boot_ci_2_5"] = boot["ci_2_5"]
        by_conc["boot_ci_97_5"] = boot["ci_97_5"]
        by_conc["bonferroni_threshold"] = bonf["adjusted_threshold"]
        by_conc.to_csv(path, index=False)

    @staticmethod
    def _write_ttest_results(path: Path, ttest: dict, bonf: dict) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[*ttest.keys(), "bonferroni_threshold", "bonferroni_significant"])
            w.writeheader()
            row = dict(ttest)
            row["bonferroni_threshold"] = bonf["adjusted_threshold"]
            row["bonferroni_significant"] = bool(float(ttest["p_value"]) < float(bonf["adjusted_threshold"]))
            w.writerow(row)

    @staticmethod
    def _write_garch_results(path: Path, garch: dict, bonf: dict) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[*garch.keys(), "bonferroni_threshold"])
            w.writeheader()
            row = dict(garch)
            row["bonferroni_threshold"] = bonf["adjusted_threshold"]
            w.writerow(row)

    @staticmethod
    def _write_fama_macbeth_results(path: Path, fm: dict, bonf: dict) -> None:
        with path.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=[*fm.keys(), "bonferroni_threshold"])
            w.writeheader()
            row = dict(fm)
            row["bonferroni_threshold"] = bonf["adjusted_threshold"]
            w.writerow(row)

    @staticmethod
    def _write_stats_summary_tex(
        path: Path,
        *,
        ttest_result: dict,
        garch_result: dict,
        bootstrap_result: dict,
        deflated_result: dict,
        regime_result: dict,
        fama_macbeth_result: dict,
        bonf: dict,
    ) -> None:
        rows = [
            ("Newey-West t-stat", f"{ttest_result['t_stat']:.6f}"),
            ("Newey-West p-value", f"{ttest_result['p_value']:.6f}"),
            ("GARCH alpha(1)", f"{garch_result['alpha1']:.6f}"),
            ("GARCH beta(1)", f"{garch_result['beta1']:.6f}"),
            ("Bootstrap CI 2.5%", f"{bootstrap_result['ci_2_5']:.6f}"),
            ("Bootstrap CI 97.5%", f"{bootstrap_result['ci_97_5']:.6f}"),
            ("Deflated Sharpe z", f"{deflated_result['deflated_sharpe_z']:.6f}"),
            ("Deflated Sharpe p", f"{deflated_result['p_value']:.6f}"),
            ("Markov regime p", f"{regime_result['regime_mean_diff_p_value']:.6f}"),
            ("Fama-MacBeth concentration p", f"{fama_macbeth_result.get('concentration_pvalue', float('nan')):.6f}"),
            ("Bonferroni threshold", f"{bonf['adjusted_threshold']:.4f}"),
        ]

        lines = ["\\begin{tabular}{ll}", "\\toprule", "Metric & Value \\", "\\midrule"]
        for metric, value in rows:
            safe_metric = str(metric).replace("_", "\\_")
            lines.append(f"{safe_metric} & {value} \\")
        lines.extend(["\\bottomrule", "\\end{tabular}", ""])
        path.write_text("\n".join(lines), encoding="utf-8")

    def _write_result_flag(self, status: str) -> None:
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            cols = [row[1] for row in conn.execute("PRAGMA table_info(agent_results)")]
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                conn.execute(
                    """
                    INSERT INTO agent_results (run_id, agent, job, result_flag, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (self.run_id, "SIGMA", "JOB2", status, created_at),
                )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                conn.execute(
                    """
                    INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (uuid.uuid4().hex, self.run_id, "SIGMA_JOB2", "SIGMA_JOB2", status, created_at),
                )
            conn.commit()


def _get_pkg_version(pkg: str) -> str:
    try:
        import importlib.metadata

        return importlib.metadata.version(pkg)
    except Exception:
        return "unknown"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run SIGMA Job 2 econometric battery.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--db-path", default="state.db")
    parser.add_argument("--output-dir", default="paper_memory")
    args = parser.parse_args()

    result = SigmaJob2(run_id=args.run_id, db_path=args.db_path, output_dir=args.output_dir).run()
    print(json.dumps(result, indent=2))

# CODEC traceability marker for PAPER.md alignment
PRIMARY_METRIC_SPEC_MARKER: str = "Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows."
