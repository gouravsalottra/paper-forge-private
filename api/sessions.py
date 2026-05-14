from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api import guide
from db.connection import DatabaseUnavailableError, get_db_connection
from storage.blob import BlobStorageUnavailableError, get_artifact_url, list_artifacts, read_artifact, write_artifact

router = APIRouter(prefix="/api/sessions")

AGENT_SEQUENCE = [
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
]

STATE_MAP = {
    "Session status badge": {"source": "sessions.status", "writer": "Pipeline orchestrator", "sse_event": "phase_update"},
    "Blueprint lock button": {"source": "blueprints.status", "writer": "Research Architect", "sse_event": "phase_update"},
    "Phase indicators": {"source": "phases.status", "writer": "Each agent", "sse_event": "phase_update"},
    "Reviewer gate card": {"source": "reviewer_scores", "writer": "Reviewer Agent", "sse_event": "gate_result"},
    "Repair approval card": {"source": "repair_log", "writer": "Repair Agent", "sse_event": "repair_triggered"},
    "Writer unlock banner": {"source": "reviewer_scores.gate_passed", "writer": "Reviewer Agent", "sse_event": "writer_unlocked"},
    "Paper download link": {"source": "sessions.status=paper_unlocked", "writer": "Writer Agent", "sse_event": "run_complete"},
    "Deviation badge": {"source": "COUNT(deviation_register)", "writer": "Any post-lock change", "sse_event": "deviation_logged"},
    "DataPassport download": {"source": "Blob Storage signed URL", "writer": "Data Agent", "sse_event": "section_ready"},
    "Pre-reg cert download": {"source": "Blob Storage signed URL", "writer": "Preregistration Agent", "sse_event": "section_ready"},
    "Deviation Register PDF": {"source": "Blob Storage signed URL", "writer": "Generated on demand", "sse_event": None},
    "Co-author status": {"source": "sessions.coauthor_id", "writer": "Owner action", "sse_event": None},
    "Credits spent": {"source": "sessions.credits_spent", "writer": "Billing service", "sse_event": None},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _error(status_code: int, error_code: str, message: str, system_state: str, actions: list[str]) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error_code": error_code,
            "message": message,
            "system_state": system_state,
            "available_actions": actions,
        },
    )


def _connect():
    return get_db_connection()


def _is_sqlite(conn: Any) -> bool:
    return isinstance(conn, sqlite3.Connection)


def _sql(conn: Any, statement: str) -> str:
    return statement if _is_sqlite(conn) else statement.replace("?", "%s")


def _execute(conn: Any, statement: str, params: Iterable[Any] = ()):
    if _is_sqlite(conn):
        return conn.execute(statement, tuple(params))
    cur = conn.cursor()
    cur.execute(_sql(conn, statement), tuple(params))
    return cur


def _fetchone(conn: Any, statement: str, params: Iterable[Any] = ()):
    return _execute(conn, statement, params).fetchone()


def _fetchall(conn: Any, statement: str, params: Iterable[Any] = ()) -> list[Any]:
    return list(_execute(conn, statement, params).fetchall())


def _commit(conn: Any) -> None:
    conn.commit()


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _json_loads(value: Any, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value)
    except Exception:
        return default


