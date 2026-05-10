from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import pytest

from agents.forge.adapters.none_adapter import NoneAdapter
from agents.forge.adapters.registry import ADAPTER_REGISTRY
from agents.miner.connectors.registry import CONNECTOR_REGISTRY, get_connector
from agents.sigma.tests.newey_west_hac import NeweyWestHAC
from agents.sigma.tests.registry import TEST_REGISTRY, get_test


def test_all_connectors_registered() -> None:
    for key in ["yfinance", "wrds_futures", "wrds_crsp", "fred", "sec_edgar", "upload"]:
        assert key in CONNECTOR_REGISTRY


def test_unknown_connector_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown data source"):
        get_connector("bloomberg_terminal_v999")


def test_upload_connector_reads_csv(tmp_path: Path) -> None:
    uploads = tmp_path / "data" / "uploads"
    uploads.mkdir(parents=True, exist_ok=True)
    p = uploads / "test_data.csv"
    p.write_text("date,x\n2020-01-01,1\n2020-01-02,2\n", encoding="utf-8")

    conn = get_connector("upload")
    df, cert = conn.fetch(
        dataset="test_data",
        fields=["date", "x"],
        date_range=("2020-01-01", "2020-12-31"),
        filters=[],
        output_dir=tmp_path,
    )
    assert not df.empty
    assert "sha256" in cert and cert["sha256"]


def test_all_stat_tests_registered() -> None:
    expected = {
        "newey_west_hac",
        "garch_11",
        "bootstrap_ci",
        "deflated_sharpe",
        "fama_macbeth",
        "regime_switching",
        "markov_switching",
        "descriptive_stats",
        "placebo_test",
        "out_of_sample_r2",
    }
    assert expected.issubset(TEST_REGISTRY.keys())


def test_unknown_stat_test_raises() -> None:
    with pytest.raises(ValueError, match="Unknown statistical test"):
        get_test("p_hacking_machine")


def test_newey_west_hac_runs_on_sample_data() -> None:
    data = pd.DataFrame({"returns": [0.01, -0.02, 0.03, 0.01, -0.01, 0.02, -0.01]})
    out = NeweyWestHAC().run(data, seed=1337, params={})
    for key in ["test_name", "p_value", "statistic", "significant"]:
        assert key in out


def test_none_adapter_is_immediate_passthrough(tmp_path: Path) -> None:
    t0 = time.perf_counter()
    out = NoneAdapter().run(params={}, output_dir=tmp_path, seeds=[1337])
    elapsed = time.perf_counter() - t0
    assert out["skipped"] is True
    assert elapsed < 0.1


def test_compute_registry_has_rl_none_backtest_event_study() -> None:
    assert {"rl", "none", "backtest", "event_study"}.issubset(ADAPTER_REGISTRY.keys())


def test_miner_legacy_mode_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import agents.miner.miner as miner_mod

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(miner_mod, "build_returns_frame", lambda: pd.DataFrame({"x": [0.1, 0.2]}), raising=True)
    monkeypatch.setattr(miner_mod, "write_data_passport", lambda _df: {"ok": True}, raising=True)
    out = miner_mod.run_miner_pipeline(run_id="r-miner", output_dir=str(tmp_path / "runs"), source="yfinance")
    assert out["result_flag"] == "DONE"
    assert (tmp_path / "outputs" / "commodity_returns.csv").exists()


def test_sigma_legacy_mode_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.statsrun.statsrun_job import SigmaJob2

    monkeypatch.chdir(tmp_path)
    out_dir = tmp_path / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    sim = []
    for concentration, base in [(0.1, 0.02), (0.3, 0.005), (0.6, -0.015)]:
        for seed, bump in [(1337, 0.0), (42, 0.002), (9999, -0.001)]:
            sim.append(
                {
                    "concentration": concentration,
                    "seed": seed,
                    "sharpe": float(base * 10 + bump * 5),
                    "mean_reward": float(base + bump),
                    "n_episodes": 2000,
                }
            )
    (out_dir / "sim_results.json").write_text(json.dumps(sim), encoding="utf-8")
    out = SigmaJob2(run_id="r-sigma", output_dir=str(tmp_path / "runs"), db_path=str(tmp_path / "pipeline.db")).run()
    assert out["result_flag"] == "DONE"
    stats_dir = tmp_path / "runs" / "r-sigma" / "stats_tables"
    assert stats_dir.exists()
