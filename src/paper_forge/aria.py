from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from paper_forge.errors import PapGateError, PhaseTransitionError
from paper_forge.lanes import with_lane
from paper_forge.models import Agent, Phase
from paper_forge.provenance import canonical_json_hash, sha256_text
from paper_forge.schema import DDL, SCHEMA_VERSION

ALLOWED_TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    Phase.INIT: frozenset({Phase.SCOUT}),
    Phase.SCOUT: frozenset({Phase.MINER}),
    Phase.MINER: frozenset({Phase.SIGMA}),
    Phase.SIGMA: frozenset({Phase.PAP_COMMIT}),
    Phase.PAP_COMMIT: frozenset({Phase.PAP_SEAL}),
    Phase.PAP_SEAL: frozenset({Phase.FORGE}),
    Phase.FORGE: frozenset({Phase.CODEC}),
    Phase.CODEC: frozenset({Phase.QUILL}),
    Phase.QUILL: frozenset({Phase.HAWK}),
    Phase.HAWK: frozenset({Phase.DONE}),
    Phase.DONE: frozenset(),
}


class ARIA:
    """Control plane: SQLite state, routing log, checkpoints, PAP commit/seal, phase transitions."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def init_schema(self, conn: sqlite3.Connection | None = None) -> None:
        close = False
        if conn is None:
            conn = self.connect()
            close = True
        try:
            conn.executescript(DDL)
            cur = conn.cursor()
            cur.execute(
                "INSERT OR IGNORE INTO run_state (id, phase) VALUES (1, ?)",
                (Phase.INIT.value,),
            )
            cur.execute(
                """INSERT OR IGNORE INTO pap_lock (id, sealed, sealed_at, seal_content_sha256)
                   VALUES (1, 0, NULL, '')"""
            )
            cur.execute(
                "INSERT OR REPLACE INTO aria_meta (key, value) VALUES ('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            conn.commit()
        finally:
            if close:
                conn.close()

    @contextmanager
    def transaction(self, conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def current_phase(self, conn: sqlite3.Connection) -> Phase:
        cur = conn.cursor()
        cur.execute("SELECT phase FROM run_state WHERE id = 1")
        row = cur.fetchone()
        if row is None:
            raise PhaseTransitionError("run_state missing; call init_schema()")
        return Phase(row["phase"])

    def transition_phase(
        self,
        conn: sqlite3.Connection,
        to_phase: Phase,
        *,
        expected_from: Phase | None = None,
    ) -> None:
        """Atomic phase change with graph validation and FORGE PAP gate."""

        def work(c: sqlite3.Cursor) -> None:
            c.execute("SELECT phase FROM run_state WHERE id = 1")
            row = c.fetchone()
            if row is None:
                raise PhaseTransitionError("run_state missing")
            current = Phase(row["phase"])
            if expected_from is not None and current != expected_from:
                raise PhaseTransitionError(
                    f"expected phase {expected_from.value}, got {current.value}"
                )
            allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
            if to_phase not in allowed:
                raise PhaseTransitionError(
                    f"transition {current.value} -> {to_phase.value} not allowed"
                )
            if to_phase == Phase.FORGE:
                self._assert_pap_gate_cursor(c)
            c.execute(
                "UPDATE run_state SET phase = ?, updated_at = datetime('now') WHERE id = 1",
                (to_phase.value,),
            )

        with self.transaction(conn):
            with_lane(conn, Agent.ARIA, ["run_state"], lambda c: work(c))

    def commit_pap(self, conn: sqlite3.Connection) -> str:
        """Freeze PAP row snapshot into pap_commit (must be in PAP_COMMIT phase)."""

        def work(c: sqlite3.Cursor) -> None:
            c.execute("SELECT phase FROM run_state WHERE id = 1")
            row = c.fetchone()
            if row is None or Phase(row["phase"]) != Phase.PAP_COMMIT:
                raise PhaseTransitionError("commit_pap requires phase PAP_COMMIT")
            agg = self._pap_rows_aggregate_hash(c)
            c.execute(
                """INSERT OR REPLACE INTO pap_commit (id, committed_at, committed_content_sha256)
                   VALUES (1, datetime('now'), ?)""",
                (agg,),
            )

        with self.transaction(conn):
            with_lane(conn, Agent.ARIA, ["pap_commit"], work)
        return self._read_commit_hash(conn)

    def seal_pap_lock(self, conn: sqlite3.Connection) -> str:
        """Seal PAP after commit (must be in PAP_SEAL phase)."""

        def work(c: sqlite3.Cursor) -> None:
            c.execute("SELECT phase FROM run_state WHERE id = 1")
            row = c.fetchone()
            if row is None or Phase(row["phase"]) != Phase.PAP_SEAL:
                raise PhaseTransitionError("seal_pap_lock requires phase PAP_SEAL")
            c.execute(
                "SELECT committed_content_sha256, committed_at FROM pap_commit WHERE id = 1"
            )
            prow = c.fetchone()
            if prow is None:
                raise PapGateError("pap_commit missing; run commit_pap first")
            commit_hash = prow["committed_content_sha256"]
            committed_at = prow["committed_at"]
            seal = sha256_text(f"{commit_hash}|{committed_at}|PAP_SEAL")
            c.execute(
                """UPDATE pap_lock SET sealed = 1, sealed_at = datetime('now'),
                   seal_content_sha256 = ? WHERE id = 1""",
                (seal,),
            )

        with self.transaction(conn):
            with_lane(conn, Agent.ARIA, ["pap_lock"], work)
        cur = conn.cursor()
        cur.execute("SELECT seal_content_sha256 FROM pap_lock WHERE id = 1")
        r = cur.fetchone()
        if r is None:
            raise PapGateError("pap_lock row missing")
        return r["seal_content_sha256"]

    def assert_forge_gate(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        self._assert_pap_gate_cursor(cur)

    def log_route(
        self,
        conn: sqlite3.Connection,
        route: str,
        payload: dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> int:
        payload_json = json.dumps(payload, sort_keys=True) if payload is not None else None

        def work(c: sqlite3.Cursor) -> None:
            c.execute(
                """INSERT INTO routing_log (route, payload_json, correlation_id)
                   VALUES (?, ?, ?)""",
                (route, payload_json, correlation_id),
            )

        with self.transaction(conn):
            with_lane(conn, Agent.ARIA, ["routing_log"], work)
        cur = conn.cursor()
        cur.execute("SELECT last_insert_rowid()")
        return int(cur.fetchone()[0])

    def checkpoint(
        self,
        conn: sqlite3.Connection,
        name: str,
        payload: dict[str, Any],
    ) -> tuple[int, str]:
        phase = self.current_phase(conn)
        h = canonical_json_hash(payload)

        def work(c: sqlite3.Cursor) -> None:
            c.execute(
                """INSERT INTO checkpoints (name, phase, payload_json, content_sha256)
                   VALUES (?, ?, ?, ?)""",
                (name, phase.value, json.dumps(payload, sort_keys=True), h),
            )

        with self.transaction(conn):
            with_lane(conn, Agent.ARIA, ["checkpoints"], work)
        cur = conn.cursor()
        cur.execute("SELECT last_insert_rowid()")
        rid = int(cur.fetchone()[0])
        return rid, h

    def _read_commit_hash(self, conn: sqlite3.Connection) -> str:
        cur = conn.cursor()
        cur.execute("SELECT committed_content_sha256 FROM pap_commit WHERE id = 1")
        row = cur.fetchone()
        if row is None:
            raise PapGateError("pap_commit missing")
        return row["committed_content_sha256"]

    def _pap_rows_aggregate_hash(self, cur: sqlite3.Cursor) -> str:
        cur.execute(
            "SELECT hypothesis_id, content_sha256 FROM pap_row ORDER BY hypothesis_id"
        )
        rows = cur.fetchall()
        if not rows:
            raise PapGateError("cannot commit PAP: pap_row is empty")
        blob = "\n".join(f"{r['hypothesis_id']}:{r['content_sha256']}" for r in rows)
        return sha256_text(blob)

    def _assert_pap_gate_cursor(self, cur: sqlite3.Cursor) -> None:
        cur.execute("SELECT committed_content_sha256 FROM pap_commit WHERE id = 1")
        if cur.fetchone() is None:
            raise PapGateError("pap_commit missing")
        cur.execute("SELECT sealed FROM pap_lock WHERE id = 1")
        lock = cur.fetchone()
        if lock is None or lock["sealed"] != 1:
            raise PapGateError("pap_lock not sealed")
