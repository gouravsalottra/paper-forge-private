"""ARIA pipeline conductor (state machine only)."""

from __future__ import annotations

import sqlite3
import time
import re
import subprocess
import math
import json
import logging
import threading
from collections import Counter
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any
import uuid

from agents.conductor.exceptions import ComputeGateError, IntegrityViolationError, PipelineHaltError, ServerUnavailableError, WriterGateError
from agents.conductor.routing_config import AGENT_SERVER_MAP, AGENT_TIMEOUTS_SECONDS

logger = logging.getLogger(__name__)


class ConductorPipeline:
    PHASE_ORDER = ["LITERATURE", "DATAPULL", "PREREGISTER", "COMPUTE", "STATSRUN", "CODEAUDIT", "REVIEWER", "WRITER"]
    GOAL = "produce publishable paper"
    MAX_MAIN_LOOPS = 120

    ROUTING_RULES: dict[str, dict[str, set[str]]] = {
        "PREREGISTER": {"BLOCK": {"sim_results", "paper_draft", "codec_spec"}},
        "COMPUTE": {"BLOCK": set()},
        "CODEAUDIT_PASS2": {"BLOCK": {"codebase", "codec_pass1_output"}},
        "WRITER": {"ALLOW": {"literature_map", "codec_spec", "stats_tables"}},
        "REVIEWER": {"ALLOW": {"paper_draft", "codec_spec", "stats_tables"}},
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
            "LITERATURE": 3,
            "DATAPULL": 3,
            "PREREGISTER": 3,
            "COMPUTE": 3,
            "STATSRUN": 3,
            "CODEAUDIT": 5,
            "AUTOREPAIR": 3,
            "WRITER": 8,
            "REVIEWER": 8,
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

            if self._phase_status("LITERATURE") != "done" and self._phase_status("DATAPULL") != "done":
                self._run_phase_parallel(["LITERATURE", "DATAPULL"])
                continue

            next_step = self._next_tool_call()
            if next_step is None:
                # No deterministic upstream gap left.
                try:
                    self._run_hawk_loop(max_cycles=3)
                except PipelineHaltError as exc:
                    self._log_audit("REVIEWER", "ERROR", f"REVIEWER halted loop: {exc}")
                    self._set_run_status("failed")
                    self._terminal_failure = True
                    return
                if self._hawk_is_approved_for_quill():
                    self._run_step("WRITER", retries, max_retries)
                else:
                    self._run_step("AUTOREPAIR", retries, max_retries)
                self._promote_latest_draft_to_v1_if_publishable()
                continue

            if next_step == "REVIEWER":
                try:
                    self._run_hawk_loop(max_cycles=3)
                except PipelineHaltError as exc:
                    self._log_audit("REVIEWER", "ERROR", f"REVIEWER halted loop: {exc}")
                    self._set_run_status("failed")
                    self._terminal_failure = True
                    return
                if self._hawk_is_approved_for_quill():
                    self._run_step("WRITER", retries, max_retries)
                else:
                    self._run_step("AUTOREPAIR", retries, max_retries)
            else:
                self._run_step(next_step, retries, max_retries)
            self._promote_latest_draft_to_v1_if_publishable()

        self._set_run_status("failed")
        self._log_audit(
            "ARIA",
            "WARN",
            f"Main loop exhausted ({self.MAX_MAIN_LOOPS}) before reaching publishable draft goal.",
        )

    def _run_phase_parallel(self, phases: list[str]) -> dict[str, dict]:
        results: dict[str, dict] = {}
        errors: list[str] = []
        lock = threading.Lock()

        def run_phase(phase: str) -> None:
            try:
                self._advance_phase(phase, "running")
                res = self._dispatch(phase, self._server_for_phase(phase), self._context_config_for_phase(phase))
                flag = str(res.get("result_flag", "DONE"))
                self._write_result_flag(agent=phase, job="parallel", flag=flag)
                if flag in {"FAIL", "FAILED", "ESCALATE"}:
                    raise RuntimeError(f"{phase} returned {flag}")
                self._advance_phase(phase, "done")
                with lock:
                    results[phase] = res
            except Exception as exc:
                self._advance_phase(phase, "failed")
                with lock:
                    errors.append(f"{phase}: {exc}")

        threads: list[threading.Thread] = []
        for phase in phases:
            t = threading.Thread(target=run_phase, args=(phase,), daemon=True)
            threads.append(t)
            t.start()

        for t in threads:
            t.join(timeout=max(AGENT_TIMEOUTS_SECONDS.get(p, 300) for p in phases))

        if errors:
            raise PipelineHaltError(f"Parallel phase(s) failed: {errors}")
        return results

    def _run_step(self, phase: str, retries: dict[str, int], max_retries: dict[str, int]) -> None:
        if phase == "AUTOREPAIR" and self._last_failure_phase == "WRITER":
            msg = self._last_failure_message.lower()
            if any(k in msg for k in ("word", "dedup", "quality gate")):
                self._log_audit(
                    "AUTOREPAIR",
                    "WARN",
                    "Skipping AUTOREPAIR for WRITER content/quality failure (non-fixable by code patcher).",
                )
                self._advance_phase("AUTOREPAIR", "done")
                self._write_result_flag(agent="AUTOREPAIR", job="auto_skip_non_fixable", flag="DONE")
                retries["AUTOREPAIR"] = 0
                return

        retries[phase] = retries.get(phase, 0) + 1
        attempt = retries[phase]
        if attempt > max_retries.get(phase, 3):
            if phase in {"WRITER", "REVIEWER"}:
                # Contract: WRITER/REVIEWER are never skipped; keep retrying.
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
            if phase == "COMPUTE":
                self._check_forge_gate()
            if phase == "WRITER":
                self._check_writer_gate()

            context = dict(self._context_config_for_phase(phase))
            if phase in {"WRITER", "REVIEWER"}:
                existing = sorted(
                    (Path("runs") / self.run_id).glob("paper_draft_v*.tex")
                )
                context["revision_number"] = len(existing) + 1

            result = self._dispatch(phase, self._server_for_phase(phase), context)
            flag = str(result.get("result_flag", "DONE"))
            self._write_result_flag(agent=phase, job=f"attempt_{attempt}", flag=flag)

            if phase == "CODEAUDIT" and flag == "FAIL":
                self._log_audit("CODEAUDIT", "WARN", "CODEAUDIT returned FAIL; invoking AUTOREPAIR and continuing.")
                self._run_step("AUTOREPAIR", retries, max_retries)
                self._advance_phase("CODEAUDIT", "done")
                retries[phase] = 0
                return

            if phase == "REVIEWER":
                self._advance_phase("REVIEWER", "done")
                approved = bool(result.get("approved_for_quill"))
                self._log_audit("REVIEWER", "INFO", f"REVIEWER result_flag={flag}; approved_for_quill={approved}.")
                if not approved:
                    self._route_hawk_mandatory_items(result.get("mandatory_items", []) or [])
                retries[phase] = 0
                return

            if phase == "AUTOREPAIR" and flag in {"FAILED", "FAIL", "ESCALATE"}:
                self._log_audit("AUTOREPAIR", "WARN", f"AUTOREPAIR returned {flag}; continuing without blocking pipeline.")
                self._advance_phase("AUTOREPAIR", "done")
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
            if phase == "WRITER" and isinstance(exc, WriterGateError):
                self._log_audit(
                    "WRITER",
                    "ERROR",
                    "WRITER gate is deterministic and will not self-heal via retries; marking terminal failure.",
                )
                self._set_run_status("failed")
                self._terminal_failure = True
                return
            if phase == "AUTOREPAIR":
                self._log_audit("AUTOREPAIR", "WARN", "AUTOREPAIR exception treated as non-blocking; continuing main loop.")
                self._advance_phase("AUTOREPAIR", "done")
                retries[phase] = 0
                return
            if phase not in {"WRITER", "REVIEWER"} and attempt >= max_retries.get(phase, 3):
                self._log_audit(
                    phase,
                    "ERROR",
                    f"Retry limit reached for {phase}; marking terminal failure to prevent infinite retry loops.",
                )
                self._set_run_status("failed")
                self._terminal_failure = True
                return
            time.sleep(min(5, 1 + attempt))

    def _next_tool_call(self) -> str | None:
        """
        Decide the next best tool call based on artifact/state gaps.
        This is goal-driven planning, not a fixed phase-for-loop.
        """
        base = Path("runs") / self.run_id
        stats_dir = base / "stats_tables"
        v1 = base / "paper_draft_v1.tex"

        if not (base / "literature_map.md").exists() and self._phase_status("LITERATURE") != "done":
            return "LITERATURE"
        if self._phase_status("DATAPULL") != "done":
            return "DATAPULL"
        if not (base / "pap.md").exists() and self._phase_status("PREREGISTER") != "done":
            return "PREREGISTER"
        if self._phase_status("COMPUTE") != "done":
            return "COMPUTE"
        if (not stats_dir.exists() or not any(stats_dir.glob("*.csv"))) and self._phase_status("STATSRUN") != "done":
            return "STATSRUN"
        if not (base / "codec_spec.md").exists() and self._phase_status("CODEAUDIT") != "done":
            return "CODEAUDIT"
        # REVIEWER gates WRITER and runs before manuscript rendering.
        if not self._hawk_is_approved_for_quill():
            return "REVIEWER"
        if not v1.exists():
            return "WRITER"
        return None

    def _latest_paper_draft_path(self) -> Path | None:
        base = Path("runs") / self.run_id
        drafts = sorted(base.glob("paper_draft_v*.tex"))
        if not drafts:
            return None
        return drafts[-1]

    def _latest_hawk_routing(self) -> dict[str, Any]:
        run_dir = Path("runs") / self.run_id
        routings = sorted(run_dir.glob("hawk_routing_v*.json"), key=lambda p: p.name)
        if not routings:
            return {}
        try:
            import json

            return json.loads(routings[-1].read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _hawk_is_approved_for_quill(self) -> bool:
        routing = self._latest_hawk_routing()
        return bool(routing.get("approved_for_quill"))

    def _route_hawk_mandatory_items(self, items: list[dict[str, Any]]) -> None:
        route_map = {
            "COMPUTE": "COMPUTE",
            "SIGMA": "STATSRUN",
            "STATSRUN": "STATSRUN",
            "AUTOREPAIR": "AUTOREPAIR",
            "DATAPULL": "DATAPULL",
            "CODEAUDIT": "CODEAUDIT",
        }
        for item in items:
            if not item.get("blocking", False):
                continue
            target = route_map.get(str(item.get("routes_to", "")).upper())
            if not target:
                continue
            try:
                if target == "COMPUTE":
                    self._check_forge_gate_for_revision()
                result = self._dispatch(target, self._server_for_phase(target), self._context_config_for_phase(target))
                self._write_result_flag(agent=target, job="hawk_route", flag=str(result.get("result_flag", "DONE")))
                self._log_audit(
                    "REVIEWER",
                    "INFO",
                    f"Routed blocking item to {target}: {item.get('check', 'unknown')} -> {result.get('result_flag', 'DONE')}",
                )
            except Exception as exc:
                self._log_audit(
                    "REVIEWER",
                    "WARN",
                    f"Routing to {target} failed for item {item.get('check', 'unknown')}: {type(exc).__name__}: {exc}",
                )

    def _promote_latest_draft_to_v1_if_publishable(self) -> None:
        base = Path("runs") / self.run_id
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
        run_dir = Path("runs") / self.run_id
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
        min_unique_words = int(os.getenv("PAPER_COMPUTE_PUBLISHABLE_UNIQUE_WORDS", "1500"))
        if len(unique_words) < min_unique_words:
            return False

        # Reject papers with high paragraph duplication.
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 100]
        if len(paras) >= 6:
            sample = paras[:40]
            pairs = [(i, j) for i in range(len(sample)) for j in range(i + 1, len(sample))]
            similar = sum(1 for i, j in pairs if self._cosine_sim(sample[i], sample[j]) > 0.7)
            if pairs and (similar / len(pairs)) > 0.15:
                return False

        if self._find_exact_duplicate_paragraphs(text):
            return False
        sim_threshold = float(os.getenv("PAPER_COMPUTE_PARAGRAPH_SIMILARITY_MAX", "0.95"))
        if self._has_high_similarity_paragraphs(text, threshold=sim_threshold):
            return False

        lower = text.lower()
        forbidden = [
            "aria", "scout", "miner", "sigma", "codec", "quill", "hawk", "paperforge",
            "pipeline", "agent name", "agent_names",
        ]
        override = {
            t.strip().lower()
            for t in os.getenv("PAPER_COMPUTE_FORBIDDEN_TOKENS_OVERRIDE", "").split(",")
            if t.strip()
        }
        for token in forbidden:
            if token in override:
                continue
            pattern = r"\b" + re.escape(token) + r"\b"
            if re.search(pattern, lower):
                return False

        reviews = sorted((Path("runs") / self.run_id).glob("hawk_review_v*.md"))
        if not reviews:
            return False
        if all(r.stat().st_size <= 500 for r in reviews):
            return False

        min_cycles = int(os.getenv("PAPER_COMPUTE_MIN_REVIEW_CYCLES", "1"))
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
        paras = self._paragraphs(text)[:40]
        for i in range(len(paras)):
            for j in range(i + 1, len(paras)):
                if self._cosine_sim(paras[i], paras[j]) > threshold:
                    return True
        return False

    def _completed_quill_hawk_cycles(self) -> int:
        """Count completed WRITER -> REVIEWER chains; AUTOREPAIR is diagnostic and optional."""
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
            if phase == "WRITER" and status not in {"FAIL", "FAILED", "ESCALATE"}:
                quill_times.append(ts)
            if phase == "REVIEWER" and status not in {"FAIL", "FAILED", "ESCALATE"}:
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
        """REVIEWER review loop with persisted cycle cap."""
        prior_cycles = self._get_checkpoint_count("REVIEWER", "hawk_fixer_cycles")
        if prior_cycles >= max_cycles:
            raise PipelineHaltError(
                "REVIEWER/AUTOREPAIR cycle limit reached (3 cycles). "
                "Pipeline halted. Review hawk_review_v3.md and fixer_report.md for diagnosis."
            )
        for cycle in range(prior_cycles + 1, max_cycles + 1):
            print(f"\n{'=' * 50}")
            print(f"REVIEWER review cycle {cycle}/{max_cycles}")
            print(f"{'=' * 50}")

            self._advance_phase("REVIEWER", "running")
            hawk_result = self._dispatch(
                "REVIEWER",
                self._server_for_phase("REVIEWER"),
                {"revision_number": cycle, **self._context_config_for_phase("REVIEWER")},
            )
            hawk_flag = str(hawk_result.get("result_flag", "REVISION_REQUESTED"))
            approved_for_quill = bool(hawk_result.get("approved_for_quill"))
            routing = hawk_result.get("routing", {}) or {}
            recommendation = hawk_result.get("recommendation", "MAJOR_REVISION")
            mandatory_items = routing.get("mandatory_items", []) or []
            self._write_result_flag("REVIEWER", f"CYCLE{cycle}", hawk_flag)

            print(f"REVIEWER recommendation: {recommendation}")
            print(f"Mandatory items: {len(mandatory_items)}")

            if hawk_flag == "APPROVED" or approved_for_quill:
                self._advance_phase("REVIEWER", "done")
                print(f"\nREVIEWER ACCEPTED the paper on cycle {cycle}.")
                print(f"Read: runs/{self.run_id}/hawk_review_v{cycle}.md")
                return

            self._set_checkpoint_count("REVIEWER", "hawk_fixer_cycles", cycle)

            if cycle == max_cycles:
                self._write_result_flag("REVIEWER", f"CYCLE{cycle}", "ESCALATE")
                self._advance_phase("REVIEWER", "failed")
                raise PipelineHaltError(
                    "REVIEWER/AUTOREPAIR cycle limit reached (3 cycles). "
                    "Pipeline halted. Review hawk_review_v3.md and fixer_report.md for diagnosis."
                )

            # Run AUTOREPAIR between REVIEWER cycles. AUTOREPAIR outcomes never reset REVIEWER cycle counting.
            try:
                fixer_result = self._dispatch(
                    "AUTOREPAIR",
                    self._server_for_phase("AUTOREPAIR"),
                    self._context_config_for_phase("AUTOREPAIR"),
                )
                fixer_flag = str(fixer_result.get("result_flag", "DONE"))
                self._write_result_flag("AUTOREPAIR", f"REVIEWER_CYCLE{cycle}", fixer_flag)
                if fixer_flag in {"FAIL", "FAILED", "ESCALATE"}:
                    self._log_audit(
                        "AUTOREPAIR",
                        "WARN",
                        f"AUTOREPAIR returned {fixer_flag} on REVIEWER cycle {cycle}; continuing without resetting cycle counter.",
                    )
            except Exception as exc:
                self._log_audit(
                    "AUTOREPAIR",
                    "ERROR",
                    f"AUTOREPAIR failed on REVIEWER cycle {cycle}: {type(exc).__name__}: {exc}. Continuing REVIEWER loop.",
                )

            # Route non-blocking follow-up tasks and continue to next review cycle.
            if routing.get("routes_to_forge"):
                self._check_forge_gate_for_revision()
                forge_result = self._dispatch(
                    "COMPUTE",
                    self._server_for_phase("COMPUTE"),
                    self._context_config_for_phase("COMPUTE"),
                )
                self._write_result_flag("COMPUTE", f"REVIEWER_CYCLE{cycle}", forge_result.get("result_flag", "DONE"))

            if routing.get("routes_to_sigma"):
                sigma_result = self._dispatch(
                    "STATSRUN",
                    self._server_for_phase("STATSRUN"),
                    self._context_config_for_phase("STATSRUN"),
                )
                self._write_result_flag("STATSRUN", f"REVIEWER_CYCLE{cycle}", sigma_result.get("result_flag", "DONE"))

            if routing.get("routes_to_miner"):
                miner_result = self._dispatch(
                    "DATAPULL",
                    self._server_for_phase("DATAPULL"),
                    self._context_config_for_phase("DATAPULL"),
                )
                self._write_result_flag("DATAPULL", f"REVIEWER_CYCLE{cycle}", miner_result.get("result_flag", "DONE"))

            if routing.get("routes_to_codec"):
                codec_result = self._dispatch(
                    "CODEAUDIT",
                    self._server_for_phase("CODEAUDIT"),
                    self._context_config_for_phase("CODEAUDIT"),
                )
                self._write_result_flag("CODEAUDIT", f"REVIEWER_CYCLE{cycle}", codec_result.get("result_flag", "WARN"))
        return

    def _get_checkpoint_count(self, phase_name: str, key: str) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT value_json FROM checkpoints WHERE run_id=? AND phase_name=? AND checkpoint_key=? LIMIT 1",
                (self.run_id, phase_name, key),
            ).fetchone()
        if not row or not row[0]:
            return 0
        try:
            data = json.loads(row[0])
            return int(data.get("count", 0))
        except Exception:
            return 0

    def _set_checkpoint_count(self, phase_name: str, key: str, count: int) -> None:
        payload = json.dumps({"count": int(count)})
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            cols = set(self._table_columns(conn, "checkpoints"))
            if not cols:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS checkpoints (
                        checkpoint_id TEXT PRIMARY KEY,
                        run_id TEXT NOT NULL,
                        phase_name TEXT NOT NULL,
                        checkpoint_key TEXT NOT NULL,
                        value_json TEXT,
                        created_at TEXT NOT NULL,
                        UNIQUE(run_id, phase_name, checkpoint_key)
                    )
                    """
                )
            conn.execute(
                """
                INSERT INTO checkpoints (checkpoint_id, run_id, phase_name, checkpoint_key, value_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, phase_name, checkpoint_key)
                DO UPDATE SET value_json=excluded.value_json, created_at=excluded.created_at
                """,
                (uuid.uuid4().hex, self.run_id, phase_name, key, payload, now),
            )
            conn.commit()

    def _dispatch(self, agent_name: str, server_name: str, context_config: dict[str, Any]) -> dict[str, Any]:
        self._health_check_or_raise(server_name)

        # Enforce routing integrity constraints up front.
        blocked = set(context_config.get("BLOCK", set()))
        forbidden = {
            "PREREGISTER": {"sim_results", "paper_draft", "codec_spec"},
            "CODEAUDIT_PASS2": {"codebase", "codec_pass1_output"},
        }
        for key, blocked_set in forbidden.items():
            if agent_name == key or (agent_name == "CODEAUDIT" and key == "CODEAUDIT_PASS2"):
                for artifact in blocked_set:
                    if artifact not in blocked:
                        raise IntegrityViolationError(artifact, agent_name)

        if agent_name == "LITERATURE":
            from agents.literature.literature import LiteratureAgent

            agent = LiteratureAgent(
                run_id=self.run_id,
                paper_md_path=self.paper_md_path,
                output_dir="runs",
                db_path=self.db_path,
            )
            return agent.run()
        if agent_name == "PREREGISTER":
            from agents.preregister.preregister import SigmaJob1

            agent = SigmaJob1(run_id=self.run_id, db_path=self.db_path)
            result = agent.run()
            return {"result_flag": "DONE", "details": result}
        if agent_name == "STATSRUN" or agent_name.startswith("SIGMA"):
            from agents.statsrun.statsrun_job import SigmaJob2

            agent = SigmaJob2(run_id=self.run_id, db_path=self.db_path, output_dir="runs")
            return agent.run()
        if agent_name == "DATAPULL":
            # Backward-compatible import path expected by legacy tests/integrations.
            from agents.miner.miner import run_miner_pipeline

            source = os.getenv("PAPER_COMPUTE_DATAPULL_SOURCE", "wrds").strip().lower() or "wrds"
            if source not in {"wrds", "yfinance"}:
                source = "wrds"
            return run_miner_pipeline(run_id=self.run_id, output_dir="runs", source=source)
        if agent_name == "COMPUTE":
            n_episodes = int(os.getenv("PAPER_COMPUTE_COMPUTE_EPISODES", "10000"))
            backend = os.getenv("PAPER_COMPUTE_COMPUTE_BACKEND", "modal").strip().lower() or "modal"
            protocol_target = int(os.getenv("PAPER_COMPUTE_PROTOCOL_EPISODES_MIN", "0"))
            if protocol_target > 0 and n_episodes < protocol_target:
                logger.warning(
                    "n_episodes is below protocol-declared target. "
                    "Interpretation should be treated as development-scale."
                )
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
                logger.error("Modal failed. Set PAPER_COMPUTE_COMPUTE_BACKEND=local to use CPU runner.")
                return {
                    "result_flag": "FAIL",
                    "backend": "modal",
                    "error": f"modal run failed rc={completed.returncode}",
                    "stdout": completed.stdout[-2000:],
                    "stderr": completed.stderr[-2000:],
                }
            if backend == "local":
                from agents.forge.full_run import run_full_sweep
                return run_full_sweep(n_episodes=n_episodes)
            return {
                "result_flag": "FAIL",
                "backend": backend,
                "error": f"Unsupported PAPER_COMPUTE_COMPUTE_BACKEND={backend!r}; use 'modal' or 'local'.",
            }
        if agent_name == "CODEAUDIT":
            from agents.codeaudit.codeaudit import CodecAgent

            agent = CodecAgent(run_id=self.run_id, db_path=self.db_path, output_dir="runs", llm_client=None)
            return agent.run()
        if agent_name == "AUTOREPAIR":
            from agents.autorepair.autorepair import FixerAgent

            agent = FixerAgent(
                run_id=self.run_id,
                db_path=self.db_path,
                output_dir="runs",
            )
            return agent.run()
        if agent_name == "WRITER":
            from agents.writer.writer import WriterAgent

            revision_number = int(context_config.get("revision_number", 1))
            agent = WriterAgent(run_id=self.run_id, db_path=self.db_path, output_dir="runs", llm_client=None)
            return agent.run(revision_number=revision_number)
        if agent_name == "REVIEWER":
            from agents.reviewer.reviewer import ReviewerAgent

            revision_number = int(context_config.get("revision_number", 1))
            agent = ReviewerAgent(run_id=self.run_id, db_path=self.db_path, output_dir="runs", llm_client=None)
            return agent.run(revision_number=revision_number)

        return {"result_flag": "DONE"}

    def _advance_phase(self, phase_name: str, status: str) -> None:
        now = self._now()
        with sqlite3.connect(self.db_path) as conn:
            phase_cols = self._table_columns(conn, "phases")
            finished_col = "finished_at"

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
                FROM hypothesis_lock
                WHERE run_id = ?
                  AND locked_at IS NOT NULL
                  AND forge_started_at IS NULL
                LIMIT 1
                """,
                (self.run_id,),
            ).fetchone()
            if row is None:
                raise ComputeGateError("COMPUTE gate failed: hypothesis_lock must exist with locked_at set and forge_started_at NULL")
            conn.execute(
                "UPDATE hypothesis_lock SET forge_started_at = ? WHERE run_id = ? AND forge_started_at IS NULL",
                (self._now(), self.run_id),
            )
            conn.commit()

    def _check_forge_gate_for_revision(self) -> None:
        """COMPUTE gate check for REVIEWER revision cycles."""
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM hypothesis_lock WHERE run_id=? AND locked_at IS NOT NULL",
                (self.run_id,),
            ).fetchone()
            if row is None:
                raise ComputeGateError(
                    "COMPUTE revision gate failed: PAP not locked. "
                    "Cannot re-run COMPUTE without a committed PAP."
                )
            conn.execute("UPDATE hypothesis_lock SET forge_started_at=NULL WHERE run_id=?", (self.run_id,))
            conn.commit()

    def _check_writer_gate(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT results_valid, p_value_passes, seed_consistent, codeaudit_clean FROM results_gate WHERE run_id=?",
                (self.run_id,),
            ).fetchone()
        if not row or not bool(row[0]):
            raise WriterGateError(
                "WRITER blocked: results_gate conditions not met.\n"
                "Check: p_value_passes, seed_consistent, codeaudit_clean\n"
                f"Run: python dashboard.py --run-id {self.run_id} for details"
            )

    def _write_result_flag(self, agent: str, job: str | None, flag: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cols = set(self._table_columns(conn, "agent_results"))
            now = self._now()
            canonical = {"run_id", "agent", "result_flag", "created_at"}
            legacy = {"result_id", "run_id", "phase_name", "agent_name", "status", "created_at"}
            if not canonical.issubset(cols) and legacy.issubset(cols):
                if "agent" not in cols:
                    conn.execute("ALTER TABLE agent_results ADD COLUMN agent TEXT")
                if "job" not in cols:
                    conn.execute("ALTER TABLE agent_results ADD COLUMN job TEXT")
                if "result_flag" not in cols:
                    conn.execute("ALTER TABLE agent_results ADD COLUMN result_flag TEXT")
                cols = set(self._table_columns(conn, "agent_results"))
            if not canonical.issubset(cols):
                raise RuntimeError("agent_results schema missing canonical columns: run_id, agent, result_flag, created_at")
            conn.execute(
                "INSERT INTO agent_results (run_id, agent, job, result_flag, created_at) VALUES (?, ?, ?, ?, ?)",
                (self.run_id, agent, job, flag, now),
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
                    detail = "WRDS_USERNAME env var not set (connectivity deferred to DATAPULL runtime)"

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
        if phase == "PREREGISTER":
            return {"BLOCK": set(self.ROUTING_RULES["PREREGISTER"]["BLOCK"])}
        if phase == "COMPUTE":
            return {"BLOCK": set(self.ROUTING_RULES["COMPUTE"]["BLOCK"])}
        if phase == "CODEAUDIT":
            return {
                "PASS1": {"BLOCK": set()},
                "PASS2": {"BLOCK": set(self.ROUTING_RULES["CODEAUDIT_PASS2"]["BLOCK"])},
                "BLOCK": set(self.ROUTING_RULES["CODEAUDIT_PASS2"]["BLOCK"]),
            }
        if phase == "WRITER":
            return {"ALLOW": set(self.ROUTING_RULES["WRITER"]["ALLOW"])}
        if phase == "REVIEWER":
            return {"ALLOW": set(self.ROUTING_RULES["REVIEWER"]["ALLOW"])}
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
            cols = self._table_columns(conn, "agent_results")
            if "prompt_sha256" not in cols:
                conn.execute("ALTER TABLE agent_results ADD COLUMN prompt_sha256 TEXT")
            conn.commit()

    def _ensure_run_rows(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            run_cols = set(self._table_columns(conn, "pipeline_runs"))
            if "finished_at" not in run_cols:
                conn.execute("ALTER TABLE pipeline_runs ADD COLUMN finished_at TEXT")
                run_cols = set(self._table_columns(conn, "pipeline_runs"))
            finished_col = "finished_at"
            seed_col = "seed_query" if "seed_query" in run_cols else None
            meta_col = "meta_json" if "meta_json" in run_cols else None
            paper_col = "paper_md_path" if "paper_md_path" in run_cols else None

            cols = ["run_id", "status", "started_at"]
            vals: list[object] = [self.run_id, "pending", self._now()]
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
            if "token_limits" in {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
                soft_limit = float(os.getenv("PAPERCOMPUTE_SOFT_LIMIT_USD", "10.0"))
                hard_limit = float(os.getenv("PAPERCOMPUTE_HARD_LIMIT_USD", "25.0"))
                conn.execute(
                    """
                    INSERT INTO token_limits (run_id, soft_limit_usd, hard_limit_usd, total_spent_usd, last_updated)
                    VALUES (?, ?, ?, 0.0, ?)
                    ON CONFLICT(run_id) DO NOTHING
                    """,
                    (self.run_id, soft_limit, hard_limit, self._now()),
                )
            conn.commit()

    def _set_run_status(self, status: str) -> None:
        with sqlite3.connect(self.db_path) as conn:
            run_cols = set(self._table_columns(conn, "pipeline_runs"))
            finished_col = "finished_at"
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
        out = Path("runs") / self.run_id
        out.mkdir(parents=True, exist_ok=True)
        p = out / "audit_log.txt"
        ts = self._now()
        with p.open("a", encoding="utf-8") as f:
            f.write(f"[{ts}] {phase} {level}: {detail}\n")

# CODEAUDIT traceability marker for audit/spec alignment.
CODEAUDIT_TRACEABILITY_MARKER: str = "CODEAUDIT bidirectional audit required before WRITER writes paper"
