from __future__ import annotations

from pathlib import Path

import pytest


def _seed_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "agent-io.db"))
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from api import sessions
    from storage import blob

    blob.reset_mock_storage()
    session_id = "agent-session"
    with sessions._with_conn() as conn:
        sessions._execute(
            conn,
            "INSERT INTO sessions (id, topic, domain, research_type, status, created_at, updated_at, credits_spent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, "Test finance question", "finance_economics", "confirmatory", "running", sessions._now(), sessions._now(), 0),
        )
        sessions._execute(
            conn,
            "INSERT INTO blueprints (id, session_id, content, status, created_at) VALUES (?, ?, ?, ?, ?)",
            ("bp-1", session_id, '{"hypothesis":"returns are predictable"}', "locked", sessions._now()),
        )
        conn.commit()
    blob.write_artifact(session_id, "00_runspec/runspec.json", {"session_id": session_id})
    return session_id


@pytest.mark.parametrize("agent_name", [
    "Research Architect",
    "Literature Agent",
    "Data Agent",
    "Feature / Mining Agent",
    "Preregistration Agent",
    "Method / Compute Agent",
    "Code Audit Agent",
    "Statistics Agent",
    "Spec Audit Agent",
    "Reviewer Agent",
    "Repair Agent",
    "Paper-Code Verifier",
    "Writer Agent",
])
def test_agent_io_wrapper_writes_db_blob_and_sse(agent_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed_session(tmp_path, monkeypatch)

    from agents.io_wrapper import AgentResult, run_agent_io
    from api import sessions
    from storage import blob

    def logic(inputs, run_config):
        assert inputs["session"]["id"] == session_id
        assert inputs["blueprint"]["hypothesis"] == "returns are predictable"
        return AgentResult(summary=f"{agent_name} complete", artifacts={"output.json": {"agent": agent_name}})

    run_agent_io(session_id, agent_name, logic, {"cycle": 1})

    contract = blob.read_artifact(session_id, f"{sessions.AGENT_SEQUENCE.index(agent_name):02d}_{agent_name.lower().replace(' ', '_').replace('/', '').replace('-', '_')}/output.json")
    assert agent_name.encode() in contract
    assert not (tmp_path / "sessions" / session_id).exists()

    with sessions._with_conn() as conn:
        phase = sessions._fetchone(conn, "SELECT status, summary_text FROM phases WHERE session_id=? AND agent_name=?", (session_id, agent_name))
        event = sessions._fetchone(conn, "SELECT event_type, payload FROM session_events WHERE session_id=? AND agent=? ORDER BY created_at DESC LIMIT 1", (session_id, agent_name))
    assert phase["status"] == "complete"
    assert phase["summary_text"] == f"{agent_name} complete"
    assert event["event_type"] == "phase_update"
    assert "complete" in event["payload"]


def test_agent_io_wrapper_writes_failure_state_before_sse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed_session(tmp_path, monkeypatch)

    from agents.io_wrapper import AgentFailure, run_agent_io
    from api import sessions

    def logic(_inputs, _run_config):
        raise AgentFailure(
            mode="data_source_unavailable",
            reason="yfinance timeout",
            system_state="failed_resumable",
            available_actions=["retry", "upload_data"],
        )

    with pytest.raises(AgentFailure):
        run_agent_io(session_id, "Data Agent", logic, {})

    with sessions._with_conn() as conn:
        phase = sessions._fetchone(conn, "SELECT status, failure_mode, failure_reason FROM phases WHERE session_id=? AND agent_name=?", (session_id, "Data Agent"))
        event = sessions._fetchone(conn, "SELECT payload FROM session_events WHERE session_id=? AND agent=? ORDER BY created_at DESC LIMIT 1", (session_id, "Data Agent"))
    assert phase["status"] == "failed_resumable"
    assert phase["failure_mode"] == "data_source_unavailable"
    assert phase["failure_reason"] == "yfinance timeout"
    assert "upload_data" in event["payload"]
