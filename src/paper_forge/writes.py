from __future__ import annotations

import sqlite3

from paper_forge.aria import ARIA
from paper_forge.lanes import with_lane
from paper_forge.models import Agent
from paper_forge.provenance import sha256_text

__all__ = ["insert_pap_row", "insert_forge_simulation"]


def insert_pap_row(
    conn: sqlite3.Connection,
    hypothesis_id: str,
    hypothesis_text: str,
) -> int:
    """SIGMA lane: preregistered hypothesis row."""

    h = sha256_text(hypothesis_text)

    def work(c: sqlite3.Cursor) -> None:
        c.execute(
            """INSERT INTO pap_row (hypothesis_id, hypothesis_text, content_sha256)
               VALUES (?, ?, ?)""",
            (hypothesis_id, hypothesis_text, h),
        )

    with_lane(conn, Agent.SIGMA, ["pap_row"], work)
    cur = conn.cursor()
    cur.execute("SELECT last_insert_rowid()")
    return int(cur.fetchone()[0])


def insert_forge_simulation(
    aria: ARIA,
    conn: sqlite3.Connection,
    code_path: str | None,
    code_text: str,
) -> int:
    """FORGE lane: blocked until PAP commit + pap_lock sealed."""

    aria.assert_forge_gate(conn)
    code_sha = sha256_text(code_text)

    def work(c: sqlite3.Cursor) -> None:
        c.execute(
            "INSERT INTO forge_simulation (code_path, code_sha256) VALUES (?, ?)",
            (code_path, code_sha),
        )

    with_lane(conn, Agent.FORGE, ["forge_simulation"], work)
    cur = conn.cursor()
    cur.execute("SELECT last_insert_rowid()")
    return int(cur.fetchone()[0])
