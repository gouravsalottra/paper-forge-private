from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "resumption.db"))
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from storage import blob

    blob.reset_mock_storage()
    from main import app

    return TestClient(app)


def _insert_session(session_id: str, status: str, *, topic: str = "Topic", parent: str | None = None) -> None:
    from api import sessions

    with sessions._with_conn() as conn:
        sessions._execute(
            conn,
            "INSERT INTO sessions (id, topic, domain, research_type, status, created_at, updated_at, parent_run_id, credits_spent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, topic, "finance_economics", "confirmatory", status, sessions._now(), sessions._now(), parent, 0),
        )
        sessions._execute(
            conn,
            "INSERT INTO blueprints (id, session_id, content, status, created_at) VALUES (?, ?, ?, ?, ?)",
            ("bp-" + session_id, session_id, json.dumps({"question": topic, "method": "regression", "data_source": "upload"}), "draft", sessions._now()),
        )
        sessions._phase_status(conn, session_id, "Research Architect", "pending", "Pending clarification.")
        conn.commit()


def test_session_history_next_actions_cover_resumption_states(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    cases = {
        "draft": "Resume draft",
        "needs_clarification": "Answer clarification",
        "evidence_blocked": "Review data preview",
        "scope_confirmed": "Approve Blueprint",
        "running": "Running: Research Architect",
        "failed_resumable": "Review failure",
        "failed_terminal": "Download or fork package",
        "paper_unlocked": "Download paper",
    }
    for status in cases:
        _insert_session("s-" + status, status, topic=status)

    response = client.get("/api/sessions")
    assert response.status_code == 200
    by_status = {item["status"]: item for item in response.json()}
    for status, next_action in cases.items():
        assert by_status[status]["next_action"] == next_action
        assert by_status[status]["resume_route"].startswith("/")


def test_resume_endpoint_routes_to_correct_screen(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    _insert_session("resume-running", "running")

    response = client.get("/api/sessions/resume-running/resume")
    assert response.status_code == 200
    assert response.json()["route"] == "/run/resume-running"
    assert response.json()["stream"] == "/api/sessions/resume-running/stream"


def test_sse_reconnect_replays_last_ten_events(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    _insert_session("resume-events", "running")
    from api import sessions

    with sessions._with_conn() as conn:
        for idx in range(12):
            sessions._execute(
                conn,
                "INSERT INTO session_events (id, session_id, event_type, agent, status, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (f"event-{idx}", "resume-events", "phase_update", "Agent", "running", json.dumps({"n": idx}), f"2026-05-14T00:{idx:02d}:00+00:00"),
            )
        conn.commit()

    stream = client.get("/api/sessions/resume-events/stream")
    assert stream.status_code == 200
    assert '"n": 2' in stream.text
    assert '"n": 11' in stream.text
    assert '"n": 0' not in stream.text


def test_fork_does_not_modify_parent_and_compare_returns_diff(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/sessions", json={"topic": "Original question"}).json()
    parent_id = created["session_id"]
    client.patch(f"/api/sessions/{parent_id}/scope", json={"research_type": "confirmatory", "focus_question": "Original question", "hypothesis": "Original hypothesis"})

    child_id = client.post(f"/api/sessions/{parent_id}/fork", json={"changes": {"question": "New weekly question", "method": "event_study"}}).json()["new_session_id"]
    parent = client.get(f"/api/sessions/{parent_id}").json()
    child = client.get(f"/api/sessions/{child_id}").json()
    assert parent["topic"] == "Original question"
    assert child["parent_run_id"] == parent_id

    compare = client.get(f"/api/sessions/{parent_id}/compare/{child_id}")
    assert compare.status_code == 200
    diff = compare.json()["diff"]
    assert diff["topic"]["from"] == "Original question"
    assert diff["topic"]["to"] == "New weekly question"
