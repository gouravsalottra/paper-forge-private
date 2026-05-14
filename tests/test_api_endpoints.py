from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from storage import blob

    blob.reset_mock_storage()
    from main import app

    return TestClient(app)


def test_session_api_create_scope_lock_run_results_and_fork(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    created = client.post("/api/sessions", json={"topic": "Do ETF flows predict sector ETF overnight returns?", "domain": "finance_economics", "file_refs": ["raw.csv"]})
    assert created.status_code == 200
    payload = created.json()
    session_id = payload["session_id"]
    assert payload["status"] == "initializing"
    assert payload["upload_urls"][0]["path"].startswith(f"sessions/{session_id}/uploads/")

    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    assert listed.json()[0]["next_action"] == "Resume draft"

    scoped = client.patch(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "ETF flow shocks and overnight sector returns",
            "hypothesis": "ETF flow shocks predict negative overnight returns.",
            "constraints": {"data": "yfinance plus uploaded ETF flow file"},
            "target_outcome": "paper",
        },
    )
    assert scoped.status_code == 200
    assert scoped.json() == {"status": "scope_confirmed"}

    blueprint = client.get(f"/api/sessions/{session_id}/blueprint")
    assert blueprint.status_code == 200
    body = blueprint.json()
    assert body["clarification_policy"]
    assert body["reviewer_gate"]["thresholds"]["average_minimum"] == 7.0
    assert body["repair_contract_template"]["max_cycles_per_issue"] == 3

    locked = client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"})
    assert locked.status_code == 200
    lock_payload = locked.json()
    assert lock_payload["blueprint_hash"]
    assert lock_payload["pap" + "_lock_id"]

    deviation = client.post(
        f"/api/sessions/{session_id}/blueprint/deviation",
        json={"field": "benchmark", "from": "SPY", "to": "XLF", "reason": "Sector-specific benchmark is required."},
    )
    assert deviation.status_code == 200
    assert deviation.json()["approval_required"] is True

    truth = client.get(f"/api/sessions/{session_id}/truth_contract")
    assert truth.status_code == 200
    assert truth.json()["state_map"]["Reviewer gate card"]["source"] == "reviewer_scores"

    run = client.post(f"/api/sessions/{session_id}/run", json={"approved": True})
    assert run.status_code == 200
    assert run.json()["run_started"] is True
    assert run.json()["estimated_minutes"] > 0

    artifacts = client.get(f"/api/sessions/{session_id}/artifacts")
    assert artifacts.status_code == 200
    assert any(item["path"].endswith("truth_contract.json") for item in artifacts.json()["artifacts"])

    results = client.get(f"/api/sessions/{session_id}/results")
    assert results.status_code == 200
    assert {"reviewer_scores", "integrity_artifacts", "deviation_count"} <= set(results.json())

    stream = client.get(f"/api/sessions/{session_id}/stream")
    assert stream.status_code == 200
    assert "text/event-stream" in stream.headers["content-type"]
    assert "phase_update" in stream.text

    forked = client.post(f"/api/sessions/{session_id}/fork", json={"changes": {"question": "Use weekly returns instead."}})
    assert forked.status_code == 200
    new_session_id = forked.json()["new_session_id"]
    child = client.get(f"/api/sessions/{new_session_id}").json()
    assert child["parent_run_id"] == session_id


def test_api_guide_and_data_aliases_exist(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    guide = client.get("/api/guide")
    assert guide.status_code == 200
    assert "research_package" in json.dumps(guide.json())

    preview = client.post("/api/data/preview", json={"data_mode": "upload"})
    assert preview.status_code == 200
    assert "preview" in preview.json()


def test_session_api_returns_structured_errors(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    missing = client.get("/api/sessions/not-a-real-session")
    assert missing.status_code == 404
    body = missing.json()
    assert body["error_code"] == "SESSION_NOT_FOUND"
    assert body["system_state"] == "not_found"
    assert body["available_actions"] == ["return_to_sessions"]
