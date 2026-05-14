from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from tests.test_topic4_e2e_research_flow import MENTOR_TOPICS


EXPECTED_EXECUTION = {
    "tail_risk_momentum": {
        "method": "backtest",
        "evidence": "yfinance",
        "compute_suffix": "06_compute/method_outputs/backtest_results.json",
        "must_contain": ["Tail Risk Conditioning", "Sharpe", "switching threshold"],
        "forbidden": ["flash crash", "earnings call", "SEC filing"],
    },
    "sec_filing_language": {
        "method": "text_analysis",
        "evidence": "edgar_yfinance",
        "compute_suffix": "06_compute/method_outputs/text_analysis_results.json",
        "must_contain": ["SEC", "embedding", "overnight volatility"],
        "forbidden": ["flash crash", "momentum strategy allocation"],
    },
    "earnings_call_sentiment": {
        "method": "text_analysis",
        "evidence": "text_corpus",
        "compute_suffix": "06_compute/method_outputs/text_analysis_results.json",
        "must_contain": ["earnings", "sentiment", "overnight gap"],
        "forbidden": ["flash crash", "SEC filing risk language"],
    },
    "agent_flash_crash": {
        "method": "agent_based_model",
        "evidence": "simulation_generated",
        "compute_suffix": "06_compute/method_outputs/simulation_results.json",
        "must_contain": ["flash crash", "agent-based", "188.0 bps"],
        "forbidden": ["earnings call sentiment", "ETF NAV half-life"],
    },
    "etf_arbitrage_half_life": {
        "method": "regression",
        "evidence": "yfinance",
        "compute_suffix": "06_compute/method_outputs/regression_results.json",
        "must_contain": ["ETF", "half-life", "mean-reversion"],
        "forbidden": ["flash crash", "earnings call"],
    },
}


def _client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "general-research.db"))
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from storage import blob

    blob.reset_mock_storage()
    from main import app

    return TestClient(app)


def _launch(client: TestClient, topic: str) -> str:
    created = client.post("/runs/create", json={"topic": topic, "approach": "confirmatory", "output_format": "paper"})
    assert created.status_code == 200
    return created.json()["run_id"]


def test_all_mentor_topics_execute_with_method_specific_research_contracts(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    from storage.blob import read_artifact

    for key, topic in MENTOR_TOPICS.items():
        expected = EXPECTED_EXECUTION[key]
        run_id = _launch(client, topic)

        blueprint = client.get(f"/api/sessions/{run_id}/blueprint").json()
        assert blueprint["method_family"] == expected["method"], key
        assert blueprint["evidence_source"] == expected["evidence"], key

        status = client.get(f"/runs/{run_id}/status").json()
        assert status["status"] == "paper_unlocked", key
        assert status["reviewer_gate"]["passed"] is True, key

        artifacts = client.get(f"/runs/{run_id}/artifacts").json()["artifacts"]
        paths = {item["path"] for item in artifacts}
        assert any(path.endswith("00_runspec/execution_profile.json") for path in paths), key
        assert any(path.endswith("00_runspec/agent_context.json") for path in paths), key
        assert any(path.endswith(expected["compute_suffix"]) for path in paths), key
        assert any(path.endswith("07_statistics/research_findings.json") for path in paths), key
        assert any(path.endswith("10_verification/paper_code_verification.json") for path in paths), key
        assert any(path.endswith("11_paper/final.tex") for path in paths), key

        compute = json.loads(read_artifact(run_id, expected["compute_suffix"]))
        assert compute["method_family"] == expected["method"], key
        assert compute["evidence_source"] == expected["evidence"], key
        assert compute["blueprint_topic"] == topic, key
        assert compute["result_schema"] != "agent_flash_crash_demo", key

        agent_context = json.loads(read_artifact(run_id, "00_runspec/agent_context.json"))
        assert agent_context["method_family"] == expected["method"], key
        assert agent_context["evidence_source"] == expected["evidence"], key
        assert agent_context["agents"]["Method / Compute Agent"]["skills"], key
        assert expected["method"] in agent_context["agents"]["Method / Compute Agent"]["skills"], key

        findings = json.loads(read_artifact(run_id, "07_statistics/research_findings.json"))
        assert findings["method_family"] == expected["method"], key
        assert findings["claim_scope"], key
        assert findings["primary_numbers"], key

        verifier = json.loads(read_artifact(run_id, "10_verification/paper_code_verification.json"))
        assert verifier["status"] == "verified", key
        assert verifier["numbers_verified"] is True, key
        assert verifier["method_family"] == expected["method"], key

        frontend_findings = client.get(f"/runs/{run_id}/findings").json()["findings"]
        assert frontend_findings["method_family"] == expected["method"], key
        assert frontend_findings["claim_scope"], key
        assert frontend_findings["key_numbers"], key

        frontend_paper = client.get(f"/runs/{run_id}/paper").json()["paper"]["thrivarc"]
        assert frontend_paper["abstract_stub"], key
        assert frontend_paper["data_description"], key
        assert expected["method"] in frontend_paper["robustness"], key

        paper = read_artifact(run_id, "11_paper/final.tex").decode("utf-8")
        for phrase in expected["must_contain"]:
            assert phrase.lower() in paper.lower(), (key, phrase)
        for phrase in expected["forbidden"]:
            assert phrase.lower() not in paper.lower(), (key, phrase)
        assert "Writer is last and never invents numbers" in paper, key
