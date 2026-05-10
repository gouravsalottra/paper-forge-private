from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from agents.aria.aria import ARIAPipeline
from agents.aria.exceptions import PipelineHaltError
from agents.logger import get_logger
from dashboard import main as dashboard_main


def _make_pipeline(tmp_path: Path, run_id: str = "r-obs") -> ARIAPipeline:
    return ARIAPipeline(db_path=str(tmp_path / "state.db"), run_id=run_id, paper_md_path=str(tmp_path / "PAPER.md"))


def test_structured_logger_emits_json(capfd: pytest.CaptureFixture[str]) -> None:
    logger = get_logger("TEST_AGENT", run_id=None)
    logger.info("test event", extra={"phase": "SCOUT"})
    out = capfd.readouterr().err or capfd.readouterr().out
    line = out.strip().splitlines()[-1]
    parsed = json.loads(line)
    assert parsed["agent"] == "TEST_AGENT"
    assert parsed["event"] == "test event"
    assert parsed["phase"] == "SCOUT"


def test_structured_logger_writes_to_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    logger = get_logger("HAWK", run_id="test-run-001")
    logger.warning("review cycle 1")
    p = tmp_path / "runs" / "test-run-001" / "pipeline.log"
    assert p.exists()
    line = p.read_text(encoding="utf-8").splitlines()[0]
    parsed = json.loads(line)
    assert parsed["level"] == "WARNING"


def test_dashboard_shows_all_runs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    db = tmp_path / "state.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE pipeline_runs (run_id TEXT, status TEXT, started_at TEXT, finished_at TEXT, completed_at TEXT)")
        conn.execute("CREATE TABLE phases (run_id TEXT, phase_name TEXT, status TEXT)")
        conn.execute("CREATE TABLE token_limits (run_id TEXT, total_spent_usd REAL)")
        conn.execute("INSERT INTO pipeline_runs VALUES ('r1','done','2026-01-01',NULL,NULL)")
        conn.execute("INSERT INTO pipeline_runs VALUES ('r2','failed','2026-01-02',NULL,NULL)")
        conn.execute("INSERT INTO token_limits VALUES ('r1', 1.23)")
        conn.execute("INSERT INTO token_limits VALUES ('r2', 0.50)")
        conn.commit()
    monkeypatch.setattr("sys.argv", ["dashboard.py", "--db", str(db)])
    dashboard_main()
    out = capsys.readouterr().out
    assert "r1" in out and "r2" in out


def test_hawk_fixer_cycle_halts_at_max(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _make_pipeline(tmp_path, run_id="r-hawk-cap")

    calls = {"hawk": 0}

    def fake_dispatch(agent, *_a, **_k):
        if agent == "HAWK":
            calls["hawk"] += 1
            return {"result_flag": "REVISION_REQUESTED", "routing": {"mandatory_items": []}, "approved_for_quill": False}
        if agent == "FIXER":
            return {"result_flag": "ESCALATE"}
        return {"result_flag": "DONE"}

    monkeypatch.setattr(p, "_dispatch", fake_dispatch)
    with pytest.raises(PipelineHaltError):
        p._run_hawk_loop(max_cycles=3)

    with sqlite3.connect(p.db_path) as conn:
        row = conn.execute(
            "SELECT value_json FROM checkpoints WHERE run_id=? AND phase_name='HAWK' AND checkpoint_key='hawk_fixer_cycles'",
            (p.run_id,),
        ).fetchone()
    assert row is not None
    assert int(json.loads(row[0])["count"]) == 3
    assert calls["hawk"] == 3


def test_hawk_fixer_cycle_counter_persists_across_resume(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _make_pipeline(tmp_path, run_id="r-hawk-resume")

    state = {"hawk_calls": 0}

    def fake_dispatch(agent, *_a, **_k):
        if agent == "HAWK":
            state["hawk_calls"] += 1
            return {"result_flag": "REVISION_REQUESTED", "routing": {"mandatory_items": []}, "approved_for_quill": False}
        if agent == "FIXER":
            return {"result_flag": "DONE"}
        return {"result_flag": "DONE"}

    monkeypatch.setattr(p, "_dispatch", fake_dispatch)
    with pytest.raises(PipelineHaltError):
        p._run_hawk_loop(max_cycles=2)

    # Resume with same run_id; should continue from checkpoint and halt at 3.
    p2 = ARIAPipeline(db_path=p.db_path, run_id=p.run_id, paper_md_path=p.paper_md_path)
    monkeypatch.setattr(p2, "_dispatch", fake_dispatch)
    with pytest.raises(PipelineHaltError):
        p2._run_hawk_loop(max_cycles=3)

    with sqlite3.connect(p.db_path) as conn:
        row = conn.execute(
            "SELECT value_json FROM checkpoints WHERE run_id=? AND phase_name='HAWK' AND checkpoint_key='hawk_fixer_cycles'",
            (p.run_id,),
        ).fetchone()
    assert row is not None
    assert int(json.loads(row[0])["count"]) == 3
