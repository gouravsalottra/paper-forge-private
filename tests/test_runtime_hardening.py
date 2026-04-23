from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from agents.aria.aria import ARIAPipeline
from agents.hawk.hawk import HawkAgent
from agents.quill.quill import QuillAgent
from agents.scout.scout import ScoutAgent
from agents.sigma_job2 import SigmaJob2


def _make_pipeline(tmp_path: Path, run_id: str = "r-hardening") -> ARIAPipeline:
    return ARIAPipeline(db_path=str(tmp_path / "state.db"), run_id=run_id, paper_md_path=str(tmp_path / "PAPER.md"))


def test_aria_dispatches_real_miner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("PAPER.md").write_text("## Topic\nx\n## Hypothesis\ny\n", encoding="utf-8")
    pipeline = _make_pipeline(tmp_path)

    called = {"miner": False}

    def fake_run_miner(*, run_id: str, output_dir: str, source: str) -> dict:
        called["miner"] = True
        assert run_id == pipeline.run_id
        assert source == "wrds"
        return {"result_flag": "DONE", "source": source}

    import agents.miner.miner as miner_mod

    monkeypatch.setattr(miner_mod, "run_miner_pipeline", fake_run_miner, raising=True)
    out = pipeline._dispatch("MINER", "wrds", {})
    assert called["miner"] is True
    assert out["result_flag"] == "DONE"


def test_aria_dispatches_real_forge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("PAPER.md").write_text("## Topic\nx\n## Hypothesis\ny\n", encoding="utf-8")
    pipeline = _make_pipeline(tmp_path)

    # In production profile, FORGE defaults to modal backend.
    called = {"modal": False}
    monkeypatch.delenv("PAPER_FORGE_FORGE_BACKEND", raising=False)

    def fake_subprocess_run(cmd, cwd, check, capture_output, text):
        called["modal"] = True
        assert cmd[:3] == ["modal", "run", "agents/forge/modal_run.py"]
        out_dir = Path(cwd) / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "sim_results.json").write_text("[]", encoding="utf-8")
        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""
        return R()

    import agents.aria.aria as aria_mod
    monkeypatch.setattr(aria_mod.subprocess, "run", fake_subprocess_run, raising=True)
    out = pipeline._dispatch("FORGE", "forge_cluster", {})
    assert called["modal"] is True
    assert out["result_flag"] == "DONE"


def test_miner_requires_wrds_by_default() -> None:
    import agents.miner.miner as miner_mod

    with pytest.raises(RuntimeError):
        miner_mod.select_data_source(require_wrds=True, wrds_available=False)


def test_scout_filters_non_finance_citations(tmp_path: Path) -> None:
    paper = tmp_path / "PAPER.md"
    paper.write_text("## Topic\nCommodity futures\n## Hypothesis\nMomentum and concentration\n", encoding="utf-8")
    scout = ScoutAgent(run_id="r", paper_md_path=str(paper), output_dir=str(tmp_path))
    papers = [
        {
            "title": "Non-relativistic Conformal Field Theory in Momentum Space",
            "abstract": "particle physics",
            "year": 2024,
            "venue": "Physics Letters",
            "ids": {"ArXiv": "2403.01933"},
        },
        {
            "title": "Time Series Momentum",
            "abstract": "asset pricing futures momentum",
            "year": 2012,
            "venue": "Journal of Financial Economics",
            "ids": {"DOI": "10.1016/j.jfineco.2011.11.003"},
        },
    ]
    lit = scout._build_literature_map(papers)
    assert "Conformal Field Theory" not in lit
    assert "Time Series Momentum" in lit


def test_canonical_artifact_precedence_for_readers(tmp_path: Path) -> None:
    run_id = "r-canonical"
    base = tmp_path / "paper_memory" / run_id
    base.mkdir(parents=True)
    # conflicting artifacts
    (base / "codec_spec.md").write_text("CANONICAL_CODEC_SPEC", encoding="utf-8")
    (base / "codecspec.md").write_text("LEGACY_CODEC_SPEC", encoding="utf-8")
    (base / "literature_map.md").write_text("CANONICAL_LIT_MAP", encoding="utf-8")
    (base / "literaturemap.md").write_text("LEGACY_LIT_MAP", encoding="utf-8")
    (base / "stats_tables").mkdir()
    (base / "stats_tables" / "a.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    (base / "paper_draft_v1.tex").write_text("\\section{Methods}", encoding="utf-8")
    Path(tmp_path / "PAPER.md").write_text("## Topic\nx\n## Hypothesis\ny\n", encoding="utf-8")

    q = QuillAgent(run_id=run_id, output_dir=str(tmp_path / "paper_memory"), db_path=str(tmp_path / "state.db"), llm_client=lambda _p: "ok")
    h = HawkAgent(run_id=run_id, output_dir=str(tmp_path / "paper_memory"), db_path=str(tmp_path / "state.db"), llm_client=lambda _p: "{}")

    # run small in-memory DB for agents writing result flags
    with sqlite3.connect(tmp_path / "state.db") as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_results (run_id TEXT, agent TEXT, job TEXT, result_flag TEXT, created_at TEXT)"
        )
        conn.commit()

    src = q._load_sources()
    ctx = h._load_review_context()
    assert src["codec_spec"] == "CANONICAL_CODEC_SPEC"
    assert src["literature_map"] == "CANONICAL_LIT_MAP"
    assert ctx["codec_spec"] == "CANONICAL_CODEC_SPEC"


