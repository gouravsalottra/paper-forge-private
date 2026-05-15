from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from db.connection import get_db_connection
from init_db import init_db
from storage.blob import list_artifacts, read_artifact, write_artifact

router = APIRouter()

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "pipeline.db"
RUN_STORE = ROOT / "research_memory"
LEGACY_RUN_STORE = ROOT / ("paper" + "_memory")
PIPELINE_SCRIPT = ROOT / "run_pipeline.py"

PHASE_MAP = {
    "SCOUT": "LITERATURE",
    "MINER": "DATAPULL",
    "SIGMA" + "_JOB1": "PREREGISTER",
    "FORGE": "COMPUTE",
    "SIGMA" + "_JOB2": "STATSRUN",
    "CODEC": "CODEAUDIT",
    "QUILL": "WRITER",
    "HAWK": "REVIEWER",
}
CANONICAL_PHASES = [
    "LITERATURE",
    "DATAPULL",
    "PREREGISTER",
    "COMPUTE",
    "STATSRUN",
    "CODEAUDIT",
    "REVIEWER",
    "WRITER",
]
RUN_PROCESSES: dict[str, asyncio.subprocess.Process] = {}

SESSION_PHASE_TO_LEGACY = {
    "Literature Agent": "LITERATURE",
    "Data Agent": "DATAPULL",
    "Preregistration Agent": "PREREGISTER",
    "Method / Compute Agent": "COMPUTE",
    "Statistics Agent": "STATSRUN",
    "Code Audit Agent": "CODEAUDIT",
    "Spec Audit Agent": "CODEAUDIT",
    "Reviewer Agent": "REVIEWER",
    "Paper-Code Verifier": "REVIEWER",
    "Writer Agent": "WRITER",
}


def _legacy_runs_enabled() -> bool:
    env = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).strip().lower()
    if env == "production":
        return False
    return os.getenv("THRIVARC_ENABLE_LEGACY_RUNS", "").strip().lower() in {"1", "true", "yes"}


def _raise_run_not_found(run_id: str) -> None:
    raise HTTPException(status_code=404, detail=f"Run not found: {run_id}")


def _canonical_session_exists(run_id: str) -> bool:
    from api import sessions

    with sessions._with_conn() as conn:
        return sessions._session_row(conn, run_id) is not None


def _canonical_run_object(run_id: str) -> dict[str, Any] | None:
    from api import sessions

    with sessions._with_conn() as conn:
        row = sessions._session_row(conn, run_id)
        if not row:
            return None
        blueprint = sessions._blueprint_content(sessions._blueprint_row(conn, run_id))
        phases = sessions._fetchall(
            conn,
            "SELECT agent_name, status FROM phases WHERE session_id=? ORDER BY started_at ASC",
            (run_id,),
        )
        score = sessions._fetchone(
            conn,
            "SELECT * FROM reviewer_scores WHERE session_id=? ORDER BY cycle DESC LIMIT 1",
            (run_id,),
        )
    data_passport: dict[str, Any] = {}
    try:
        data_passport = json.loads(read_artifact(run_id, "03_data/data_passport.json").decode("utf-8"))
    except Exception:
        data_passport = {}
    completed = [
        SESSION_PHASE_TO_LEGACY.get(sessions._row_get(phase, "agent_name"))
        for phase in phases
        if sessions._row_get(phase, "status") == "complete"
    ]
    completed = [phase for phase in completed if phase]
    current = next(
        (
            SESSION_PHASE_TO_LEGACY.get(sessions._row_get(phase, "agent_name"))
            for phase in phases
            if sessions._row_get(phase, "status") == "running"
        ),
        None,
    )
    if current is None:
        current = next(
            (
                SESSION_PHASE_TO_LEGACY.get(sessions._row_get(phase, "agent_name"))
                for phase in phases
                if sessions._row_get(phase, "status") in {"failed_resumable", "failed_terminal", "repair_required", "paper_locked"}
            ),
            None,
        )
    status = sessions._row_get(row, "status")
    gate_passed = bool(sessions._row_get(score, "gate_passed")) if score else False
    data_sha = (
        blueprint.get("uploaded_event_sha256")
        or blueprint.get("data_preview_sha256")
        or data_passport.get("sha256")
    )
    return {
        "run_id": run_id,
        "topic": sessions._row_get(row, "topic"),
        "hypothesis": blueprint.get("hypothesis") or sessions._row_get(row, "topic"),
        "status": status,
        "current_phase": current,
        "phase": current,
        "phases_completed": sorted(set(completed), key=CANONICAL_PHASES.index),
        "cost_usd": float(sessions._row_get(row, "credits_spent", 0) or 0),
        "created_at": sessions._row_get(row, "created_at"),
        "research_type": sessions._row_get(row, "research_type") or "unknown",
        "research_state": sessions._row_get(row, "research_type") or "unknown",
        "finding_valid": gate_passed if score else None,
        "data_preview_sha256": data_sha,
        "data_sha256": data_sha,
        "data_passport": data_passport,
        "parent_run_id": sessions._row_get(row, "parent_run_id"),
        "hypothesis_id": None,
        "plan": blueprint,
        "reviewer_gate": {"passed": gate_passed, "average_score": sessions._row_get(score, "average_score")},
    }


