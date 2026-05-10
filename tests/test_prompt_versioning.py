from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from agents.reviewer.reviewer import ReviewerAgent
from init_db import init_db


def test_prompt_files_exist_for_all_llm_agents() -> None:
    required = [
        Path("prompts/codeaudit.md"),
        Path("prompts/specaudit.md"),
        Path("prompts/autorepair.md"),
        Path("prompts/writer.md"),
        Path("prompts/reviewer.md"),
    ]
    for p in required:
        assert p.exists(), f"Missing prompt file: {p}"
        assert p.stat().st_size > 100, f"Prompt file too small: {p}"


def test_prompt_loader_returns_text_and_sha256() -> None:
    from agents.prompt_loader import load_prompt

    text, sha256 = load_prompt("reviewer")
    assert isinstance(text, str) and len(text) > 0
    assert isinstance(sha256, str) and len(sha256) == 64

    changed_sha = hashlib.sha256((text + "\nchanged").encode()).hexdigest()
    assert changed_sha != sha256


def test_agent_results_schema_has_prompt_sha256(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(agent_results)")]
    assert "prompt_sha256" in cols


def test_prompt_hash_recorded_in_agent_results(tmp_path: Path) -> None:
    run_id = "r-prompt-hash"
    db = tmp_path / "pipeline.db"
    init_db(db)

    out = tmp_path / "runs" / run_id
    out.mkdir(parents=True, exist_ok=True)
    (out / "pap.md").write_text('{"claim_text":"test hypothesis"}', encoding="utf-8")
    (out / "codec_mismatch.md").write_text("verdict: PASS\n", encoding="utf-8")
    stats = out / "stats_tables"
    stats.mkdir(parents=True, exist_ok=True)
    (stats / "primary_metric.csv").write_text(
        "sharpe_differential,meets_minimum_effect\n-0.2,True\n", encoding="utf-8"
    )
    (stats / "ttest_results.csv").write_text(
        "p_value,bonferroni_threshold\n0.01,0.008333\n", encoding="utf-8"
    )
    (out / "seed_consistency.csv").write_text("consistent\nTrue\n", encoding="utf-8")
    Path("outputs").mkdir(exist_ok=True)
    Path("outputs/sim_results.json").write_text(
        json.dumps([{"n_episodes": 500000}]), encoding="utf-8"
    )

    agent = ReviewerAgent(run_id=run_id, db_path=str(db), output_dir=str(tmp_path / "runs"))
    agent.run(revision_number=1)

    with sqlite3.connect(db) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(agent_results)")]
        if "agent" in cols:
            row = conn.execute(
                "SELECT prompt_sha256 FROM agent_results WHERE run_id=? AND agent='REVIEWER' ORDER BY id DESC LIMIT 1",
                (run_id,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT prompt_sha256 FROM agent_results WHERE run_id=? AND agent_name='REVIEWER' ORDER BY created_at DESC LIMIT 1",
                (run_id,),
            ).fetchone()
    assert row is not None
    assert row[0] is not None
    assert len(row[0]) == 64
