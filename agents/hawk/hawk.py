"""HAWK agent: programmatic research-quality reviewer (pre-QUILL gate)."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class HawkAgent:
    def __init__(
        self,
        run_id: str,
        db_path: str = "state.db",
        output_dir: str = "paper_memory",
        llm_client=None,
    ) -> None:
        self.run_id = run_id
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.llm_client = llm_client

    def run(self, revision_number: int = 1) -> dict[str, Any]:
        _ = revision_number  # retained for interface compatibility
        context = self._load_context()
        review = self._programmatic_review(context)

        out_dir = self.output_dir / self.run_id
        out_dir.mkdir(parents=True, exist_ok=True)

        next_rev = self._next_revision_number(out_dir)
        routing_path = out_dir / f"hawk_routing_v{next_rev}.json"
        review_path = out_dir / f"hawk_review_v{next_rev}.md"

        routing_path.write_text(json.dumps(review, indent=2), encoding="utf-8")
        review_path.write_text(self._render_markdown(review), encoding="utf-8")

        self._write_result_flag(review["result_flag"])

        return {
            "result_flag": review["result_flag"],
            "approved_for_quill": review["approved_for_quill"],
            "routing": review,
            "routing_path": str(routing_path),
            "report_path": str(review_path),
            "mandatory_items": review.get("mandatory_items", []),
        }

    def _programmatic_review(self, context: dict[str, Any]) -> dict[str, Any]:
        mandatory_items: list[dict[str, Any]] = []

        hypothesis = self._extract_hypothesis(context.get("pap_text", ""))
        expected_negative = self._hypothesis_expects_negative(hypothesis)

        primary = context.get("primary_metric", {})
        sharpe_diff = self._to_float(primary.get("sharpe_differential"))
        meets_min_effect = self._to_bool(primary.get("meets_minimum_effect"))

        # CHECK 1 — Hypothesis fidelity
        if expected_negative and sharpe_diff is not None and sharpe_diff > 0:
            mandatory_items.append(
                self._item(
                    check="Hypothesis fidelity",
                    finding=f"Hypothesis implies negative differential, observed differential={sharpe_diff:.6f} (positive).",
                    issue="Observed direction contradicts pre-registered hypothesis direction.",
                    action="Re-run FORGE or revise model specification to test directional mechanism; do not claim confirmatory support.",
                    routes_to="FORGE",
                    blocking=True,
                )
            )

        # CHECK 2 — Statistical significance
        ttest = context.get("ttest", {})
        p_val = self._to_float(ttest.get("p_value"))
        bonf = self._to_float(ttest.get("bonferroni_threshold"))
        passes_bonf = bool(p_val is not None and bonf is not None and p_val < bonf)
        if not passes_bonf:
            mandatory_items.append(
                self._item(
                    check="Statistical significance",
                    finding=f"p_value={self._fmt(p_val)}, bonferroni_threshold={self._fmt(bonf)}.",
                    issue="Finding does not clear Bonferroni threshold; suggestive but not confirmatory.",
                    action="Disclose non-confirmatory status in findings and avoid confirmatory language.",
                    routes_to="SIGMA",
                    blocking=False,
                )
            )

        # CHECK 3 — Seed consistency
        seed = context.get("seed_consistency", {})
        seed_consistent = self._to_bool(seed.get("consistent"))
        if not seed_consistent:
            mandatory_items.append(
                self._item(
                    check="Seed consistency",
                    finding=f"consistent={seed.get('consistent')}.",
                    issue="Mixed directional evidence across seeds.",
                    action="Increase seed count and/or report findings as exploratory only.",
                    routes_to="FORGE",
                    blocking=False,
                )
            )

        # CHECK 4 — CODEC mismatch
        codec_text = context.get("codec_mismatch_text", "")
        codec_fail_items = self._extract_codec_fail_items(codec_text)
        codec_clean = len(codec_fail_items) == 0
        if not codec_clean:
            mandatory_items.append(
                self._item(
                    check="CODEC mismatch",
                    finding="; ".join(codec_fail_items[:5]) or "CODEC report contains FAIL items.",
                    issue="CODEC audit contains FAIL conditions.",
                    action="Run FIXER and resolve all CODEC FAIL mismatches before manuscript generation.",
                    routes_to="FIXER",
                    blocking=True,
                )
            )

        # CHECK 5 — Minimum effect size
        if not meets_min_effect:
            mandatory_items.append(
                self._item(
                    check="Minimum effect size",
                    finding=f"meets_minimum_effect={primary.get('meets_minimum_effect')} with sharpe_differential={self._fmt(sharpe_diff)}.",
                    issue="Finding does not meet pre-registered minimum effect threshold.",
                    action="Route to FORGE for stronger simulation evidence or report null economic significance.",
                    routes_to="FORGE",
                    blocking=True,
                )
            )

        # CHECK 6 — Sample size adequacy
        n_episodes = context.get("n_episodes", 0)
        if n_episodes < 10000:
            mandatory_items.append(
                self._item(
                    check="Sample size adequacy",
                    finding=f"n_episodes={n_episodes}.",
                    issue="Simulation underpowered for publication-grade inference.",
                    action="Run n_episodes >= 500000 before publication claims.",
                    routes_to="FORGE",
                    blocking=False,
                )
            )

        hard_blocks = [m for m in mandatory_items if m.get("blocking")]
        approved_for_quill = codec_clean and meets_min_effect and len(hard_blocks) == 0

        result_flag = "APPROVED" if approved_for_quill else "REVISION_REQUESTED"

        review = {
            "result_flag": result_flag,
            "approved_for_quill": approved_for_quill,
            "mandatory_items": mandatory_items,
            "research_summary": {
                "hypothesis": hypothesis,
                "primary_result": f"Sharpe differential = {self._fmt(sharpe_diff)} ({'negative' if (sharpe_diff is not None and sharpe_diff < 0) else 'positive/non-negative'})",
                "p_value": self._fmt(p_val),
                "bonferroni_threshold": self._fmt(bonf),
                "passes_bonferroni": passes_bonf,
                "seed_consistent": seed_consistent,
                "codec_clean": codec_clean,
                "n_episodes": n_episodes,
                "production_ready": bool(approved_for_quill and n_episodes >= 500000 and passes_bonf and seed_consistent),
            },
        }
        return review

    @staticmethod
    def _item(
        *,
        check: str,
        finding: str,
        issue: str,
        action: str,
        routes_to: str,
        blocking: bool,
    ) -> dict[str, Any]:
        return {
            "check": check,
            "finding": finding,
            "issue": issue,
            "action": action,
            "routes_to": routes_to,
            "blocking": blocking,
        }

    def _load_context(self) -> dict[str, Any]:
        run_dir = self.output_dir / self.run_id
        pap_path = run_dir / "pap.md"
        codec_path = self._first_existing(run_dir / "codec_mismatch.md", run_dir / "codecmismatch.md")
        stats_dir = self._first_existing(run_dir / "stats_tables", run_dir / "statstables")

        stats_map: dict[str, list[dict[str, str]]] = {}
        if stats_dir and stats_dir.exists():
            for csv_file in sorted(stats_dir.glob("*.csv")):
                stats_map[csv_file.name] = self._read_csv_dicts(csv_file)

        # seed consistency can appear in run root or stats_tables
        seed_rows = []
        for candidate in [run_dir / "seed_consistency.csv", (stats_dir / "seed_consistency.csv") if stats_dir else None]:
            if candidate and candidate.exists():
                seed_rows = self._read_csv_dicts(candidate)
                if seed_rows:
                    break

        sim_path = Path("outputs") / "sim_results.json"
        sim_data = []
        if sim_path.exists():
            try:
                sim_data = json.loads(sim_path.read_text(encoding="utf-8"))
                if not isinstance(sim_data, list):
                    sim_data = []
            except Exception:
                sim_data = []

        episodes = 0
        if sim_data:
            vals = [int(x.get("n_episodes", 0)) for x in sim_data if isinstance(x, dict)]
            episodes = max(vals) if vals else 0

        return {
            "pap_text": pap_path.read_text(encoding="utf-8", errors="ignore") if pap_path.exists() else "",
            "codec_mismatch_text": codec_path.read_text(encoding="utf-8", errors="ignore") if codec_path else "",
            "primary_metric": (stats_map.get("primary_metric.csv") or [{}])[0],
            "ttest": (stats_map.get("ttest_results.csv") or [{}])[0],
            "seed_consistency": seed_rows[0] if seed_rows else {},
            "n_episodes": episodes,
            "stats_map": stats_map,
        }

    @staticmethod
    def _read_csv_dicts(path: Path) -> list[dict[str, str]]:
        try:
            with path.open("r", encoding="utf-8", newline="") as f:
                return list(csv.DictReader(f))
        except Exception:
            return []

    @staticmethod
    def _extract_hypothesis(pap_text: str) -> str:
        if not pap_text.strip():
            return "Hypothesis not found in pap.md"
        m = re.search(r'"claim_text"\s*:\s*"([^"]+)"', pap_text)
        if m:
            return m.group(1).strip()
        # fallback: first hypothesis-like line
        for line in pap_text.splitlines():
            line_l = line.lower().strip()
            if "hypothesis" in line_l or "claim" in line_l:
                return line.strip()
        return pap_text.strip()[:300]

    @staticmethod
    def _hypothesis_expects_negative(hypothesis: str) -> bool:
        h = hypothesis.lower()
        if any(k in h for k in ["reduce", "decrease", "lower", "negative", "decline", "attenuat", "weaker"]):
            return True
        if any(k in h for k in ["increase", "higher", "positive", "rise", "strengthen"]):
            return False
        return True

    @staticmethod
    def _extract_codec_fail_items(codec_text: str) -> list[str]:
        if not codec_text.strip():
            return ["codec_mismatch.md missing"]
        out: list[str] = []
        verdict_fail = re.search(r"verdict\s*:\s*FAIL", codec_text, flags=re.I)
        if verdict_fail:
            out.append("verdict: FAIL")
        for line in codec_text.splitlines():
            l = line.strip()
            if not l:
                continue
            if l.lower().startswith("issue:"):
                out.append(l)
            if "fatal" in l.lower() or "mismatch" in l.lower() and l.startswith("-"):
                out.append(l)
        # dedupe preserve order
        seen = set()
        uniq = []
        for x in out:
            if x in seen:
                continue
            seen.add(x)
            uniq.append(x)
        return uniq

    @staticmethod
    def _to_float(v: Any) -> float | None:
        try:
            if v is None or str(v).strip() == "":
                return None
            return float(v)
        except Exception:
            return None

    @staticmethod
    def _to_bool(v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        return s in {"1", "true", "yes", "y"}

    @staticmethod
    def _fmt(v: float | None) -> str:
        if v is None:
            return "NA"
        return f"{v:.6f}"

    @staticmethod
    def _next_revision_number(run_dir: Path) -> int:
        nums = []
        for p in run_dir.glob("hawk_routing_v*.json"):
            m = re.search(r"_v(\d+)\.json$", p.name)
            if m:
                nums.append(int(m.group(1)))
        return (max(nums) + 1) if nums else 1

    @staticmethod
    def _render_markdown(review: dict[str, Any]) -> str:
        rs = review.get("research_summary", {})
        lines = [
            "# HAWK Research Review",
            "",
            f"result_flag: {review.get('result_flag')}",
            f"approved_for_quill: {review.get('approved_for_quill')}",
            "",
            "## Research Summary",
            f"- hypothesis: {rs.get('hypothesis')}",
            f"- primary_result: {rs.get('primary_result')}",
            f"- p_value: {rs.get('p_value')}",
            f"- bonferroni_threshold: {rs.get('bonferroni_threshold')}",
            f"- passes_bonferroni: {rs.get('passes_bonferroni')}",
            f"- seed_consistent: {rs.get('seed_consistent')}",
            f"- codec_clean: {rs.get('codec_clean')}",
            f"- n_episodes: {rs.get('n_episodes')}",
            f"- production_ready: {rs.get('production_ready')}",
            "",
            "## Mandatory Items",
        ]
        items = review.get("mandatory_items", [])
        if not items:
            lines.append("- none")
        for item in items:
            lines.extend(
                [
                    f"- [{item.get('check')}] blocking={item.get('blocking')} route={item.get('routes_to')}",
                    f"  finding: {item.get('finding')}",
                    f"  issue: {item.get('issue')}",
                    f"  action: {item.get('action')}",
                ]
            )
        return "\n".join(lines) + "\n"

    def _write_result_flag(self, flag: str) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with sqlite3.connect(self.db_path) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(agent_results)")}
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results "
                    "(run_id, agent, job, result_flag, created_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (self.run_id, "HAWK", None, flag, now),
                )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results "
                    "(result_id, run_id, phase_name, agent_name, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (uuid.uuid4().hex, self.run_id, "HAWK", "HAWK", flag, now),
                )
            conn.commit()

    @staticmethod
    def _first_existing(*candidates: Path) -> Path | None:
        for p in candidates:
            if p and p.exists():
                return p
        return None