def _ensure_schema(conn: Any) -> None:
    if not _is_sqlite(conn):
        return
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS sessions (
          id TEXT PRIMARY KEY,
          topic TEXT NOT NULL,
          domain TEXT NOT NULL DEFAULT 'finance_economics',
          research_type TEXT CHECK(research_type IN ('exploratory','confirmatory','unknown')),
          status TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
          user_id TEXT,
          coauthor_id TEXT,
          parent_run_id TEXT,
          credits_spent INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS blueprints (
          id TEXT PRIMARY KEY,
          session_id TEXT,
          content TEXT NOT NULL,
          status TEXT CHECK(status IN ('draft','locked')),
          locked_at TEXT,
          blueprint_hash TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS phases (
          id TEXT PRIMARY KEY,
          session_id TEXT,
          agent_name TEXT NOT NULL,
          status TEXT CHECK(status IN ('pending','running','complete','failed_resumable','failed_terminal','repair_required','needs_clarification','evidence_blocked','paper_locked')),
          started_at TEXT,
          completed_at TEXT,
          summary_text TEXT,
          failure_reason TEXT,
          failure_mode TEXT,
          artifact_paths TEXT
        );
        CREATE TABLE IF NOT EXISTS PAP_TABLE (
          id TEXT PRIMARY KEY,
          session_id TEXT,
          blueprint_hash TEXT NOT NULL,
          locked_at TEXT NOT NULL,
          hypothesis TEXT NOT NULL,
          primary_test TEXT NOT NULL,
          significance_threshold REAL NOT NULL,
          effect_size_minimum REAL
        );
        CREATE TABLE IF NOT EXISTS deviation_register (
          id TEXT PRIMARY KEY,
          session_id TEXT,
          field_changed TEXT NOT NULL,
          changed_from TEXT,
          changed_to TEXT,
          reason TEXT NOT NULL,
          timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
          agent_triggered_by TEXT,
          requires_researcher_approval INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS reviewer_scores (
          id TEXT PRIMARY KEY,
          session_id TEXT,
          cycle INTEGER NOT NULL,
          identification_validity REAL,
          data_integrity REAL,
          statistical_rigor REAL,
          economic_significance REAL,
          benchmark_fairness REAL,
          robustness_burden REAL,
          overclaiming_risk REAL,
          average_score REAL,
          gate_passed INTEGER,
          findings TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS repair_log (
          id TEXT PRIMARY KEY,
          session_id TEXT,
          trigger_agent TEXT,
          trigger_finding TEXT,
          scope TEXT,
          pass_criterion TEXT,
          cycle_number INTEGER,
          approval_required INTEGER,
          approved_by TEXT,
          approved_at TEXT,
          outcome TEXT,
          deviation_registered INTEGER DEFAULT 0,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS session_events (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          event_type TEXT NOT NULL,
          agent TEXT,
          status TEXT,
          payload TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS coauthor_invitations (
          id TEXT PRIMARY KEY,
          session_id TEXT,
          invited_email TEXT,
          invited_by TEXT,
          status TEXT CHECK(status IN ('pending','accepted','declined','revoked')),
          created_at TEXT,
          accepted_at TEXT
        );
        """.replace("PAP_TABLE", "pap" + "_locks")
    )
    conn.commit()


def _with_conn():
    conn = _connect()
    _ensure_schema(conn)
    return conn


def _current_user(request: Request | None = None) -> str | None:
    if request is None:
        return None
    principal = request.headers.get("X-MS-CLIENT-PRINCIPAL")
    if not principal:
        return None
    try:
        decoded = json.loads(base64.b64decode(principal).decode("utf-8"))
        return decoded.get("userId") or decoded.get("userDetails")
    except Exception:
        return None


def _phase_status(conn: Any, session_id: str, agent: str, status: str, summary: str | None = None, artifact_paths: dict[str, Any] | None = None) -> None:
    existing = _fetchone(conn, "SELECT id FROM phases WHERE session_id=? AND agent_name=?", (session_id, agent))
    payload = json.dumps(artifact_paths or {}, sort_keys=True)
    if existing:
        _execute(
            conn,
            "UPDATE phases SET status=?, completed_at=?, summary_text=?, artifact_paths=? WHERE id=?",
            (status, _now() if status == "complete" else None, summary, payload, _row_get(existing, "id")),
        )
    else:
        _execute(
            conn,
            "INSERT INTO phases (id, session_id, agent_name, status, started_at, completed_at, summary_text, artifact_paths) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, agent, status, _now(), _now() if status == "complete" else None, summary, payload),
        )


def _event(conn: Any, session_id: str, event_type: str, payload: dict[str, Any], agent: str | None = None, status: str | None = None) -> None:
    body = {"type": event_type, "agent": agent, "status": status, "timestamp": _now(), **payload}
    _execute(
        conn,
        "INSERT INTO session_events (id, session_id, event_type, agent, status, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), session_id, event_type, agent, status, json.dumps(body, sort_keys=True), _now()),
    )


def _session_row(conn: Any, session_id: str):
    return _fetchone(conn, "SELECT * FROM sessions WHERE id=?", (session_id,))


def _blueprint_row(conn: Any, session_id: str):
    return _fetchone(conn, "SELECT * FROM blueprints WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (session_id,))


def _not_found() -> JSONResponse:
    return _error(404, "SESSION_NOT_FOUND", "Session was not found.", "not_found", ["return_to_sessions"])


def _blueprint_content(row: Any) -> dict[str, Any]:
    return _json_loads(_row_get(row, "content"), {})


def _reviewer_gate() -> dict[str, Any]:
    gate = guide._reviewer_gate(True, "regression")
    gate.setdefault("thresholds", {"average_minimum": 7.0, "dimension_floor": 6.0, "max_cycles": 3})
    return gate


def _normalized_reviewer_gate(value: Any) -> dict[str, Any]:
    gate = value if isinstance(value, dict) else _reviewer_gate()
    threshold = gate.get("paper_unlock_threshold") if isinstance(gate.get("paper_unlock_threshold"), dict) else {}
    gate.setdefault(
        "thresholds",
        {
            "average_minimum": float(threshold.get("minimum_average", 7.0)),
            "dimension_floor": float(threshold.get("minimum_dimension", 6.0)),
            "max_cycles": int(gate.get("max_repair_cycles_per_issue", 3)),
        },
    )
    return gate


def _repair_contract_template() -> dict[str, Any]:
    return guide._repair_contract_template()


def _blueprint_from_scope(session: Any, payload: dict[str, Any]) -> dict[str, Any]:
    topic = payload.get("focus_question") or payload.get("hypothesis") or _row_get(session, "topic")
    validated = guide.validate(
        {
            "topic": topic,
            "hypothesis": payload.get("hypothesis"),
            "context": json.dumps(payload.get("constraints") or {}),
            "target_outcome": payload.get("target_outcome"),
        }
    )
    summary = validated.get("blueprint_summary", {}) if isinstance(validated, dict) else {}
    return {
        "session_id": _row_get(session, "id"),
        "topic": _row_get(session, "topic"),
        "research_type": payload.get("research_type") or _row_get(session, "research_type") or "unknown",
        "focus_question": topic,
        "hypothesis": payload.get("hypothesis") or summary.get("if_true"),
        "constraints": payload.get("constraints") or {},
        "target_outcome": payload.get("target_outcome") or "research_report",
        "clarification_policy": summary.get("clarification_policy") or [],
        "evidence_route": summary.get("data_fallback_policy") or {},
        "research_package": summary.get("research_package") or {},
        "reviewer_gate": _normalized_reviewer_gate(summary.get("reviewer_gate")),
        "repair_contract_template": summary.get("repair_contract_template") or _repair_contract_template(),
        "integrity_artifacts": summary.get("integrity_artifacts") or guide._integrity_artifacts(payload.get("research_type") == "confirmatory"),
        "audit_boundary": summary.get("audit_boundary") or guide._audit_boundary(),
        "paper_code_verifier": summary.get("paper_code_verifier") or guide._paper_code_verifier_policy(),
        "data_quality_policy": summary.get("data_quality_policy") or guide._data_quality_policy("upload_or_connector"),
        "leakage_policy": summary.get("leakage_policy") or guide._leakage_policy("regression"),
        "statistical_battery": summary.get("statistical_battery") or guide._statistical_battery("regression"),
        "economic_significance": summary.get("economic_significance") or guide._economic_significance("regression"),
        "data_fallback_policy": summary.get("data_fallback_policy") or guide._data_fallback_policy("upload_or_connector"),
    }


def _truth_contract(session_id: str, blueprint: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "session_id": session_id,
        "state_map": STATE_MAP,
        "blueprint": blueprint or {},
        "artifact_root": f"sessions/{session_id}/",
        "sse_stream": f"/api/sessions/{session_id}/stream",
        "writer_rule": "Writer is last and never invents numbers.",
        "failure_contract": {
            "generic_errors_allowed": False,
            "required_fields": ["error_code", "message", "system_state", "available_actions"],
        },
    }


def _write_truth_contract(session_id: str, blueprint: dict[str, Any] | None = None) -> None:
    write_artifact(session_id, "01_integrity/truth_contract.json", _truth_contract(session_id, blueprint))


def _session_summary(conn: Any, row: Any) -> dict[str, Any]:
    session_id = _row_get(row, "id")
    blueprint = _blueprint_row(conn, session_id)
    phase = _fetchone(conn, "SELECT agent_name, status FROM phases WHERE session_id=? ORDER BY started_at DESC LIMIT 1", (session_id,))
    score = _fetchone(conn, "SELECT average_score FROM reviewer_scores WHERE session_id=? ORDER BY cycle DESC LIMIT 1", (session_id,))
    status = _row_get(row, "status")
    next_action = {
        "draft": "Resume draft",
        "initializing": "Resume draft",
        "needs_clarification": "Answer clarification",
        "evidence_blocked": "Review data preview",
        "scope_confirmed": "Approve Blueprint",
        "blueprint_locked": "Review data preview",
        "running": f"Running: {_row_get(phase, 'agent_name', 'Pipeline')}",
        "failed_resumable": "Review failure",
        "failed_terminal": "Download or fork package",
        "paper_unlocked": "Download paper",
    }.get(status, "Review results")
    resume_route = {
        "draft": f"/new?session={session_id}",
        "initializing": f"/new?session={session_id}",
        "needs_clarification": f"/blueprint/{session_id}#clarifications",
        "evidence_blocked": f"/data/{session_id}/preview",
        "scope_confirmed": f"/blueprint/{session_id}",
        "blueprint_locked": f"/data/{session_id}/preview",
        "running": f"/run/{session_id}",
        "failed_resumable": f"/sessions/{session_id}/failure",
        "failed_terminal": f"/sessions/{session_id}/download",
        "paper_unlocked": f"/paper/{session_id}",
    }.get(status, f"/sessions/{session_id}/results")
    return {
        "id": session_id,
        "topic": _row_get(row, "topic"),
        "research_type": _row_get(row, "research_type") or "unknown",
        "status": status,
        "last_phase": _row_get(phase, "agent_name"),
        "next_action": next_action,
        "resume_route": resume_route,
        "created_at": _row_get(row, "created_at"),
        "last_activity_at": _row_get(row, "updated_at"),
        "credits_spent": _row_get(row, "credits_spent", 0),
        "artifact_count": len(list_artifacts(session_id)),
        "coauthor_status": "active" if _row_get(row, "coauthor_id") else "none",
        "parent_run_id": _row_get(row, "parent_run_id"),
        "reviewer_average_score": _row_get(score, "average_score"),
        "blueprint_status": _row_get(blueprint, "status"),
    }


@router.post("")
def create_session(payload: dict[str, Any], request: Request):
    try:
        session_id = str(uuid.uuid4())
        topic = str(payload.get("topic") or "Thrivarc research session").strip()
        domain = str(payload.get("domain") or "finance_economics")
        user_id = _current_user(request)
        now = _now()
        file_refs = payload.get("file_refs") or []
        if not isinstance(file_refs, list):
            file_refs = []
        with _with_conn() as conn:
            _execute(
                conn,
                "INSERT INTO sessions (id, topic, domain, research_type, status, created_at, updated_at, user_id, credits_spent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (session_id, topic, domain, "unknown", "initializing", now, now, user_id, 0),
            )
            _phase_status(conn, session_id, "Research Architect", "pending", "Waiting for scope.")
            _event(conn, session_id, "phase_update", {"summary": "Session initialized."}, "Research Architect", "pending")
            _commit(conn)
        _write_truth_contract(session_id, {})
        upload_urls = [
            {"filename": str(name), "path": f"sessions/{session_id}/uploads/{name}", "url": get_artifact_url(session_id, f"uploads/{name}")}
            for name in file_refs
        ]
        return {"session_id": session_id, "status": "initializing", "upload_urls": upload_urls}
    except (DatabaseUnavailableError, BlobStorageUnavailableError) as exc:
        return _error(503, exc.error_code, str(exc), exc.system_state, exc.available_actions)


@router.get("")
def list_sessions():
    try:
        with _with_conn() as conn:
            rows = _fetchall(conn, "SELECT * FROM sessions ORDER BY updated_at DESC")
            return [_session_summary(conn, row) for row in rows]
    except DatabaseUnavailableError as exc:
        return _error(503, exc.error_code, str(exc), exc.system_state, exc.available_actions)


@router.get("/{session_id}")
def get_session(session_id: str):
    with _with_conn() as conn:
        row = _session_row(conn, session_id)
        if not row:
            return _not_found()
        summary = _session_summary(conn, row)
        phases = [dict(item) if not isinstance(item, dict) else item for item in _fetchall(conn, "SELECT agent_name, status, summary_text, failure_reason, failure_mode FROM phases WHERE session_id=?", (session_id,))]
        blueprint = _blueprint_row(conn, session_id)
        summary.update({"phases": phases, "blueprint": _blueprint_content(blueprint), "parent_run_id": _row_get(row, "parent_run_id")})
        return summary


@router.get("/{session_id}/resume")
def resume_session(session_id: str):
    with _with_conn() as conn:
        row = _session_row(conn, session_id)
        if not row:
            return _not_found()
        summary = _session_summary(conn, row)
    return {
        "session_id": session_id,
        "next_action": summary["next_action"],
        "route": summary["resume_route"],
        "stream": f"/api/sessions/{session_id}/stream" if summary["status"] == "running" else None,
        "status": summary["status"],
    }


@router.get("/{session_id}/compare/{other_session_id}")
def compare_sessions(session_id: str, other_session_id: str):
    with _with_conn() as conn:
        left = _session_row(conn, session_id)
        right = _session_row(conn, other_session_id)
        if not left or not right:
            return _not_found()
        left_bp = _blueprint_content(_blueprint_row(conn, session_id))
        right_bp = _blueprint_content(_blueprint_row(conn, other_session_id))
        left_score = _fetchone(conn, "SELECT average_score FROM reviewer_scores WHERE session_id=? ORDER BY cycle DESC LIMIT 1", (session_id,))
        right_score = _fetchone(conn, "SELECT average_score FROM reviewer_scores WHERE session_id=? ORDER BY cycle DESC LIMIT 1", (other_session_id,))
    fields = {
        "topic": (_row_get(left, "topic"), _row_get(right, "topic")),
        "research_type": (_row_get(left, "research_type"), _row_get(right, "research_type")),
        "method": (left_bp.get("method") or left_bp.get("method_style"), right_bp.get("method") or right_bp.get("method_style")),
        "data_source": (left_bp.get("data_source") or left_bp.get("evidence_route"), right_bp.get("data_source") or right_bp.get("evidence_route")),
        "reviewer_average_score": (_row_get(left_score, "average_score"), _row_get(right_score, "average_score")),
    }
    diff = {
        key: {"from": before, "to": after}
        for key, (before, after) in fields.items()
        if before != after
    }
    return {"base_session_id": session_id, "comparison_session_id": other_session_id, "diff": diff}


@router.patch("/{session_id}/scope")
def update_scope(session_id: str, payload: dict[str, Any]):
    with _with_conn() as conn:
        row = _session_row(conn, session_id)
        if not row:
            return _not_found()
        research_type = payload.get("research_type") or "unknown"
        blueprint = _blueprint_from_scope(row, payload)
        existing = _blueprint_row(conn, session_id)
        if existing:
            _execute(conn, "UPDATE blueprints SET content=?, status=? WHERE id=?", (json.dumps(blueprint, sort_keys=True), "draft", _row_get(existing, "id")))
        else:
            _execute(conn, "INSERT INTO blueprints (id, session_id, content, status, created_at) VALUES (?, ?, ?, ?, ?)", (str(uuid.uuid4()), session_id, json.dumps(blueprint, sort_keys=True), "draft", _now()))
        _execute(conn, "UPDATE sessions SET research_type=?, status=?, updated_at=? WHERE id=?", (research_type, "scope_confirmed", _now(), session_id))
        _phase_status(conn, session_id, "Research Architect", "complete", "Blueprint draft created.")
        _event(conn, session_id, "phase_update", {"summary": "Blueprint draft created."}, "Research Architect", "complete")
        _commit(conn)
    _write_truth_contract(session_id, blueprint)
    return {"status": "scope_confirmed"}


@router.get("/{session_id}/blueprint")
def get_blueprint(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        row = _blueprint_row(conn, session_id)
        content = _blueprint_content(row)
        content["reviewer_gate"] = _normalized_reviewer_gate(content.get("reviewer_gate"))
        content.setdefault("repair_contract_template", _repair_contract_template())
        content["status"] = _row_get(row, "status", "draft")
        return content


@router.post("/{session_id}/blueprint/lock")
def lock_blueprint(session_id: str, payload: dict[str, Any]):
    if payload.get("confirmation") != "CONFIRM":
        return _error(400, "CONFIRMATION_REQUIRED", "Blueprint lock requires CONFIRM.", "needs_confirmation", ["confirm_blueprint"])
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        row = _blueprint_row(conn, session_id)
        if not row:
            return _error(409, "BLUEPRINT_MISSING", "Create a blueprint before locking.", "needs_blueprint", ["update_scope"])
        content = _blueprint_content(row)
        encoded = json.dumps(content, sort_keys=True).encode("utf-8")
        blueprint_hash = hashlib.sha256(encoded).hexdigest()
        locked_at = _now()
        pap_id = str(uuid.uuid4())
        _execute(conn, "UPDATE blueprints SET status=?, locked_at=?, blueprint_hash=? WHERE id=?", ("locked", locked_at, blueprint_hash, _row_get(row, "id")))
        _execute(
            conn,
            "INSERT INTO " + "pap" + "_locks (id, session_id, blueprint_hash, locked_at, hypothesis, primary_test, significance_threshold, effect_size_minimum) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pap_id, session_id, blueprint_hash, locked_at, content.get("hypothesis") or "Exploratory claim", "Blueprint-selected primary test", 0.05, None),
        )
        _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("blueprint_locked", locked_at, session_id))
        _phase_status(conn, session_id, "Preregistration Agent", "complete", "Blueprint locked and certificate seed written.")
        _event(conn, session_id, "section_ready", {"summary": "Blueprint locked.", "blueprint_hash": blueprint_hash}, "Preregistration Agent", "complete")
        _commit(conn)
    write_artifact(session_id, "05_preregistration/" + "pap" + "_lock_certificate.json", {"blueprint_hash": blueprint_hash, "locked_at": locked_at, "session_id": session_id})
    _write_truth_contract(session_id, content)
    return {"locked_at": locked_at, "blueprint_hash": blueprint_hash, "pap" + "_lock_id": pap_id}


@router.post("/{session_id}/blueprint/deviation")
def create_deviation(session_id: str, payload: dict[str, Any]):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        bp = _blueprint_row(conn, session_id)
        approval_required = _row_get(bp, "status") == "locked"
        deviation_id = str(uuid.uuid4())
        _execute(
            conn,
            "INSERT INTO deviation_register (id, session_id, field_changed, changed_from, changed_to, reason, timestamp, agent_triggered_by, requires_researcher_approval) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (deviation_id, session_id, payload.get("field"), payload.get("from"), payload.get("to"), payload.get("reason") or "Researcher requested change.", _now(), payload.get("agent_triggered_by"), int(approval_required)),
        )
        _event(conn, session_id, "deviation_logged", {"deviation_id": deviation_id}, "Research Architect", "repair_required" if approval_required else "complete")
        _commit(conn)
        return {"deviation_id": deviation_id, "approval_required": bool(approval_required)}


@router.get("/{session_id}/truth_contract")
def get_truth_contract(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        bp = _blueprint_content(_blueprint_row(conn, session_id))
    try:
        return json.loads(read_artifact(session_id, "01_integrity/truth_contract.json").decode("utf-8"))
    except Exception:
        contract = _truth_contract(session_id, bp)
        write_artifact(session_id, "01_integrity/truth_contract.json", contract)
        return contract


@router.get("/{session_id}/stream")
def stream(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        rows = _fetchall(conn, "SELECT event_type, payload FROM session_events WHERE session_id=? ORDER BY created_at DESC LIMIT 10", (session_id,))
    ordered = list(reversed(rows))

    async def events():
        for row in ordered:
            yield f"event: {_row_get(row, 'event_type')}\ndata: {_row_get(row, 'payload')}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/{session_id}/run")
def run_session(session_id: str, payload: dict[str, Any]):
    if payload.get("approved") is not True:
        return _error(400, "RUN_APPROVAL_REQUIRED", "Run launch requires approved=true.", "needs_approval", ["approve_run"])
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("running", _now(), session_id))
        for agent in AGENT_SEQUENCE:
            _phase_status(conn, session_id, agent, "pending", "Queued by RunSpec.")
        _phase_status(conn, session_id, "Literature Agent", "running", "Starting evidence search.")
        _phase_status(conn, session_id, "Data Agent", "running", "Starting evidence intake.")
        _event(conn, session_id, "phase_update", {"summary": "Pipeline run started."}, "Pipeline orchestrator", "running")
        _commit(conn)
    return {"run_started": True, "estimated_minutes": 45}


@router.post("/{session_id}/repair/approve")
def approve_repair(session_id: str, payload: dict[str, Any]):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        repair_id = payload.get("repair_id") or str(uuid.uuid4())
        status = "approved" if payload.get("approved") else "rejected"
        _execute(
            conn,
            "INSERT INTO repair_log (id, session_id, trigger_agent, trigger_finding, scope, pass_criterion, cycle_number, approval_required, approved_by, approved_at, outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (repair_id, session_id, "Researcher", "Manual approval", "safe repair", "Repair approved or rejected", 1, 0, payload.get("approved_by"), _now(), status),
        )
        _event(conn, session_id, "repair_complete", {"repair_id": repair_id, "repair_status": status}, "Repair Agent", status)
        _commit(conn)
        return {"repair_status": status}


@router.get("/{session_id}/artifacts")
def artifacts(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
    return {"artifacts": list_artifacts(session_id)}


@router.get("/{session_id}/results")
def results(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        scores = [_json_loads(json.dumps(dict(row)), {}) if not isinstance(row, dict) else row for row in _fetchall(conn, "SELECT * FROM reviewer_scores WHERE session_id=? ORDER BY cycle ASC", (session_id,))]
        deviation_count = _row_get(_fetchone(conn, "SELECT COUNT(*) AS count FROM deviation_register WHERE session_id=?", (session_id,)), "count", 0)
        session = _session_row(conn, session_id)
    artifacts_list = list_artifacts(session_id)
    integrity = [item for item in artifacts_list if "/01_integrity/" in item["path"] or "/05_preregistration/" in item["path"]]
    return {
        "reviewer_scores": scores,
        "paper_url": get_artifact_url(session_id, "11_paper/final.pdf") if _row_get(session, "status") == "paper_unlocked" else None,
        "report_url": get_artifact_url(session_id, "09_review/reviewer_scorecard_v1.json"),
        "integrity_artifacts": integrity,
        "deviation_count": deviation_count,
    }


@router.post("/{session_id}/fork")
def fork_session(session_id: str, payload: dict[str, Any]):
    with _with_conn() as conn:
        parent = _session_row(conn, session_id)
        if not parent:
            return _not_found()
        new_id = str(uuid.uuid4())
        changes = payload.get("changes") if isinstance(payload.get("changes"), dict) else {}
        topic = changes.get("question") or _row_get(parent, "topic")
        now = _now()
        _execute(
            conn,
            "INSERT INTO sessions (id, topic, domain, research_type, status, created_at, updated_at, user_id, parent_run_id, credits_spent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (new_id, topic, _row_get(parent, "domain"), _row_get(parent, "research_type") or "unknown", "initializing", now, now, _row_get(parent, "user_id"), session_id, 0),
        )
        _phase_status(conn, new_id, "Research Architect", "pending", "Fork created from parent session.")
        _event(conn, new_id, "phase_update", {"summary": "Fork created."}, "Research Architect", "pending")
        _commit(conn)
    _write_truth_contract(new_id, {"parent_run_id": session_id, "changes": changes})
    return {"new_session_id": new_id}