def test_pipeline_dry_through_enforces_quill_quality_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    Path("PAPER.md").write_text("## Topic\nx\n## Hypothesis\ny\n", encoding="utf-8")
    pipeline = _make_pipeline(tmp_path, run_id="r-dry-gate")

    with sqlite3.connect(pipeline.db_path) as conn:
        conn.execute(
            """
            INSERT INTO pap_lock (run_id, locked_at, locked_by, pap_sha256, forge_started_at)
            VALUES (?, datetime('now'), 'SIGMA_JOB1', 'abc', NULL)
            """,
            (pipeline.run_id,),
        )
        conn.commit()

    # Force QUILL runtime path to fail quality gate without any OpenAI calls.
    monkeypatch.setattr(QuillAgent, "_load_sources", lambda self: {"literature_map": "", "codec_spec": "", "pap": "", "stats_tables_csv": "", "codec_mismatch": "", "paper_md": ""})
    monkeypatch.setattr(QuillAgent, "_write_section", lambda self, _section, _sources: "Thin text.")

    original_dispatch = pipeline._dispatch

    def selective_dispatch(agent_name: str, server_name: str, context_config: dict) -> dict:
        if agent_name in {"SCOUT", "MINER", "SIGMA_JOB1", "FORGE", "SIGMA_JOB2"}:
            return {"result_flag": "DONE"}
        if agent_name == "CODEC":
            return {"result_flag": "PASS"}
        if agent_name == "HAWK":
            return {"result_flag": "APPROVED"}
        return original_dispatch(agent_name, server_name, context_config)

    monkeypatch.setattr(pipeline, "_dispatch", selective_dispatch)

    with pytest.raises(ValueError, match="QUILL quality gate failed"):
        pipeline.run()


def test_sigma_job2_markov_regime_aligns_lengths() -> None:
    # 9 observations can produce 8 smoothed probabilities with AR order=1.
    returns = [0.01, -0.02, 0.03, 0.00, 0.01, -0.01, 0.02, -0.03, 0.01]
    out = SigmaJob2._markov_regime(np.asarray(returns, dtype=float))
    assert "regime_mean_diff_p_value" in out


def test_miner_passport_sha256_matches_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib
    import json

    monkeypatch.chdir(tmp_path)

    import agents.miner.miner as miner_mod

    (tmp_path / "outputs").mkdir()
    import pandas as pd

    idx = pd.date_range("2020-01-01", periods=4, freq="D")
    fake_returns = pd.DataFrame(
        {
            "crude_oil_wti": [0.01, -0.01, 0.0, 0.02],
            "gold": [0.0, 0.001, -0.002, 0.003],
            "corn": [0.003, -0.001, 0.002, 0.001],
            "natural_gas": [0.02, -0.03, 0.01, 0.0],
            "copper": [0.004, 0.005, -0.003, 0.002],
        },
        index=idx,
    )
    fake_returns.index.name = "date"
    monkeypatch.setattr(miner_mod, "build_returns_frame", lambda: fake_returns, raising=True)

    miner_mod.run_miner_pipeline(run_id="r-passport", output_dir=str(tmp_path), source="yfinance")

    passport_path = Path("outputs/data_passport.json")
    assert passport_path.exists(), "DataPassport not written"

    passport = json.loads(passport_path.read_text())
    returns_path = Path(passport["file"])
    assert returns_path.exists(), f"Returns file not found: {returns_path}"

    actual_sha = hashlib.sha256(returns_path.read_bytes()).hexdigest()
    assert actual_sha == passport["sha256"], (
        f"DataPassport SHA-256 mismatch: stored={passport['sha256']} actual={actual_sha}"
    )
    assert passport["row_count"] > 0, "DataPassport row count is zero"
    assert "library_versions" in passport, "DataPassport missing library_versions"


def test_forge_episodes_match_paper_md() -> None:
    from agents.forge.full_run import run_full_sweep
    import inspect

    sig = inspect.signature(run_full_sweep)
    default_episodes = sig.parameters["n_episodes"].default
    assert default_episodes >= 500_000, (
        f"run_full_sweep default n_episodes={default_episodes} is below "
        f"PAPER.md requirement of 500,000"
    )
