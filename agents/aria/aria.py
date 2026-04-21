"""ARIA pipeline conductor (state machine only)."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any

from agents.aria.exceptions import ForgeGateError, IntegrityViolationError, PipelineHaltError, ServerUnavailableError
from agents.aria.routing_config import AGENT_SERVER_MAP, AGENT_TIMEOUTS_SECONDS


class ARIAPipeline:
    PHASE_ORDER = ["SCOUT", "MINER", "SIGMA_JOB1", "FORGE", "SIGMA_JOB2", "CODEC", "QUILL", "HAWK"]

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
        self._init_db()
        self._ensure_run_rows()

    def run(self) -> None:
        self._set_run_status("running")
        for phase in self.PHASE_ORDER:
            current_status = self._phase_status(phase)
            if current_status == "done":
                continue

            if phase == "FORGE":
                self._check_forge_gate()

            if phase == "CODEC":
                max_codec_attempts = 3
                for attempt in range(1, max_codec_attempts + 1):
                    self._advance_phase("CODEC", "running")
                    result = self._dispatch(
                        "CODEC",
                        self._server_for_phase("CODEC"),
                        self._context_config_for_phase("CODEC"),
                    )
                    flag = str(result.get("result_flag", "FAIL"))
                    self._write_result_flag(agent="CODEC", job=f"attempt_{attempt}", flag=flag)

                    if flag in ("PASS", "WARN"):
                        self._advance_phase("CODEC", "done")
                        if flag == "WARN":
                            print(
                                f"CODEC WARN: minor discrepancies found. "
                                f"QUILL will acknowledge them in limitations. "
                                f"Read paper_memory/{self.run_id}/codec_mismatch.md"
                            )
                        break
                    else:
                        self._advance_phase("CODEC", "failed")
                        self._set_run_status("failed")
                        raise PipelineHaltError(
                            f"\n"
                            f"{'=' * 60}\n"
                            f"CODEC FAIL — pipeline halted (attempt {attempt}/{max_codec_attempts})\n"
                            f"{'=' * 60}\n"
                            f"The code does not match what PAPER.md specifies.\n"
                            f"This means a paper cannot be written yet.\n"
                            f"\n"
                            f"Read the mismatch report:\n"
                            f"  cat paper_memory/{self.run_id}/codec_mismatch.md\n"
                            f"\n"
                            f"Fix the gaps in the code so it implements what PAPER.md describes.\n"
                            f"Then re-run from CODEC:\n"
                            f"  python run_aria_pipeline.py --resume {self.run_id} --from CODEC\n"
                            f"{'=' * 60}"
                        )
                continue

            if phase == "HAWK":
                self._run_hawk_loop(max_cycles=5)
                continue

            self._advance_phase(phase, "running")
            result = self._dispatch(phase, self._server_for_phase(phase), self._context_config_for_phase(phase))
            flag = str(result.get("result_flag", "DONE"))
            self._write_result_flag(agent=phase, job=None, flag=flag)
            if flag in {"FAILED", "FAIL", "ESCALATE"}:
                self._advance_phase(phase, "failed")
                self._set_run_status("failed")
                raise PipelineHaltError(f"Pipeline halted at phase {phase} with flag={flag}")
            self._advance_phase(phase, "done")

        self._set_run_status("done")

    def _phase_status(self, phase_name: str) -> str | None:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT status FROM phases WHERE run_id=? AND phase_name=? LIMIT 1",
                (self.run_id, phase_name),
            ).fetchone()
        if row is None:
            return None
        return str(row[0]) if row[0] is not None else None

    def _run_hawk_loop(self, max_cycles: int = 5) -> None:
        """Fully automatic HAWK review loop with agent routing."""
        for cycle in range(1, max_cycles + 1):
            print(f"\n{'=' * 50}")
            print(f"HAWK review cycle {cycle}/{max_cycles}")
            print(f"{'=' * 50}")

            self._advance_phase("QUILL", "running")
            quill_result = self._dispatch(
                "QUILL",
                self._server_for_phase("QUILL"),
                {"revision_number": cycle, **self._context_config_for_phase("QUILL")},
            )
            quill_flag = str(quill_result.get("result_flag", "DONE"))
            self._write_result_flag("QUILL", f"CYCLE{cycle}", quill_flag)
            if quill_flag in ("FAILED", "FAIL"):
                self._advance_phase("QUILL", "failed")
                self._set_run_status("failed")
                raise PipelineHaltError(
                    f"QUILL failed on cycle {cycle}. Check stats_tables/ and literature_map.md are populated."
                )
            self._advance_phase("QUILL", "done")
            print(f"QUILL draft v{cycle} written.")

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
            for item in mandatory_items:
                print(f"  [{item.get('agent', '?')}] {str(item.get('issue', ''))[:80]}")

            if hawk_flag == "APPROVED":
                self._advance_phase("HAWK", "done")
                print(f"\nHAWK ACCEPTED the paper on cycle {cycle}.")
                print(f"Read: paper_memory/{self.run_id}/hawk_review_v{cycle}.md")
                return

            if hawk_flag == "ESCALATE" or recommendation == "REJECT":
                self._advance_phase("HAWK", "failed")
                self._set_run_status("failed")
                raise PipelineHaltError(
                    f"\n"
                    f"{'=' * 60}\n"
                    f"HAWK {'ESCALATED' if hawk_flag == 'ESCALATE' else 'REJECTED'} the paper (cycle {cycle})\n"
                    f"{'=' * 60}\n"
                    f"Read the full referee report:\n"
                    f"  cat paper_memory/{self.run_id}/hawk_review_v{cycle}.md\n"
                    f"\n"
                    f"These issues cannot be fixed by revision alone.\n"
                    f"The paper requires fundamental rethinking.\n"
                    f"{'=' * 60}"
                )

            if cycle == max_cycles:
                self._advance_phase("HAWK", "failed")
                self._set_run_status("failed")
                raise PipelineHaltError(
                    f"\n"
                    f"{'=' * 60}\n"
                    f"HAWK did not accept after {max_cycles} cycles\n"
                    f"{'=' * 60}\n"
                    f"Read final referee report:\n"
                    f"  cat paper_memory/{self.run_id}/hawk_review_v{cycle}.md\n"
                    f"\n"
                    f"Remaining mandatory items:\n"
                    + "\n".join(
                        f"  [{i.get('agent', '?')}] {i.get('issue', '')}"
                        for i in mandatory_items
                    )
                    + f"\n{'=' * 60}"
                )

            print("\nRouting mandatory items to agents...")

            if routing.get("routes_to_codec"):
                self._advance_phase("HAWK", "failed")
                self._set_run_status("failed")
                codec_items = [i for i in mandatory_items if i.get("agent") == "CODEC"]
                raise PipelineHaltError(
                    f"\n"
                    f"{'=' * 60}\n"
                    f"HAWK found code-paper mismatch\n"
                    f"{'=' * 60}\n"
                    f"Fix the code so it implements what the paper claims:\n"
                    + "\n".join(f"  - {i.get('required_action', '')}" for i in codec_items)
                    + f"\n\nThen re-run from CODEC:\n"
                    f"  python run_aria_pipeline.py --resume {self.run_id} --from CODEC\n"
                    f"{'=' * 60}"
                )

            if routing.get("routes_to_forge"):
                print("  [FORGE] Re-running simulation per HAWK instructions...")
                forge_items = [i for i in mandatory_items if i.get("agent") == "FORGE"]
                for item in forge_items:
                    print(f"    Issue: {str(item.get('issue', ''))[:100]}")
                    print(f"    Fix:   {str(item.get('required_action', ''))[:100]}")

                self._check_forge_gate_for_revision()
                forge_result = self._dispatch(
                    "FORGE",
                    self._server_for_phase("FORGE"),
                    self._context_config_for_phase("FORGE"),
                )
                self._write_result_flag("FORGE", f"HAWK_CYCLE{cycle}", forge_result.get("result_flag", "DONE"))
                print("  [FORGE] Complete. Re-running SIGMA JOB 2...")

                sigma_result = self._dispatch(
                    "SIGMA_JOB2",
                    self._server_for_phase("SIGMA_JOB2"),
                    self._context_config_for_phase("SIGMA_JOB2"),
                )
                self._write_result_flag("SIGMA_JOB2", f"HAWK_CYCLE{cycle}", sigma_result.get("result_flag", "DONE"))
                print("  [SIGMA JOB 2] Complete. Re-running CODEC...")

                codec_result = self._dispatch(
                    "CODEC",
                    self._server_for_phase("CODEC"),
                    self._context_config_for_phase("CODEC"),
                )
                codec_flag = str(codec_result.get("result_flag", "FAIL"))
                self._write_result_flag("CODEC", f"HAWK_CYCLE{cycle}", codec_flag)
                if codec_flag == "FAIL":
                    self._advance_phase("HAWK", "failed")
                    self._set_run_status("failed")
                    raise PipelineHaltError(
                        "CODEC still failing after HAWK-requested FORGE revision.\n"
                        "Fix code gaps before continuing.\n"
                        f"cat paper_memory/{self.run_id}/codec_mismatch.md"
                    )
                print("  [CODEC] PASS. Continuing to QUILL.")

            if routing.get("routes_to_sigma"):
                print("  [SIGMA] Running additional tests per HAWK instructions...")
                sigma_items = [i for i in mandatory_items if i.get("agent") == "SIGMA"]
                for item in sigma_items:
                    print(f"    Issue: {str(item.get('issue', ''))[:100]}")
                    print(f"    Fix:   {str(item.get('required_action', ''))[:100]}")

                sigma_result = self._dispatch(
                    "SIGMA_JOB2",
                    self._server_for_phase("SIGMA_JOB2"),
                    self._context_config_for_phase("SIGMA_JOB2"),
                )
                self._write_result_flag("SIGMA_JOB2", f"HAWK_CYCLE{cycle}", sigma_result.get("result_flag", "DONE"))
                print("  [SIGMA JOB 2] Additional tests complete.")

            if routing.get("routes_to_miner"):
                print("  [MINER] Re-fetching data per HAWK instructions...")
                miner_items = [i for i in mandatory_items if i.get("agent") == "MINER"]
                for item in miner_items:
                    print(f"    Issue: {str(item.get('issue', ''))[:100]}")

                miner_result = self._dispatch(
                    "MINER",
                    self._server_for_phase("MINER"),
                    self._context_config_for_phase("MINER"),
                )
                self._write_result_flag("MINER", f"HAWK_CYCLE{cycle}", miner_result.get("result_flag", "DONE"))
                print("  [MINER] Data refresh complete.")

                sigma_result = self._dispatch(
                    "SIGMA_JOB2",
                    self._server_for_phase("SIGMA_JOB2"),
                    self._context_config_for_phase("SIGMA_JOB2"),
                )
                self._write_result_flag(
                    "SIGMA_JOB2", f"MINER_REFRESH_CYCLE{cycle}", sigma_result.get("result_flag", "DONE")
                )
                print("  [SIGMA JOB 2] Re-run on fresh data complete.")

            quill_items = [i for i in mandatory_items if i.get("agent") == "QUILL"]
            if quill_items:
                print(f"  [QUILL] {len(quill_items)} writing issues will be")
                print(f"          addressed in next draft (cycle {cycle + 1}).")
                for item in quill_items:
                    print(f"    - {str(item.get('issue', ''))[:100]}")

            print(f"\nAll upstream fixes complete. Starting cycle {cycle + 1}...")

        raise PipelineHaltError(f"HAWK loop exhausted {max_cycles} cycles.")

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

            # WRDS-first policy by default; explicit override only via env for controlled runs.
            source = os.getenv("PAPER_FORGE_MINER_SOURCE", "wrds").strip().lower() or "wrds"
            if source not in {"wrds", "yfinance"}:
                source = "wrds"
            return run_miner_pipeline(run_id=self.run_id, output_dir="paper_memory", source=source)
        if agent_name == "FORGE":
            from agents.forge.full_run import run_full_sweep

            return run_full_sweep(n_episodes=500_000)
        if agent_name == "CODEC":
            from agents.codec.codec import CodecAgent

            agent = CodecAgent(run_id=self.run_id, db_path=self.db_path, output_dir="paper_memory", llm_client=None)
            return agent.run()
        if agent_name == "QUILL":
            from agents.quill.quill import QuillAgent

            agent = QuillAgent(run_id=self.run_id, db_path=self.db_path, output_dir="paper_memory", llm_client=None)
            revision_number = int(context_config.get("revision_number", 1))
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

                req = urllib.request.Request(
                    "https://api.semanticscholar.org/graph/v1/paper/search?query=test&limit=1",
                    headers={"User-Agent": "paper-forge-health/1.0"},
                )
                with urllib.request.urlopen(req, timeout=10) as resp:
                    healthy = resp.status == 200
                    detail = f"semantic_scholar status={resp.status}"

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