def _canonical_runs() -> list[dict[str, Any]]:
    from api import sessions

    with sessions._with_conn() as conn:
        rows = sessions._fetchall(conn, "SELECT id FROM sessions ORDER BY updated_at DESC")
    runs: list[dict[str, Any]] = []
    for row in rows:
        run = _canonical_run_object(sessions._row_get(row, "id"))
        if run:
            runs.append(run)
    return runs


def _create_canonical_run(payload: dict[str, Any]) -> dict[str, str]:
    from api import sessions
    import threading

    session_id = str(uuid.uuid4())
    topic = str(payload.get("topic") or payload.get("hypothesis") or "Thrivarc research run").strip()
    research_state = str(payload.get("research_type") or payload.get("approach") or payload.get("research_state") or "unknown").lower()
    research_type = "confirmatory" if "confirm" in research_state else "exploratory" if "explor" in research_state else "unknown"
    now = sessions._now()
    with sessions._with_conn() as conn:
        sessions._execute(
            conn,
            "INSERT INTO sessions (id, topic, domain, research_type, status, created_at, updated_at, credits_spent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, topic, "finance_economics", research_type, "initializing", now, now, 0),
        )
        sessions._phase_status(conn, session_id, "Research Architect", "pending", "Waiting for scope.")
        sessions._event(conn, session_id, "phase_update", {"summary": "Session initialized from website run request."}, "Research Architect", "pending")
        sessions._commit(conn)
    sessions._write_truth_contract(session_id, {})
    scope_payload = {
        "research_type": research_type,
        "focus_question": topic,
        "hypothesis": payload.get("hypothesis") or topic,
        "constraints": {
            "data_source": payload.get("data_source") or payload.get("connector"),
            "compute_type": payload.get("compute_type"),
            "data_preview_sha256": payload.get("data_preview_sha256"),
            "runspec": payload.get("runspec"),
        },
        "target_outcome": payload.get("output_format") or "paper",
    }
    sessions.update_scope(session_id, scope_payload)
    sessions.lock_blueprint(session_id, {"confirmation": "CONFIRM"})

    # Run the pipeline in a background thread so the HTTP response returns
    # immediately. The session, blueprint, and PAP lock are fully committed
    # before the thread starts — callers receive {"run_id": "..."} in ~1s.
    def _launch() -> None:
        try:
            sessions.run_session(session_id, {"approved": True})
        except Exception as exc:  # noqa: BLE001
            import logging
            logging.getLogger(__name__).error(
                "Background pipeline failed for session %s: %s", session_id, exc
            )

    t = threading.Thread(target=_launch, daemon=True)
    t.start()
    # In the test suite PYTEST_CURRENT_TEST is set automatically by pytest.
    # The pipeline uses LLM fallbacks there and completes in milliseconds —
    # joining keeps the synchronous assertion behaviour tests rely on.
    # In production this env var is absent so we return immediately.
    if os.getenv("PYTEST_CURRENT_TEST"):
        t.join()
    return {"run_id": session_id}



