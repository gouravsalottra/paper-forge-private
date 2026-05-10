from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from agents.aria.aria import ARIAPipeline


@pytest.mark.skipif(
    os.getenv("PAPERFORGE_RUN_SMOKE", "0") != "1",
    reason="Set PAPERFORGE_RUN_SMOKE=1 to run end-to-end smoke test.",
)
def test_smoke_pipeline_end_to_end() -> None:
    run_id = "pf-smoke-test"
    repo = Path(__file__).resolve().parents[1]

    subprocess.run(
        [sys.executable, "run_aria_pipeline.py", "--resume", run_id, "--from", "SCOUT"],
        cwd=repo,
        check=True,
    )

    base = repo / "paper_memory" / run_id
    assert (base / "literature_map.md").exists()
    assert (base / "pap.md").exists()
    stats_dir = base / "stats_tables"
    assert stats_dir.exists() and any(stats_dir.iterdir())
    draft = base / "paper_draft_v1.tex"
    assert draft.exists()

    with sqlite3.connect(repo / "state.db") as conn:
        rows = conn.execute(
            "SELECT phase_name, status FROM phases WHERE run_id=?",
            (run_id,),
        ).fetchall()
    by_phase = {name: status for name, status in rows}
    expected = ["SCOUT", "MINER", "SIGMA_JOB1", "FORGE", "SIGMA_JOB2", "CODEC", "QUILL", "HAWK"]
    for phase in expected:
        assert by_phase.get(phase) == "done"

    text = draft.read_text(encoding="utf-8")
    assert "\\begin{document}" in text
    assert "\\end{document}" in text


def test_smoke_pipeline_mock_no_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run_id = "pf-smoke-mock"
    paper_path = tmp_path / "PAPER.md"
    paper_path.write_text("# Mock Protocol\n", encoding="utf-8")

    pipeline = ARIAPipeline(
        db_path=str(tmp_path / "state.db"),
        run_id=run_id,
        paper_md_path=str(paper_path),
    )

    calls: list[str] = []

    def fake_dispatch(agent_name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(agent_name)
        if agent_name == "HAWK":
            return {"result_flag": "DONE", "approved_for_quill": True}
        if agent_name == "CODEC":
            return {"result_flag": "PASS", "approved_for_quill": True}
        return {"result_flag": "DONE"}

    monkeypatch.setattr(pipeline, "_dispatch", fake_dispatch)
    monkeypatch.setattr(pipeline, "_check_forge_gate", lambda: None)
    monkeypatch.setattr(pipeline, "_hawk_is_approved_for_quill", lambda: True)
    sequence = iter(["SCOUT", "MINER", "SIGMA_JOB1", "FORGE", "SIGMA_JOB2", "CODEC", "HAWK"])
    monkeypatch.setattr(pipeline, "_next_tool_call", lambda: next(sequence, None))
    monkeypatch.setattr(
        pipeline,
        "_paper_is_publishable",
        lambda path=None: all(pipeline._phase_status(p) == "done" for p in pipeline.PHASE_ORDER),
    )

    pipeline.run()

    with sqlite3.connect(pipeline.db_path) as conn:
        rows = conn.execute(
            "SELECT phase_name, status FROM phases WHERE run_id=?",
            (run_id,),
        ).fetchall()

    by_phase = {name: status for name, status in rows}
    expected = ["SCOUT", "MINER", "SIGMA_JOB1", "FORGE", "SIGMA_JOB2", "CODEC", "QUILL", "HAWK"]
    for phase in expected:
        assert by_phase.get(phase) == "done"

    for phase in ["SCOUT", "MINER", "SIGMA_JOB1", "FORGE", "SIGMA_JOB2", "CODEC", "HAWK", "QUILL"]:
        assert phase in calls
