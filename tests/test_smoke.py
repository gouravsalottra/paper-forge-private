from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest


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