def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _phase_name(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip().upper()
    return PHASE_MAP.get(raw, raw)


def _uses_legacy_sqlite() -> bool:
    url = os.getenv("DATABASE_URL", "")
    env = os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).lower()
    return env != "production" and not (url.startswith("postgresql://") or url.startswith("postgres://"))


def _connect():
    if _uses_legacy_sqlite():
        init_db(DB_PATH)
    conn = get_db_connection(DB_PATH)
    if isinstance(conn, sqlite3.Connection):
        conn.row_factory = sqlite3.Row
    return conn


def _parse_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _phase_state(conn: sqlite3.Connection, run_id: str) -> tuple[str | None, list[str]]:
    rows = conn.execute(
        "SELECT phase_name, status FROM phases WHERE run_id=? ORDER BY phase_id ASC",
        (run_id,),
    ).fetchall()
    completed = [_phase_name(r["phase_name"]) for r in rows if str(r["status"]).lower() in {"done", "skipped"}]
    running = next((_phase_name(r["phase_name"]) for r in rows if str(r["status"]).lower() == "running"), None)
    failed = next((_phase_name(r["phase_name"]) for r in rows if str(r["status"]).lower() == "failed"), None)
    current = failed or running
    if not current and rows:
        pending = next((_phase_name(r["phase_name"]) for r in rows if str(r["status"]).lower() == "pending"), None)
        current = pending or _phase_name(rows[-1]["phase_name"])
    return current, [p for p in completed if p]


def _cost(conn: sqlite3.Connection, run_id: str) -> float:
    try:
        row = conn.execute(
            "SELECT COALESCE(SUM(COALESCE(estimated_cost_usd,0)),0) AS cost FROM token_budget WHERE run_id=?",
            (run_id,),
        ).fetchone()
        return round(float(row["cost"] if row else 0.0), 4)
    except Exception:
        return 0.0


def _finding_valid(conn: sqlite3.Connection, run_id: str) -> bool | None:
    try:
        row = conn.execute("SELECT results_valid FROM results_gate WHERE run_id=? LIMIT 1", (run_id,)).fetchone()
        return None if not row else bool(row["results_valid"])
    except Exception:
        return None


def _artifact_manifest(run_id: str) -> dict[str, Any]:
    base = f"research_memory/{run_id}"
    return {
        "runspec": f"{base}/00_runspec/runspec.json",
        "blueprint": f"{base}/00_runspec/blueprint.json",
        "integrity": {
            "data_passport": f"{base}/01_integrity/data_passport_preview.json",
            "deviation_register": f"{base}/01_integrity/deviation_register.json",
            "reviewer_gate": f"{base}/01_integrity/reviewer_gate.json",
            "repair_contract_template": f"{base}/01_integrity/repair_contract_template.json",
        },
        "phase_outputs": {
            "literature": f"{base}/02_literature",
            "datapull": f"{base}/03_datapull",
            "compute": f"{base}/04_compute",
            "statsrun": f"{base}/05_statsrun",
            "audits": f"{base}/06_audits",
            "reviewer": f"{base}/07_reviewer",
            "writer": f"{base}/08_writer",
        },
    }


def _failure_catalog() -> list[dict[str, str]]:
    return [
        {"phase": "LITERATURE", "failure": "too few relevant papers", "researcher_view": "Proceed with a literature gap warning or sharpen the question."},
        {"phase": "DATAPULL", "failure": "data source unavailable or schema mismatch", "researcher_view": "Upload data, adjust source route, or stop before compute."},
        {"phase": "COMPUTE", "failure": "method cannot run on certified evidence", "researcher_view": "Repair method parameters or return to Blueprint."},
        {"phase": "STATSRUN", "failure": "weak or null evidence", "researcher_view": "Receive null-result package or launch scoped robustness repairs."},
        {"phase": "CODEAUDIT", "failure": "technical execution mismatch", "researcher_view": "Repair code/output issues before reviewer scoring."},
        {"phase": "REVIEWER", "failure": "score below paper threshold", "researcher_view": "Run issue-scoped repairs or accept a failure package."},
        {"phase": "WRITER", "failure": "paper-code mismatch", "researcher_view": "Writer stays blocked until verifier clears the claim."},
    ]


