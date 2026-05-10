from __future__ import annotations

import json
import logging
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.conductor.exceptions import ComputeGateError, WriterGateError
from agents.conductor.conductor import ConductorPipeline
from agents.conductor.phase_runner import PhaseRunner
from agents.conductor.retry import retry
from init_db import init_db
from mcp_servers.arxiv_server import mcp, search_arxiv


def test_phase_runner_retries_on_transient_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    run_id = "r-phase-runner"
    with sqlite3.connect(db) as conn:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute("INSERT INTO pipeline_runs (run_id, started_at, status) VALUES (?, ?, ?)", (run_id, now, "running"))
        conn.execute("INSERT INTO phases (run_id, phase_name, status) VALUES (?, ?, ?)", (run_id, "LITERATURE", "pending"))
        conn.commit()

    runner = PhaseRunner(str(db), run_id, logging.getLogger("test"))
    calls = {"n": 0}
    monkeypatch.setattr("time.sleep", lambda _s: None)

    def dispatch(_phase: str):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient")
        return {"ok": True}

    out = runner.run_phase("LITERATURE", dispatch, timeout_seconds=5, max_retries=3)
    assert out["status"] == "done"
    assert out["attempt"] == 3


def test_phase_runner_does_not_retry_compute_gate_error(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    run_id = "r-phase-gate"
    with sqlite3.connect(db) as conn:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        conn.execute("INSERT INTO pipeline_runs (run_id, started_at, status) VALUES (?, ?, ?)", (run_id, now, "running"))
        conn.execute("INSERT INTO phases (run_id, phase_name, status) VALUES (?, ?, ?)", (run_id, "COMPUTE", "pending"))
        conn.commit()
    runner = PhaseRunner(str(db), run_id, logging.getLogger("test"))
    with pytest.raises(ComputeGateError):
        runner.run_phase("COMPUTE", lambda _p: (_ for _ in ()).throw(ComputeGateError("x")), timeout_seconds=1)


def test_retry_decorator_retries_on_specified_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("time.sleep", lambda _s: None)
    calls = {"n": 0}

    @retry(max_attempts=3, backoff_base=2, exceptions=(TimeoutError,))
    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise TimeoutError("tmp")
        return "ok"

    assert fn() == "ok"
    assert calls["n"] == 3


def test_results_gate_table_exists_after_init(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(results_gate)")]
    for c in ["run_id", "p_value_passes", "seed_consistent", "codeaudit_clean", "last_updated"]:
        assert c in cols


def test_results_valid_is_false_when_any_condition_false(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO results_gate (run_id, p_value_passes, seed_consistent, codeaudit_clean, last_updated)
            VALUES ('r1', 1, 1, 0, ?)
            """,
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
        )
        row = conn.execute("SELECT results_valid FROM results_gate WHERE run_id='r1'").fetchone()
    assert bool(row[0]) is False


def test_results_valid_is_true_when_all_conditions_met(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO results_gate (run_id, p_value_passes, seed_consistent, codeaudit_clean, last_updated)
            VALUES ('r2', 1, 1, 1, ?)
            """,
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),),
        )
        row = conn.execute("SELECT results_valid FROM results_gate WHERE run_id='r2'").fetchone()
    assert bool(row[0]) is True


def test_arxiv_mcp_server_has_search_tool() -> None:
    names = [t.name for t in mcp.tools]
    assert "search_arxiv" in names
    assert "fetch_arxiv_paper" in names


def test_arxiv_mcp_search_returns_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Author:
        def __init__(self, name: str):
            self.name = name

    class _Paper:
        def __init__(self, i: int):
            self.title = f"T{i}"
            self.authors = [_Author("A")]
            self.summary = "S"
            self.entry_id = f"id{i}"
            self.published = datetime.now(timezone.utc)
            self.doi = "10.1/x"
            self.pdf_url = "http://x"
            self.categories = ["q-fin"]

    class _Client:
        def results(self, _search):
            return [_Paper(1), _Paper(2)]

    monkeypatch.setattr("mcp_servers.arxiv_server.arxiv.Client", lambda: _Client())
    out = search_arxiv("momentum finance", max_results=2)
    rows = json.loads(out)
    assert len(rows) == 2
    req = {"title", "authors", "abstract", "arxiv_id", "published", "doi", "pdf_url", "categories", "peer_reviewed"}
    assert req.issubset(rows[0].keys())


def test_writer_gate_blocks_when_results_invalid(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    p = tmp_path / "PAPER.md"
    p.write_text("## x\nx\n", encoding="utf-8")
    pipe = ConductorPipeline(db_path=str(db), run_id="r-writer-gate", paper_md_path=str(p))
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO results_gate (run_id, p_value_passes, seed_consistent, codeaudit_clean, last_updated) VALUES (?, 1, 1, 0, ?)",
            ("r-writer-gate", datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        conn.commit()
    with pytest.raises(WriterGateError):
        pipe._check_writer_gate()
