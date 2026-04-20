"""ARIA orchestrator for Paper Forge.

This module intentionally uses only Python stdlib + sqlite3.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


class ForgeGateError(RuntimeError):
    """Raised when FORGE cannot start because the gate condition is not met."""


class ARIA:
    """Database-backed run orchestration.

    ARIA reads orchestration state from ``state.db`` and does not read artifact files.
    """

    PHASE_ORDER = [
        "SCOUT",
        "MINER",
        "SIGMA_JOB1",
        "FORGE",
        "SIGMA_JOB2",
        "CODEC",
        "QUILL",
        "HAWK",
    ]

    def __init__(self, db_path: str | Path = "state.db") -> None:
        self.db_path = Path(db_path)

    def start_run(self, paper_md_path: str | Path) -> str:
        """Create a pipeline run and seed all phases as pending.

        Returns:
            str: The newly created run_id.
        """
        paper_path = Path(paper_md_path)
        paper_sha256 = hashlib.sha256(paper_path.read_bytes()).hexdigest()
        run_id = uuid.uuid4().hex
        now = self._now_iso()

        with self._connect() as conn:
            run_cols = self._table_columns(conn, "pipeline_runs")
            run_payload = {
                "run_id": run_id,
                "started_at": now,
                "created_at": now,
                "status": "running",
            }

            # Store PAPER.md hash in the most explicit available field.
            if "paper_sha256" in run_cols:
                run_payload["paper_sha256"] = paper_sha256
            elif "paper_hash" in run_cols:
                run_payload["paper_hash"] = paper_sha256
            elif "meta_json" in run_cols:
                run_payload["meta_json"] = json.dumps({"paper_sha256": paper_sha256})
            elif "seed_query" in run_cols:
                run_payload["seed_query"] = f"paper_sha256:{paper_sha256}"
            else:
                raise RuntimeError(
                    "pipeline_runs has no field to store PAPER.md SHA-256 "
                    "(expected one of: paper_sha256, paper_hash, meta_json, seed_query)."
                )

            self._insert_known_columns(conn, "pipeline_runs", run_payload)

            phase_cols = self._table_columns(conn, "phases")
            rows = []
            for phase_name in self.PHASE_ORDER:
                row = {
                    "run_id": run_id,
                    "phase_name": phase_name,
                    "status": "pending",
                }
                if "created_at" in phase_cols:
                    row["created_at"] = now
                rows.append(row)

            self._bulk_insert_known_columns(conn, "phases", rows)
            conn.commit()

        return run_id

    def advance(self) -> str:
        """Return the next pending phase name for the most recent run."""
        with self._connect() as conn:
            run_id = self._latest_run_id(conn)
            if run_id is None:
                raise RuntimeError("No pipeline run found in pipeline_runs.")

            rows = conn.execute(
                "SELECT phase_name FROM phases WHERE run_id = ? AND status = 'pending'",
                (run_id,),
            ).fetchall()
            pending = {row[0] for row in rows}

        for phase_name in self.PHASE_ORDER:
            if phase_name in pending:
                return phase_name

        raise RuntimeError(f"No pending phase found for run_id={run_id}.")

    def dispatch_forge(self, run_id: str) -> None:
        """Run FORGE gate SQL, then mark FORGE as started if gate passes."""
        now = self._now_iso()

        with self._connect() as conn:
            pap_lock_cols = self._table_columns(conn, "pap_lock")
            has_run_id = "run_id" in pap_lock_cols

            # Required gate SQL:
            # SELECT 1 FROM pap_lock WHERE locked_at IS NOT NULL AND forge_started_at IS NULL
            gate_sql = (
                "SELECT 1 FROM pap_lock "
                "WHERE locked_at IS NOT NULL AND forge_started_at IS NULL"
            )
            gate_params: tuple[object, ...] = ()
            if has_run_id:
                gate_sql += " AND run_id = ?"
                gate_params = (run_id,)

            rows = conn.execute(gate_sql, gate_params).fetchall()
            if not rows:
                raise ForgeGateError("FORGE gate failed: no eligible pap_lock row found.")

            update_sql = (
                "UPDATE pap_lock "
                "SET forge_started_at = ? "
                "WHERE locked_at IS NOT NULL AND forge_started_at IS NULL"
            )
            update_params: tuple[object, ...] = (now,)
            if has_run_id:
                update_sql += " AND run_id = ?"
                update_params = (now, run_id)

            conn.execute(update_sql, update_params)
            conn.commit()

    def complete_phase(self, run_id: str, phase_name: str) -> None:
        """Mark a phase as done and set completion timestamp."""
        now = self._now_iso()
        with self._connect() as conn:
            completed_col = self._phase_completed_column(conn)
            sql = (
                f"UPDATE phases SET status = 'done', {completed_col} = ? "
                "WHERE run_id = ? AND phase_name = ?"
            )
            conn.execute(sql, (now, run_id, phase_name))
            conn.commit()

    def fail_phase(self, run_id: str, phase_name: str, error: str) -> None:
        """Mark a phase as failed and log the provided error."""
        now = self._now_iso()
        with self._connect() as conn:
            phase_cols = self._table_columns(conn, "phases")
            completed_col = self._phase_completed_column(conn)

            assignments = ["status = 'failed'", f"{completed_col} = ?"]
            params: list[object] = [now]

            if "error" in phase_cols:
                assignments.append("error = ?")
                params.append(error)
            elif "details_json" in phase_cols:
                assignments.append("details_json = ?")
                params.append(json.dumps({"error": error}))

            params.extend([run_id, phase_name])
            sql = (
                f"UPDATE phases SET {', '.join(assignments)} "
                "WHERE run_id = ? AND phase_name = ?"
            )
            conn.execute(sql, tuple(params))
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {row[1] for row in rows}

    @staticmethod
    def _insert_known_columns(
        conn: sqlite3.Connection,
        table: str,
        payload: dict[str, object],
    ) -> None:
        cols = [col for col in payload if col in ARIA._table_columns(conn, table)]
        if not cols:
            raise RuntimeError(f"No matching columns found for insert into {table}.")

        placeholders = ", ".join("?" for _ in cols)
        columns_sql = ", ".join(cols)
        sql = f"INSERT INTO {table} ({columns_sql}) VALUES ({placeholders})"
        conn.execute(sql, tuple(payload[col] for col in cols))

    @staticmethod
    def _bulk_insert_known_columns(
        conn: sqlite3.Connection,
        table: str,
        payloads: Iterable[dict[str, object]],
    ) -> None:
        payload_list = list(payloads)
        if not payload_list:
            return

        cols = [
            col
            for col in payload_list[0].keys()
            if col in ARIA._table_columns(conn, table)
        ]
        if not cols:
            raise RuntimeError(f"No matching columns found for insert into {table}.")

        placeholders = ", ".join("?" for _ in cols)
        columns_sql = ", ".join(cols)
        sql = f"INSERT INTO {table} ({columns_sql}) VALUES ({placeholders})"
        values = [tuple(row.get(col) for col in cols) for row in payload_list]
        conn.executemany(sql, values)

    @staticmethod
    def _phase_completed_column(conn: sqlite3.Connection) -> str:
        cols = ARIA._table_columns(conn, "phases")
        if "completed_at" in cols:
            return "completed_at"
        if "finished_at" in cols:
            return "finished_at"
        raise RuntimeError("phases table missing completion timestamp column.")

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    @staticmethod
    def _latest_run_id(conn: sqlite3.Connection) -> str | None:
        run_cols = ARIA._table_columns(conn, "pipeline_runs")

        if "started_at" in run_cols:
            row = conn.execute(
                "SELECT run_id FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
            ).fetchone()
        elif "created_at" in run_cols:
            row = conn.execute(
                "SELECT run_id FROM pipeline_runs ORDER BY created_at DESC LIMIT 1"
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT run_id FROM pipeline_runs ORDER BY rowid DESC LIMIT 1"
            ).fetchone()

        return None if row is None else str(row[0])