def _orchestration_graph(plan: dict[str, Any]) -> dict[str, Any]:
    package = plan.get("research_package") or {}
    track = package.get("track") or "exploratory"
    phases = ["LITERATURE", "DATAPULL"]
    if track == "confirmatory":
        phases.append("PREREGISTER")
    phases.extend(["COMPUTE", "STATSRUN", "CODEAUDIT", "REVIEWER", "WRITER"])
    return {
        "serial_gates": phases,
        "parallel_after_data": ["LITERATURE follow-up synthesis", "DATAPULL quality profiling"],
        "parallel_after_stats": ["CODEAUDIT", "Spec Audit"],
        "writer_gate": "WRITER starts only after Reviewer, Code Audit, Spec Audit, and Paper-Code Verifier pass.",
    }


def _truth_contract(run_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    plan = meta.get("plan") if isinstance(meta.get("plan"), dict) else {}
    return {
        "run_id": run_id,
        "research_state": meta.get("research_state") or "exploratory",
        "runspec_present": isinstance(meta.get("runspec"), dict),
        "research_package": plan.get("research_package", {}),
        "paper_gate": plan.get("reviewer_gate", {}),
        "repair_contract_template": plan.get("repair_contract_template", {}),
        "integrity_artifacts": plan.get("integrity_artifacts", {}),
        "audit_boundary": plan.get("audit_boundary", {}),
        "paper_code_verifier": plan.get("paper_code_verifier", {}),
        "artifact_manifest": _artifact_manifest(run_id),
        "orchestration": _orchestration_graph(plan),
        "failure_catalog": _failure_catalog(),
    }


def _write_contract_artifacts(run_id: str, meta: dict[str, Any]) -> None:
    plan = meta.get("plan") if isinstance(meta.get("plan"), dict) else {}
    files = {
        "00_runspec/runspec.json": meta.get("runspec") or {},
        "00_runspec/blueprint.json": plan,
        "01_integrity/truth_contract.json": _truth_contract(run_id, meta),
        "01_integrity/reviewer_gate.json": plan.get("reviewer_gate", {}),
        "01_integrity/repair_contract_template.json": plan.get("repair_contract_template", {}),
        "01_integrity/data_passport_preview.json": (plan.get("integrity_artifacts") or {}).get("data_passport", {}),
        "01_integrity/deviation_register.json": {"entries": [], "policy": (plan.get("integrity_artifacts") or {}).get("deviation_register", {})},
    }
    for path, payload in files.items():
        write_artifact(run_id, path, payload)


def _run_object(conn: sqlite3.Connection, row: sqlite3.Row) -> dict[str, Any]:
    meta = _parse_json(row["meta_json"] if "meta_json" in row.keys() else None)
    current, completed = _phase_state(conn, row["run_id"])
    topic = meta.get("topic") or meta.get("hypothesis") or row["seed_query"] or ""
    return {
        "run_id": row["run_id"],
        "topic": topic,
        "hypothesis": meta.get("hypothesis") or topic,
        "status": row["status"],
        "current_phase": current,
        "phases_completed": completed,
        "cost_usd": _cost(conn, row["run_id"]),
        "created_at": row["started_at"],
        "research_type": meta.get("research_type") or meta.get("research_state") or "exploratory",
        "research_state": meta.get("research_state") or "exploratory",
        "finding_valid": _finding_valid(conn, row["run_id"]),
        "data_preview_sha256": meta.get("data_preview_sha256"),
        "parent_run_id": meta.get("parent_run_id"),
        "hypothesis_id": meta.get("hypothesis_id"),
        "plan": meta.get("plan") or {},
    }


async def _launch_pipeline(run_id: str) -> None:
    env = os.environ.copy()
    env.setdefault("PYTHONPATH", str(ROOT))
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(PIPELINE_SCRIPT),
        "--resume",
        run_id,
        cwd=str(ROOT),
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    RUN_PROCESSES[run_id] = process
    log_dir = RUN_STORE / run_id
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "pipeline.log"
    try:
        assert process.stdout is not None
        async for raw in process.stdout:
            line = raw.decode(errors="replace").rstrip()
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(f"{_now()} {line}\n")
        await process.wait()
    finally:
        RUN_PROCESSES.pop(run_id, None)


@router.post("/runs/create")
async def create_run(payload: dict[str, Any]) -> dict[str, str]:
    if not _legacy_runs_enabled():
        return _create_canonical_run(payload)

    run_id = "pf-live-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    topic = str(payload.get("topic") or payload.get("hypothesis") or "Thrivarc research run").strip()
    meta = {
        "topic": topic,
        "hypothesis": payload.get("hypothesis") or topic,
        "research_type": payload.get("research_type") or "exploratory",
        "research_state": payload.get("research_state") or payload.get("approach") or "exploratory",
        "data_preview_sha256": payload.get("data_preview_sha256"),
        "parent_run_id": payload.get("parent_run_id"),
        "hypothesis_id": payload.get("hypothesis_id"),
        "plan": (payload.get("runspec") or {}).get("blueprint", {}) if isinstance(payload.get("runspec"), dict) else {},
        "runspec": payload.get("runspec"),
    }
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO pipeline_runs (run_id, started_at, finished_at, status, seed_query, meta_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (run_id, _now(), None, "queued", topic, json.dumps(meta)),
        )
        conn.commit()
    _write_contract_artifacts(run_id, meta)
    asyncio.create_task(_launch_pipeline(run_id))
    return {"run_id": run_id}


@router.get("/runs")
def list_runs() -> dict[str, list[dict[str, Any]]]:
    if not _legacy_runs_enabled():
        return {"runs": _canonical_runs()}

    with _connect() as conn:
        rows = conn.execute(
            "SELECT run_id, started_at, finished_at, status, seed_query, meta_json FROM pipeline_runs ORDER BY started_at DESC"
        ).fetchall()
        return {"runs": [_run_object(conn, row) for row in rows]}


@router.get("/runs/{run_id}/status")
def run_status(run_id: str) -> dict[str, Any]:
    canonical = _canonical_run_object(run_id)
    if canonical:
        return canonical

    if not _legacy_runs_enabled():
        _raise_run_not_found(run_id)

    with _connect() as conn:
        row = conn.execute(
            "SELECT run_id, started_at, finished_at, status, seed_query, meta_json FROM pipeline_runs WHERE run_id=? LIMIT 1",
            (run_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        return _run_object(conn, row)


@router.get("/runs/{run_id}/truth_contract")
def run_truth_contract(run_id: str) -> dict[str, Any]:
    if _canonical_session_exists(run_id):
        from api import sessions
        from storage.blob import read_artifact

        try:
            return {"truth_contract": json.loads(read_artifact(run_id, "01_integrity/truth_contract.json").decode("utf-8"))}
        except Exception:
            with sessions._with_conn() as conn:
                blueprint = sessions._blueprint_content(sessions._blueprint_row(conn, run_id))
            return {"truth_contract": sessions._truth_contract(run_id, blueprint)}

    if not _legacy_runs_enabled():
        _raise_run_not_found(run_id)

    with _connect() as conn:
        row = conn.execute(
            "SELECT run_id, started_at, finished_at, status, seed_query, meta_json FROM pipeline_runs WHERE run_id=? LIMIT 1",
            (run_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        return {"truth_contract": _truth_contract(run_id, _parse_json(row["meta_json"]))}


@router.get("/runs/{run_id}/log")
def run_log(run_id: str) -> dict[str, list[dict[str, str | None]]]:
    if _canonical_session_exists(run_id):
        from api import sessions

        with sessions._with_conn() as conn:
            rows = sessions._fetchall(
                conn,
                "SELECT created_at, agent, event_type, status, payload FROM session_events WHERE session_id=? ORDER BY created_at ASC",
                (run_id,),
            )
        return {
            "log_lines": [
                {
                    "timestamp": sessions._row_get(row, "created_at"),
                    "message": f"{sessions._row_get(row, 'agent') or 'Pipeline'} {sessions._row_get(row, 'event_type')}: {sessions._row_get(row, 'status') or ''}",
                }
                for row in rows[-500:]
            ]
        }

    if not _legacy_runs_enabled():
        _raise_run_not_found(run_id)

    run_dir = RUN_STORE / run_id
    if not run_dir.exists():
        run_dir = LEGACY_RUN_STORE / run_id
    path = run_dir / "pipeline.log"
    if not path.exists():
        return {"log_lines": []}
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()[-500:]
    out = []
    for line in lines:
        if " " in line:
            timestamp, message = line.split(" ", 1)
        else:
            timestamp, message = None, line
        out.append({"timestamp": timestamp, "message": message})
    return {"log_lines": out}


@router.get("/runs/{run_id}/artifacts")
def run_artifacts(run_id: str) -> dict[str, Any]:
    if _canonical_session_exists(run_id):
        return {"artifacts": list_artifacts(run_id)}
    if not _legacy_runs_enabled():
        _raise_run_not_found(run_id)
    return {"artifacts": _artifact_manifest(run_id)}


async def _status_events(run_id: str) -> AsyncIterator[str]:
    last_payload = ""
    while True:
        try:
            with _connect() as conn:
                row = conn.execute(
                    "SELECT run_id, started_at, finished_at, status, seed_query, meta_json FROM pipeline_runs WHERE run_id=? LIMIT 1",
                    (run_id,),
                ).fetchone()
                if not row:
                    yield 'event: error\ndata: {"error":"Run not found"}\n\n'
                    return
                payload = json.dumps(_run_object(conn, row), default=str)
        except Exception as exc:
            payload = json.dumps({"error": str(exc)})
        if payload != last_payload:
            yield f"event: status\ndata: {payload}\n\n"
            last_payload = payload
        try:
            parsed = json.loads(payload)
            if parsed.get("status") in {"done", "failed", "cancelled"}:
                return
        except Exception:
            pass
        await asyncio.sleep(2)


@router.get("/runs/{run_id}/stream")
async def run_stream(run_id: str) -> StreamingResponse:
    if _canonical_session_exists(run_id):
        async def canonical_event() -> AsyncIterator[str]:
            payload = json.dumps(_canonical_run_object(run_id), default=str)
            yield f"event: status\ndata: {payload}\n\n"

        return StreamingResponse(canonical_event(), media_type="text/event-stream")
    if not _legacy_runs_enabled():
        _raise_run_not_found(run_id)
    return StreamingResponse(_status_events(run_id), media_type="text/event-stream")


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict[str, Any]:
    if _canonical_session_exists(run_id):
        from api import sessions

        with sessions._with_conn() as conn:
            sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("cancelled", sessions._now(), run_id))
            sessions._event(conn, run_id, "run_failed", {"summary": "Run cancelled by researcher."}, "Pipeline orchestrator", "cancelled")
            sessions._commit(conn)
        return {"cancelled": True, "run_id": run_id}

    if not _legacy_runs_enabled():
        _raise_run_not_found(run_id)

    process = RUN_PROCESSES.get(run_id)
    if process and process.returncode is None:
        process.kill()
    with _connect() as conn:
        conn.execute("UPDATE pipeline_runs SET status=?, finished_at=? WHERE run_id=?", ("cancelled", _now(), run_id))
        conn.commit()
    return {"cancelled": True, "run_id": run_id}
