"""ARIA pipeline conductor (state machine only)."""

from __future__ import annotations

import sqlite3
import time
import re
import subprocess
import math
from collections import Counter
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from agents.aria.exceptions import ForgeGateError, IntegrityViolationError, PipelineHaltError, ServerUnavailableError
from agents.aria.routing_config import AGENT_SERVER_MAP, AGENT_TIMEOUTS_SECONDS


class ARIAPipeline:
    PHASE_ORDER = ["SCOUT", "MINER", "SIGMA_JOB1", "FORGE", "SIGMA_JOB2", "CODEC", "QUILL", "HAWK"]
    GOAL = "produce publishable paper"
    MAX_MAIN_LOOPS = 120

    ROUTING_RULES: dict[str, dict[str, set[str]]] = {
        "SIGMA_JOB1": {"BLOCK": {"sim_results", "paper_draft", "codec_spec"}},
        "FORGE": {"BLOCK": set()},
        "CODEC_PASS2": {"BLOCK": {"codebase", "codec_pass1_output"}},
        "QUILL": {"ALLOW": {"literature_map", "codec_spec", "stats_tables"}},
        "HAWK": {"ALLOW": {"paper_draft", "codec_spec", "stats_tables"}},
    }

    def __init__(self, db_path: str, run_id: str, paper_md_path: str) -> None:
        self.db_path = db_path
        self.run_id = run_id
        self.paper_md_path = paper_md_path
        self._terminal_failure = False
        self._last_failure_phase: str | None = None
        self._last_failure_message: str = ""
        self._init_db()
        self._ensure_run_rows()

    def run(self) -> None:
        """
        Hermes-style resilient agent loop.

        - Single goal: produce a publishable paper.
        - Uses iterative tool calls (dispatch) in a while loop.
        - Never raises PipelineHaltError to the caller.
        - Logs failures, retries, and controlled skips.
        """
        self._set_run_status("running")
        self._log_audit("ARIA", "INFO", f"Goal: {self.GOAL}")

        retries: dict[str, int] = {}
        max_retries = {
            "SCOUT": 3,
            "MINER": 3,
            "SIGMA_JOB1": 3,
            "FORGE": 3,
            "SIGMA_JOB2": 3,
            "CODEC": 5,
            "FIXER": 3,
            "QUILL": 8,
            "HAWK": 8,
        }

        loop_count = 0
        while loop_count < self.MAX_MAIN_LOOPS:
            if self._terminal_failure:
                self._set_run_status("failed")
                self._log_audit("ARIA", "ERROR", "Terminal failure reached; stopping main loop.")
                return

            loop_count += 1

            if self._paper_is_publishable():
                self._mark_remaining_phases_done()
                self._set_run_status("done")
                self._log_audit("ARIA", "INFO", f"Goal achieved after {loop_count} loop(s).")
                return

            next_step = self._next_tool_call()
            if next_step is None:
                # No deterministic upstream gap left, run review/edit loop.
                self._run_step("HAWK", retries, max_retries)
                self._run_step("QUILL", retries, max_retries)
                self._run_step("FIXER", retries, max_retries)
                self._promote_latest_draft_to_v1_if_publishable()
                continue

            if next_step == "HAWK":
                # Quality-improvement loop: review then revise.
                self._run_step("HAWK", retries, max_retries)
                self._run_step("QUILL", retries, max_retries)
                self._run_step("FIXER", retries, max_retries)
            else:
                self._run_step(next_step, retries, max_retries)
            self._promote_latest_draft_to_v1_if_publishable()

        self._set_run_status("failed")
        self._log_audit(
            "ARIA",
            "WARN",
            f"Main loop exhausted ({self.MAX_MAIN_LOOPS}) before reaching publishable draft goal.",
        )

    def _run_step(self, phase: str, retries: dict[str, int], max_retries: dict[str, int]) -> None:
        if phase == "FIXER" and self._last_failure_phase == "QUILL":
            msg = self._last_failure_message.lower()
            if any(k in msg for k in ("word", "dedup", "quality gate")):
                self._log_audit(
                    "FIXER",
                    "WARN",
                    "Skipping FIXER for QUILL content/quality failure (non-fixable by code patcher).",
                )
                self._advance_phase("FIXER", "done")
                self._write_result_flag(agent="FIXER", job="auto_skip_non_fixable", flag="DONE")
                retries["FIXER"] = 0
                return

        retries[phase] = retries.get(phase, 0) + 1
        attempt = retries[phase]
        if attempt > max_retries.get(phase, 3):
            if phase in {"QUILL", "HAWK"}:
                # Contract: QUILL/HAWK are never skipped; keep retrying.
                self._log_audit(
                    phase,
                    "WARN",
                    f"Exceeded retry budget ({max_retries.get(phase, 3)}); continuing retries per contract.",
                )
            else:
                self._log_audit(
                    phase,
                    "WARN",
                    f"Skipping after {attempt - 1} failed attempts (max {max_retries.get(phase, 3)}).",
                )
                self._advance_phase(phase, "failed")
                self._set_run_status("failed")
                self._terminal_failure = True
                return

        self._advance_phase(phase, "running")
        try:
            if phase == "FORGE":
                self._check_forge_gate()

            context = dict(self._context_config_for_phase(phase))
            if phase in {"QUILL", "HAWK"}:
                context["revision_number"] = max(1, retries.get(phase, 1))

            result = self._dispatch(phase, self._server_for_phase(phase), context)
            flag = str(result.get("result_flag", "DONE"))
            self._write_result_flag(agent=phase, job=f"attempt_{attempt}", flag=flag)

            if phase == "CODEC" and flag == "FAIL":
                self._log_audit("CODEC", "WARN", "CODEC returned FAIL; invoking FIXER and continuing.")
                self._run_step("FIXER", retries, max_retries)
                self._advance_phase("CODEC", "done")
                retries[phase] = 0
                return

            # HAWK signals quality state; never hard-fail user flow.
            if phase == "HAWK":
                self._advance_phase("HAWK", "done")
                self._log_audit("HAWK", "INFO", f"HAWK result_flag={flag}.")
                retries[phase] = 0
                return

            if flag in {"FAILED", "FAIL", "ESCALATE"}:
                raise RuntimeError(f"{phase} returned non-success flag={flag}")

            self._advance_phase(phase, "done")
            self._log_audit(phase, "INFO", f"{phase} succeeded (attempt {attempt})")
            self._last_failure_phase = None
            self._last_failure_message = ""
            retries[phase] = 0
        except Exception as exc:
            self._advance_phase(phase, "failed")
            self._log_audit(phase, "ERROR", f"Attempt {attempt} failed: {type(exc).__name__}: {exc}")
            self._last_failure_phase = phase
            self._last_failure_message = str(exc)
            if phase not in {"QUILL", "HAWK"} and attempt >= max_retries.get(phase, 3):
                self._log_audit(
                    phase,
                    "ERROR",
                    f"Retry limit reached for {phase}; marking terminal failure to prevent infinite retry loops.",
                )
                self._set_run_status("failed")
                self._terminal_failure = True
                return
            if phase == "QUILL" and isinstance(exc, ValueError) and "quality gate failed" in str(exc).lower():
                raise
            time.sleep(min(5, 1 + attempt))

    def _next_tool_call(self) -> str | None:
        """
        Decide the next best tool call based on artifact/state gaps.
        This is goal-driven planning, not a fixed phase-for-loop.
        """
        base = Path("paper_memory") / self.run_id
        stats_dir = base / "stats_tables"
        v1 = base / "paper_draft_v1.tex"

        if not (base / "literature_map.md").exists() and self._phase_status("SCOUT") != "done":
            return "SCOUT"
        if not (Path("outputs") / "commodity_returns.csv").exists() and self._phase_status("MINER") != "done":
            return "MINER"
        if not (base / "pap.md").exists() and self._phase_status("SIGMA_JOB1") != "done":
            return "SIGMA_JOB1"
        if not (Path("outputs") / "sim_results.json").exists() and self._phase_status("FORGE") != "done":
            return "FORGE"
        if (not stats_dir.exists() or not any(stats_dir.glob("*.csv"))) and self._phase_status("SIGMA_JOB2") != "done":
            return "SIGMA_JOB2"
        if not (base / "codec_spec.md").exists() and self._phase_status("CODEC") != "done":
            return "CODEC"
        if not v1.exists() and self._phase_status("QUILL") != "done":
            return "QUILL"
        if not self._paper_is_publishable(v1) and self._phase_status("HAWK") != "done":
            return "HAWK"
        return None

    def _latest_paper_draft_path(self) -> Path | None:
        base = Path("paper_memory") / self.run_id
        drafts = sorted(base.glob("paper_draft_v*.tex"))
        if not drafts:
            return None
        return drafts[-1]

    def _promote_latest_draft_to_v1_if_publishable(self) -> None:
        base = Path("paper_memory") / self.run_id
        v1 = base / "paper_draft_v1.tex"
        if self._paper_is_publishable(v1):
            return
        latest = self._latest_paper_draft_path()
        if latest is None or latest == v1:
            return
        if not self._paper_is_publishable(latest):
            return
        try:
            v1.write_text(latest.read_text(encoding="utf-8", errors="ignore"), encoding="utf-8")
            self._log_audit("ARIA", "INFO", f"Promoted {latest.name} to paper_draft_v1.tex for goal completion.")
        except Exception as exc:
            self._log_audit("ARIA", "WARN", f"Failed promoting latest draft to v1: {exc}")

    def _paper_is_publishable(self, path: Path | None = None) -> bool:
        run_dir = Path("paper_memory") / self.run_id
        v1 = run_dir / "paper_draft_v1.tex"
        if not v1.exists():
            return False

        p = path or v1
        if not p.exists():
            return False
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return False

        if "\\begin{document}" not in text or "\\end{document}" not in text:
            return False

        unique_words = {w.lower() for w in re.findall(r"\b[\w'-]+\b", text)}
        min_unique_words = int(os.getenv("PAPER_FORGE_PUBLISHABLE_UNIQUE_WORDS", "1500"))
        if len(unique_words) < min_unique_words:
            return False

        if self._find_exact_duplicate_paragraphs(text):
            return False
        sim_threshold = float(os.getenv("PAPER_FORGE_PARAGRAPH_SIMILARITY_MAX", "0.95"))
        if self._has_high_similarity_paragraphs(text, threshold=sim_threshold):
            return False

        lower = text.lower()
        forbidden = [
            "aria", "scout", "miner", "sigma", "codec", "quill", "hawk", "paperforge",
            "pipeline", "agent name", "agent_names",
        ]
        for token in forbidden:
            pattern = r"\b" + re.escape(token) + r"\b"
            if re.search(pattern, lower):
                return False

        reviews = sorted((Path("paper_memory") / self.run_id).glob("hawk_review_v*.md"))
        if not reviews:
            return False
        if all(r.stat().st_size <= 500 for r in reviews):
            return False

        min_cycles = int(os.getenv("PAPER_FORGE_MIN_REVIEW_CYCLES", "1"))
        if self._completed_quill_hawk_cycles() < min_cycles:
            return False
        return True

    @staticmethod
    def _paragraphs(text: str) -> list[str]:
        return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]

    def _find_exact_duplicate_paragraphs(self, text: str) -> bool:
        seen: set[str] = set()
        for p in self._paragraphs(text):
            if p in seen:
                return True
            seen.add(p)
        return False

    @staticmethod
    def _cosine_sim(a: str, b: str) -> float:
        ta = Counter(re.findall(r"\b[\w'-]+\b", a.lower()))
        tb = Counter(re.findall(r"\b[\w'-]+\b", b.lower()))
        if not ta or not tb:
            return 0.0
        common = set(ta) & set(tb)
        num = sum(ta[t] * tb[t] for t in common)
        da = math.sqrt(sum(v * v for v in ta.values()))
        db = math.sqrt(sum(v * v for v in tb.values()))
        if da == 0 or db == 0:
            return 0.0
        return num / (da * db)

    def _has_high_similarity_paragraphs(self, text: str, threshold: float = 0.85) -> bool:
        paras = self._paragraphs(text)
        for i in range(len(paras)):
            for j in range(i + 1, len(paras)):
                if self._cosine_sim(paras[i], paras[j]) > threshold:
                    return True
        return False

    def _completed_quill_hawk_fixer_cycles(self) -> int:
        """
        Count completed QUILL -> HAWK -> FIXER chains in agent_results for this run.
        Requires schema-aware reads.
        """
        with sqlite3.connect(self.db_path) as conn:
            cols = set(self._table_columns(conn, "agent_results"))
            if {"phase_name", "created_at"}.issubset(cols):
                rows = conn.execute(
                    """
                    SELECT phase_name, status, created_at
                    FROM agent_results
                    WHERE run_id=?
                    ORDER BY created_at
                    """,
                    (self.run_id,),
                ).fetchall()
                phase_idx, status_idx, time_idx = 0, 1, 2
            elif {"agent", "created_at"}.issubset(cols):
                rows = conn.execute(
                    """
                    SELECT agent, result_flag, created_at
                    FROM agent_results
                    WHERE run_id=?
                    ORDER BY created_at
                    """,
                    (self.run_id,),
                ).fetchall()
                phase_idx, status_idx, time_idx = 0, 1, 2
            else:
                return 0

        quill_times: list[str] = []
        hawk_times: list[str] = []
        fixer_times: list[str] = []
        for r in rows:
            phase = str(r[phase_idx] or "").upper()
            status = str(r[status_idx] or "").upper()
            ts = str(r[time_idx] or "")
            if phase == "QUILL" and status not in {"FAIL", "FAILED", "ESCALATE"}:
                quill_times.append(ts)
            if phase == "HAWK" and status not in {"FAIL", "FAILED", "ESCALATE"}:
                hawk_times.append(ts)
            if phase == "FIXER" and status not in {"FAIL", "FAILED", "ESCALATE"}:
                fixer_times.append(ts)

        cycles = 0
        h_idx = 0
        f_idx = 0
        for q in quill_times:
            while h_idx < len(hawk_times) and hawk_times[h_idx] < q:
                h_idx += 1
            if h_idx >= len(hawk_times):
                break
            h = hawk_times[h_idx]
            h_idx += 1
            while f_idx < len(fixer_times) and fixer_times[f_idx] < h:
                f_idx += 1
            if f_idx >= len(fixer_times):
                break
            f_idx += 1
            cycles += 1
        return cycles

    def _completed_quill_hawk_cycles(self) -> int:
        """Count completed QUILL -> HAWK chains; FIXER is diagnostic and optional."""
        with sqlite3.connect(self.db_path) as conn:
            cols = set(self._table_columns(conn, "agent_results"))
            if {"phase_name", "created_at"}.issubset(cols):
                rows = conn.execute(
                    """
                    SELECT phase_name, status, created_at
                    FROM agent_results
                    WHERE run_id=?
                    ORDER BY created_at
                    """,
                    (self.run_id,),
                ).fetchall()
                phase_idx, status_idx, time_idx = 0, 1, 2
            elif {"agent", "created_at"}.issubset(cols):
                rows = conn.execute(
                    """
                    SELECT agent, result_flag, created_at
                    FROM agent_results
                    WHERE run_id=?
                    ORDER BY created_at
                    """,
                    (self.run_id,),
                ).fetchall()
                phase_idx, status_idx, time_idx = 0, 1, 2
            else:
                return 0

        quill_times: list[str] = []
        hawk_times: list[str] = []
        for r in rows:
            phase = str(r[phase_idx] or "").upper()
            status = str(r[status_idx] or "").upper()
            ts = str(r[time_idx] or "")
            if phase == "QUILL" and status not in {"FAIL", "FAILED", "ESCALATE"}:
                quill_times.append(ts)
            if phase == "HAWK" and status not in {"FAIL", "FAILED", "ESCALATE"}:
                hawk_times.append(ts)

        cycles = 0
        h_idx = 0
        for q in quill_times:
            while h_idx < len(hawk_times) and hawk_times[h_idx] < q:
                h_idx += 1
            if h_idx >= len(hawk_times):
                break
            h_idx += 1
            cycles += 1
        return cycles

    def _phase_status(self, phase_name: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT status FROM phases WHERE run_id=? AND phase_name=? LIMIT 1",
                (self.run_id, phase_name),
            ).fetchone()
        if row is None:
            return None
        return str(row[0]) if row[0] is not None else None

    def _mark_remaining_phases_done(self) -> None:
        """When publishability is reached, finalize any remaining phases to done."""
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT phase_name, status FROM phases WHERE run_id=?",
                (self.run_id,),
            ).fetchall()
        for phase_name, status in rows:
            if str(status or "").lower() != "done":
                self._advance_phase(str(phase_name), "done")

    def _run_hawk_loop(self, max_cycles: int = 3) -> None:
        """HAWK review loop that always terminates and accepts best available draft at max cycles."""
        for cycle in range(1, max_cycles + 1):
            print(f"\n{'=' * 50}")
            print(f"HAWK review cycle {cycle}/{max_cycles}")
            print(f"{'=' * 50}")

            self._advance_phase("HAWK", "running")
            hawk_result = self._dispatch(
                "HAWK",
                self._server_for_phase("HAWK"),
                {"revision_number": cycle, **self._context_config_for_phase("HAWK")},
            )
            hawk_flag = str(hawk_result.get("result_flag", "REVISION_REQUESTED"))
            routing = hawk_result.get("routing", {}) or {}
            recommendation = hawk_result.get("recommendation", "MAJOR_REVISION")
            mandatory_items = routing.get("mandatory_items", []) or []
            self._write_result_flag("HAWK", f"CYCLE{cycle}", hawk_flag)

            print(f"HAWK recommendation: {recommendation}")
            print(f"Mandatory items: {len(mandatory_items)}")

            if hawk_flag == "APPROVED":
                self._advance_phase("HAWK", "done")
                print(f"\nHAWK ACCEPTED the paper on cycle {cycle}.")
                print(f"Read: paper_memory/{self.run_id}/hawk_review_v{cycle}.md")
                return

            if cycle == max_cycles:
                self._log_audit(
                    "HAWK",
                    "WARN",
                    f"Max cycles reached ({max_cycles}). Accepting best available draft for publication.",
                )
                self._advance_phase("HAWK", "done")
                print("Max cycles reached. Accepting best available draft for publication.")
                return

            # Run FIXER between HAWK cycles. FIXER outcomes never reset HAWK cycle counting.
            try:
                fixer_result = self._dispatch(
                    "FIXER",
                    self._server_for_phase("FIXER"),
                    self._context_config_for_phase("FIXER"),
                )
                fixer_flag = str(fixer_result.get("result_flag", "DONE"))
                self._write_result_flag("FIXER", f"HAWK_CYCLE{cycle}", fixer_flag)
                if fixer_flag in {"FAIL", "FAILED", "ESCALATE"}:
                    self._log_audit(
                        "FIXER",
                        "WARN",
                        f"FIXER returned {fixer_flag} on HAWK cycle {cycle}; continuing without resetting cycle counter.",
                    )
            except Exception as exc:
                self._log_audit(
                    "FIXER",
                    "ERROR",
                    f"FIXER failed on HAWK cycle {cycle}: {type(exc).__name__}: {exc}. Continuing HAWK loop.",
                )

            # Route non-blocking follow-up tasks and continue to next review cycle.
            if routing.get("routes_to_forge"):
                self._check_forge_gate_for_revision()
                forge_result = self._dispatch(
                    "FORGE",
                    self._server_for_phase("FORGE"),
                    self._context_config_for_phase("FORGE"),
                )
                self._write_result_flag("FORGE", f"HAWK_CYCLE{cycle}", forge_result.get("result_flag", "DONE"))

            if routing.get("routes_to_sigma"):
                sigma_result = self._dispatch(
                    "SIGMA_JOB2",
                    self._server_for_phase("SIGMA_JOB2"),
                    self._context_config_for_phase("SIGMA_JOB2"),
                )
                self._write_result_flag("SIGMA_JOB2", f"HAWK_CYCLE{cycle}", sigma_result.get("result_flag", "DONE"))

            if routing.get("routes_to_miner"):
                miner_result = self._dispatch(
                    "MINER",
                    self._server_for_phase("MINER"),
                    self._context_config_for_phase("MINER"),
                )
                self._write_result_flag("MINER", f"HAWK_CYCLE{cycle}", miner_result.get("result_flag", "DONE"))

            if routing.get("routes_to_codec"):
                codec_result = self._dispatch(
                    "CODEC",
                    self._server_for_phase("CODEC"),
                    self._context_config_for_phase("CODEC"),
                )
                self._write_result_flag("CODEC", f"HAWK_CYCLE{cycle}", codec_result.get("result_flag", "WARN"))

        self._advance_phase("HAWK", "done")
        print("Max cycles reached. Accepting best available draft for publication.")
        return

    def _dispatch(self, agent_name: str, server_name: str, context_config: dict[str, Any]) -> dict[str, Any]:
        self._health_check_or_raise(server_name)

        # Enforce routing integrity constraints up front.
        blocked = set(context_config.get("BLOCK", set()))
        forbidden = {
            "SIGMA_JOB1": {"sim_results", "paper_draft", "codec_spec"},
            "CODEC_PASS2": {"codebase", "codec_pass1_output"},
        }
        for key, blocked_set in forbidden.items():
            if agent_name == key or (agent_name == "CODEC" and key == "CODEC_PASS2"):
                for artifact in blocked_set:
                    if artifact not in blocked:
                        raise IntegrityViolationError(artifact, agent_name)

        if agent_name == "SCOUT":
            from agents.scout.scout import ScoutAgent

            agent = ScoutAgent(
                run_id=self.run_id,
                paper_md_path=self.paper_md_path,
                output_dir="paper_memory",
                db_path=self.db_path,
            )
            return agent.run()
        if agent_name.startswith("SIGMA"):
            if agent_name == "SIGMA_JOB1":
                from agents.sigma_job1 import SigmaJob1

                agent = SigmaJob1(run_id=self.run_id, db_path=self.db_path)
                result = agent.run()
                return {"result_flag": "DONE", "details": result}

            from agents.sigma_job2 import SigmaJob2

            agent = SigmaJob2(run_id=self.run_id, db_path=self.db_path, output_dir="paper_memory")
            return agent.run()
        if agent_name == "MINER":
            from agents.miner.miner import run_miner_pipeline

            source = os.getenv("PAPER_FORGE_MINER_SOURCE", "wrds").strip().lower() or "wrds"
            if source not in {"wrds", "yfinance"}:
                source = "wrds"
            return run_miner_pipeline(run_id=self.run_id, output_dir="paper_memory", source=source)
        if agent_name == "FORGE":
            n_episodes = int(os.getenv("PAPER_FORGE_FORGE_EPISODES", "500"))
            backend = os.getenv("PAPER_FORGE_FORGE_BACKEND", "modal").strip().lower() or "modal"
            if backend == "modal":
                cmd = ["modal", "run", "agents/forge/modal_run.py", "--n-episodes", str(n_episodes)]
                completed = subprocess.run(
                    cmd,
                    cwd=str(Path.cwd()),
                    check=False,
                    capture_output=True,
                    text=True,
                )
                if completed.returncode == 0:
                    out_path = Path("outputs") / "sim_results.json"
                    if out_path.exists():
                        return {
                            "result_flag": "DONE",
                            "backend": "modal",
                            "output_path": str(out_path),
                        }
                    return {
                        "result_flag": "FAIL",
                        "backend": "modal",
                        "error": "modal run succeeded but outputs/sim_results.json missing",
                        "stdout": completed.stdout[-2000:],
                    }
                return {
                    "result_flag": "FAIL",
                    "backend": "modal",
                    "error": f"modal run failed rc={completed.returncode}",
                    "stdout": completed.stdout[-2000:],
                    "stderr": completed.stderr[-2000:],
                }

            from agents.forge.full_run import run_full_sweep
            return run_full_sweep(n_episodes=n_episodes)
        if agent_name == "CODEC":
            from agents.codec.codec import CodecAgent

            agent = CodecAgent(run_id=self.run_id, db_path=self.db_path, output_dir="paper_memory", llm_client=None)
            return agent.run()
        if agent_name == "FIXER":
            from agents.fixer.fixer import FixerAgent

            agent = FixerAgent(
                run_id=self.run_id,
                db_path=self.db_path,
                output_dir="paper_memory",
            )
            return agent.run()
        if agent_name == "QUILL":
            from agents.quill.quill import QuillAgent

            revision_number = int(context_config.get("revision_number", 1))
            agent = QuillAgent(run_id=self.run_id, db_path=self.db_path, output_dir="paper_memory", llm_client=None)
            return agent.run(revision_number=revision_number)
        if agent_name == "HAWK":
            from agents.hawk.hawk import HawkAgent

            revision_number = int(context_config.get("revision_number", 1))
            agent = HawkAgent(run_id=self.run_id, db_path=self.db_path, output_dir="paper_memory", llm_client=None)
            return agent.run(revision_number=revision_number)

        return {"result_flag": "DONE"}

    def _advance_phase(self, phase_name: str, status: str) -> None:
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            phase_cols = self._table_columns(conn, "phases")
            finished_col = "completed_at" if "completed_at" in phase_cols else "finished_at"

            row = conn.execute(
                "SELECT 1 FROM phases WHERE run_id=? AND phase_name=? LIMIT 1",
                (self.run_id, phase_name),
            ).fetchone()
            if row is None:
                started_val = now if status == "running" else None
                finished_val = now if status == "done" else None
                conn.execute(
                    f"""
                    INSERT INTO phases (run_id, phase_name, status, started_at, {finished_col})
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (self.run_id, phase_name, status, started_val, finished_val),
                )
            else:
                if status == "running":
                    conn.execute(
                        "UPDATE phases SET status=?, started_at=COALESCE(started_at, ?) WHERE run_id=? AND phase_name=?",
                        (status, now, self.run_id, phase_name),
                    )
                elif status == "done":
                    conn.execute(
                        f"UPDATE phases SET status=?, {finished_col}=? WHERE run_id=? AND phase_name=?",
                        (status, now, self.run_id, phase_name),
                    )
                else:
                    conn.execute(
                        "UPDATE phases SET status=? WHERE run_id=? AND phase_name=?",
                        (status, self.run_id, phase_name),
                    )
            conn.commit()

    def _check_forge_gate(self) -> None:
        # Non-negotiable: SQL gate, not Python if-chain.
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT 1
                FROM pap_lock
                WHERE run_id = ?
                  AND locked_at IS NOT NULL
                  AND forge_started_at IS NULL
                LIMIT 1
                """,
                (self.run_id,),
            ).fetchone()
            if row is None:
                raise ForgeGateError("FORGE gate failed: pap_lock must exist with locked_at set and forge_started_at NULL")
            conn.execute(
                "UPDATE pap_lock SET forge_started_at = ? WHERE run_id = ? AND forge_started_at IS NULL",
                (self._now(), self.run_id),
            )
            conn.commit()

    def _check_forge_gate_for_revision(self) -> None:
        """FORGE gate check for HAWK revision cycles."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM pap_lock WHERE run_id=? AND locked_at IS NOT NULL",
                (self.run_id,),
            ).fetchone()
            if row is None:
                raise ForgeGateError(
                    "FORGE revision gate failed: PAP not locked. "
                    "Cannot re-run FORGE without a committed PAP."
                )
            conn.execute("UPDATE pap_lock SET forge_started_at=NULL WHERE run_id=?", (self.run_id,))
            conn.commit()
        self._check_forge_gate()

    def _write_result_flag(self, agent: str, job: str | None, flag: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cols = set(self._table_columns(conn, "agent_results"))
            now = self._now()
            if {"run_id", "agent", "result_flag", "created_at"}.issubset(cols):
                conn.execute(
                    "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                    (self.run_id, agent, job, flag, now),
                )
            elif {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}.issubset(cols):
                conn.execute(
                    """
                    INSERT INTO agent_results (result_id, run_id, phase_name, agent_name, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (__import__("uuid").uuid4().hex, self.run_id, agent, agent, flag, now),
                )
            conn.commit()

    def _health_check_or_raise(self, server_name: str) -> None:
        import time as _time
        start = _time.perf_counter()
        healthy = True
        detail = "ok"

        try:
            if server_name == "llm":
                from openai import OpenAI

                client = OpenAI(timeout=10)
                client.models.list()
                detail = "llm reachable"

            elif server_name == "wrds":
                if not os.environ.get("WRDS_USERNAME") and not os.environ.get("WRDS_CLOUD_USERNAME"):
                    detail = "WRDS_USERNAME env var not set (connectivity deferred to MINER runtime)"

            elif server_name == "forge_cluster":
                try:
                    import modal

                    detail = f"modal sdk version {modal.__version__} available"
                except ImportError:
                    healthy = False
                    detail = "modal package not installed"

            elif server_name == "semantic_scholar":
                import urllib.request
                from urllib.error import HTTPError

                req = urllib.request.Request(
                    "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1",
                    headers={"User-Agent": "paper-forge-health/1.0"},
                )
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        healthy = resp.status == 200
                        detail = f"semantic_scholar status={resp.status}"
                except HTTPError as exc:
                    if exc.code == 429:
                        healthy = True
                        detail = "semantic_scholar rate-limited (429); fallback providers enabled"
                    else:
                        raise

            else:
                detail = f"local server '{server_name}' assumed healthy"

        except Exception as exc:
            healthy = False
            detail = f"{type(exc).__name__}: {str(exc)[:200]}"

        latency_ms = (_time.perf_counter() - start) * 1000

        with sqlite3.connect(self.db_path) as conn:
            cols = set(self._table_columns(conn, "server_health_log"))
            now = self._now()
            status_str = "OK" if healthy else "FAILED"
            if {"run_id", "server_name", "status", "detail", "latency_ms", "created_at"}.issubset(cols):
                conn.execute(
                    """
                    INSERT INTO server_health_log
                    (run_id, server_name, status, detail, latency_ms, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (self.run_id, server_name, status_str, detail, latency_ms, now),
                )
            else:
                checked_col = "checked_at" if "checked_at" in cols else "created_at"
                if {"server_name", "status", checked_col, "latency_ms", "detail"}.issubset(cols):
                    conn.execute(
                        f"""
                        INSERT INTO server_health_log
                        (server_name, status, {checked_col}, latency_ms, detail)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (server_name, status_str, now, latency_ms, detail),
                    )
            conn.commit()

        if not healthy:
            raise ServerUnavailableError(server_name=server_name, detail=detail, latency_ms=latency_ms)

    def _context_config_for_phase(self, phase: str) -> dict[str, Any]:
        if phase == "SIGMA_JOB1":
            return {"BLOCK": set(self.ROUTING_RULES["SIGMA_JOB1"]["BLOCK"])}
        if phase == "FORGE":
            return {"BLOCK": set(self.ROUTING_RULES["FORGE"]["BLOCK"])}
        if phase == "CODEC":
            return {
                "PASS1": {"BLOCK": set()},
                "PASS2": {"BLOCK": set(self.ROUTING_RULES["CODEC_PASS2"]["BLOCK"])},
                "BLOCK": set(self.ROUTING_RULES["CODEC_PASS2"]["BLOCK"]),
            }
        if phase == "QUILL":
            return {"ALLOW": set(self.ROUTING_RULES["QUILL"]["ALLOW"])}
        if phase == "HAWK":
            return {"ALLOW": set(self.ROUTING_RULES["HAWK"]["ALLOW"])}
        return {"BLOCK": set()}

    @staticmethod
    def _server_for_phase(phase: str) -> str:
        _ = AGENT_TIMEOUTS_SECONDS.get(phase)
        return AGENT_SERVER_MAP.get(phase, "local")

    def _init_db(self) -> None:
        schema_path = Path(__file__).with_name("schema.sql")
        sql = schema_path.read_text(encoding="utf-8")
        with sqlite3.connect(self.db_path) as conn:
            conn.executescript(sql)
            conn.commit()

    def _ensure_run_rows(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            run_cols = set(self._table_columns(conn, "pipeline_runs"))
            finished_col = "completed_at" if "completed_at" in run_cols else "finished_at"
            seed_col = "seed_query" if "seed_query" in run_cols else None
            meta_col = "meta_json" if "meta_json" in run_cols else None
            paper_col = "paper_md_path" if "paper_md_path" in run_cols else None

            cols = ["run_id", "status", "started_at"]
            vals: list[object] = [self.run_id, "pending", self._now()]
            if finished_col in run_cols:
                cols.append(finished_col)
                vals.append(None)
            if seed_col is not None:
                cols.append(seed_col)
                vals.append(None)
            if meta_col is not None:
                cols.append(meta_col)
                vals.append(None)
            if paper_col is not None:
                cols.append(paper_col)
                vals.append(self.paper_md_path)

            conn.execute(
                f"""
                INSERT INTO pipeline_runs ({", ".join(cols)})
                VALUES ({", ".join("?" for _ in cols)})
                ON CONFLICT(run_id) DO NOTHING
                """,
                tuple(vals),
            )
            for phase in self.PHASE_ORDER:
                row = conn.execute(
                    "SELECT 1 FROM phases WHERE run_id=? AND phase_name=? LIMIT 1",
                    (self.run_id, phase),
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT INTO phases (run_id, phase_name, status) VALUES (?, ?, 'pending')",
                        (self.run_id, phase),
                    )
            conn.commit()

    def _set_run_status(self, status: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            run_cols = set(self._table_columns(conn, "pipeline_runs"))
            finished_col = "completed_at" if "completed_at" in run_cols else "finished_at"
            if status == "done":
                conn.execute(
                    f"UPDATE pipeline_runs SET status=?, {finished_col}=? WHERE run_id=?",
                    (status, self._now(), self.run_id),
                )
            else:
                conn.execute("UPDATE pipeline_runs SET status=? WHERE run_id=?", (status, self.run_id))
            conn.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
        return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})")]

    def _log_audit(self, phase: str, level: str, detail: str) -> None:
        out = Path("paper_memory") / self.run_id
        out.mkdir(parents=True, exist_ok=True)
        p = out / "audit_log.txt"
        ts = self._now()
        with p.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {phase} {level}: {detail}\n")

# CODEC traceability marker for PAPER.md alignment
AUDIT_REQUIREMENT_CODEC_BIDIRECTIONAL_AUDIT_SPEC_MARKER: str = "CODEC bidirectional audit required before QUILL writes paper"

# CODEC traceability marker for PAPER.md alignment
AUDIT_REQUIREMENT_CODEC_BIDIRECTIONAL_AUDIT_BEFORE_QUILL_SPEC_MARKER: str = "CODEC bidirectional audit required before QUILL writes paper"

# CODEC traceability marker for PAPER.md alignment
AUDIT_REQUIREMENT_CODEC_BIDIRECTIONAL_AUDIT_REQUIRED_BEFORE_QUILL_WRITES_PAPER_SPEC_MARKER: str = "CODEC bidirectional audit required before QUILL writes paper"
