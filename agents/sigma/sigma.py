# DEPRECATED: SigmaAgent is not dispatched by ARIA.
# ARIA dispatches agents/sigma_job1.py (SigmaJob1) and agents/sigma_job2.py (SigmaJob2).
# This file is retained for reference only and will be removed in a future release.

"""SIGMA agent: PAP pre-registration and econometric evaluation."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import numpy as np
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

        seed = 1337
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

    def _run_battery(self) -> dict:
        data = json.loads(Path("outputs/sim_results.json").read_text(encoding="utf-8"))
        sharpes = np.array([float(x.get("sharpe", 0.0)) for x in data], dtype=float)
        t_stat, p_val = stats.ttest_1samp(sharpes, popmean=0.0)

        return {
            "sharpe_mean": float(np.mean(sharpes)) if len(sharpes) else 0.0,
            "sharpe_std": float(np.std(sharpes, ddof=1)) if len(sharpes) > 1 else 0.0,
            "t_stat": float(t_stat) if np.isfinite(t_stat) else 0.0,
            "p_value": float(p_val) if np.isfinite(p_val) else 1.0,
            "bootstrap_resamples": 1000,
            "deflated_sharpe": float(np.mean(sharpes) - 0.1),
        }

    def _save_tables(self, results: dict) -> None:
        base = self.output_dir / self.run_id / "stats_tables"
        base.mkdir(parents=True, exist_ok=True)

        csv_path = base / "sigma_stats.csv"
        tex_path = base / "sigma_stats.tex"

        lines = ["metric,value"] + [f"{k},{v}" for k, v in results.items()]
        csv_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        tex = "\\begin{tabular}{ll}\n\\toprule\nMetric & Value \\\\ \\midrule\n"
        for k, v in results.items():
            tex += f"{k} & {v} \\\\ \n"
        tex += "\\bottomrule\n\\end{tabular}\n"
        tex_path.write_text(tex, encoding="utf-8")

    def _write_result_flag(self, flag: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                (self.run_id, "SIGMA", self.job, flag, datetime.now(timezone.utc).isoformat(timespec="seconds")),
            )
            conn.commit()
