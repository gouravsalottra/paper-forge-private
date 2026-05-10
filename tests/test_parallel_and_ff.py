from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import pytest

from agents.aria.aria import ARIAPipeline
from agents.aria.exceptions import PipelineHaltError, ServerUnavailableError
from agents.miner.sources import wrds_src
from agents.scout.scout import ScoutAgent


def _make_pipeline(tmp_path: Path, run_id: str = "r-par") -> ARIAPipeline:
    return ARIAPipeline(db_path=str(tmp_path / "state.db"), run_id=run_id, paper_md_path=str(tmp_path / "PAPER.md"))


def test_parallel_scout_miner_both_complete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _make_pipeline(tmp_path)

    def fake_dispatch(agent, *_args, **_kwargs):
        time.sleep(0.1)
        return {"result_flag": "DONE", "agent": agent}

    monkeypatch.setattr(p, "_dispatch", fake_dispatch)
    t0 = time.perf_counter()
    out = p._run_phase_parallel(["SCOUT", "MINER"])
    elapsed = time.perf_counter() - t0
    assert out["SCOUT"]["result_flag"] == "DONE"
    assert out["MINER"]["result_flag"] == "DONE"
    assert elapsed < 0.5


def test_parallel_failure_raises_pipeline_halt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = _make_pipeline(tmp_path)

    def fake_dispatch(agent, *_args, **_kwargs):
        if agent == "SCOUT":
            raise RuntimeError("boom")
        return {"result_flag": "DONE"}

    monkeypatch.setattr(p, "_dispatch", fake_dispatch)
    with pytest.raises(PipelineHaltError):
        p._run_phase_parallel(["SCOUT", "MINER"])


def test_scout_deduplicates_same_doi(tmp_path: Path) -> None:
    s = ScoutAgent(run_id="r", paper_md_path=str(tmp_path / "PAPER.md"), output_dir=str(tmp_path))
    papers = [
        {"title": "A", "doi": "10.1/x", "source": "semscholar", "relevance_score": 1},
        {"title": "B", "doi": "10.1/x", "source": "arxiv", "relevance_score": 2},
        {"title": "C", "doi": "10.1/y", "source": "semscholar", "relevance_score": 3},
    ]
    out = s.deduplicate_papers(papers)
    assert len(out) == 2


def test_scout_deduplicates_same_title_different_source(tmp_path: Path) -> None:
    s = ScoutAgent(run_id="r", paper_md_path=str(tmp_path / "PAPER.md"), output_dir=str(tmp_path))
    papers = [
        {"title": "Time-Series Momentum!", "doi": "", "source": "arxiv", "relevance_score": 1},
        {"title": "time series momentum", "doi": "10.1/abc", "source": "semscholar", "relevance_score": 2},
    ]
    out = s.deduplicate_papers(papers)
    assert len(out) == 1
    assert out[0]["source"] == "semscholar"


def test_scout_flags_preprints_as_non_peer_reviewed(tmp_path: Path) -> None:
    s = ScoutAgent(run_id="r", paper_md_path=str(tmp_path / "PAPER.md"), output_dir=str(tmp_path))
    papers = [{"title": "x", "source": "arxiv", "doi": "", "citation_count": 1}]
    out = s.filter_by_citation_quality(papers, min_citations=0)
    assert out[0]["peer_reviewed"] is False
    assert "citation_note" in out[0]


def test_ff_factors_fall_back_to_kenneth_french(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_FORGE_MINER_SOURCE", "yfinance")

    class DummyConn:
        def __init__(self, *args, **kwargs):
            raise ConnectionError("down")

    monkeypatch.setattr(wrds_src, "wrds", type("W", (), {"Connection": DummyConn}))
    monkeypatch.setattr(
        wrds_src.web,
        "DataReader",
        lambda *_a, **_k: {0: pd.DataFrame({"Mkt-RF": [1.0], "SMB": [2.0], "HML": [3.0], "RF": [0.1]}, index=pd.to_datetime(["2020-01-02"]))},
    )
    df, meta = wrds_src.fetch_ff_factors("2020-01-01", "2020-12-31")
    assert {"mkt_rf", "smb", "hml", "rf"}.issubset(set(df.columns))
    assert meta["ff_source"] == "kenneth_french_library"


def test_ff_factors_wrds_unavailable_no_fallback_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_FORGE_MINER_SOURCE", "wrds")

    class DummyConn:
        def __init__(self, *args, **kwargs):
            raise ConnectionError("down")

    monkeypatch.setattr(wrds_src, "wrds", type("W", (), {"Connection": DummyConn}))
    with pytest.raises(ServerUnavailableError):
        wrds_src.fetch_ff_factors("2020-01-01", "2020-12-31")
