from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from api import sessions
from storage.blob import read_artifact, write_artifact


@dataclass
class AgentResult:
    summary: str
    artifacts: dict[str, Any] = field(default_factory=dict)
    db_updates: dict[str, Any] = field(default_factory=dict)


class AgentFailure(Exception):
    """Structured agent failure that maps directly to the failure catalogue."""

    def __init__(self, *, mode: str, reason: str, system_state: str, available_actions: list[str]) -> None:
        super().__init__(reason)
        self.mode = mode
        self.reason = reason
        self.system_state = system_state
        self.available_actions = available_actions


AGENT_IO_CONTRACTS: dict[str, dict[str, Any]] = {
    agent: {
        "phase_source": "phases",
        "event_source": "session_events",
        "artifact_prefix": f"{idx:02d}_{agent.lower().replace(' ', '_').replace('/', '').replace('-', '_')}",
    }
    for idx, agent in enumerate(sessions.AGENT_SEQUENCE)
}


def _artifact_prefix(agent_name: str) -> str:
    if agent_name not in AGENT_IO_CONTRACTS:
        idx = len(AGENT_IO_CONTRACTS)
        AGENT_IO_CONTRACTS[agent_name] = {
            "phase_source": "phases",
            "event_source": "session_events",
            "artifact_prefix": f"{idx:02d}_{agent_name.lower().replace(' ', '_').replace('/', '').replace('-', '_')}",
        }
    return str(AGENT_IO_CONTRACTS[agent_name]["artifact_prefix"])


def _row_to_dict(row: Any) -> dict[str, Any]:
    if row is None:
        return {}
    if isinstance(row, dict):
        return dict(row)
    try:
        return {key: row[key] for key in row.keys()}
    except Exception:
        return {}


def _read_json_artifact(session_id: str, path: str) -> dict[str, Any]:
    try:
        return json.loads(read_artifact(session_id, path).decode("utf-8"))
    except Exception:
        return {}


def load_inputs(session_id: str, agent_name: str) -> dict[str, Any]:
    with sessions._with_conn() as conn:
        session = _row_to_dict(sessions._session_row(conn, session_id))
        blueprint_row = sessions._blueprint_row(conn, session_id)
        blueprint = sessions._blueprint_content(blueprint_row)
        phase_rows = [
            _row_to_dict(row)
            for row in sessions._fetchall(conn, "SELECT * FROM phases WHERE session_id=? ORDER BY started_at ASC", (session_id,))
        ]
    return {
        "session": session,
        "blueprint": blueprint,
        "phases": phase_rows,
        "runspec": _read_json_artifact(session_id, "00_runspec/runspec.json"),
        "truth_contract": _read_json_artifact(session_id, "01_integrity/truth_contract.json"),
        "agent_name": agent_name,
    }


def write_outputs(session_id: str, agent_name: str, result: AgentResult, *, repair_cycle: int | None = None) -> dict[str, Any]:
    prefix = _artifact_prefix(agent_name)
    refs: dict[str, Any] = {}
    for filename, payload in result.artifacts.items():
        refs[filename] = write_artifact(session_id, f"{prefix}/{filename}", payload, version=repair_cycle)
    if not refs:
        refs["summary.json"] = write_artifact(session_id, f"{prefix}/summary.json", {"summary": result.summary}, version=repair_cycle)
    return refs


def _write_failure(session_id: str, agent_name: str, failure: AgentFailure) -> None:
    with sessions._with_conn() as conn:
        existing = sessions._fetchone(conn, "SELECT id FROM phases WHERE session_id=? AND agent_name=?", (session_id, agent_name))
        if existing:
            sessions._execute(
                conn,
                "UPDATE phases SET status=?, completed_at=?, failure_mode=?, failure_reason=? WHERE id=?",
                (failure.system_state, sessions._now(), failure.mode, failure.reason, sessions._row_get(existing, "id")),
            )
        else:
            sessions._execute(
                conn,
                "INSERT INTO phases (id, session_id, agent_name, status, started_at, completed_at, failure_mode, failure_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (__import__("uuid").uuid4().hex, session_id, agent_name, failure.system_state, sessions._now(), sessions._now(), failure.mode, failure.reason),
            )
        sessions._event(
            conn,
            session_id,
            "phase_update",
            {
                "failure_mode": failure.mode,
                "failure_reason": failure.reason,
                "available_actions": failure.available_actions,
            },
            agent_name,
            failure.system_state,
        )
        conn.commit()


def run_agent_io(
    session_id: str,
    agent_name: str,
    agent_logic: Callable[[dict[str, Any], dict[str, Any]], AgentResult],
    run_config: dict[str, Any] | None = None,
) -> AgentResult:
    """Run one agent through the canonical PostgreSQL/Blob/SSE I/O contract."""
    run_config = run_config or {}
    with sessions._with_conn() as conn:
        sessions._phase_status(conn, session_id, agent_name, "running", "Agent started.")
        sessions._event(conn, session_id, "phase_update", {"summary": "Agent started."}, agent_name, "running")
        conn.commit()

    try:
        inputs = load_inputs(session_id, agent_name)
        result = agent_logic(inputs, run_config)
        if not isinstance(result, AgentResult):
            result = AgentResult(summary=str(result), artifacts={})
        artifact_refs = write_outputs(session_id, agent_name, result, repair_cycle=run_config.get("repair_cycle"))
        with sessions._with_conn() as conn:
            sessions._phase_status(conn, session_id, agent_name, "complete", result.summary, artifact_refs)
            sessions._event(conn, session_id, "phase_update", {"summary": result.summary, "artifacts": artifact_refs}, agent_name, "complete")
            conn.commit()
        return result
    except AgentFailure as failure:
        _write_failure(session_id, agent_name, failure)
        raise


def run_research_architect(session_id: str, run_config: dict[str, Any], agent_logic: Callable[[dict[str, Any], dict[str, Any]], AgentResult]) -> AgentResult:
    return run_agent_io(session_id, "Research Architect", agent_logic, run_config)


def run_literature_agent(session_id: str, run_config: dict[str, Any], agent_logic: Callable[[dict[str, Any], dict[str, Any]], AgentResult]) -> AgentResult:
    return run_agent_io(session_id, "Literature Agent", agent_logic, run_config)


def run_data_agent(session_id: str, run_config: dict[str, Any], agent_logic: Callable[[dict[str, Any], dict[str, Any]], AgentResult]) -> AgentResult:
    return run_agent_io(session_id, "Data Agent", agent_logic, run_config)


def run_reviewer_agent(session_id: str, run_config: dict[str, Any], agent_logic: Callable[[dict[str, Any], dict[str, Any]], AgentResult]) -> AgentResult:
    return run_agent_io(session_id, "Reviewer Agent", agent_logic, run_config)


def run_writer_agent(session_id: str, run_config: dict[str, Any], agent_logic: Callable[[dict[str, Any], dict[str, Any]], AgentResult]) -> AgentResult:
    return run_agent_io(session_id, "Writer Agent", agent_logic, run_config)
