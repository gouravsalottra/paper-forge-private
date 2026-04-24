from __future__ import annotations

import json
from pathlib import Path

from agents.hawk.hawk import HawkAgent


def test_programmatic_review_flags_codec_and_min_effect(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_id = "r"
    run_dir = tmp_path / "paper_memory" / run_id
    stats_dir = run_dir / "stats_tables"
    stats_dir.mkdir(parents=True)

    (run_dir / "pap.md").write_text('{"claim_text":"Passive concentration should reduce Sharpe differential."}', encoding="utf-8")
    (run_dir / "codec_mismatch.md").write_text("## verdict: FAIL\nissue: mismatch", encoding="utf-8")
    (stats_dir / "primary_metric.csv").write_text(
        "sharpe_differential,meets_minimum_effect\n0.10,False\n",
        encoding="utf-8",
    )
    (stats_dir / "ttest_results.csv").write_text(
        "p_value,bonferroni_threshold\n0.12,0.0083\n",
        encoding="utf-8",
    )
    (stats_dir / "seed_consistency.csv").write_text("consistent\nFalse\n", encoding="utf-8")

    (tmp_path / "outputs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "outputs" / "sim_results.json").write_text(
        json.dumps([{"n_episodes": 2000}]),
        encoding="utf-8",
    )

    agent = HawkAgent(run_id=run_id, output_dir=str(tmp_path / "paper_memory"), db_path=str(tmp_path / "state.db"))
    with (tmp_path / "state.db").open("w", encoding="utf-8"):
        pass
    import sqlite3
    with sqlite3.connect(tmp_path / "state.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS agent_results (run_id TEXT, agent TEXT, job TEXT, result_flag TEXT, created_at TEXT)")
        conn.commit()

    out = agent.run()
    assert out["result_flag"] == "REVISION_REQUESTED"
    assert out["approved_for_quill"] is False
    checks = {i["check"] for i in out["mandatory_items"]}
    assert "CODEC mismatch" in checks
    assert "Minimum effect size" in checks
    assert "Sample size adequacy" in checks


def test_extract_codec_fail_items() -> None:
    agent = HawkAgent(run_id="r")
    context = {
        "codec_mismatch_text": "## verdict: FAIL\nissue: alpha mismatch\n- minimum_effect mismatch",
    }
    fail_items = agent._extract_codec_fail_items(context["codec_mismatch_text"])
    assert any("verdict: FAIL" in x for x in fail_items)
