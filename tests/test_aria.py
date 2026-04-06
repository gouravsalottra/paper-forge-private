from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from paper_forge.aria import ARIA
from paper_forge.errors import LaneViolationError, PapGateError, PhaseTransitionError
from paper_forge.lanes import with_lane
from paper_forge.models import Agent, Phase
from paper_forge.writes import insert_forge_simulation, insert_pap_row


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "state.db"


@pytest.fixture
def aria(db_path: Path) -> ARIA:
    a = ARIA(db_path)
    a.init_schema()
    return a


def test_init_schema_idempotent(aria: ARIA) -> None:
    aria.init_schema()
    conn = aria.connect()
    try:
        cur = conn.cursor()
        cur.execute("SELECT value FROM aria_meta WHERE key = 'schema_version'")
        assert cur.fetchone()[0] == "1"
    finally:
        conn.close()


def test_phase_progression_commit_seal_forge_checkpoint(aria: ARIA) -> None:
    conn = aria.connect()
    try:
        assert aria.current_phase(conn) == Phase.INIT
        for nxt in (
            Phase.SCOUT,
            Phase.MINER,
            Phase.SIGMA,
            Phase.PAP_COMMIT,
        ):
            aria.transition_phase(conn, nxt)
        insert_pap_row(conn, "h1", "markets underreact")
        conn.commit()
        h = aria.commit_pap(conn)
        assert len(h) == 64
        aria.transition_phase(conn, Phase.PAP_SEAL, expected_from=Phase.PAP_COMMIT)
        seal = aria.seal_pap_lock(conn)
        assert len(seal) == 64
        aria.transition_phase(conn, Phase.FORGE, expected_from=Phase.PAP_SEAL)
        rid, chk = aria.checkpoint(conn, "after_forge_gate", {"ok": True})
        assert rid > 0
        assert len(chk) == 64
    finally:
        conn.close()


def test_pap_gate_blocks_forge(aria: ARIA) -> None:
    conn = aria.connect()
    try:
        for nxt in (
            Phase.SCOUT,
            Phase.MINER,
            Phase.SIGMA,
            Phase.PAP_COMMIT,
        ):
            aria.transition_phase(conn, nxt)
        insert_pap_row(conn, "h1", "hypothesis a")
        conn.commit()
        aria.commit_pap(conn)
        with pytest.raises(PapGateError):
            insert_forge_simulation(aria, conn, None, "print(1)")
    finally:
        conn.close()


def test_forge_after_seal(aria: ARIA) -> None:
    conn = aria.connect()
    try:
        for nxt in (
            Phase.SCOUT,
            Phase.MINER,
            Phase.SIGMA,
            Phase.PAP_COMMIT,
        ):
            aria.transition_phase(conn, nxt)
        insert_pap_row(conn, "h1", "hypothesis a")
        conn.commit()
        aria.commit_pap(conn)
        aria.transition_phase(conn, Phase.PAP_SEAL, expected_from=Phase.PAP_COMMIT)
        aria.seal_pap_lock(conn)
        aria.transition_phase(conn, Phase.FORGE, expected_from=Phase.PAP_SEAL)
        sid = insert_forge_simulation(aria, conn, "sim.py", "x = 1\n")
        assert sid > 0
        conn.commit()
    finally:
        conn.close()


def test_lane_violation(aria: ARIA) -> None:
    conn = aria.connect()
    try:

        def bad(c: sqlite3.Cursor) -> None:
            c.execute(
                "INSERT INTO pap_row (hypothesis_id, hypothesis_text, content_sha256) "
                "VALUES ('x','y','z')"
            )

        with pytest.raises(LaneViolationError):
            with_lane(conn, Agent.SCOUT, ["pap_row"], bad)
    finally:
        conn.close()


def test_transition_expected_from(aria: ARIA) -> None:
    conn = aria.connect()
    try:
        with pytest.raises(PhaseTransitionError):
            aria.transition_phase(conn, Phase.MINER, expected_from=Phase.SIGMA)
    finally:
        conn.close()
