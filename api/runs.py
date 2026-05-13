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

from init_db import init_db

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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _phase_name(value: str | None) -> str | None:
    if not value:
        return None
    raw = str(value).strip().upper()
    return PHASE_MAP.get(raw, raw)


def _connect() -> sqlite3.Connection:
    init_db(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
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
    asyncio.create_task(_launch_pipeline(run_id))
    return {"run_id": run_id}


@router.get("/runs")
def list_runs() -> dict[str, list[dict[str, Any]]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT run_id, started_at, finished_at, status, seed_query, meta_json FROM pipeline_runs ORDER BY started_at DESC"
        ).fetchall()
        return {"runs": [_run_object(conn, row) for row in rows]}


@router.get("/runs/{run_id}/status")
def run_status(run_id: str) -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            "SELECT run_id, started_at, finished_at, status, seed_query, meta_json FROM pipeline_runs WHERE run_id=? LIMIT 1",
            (run_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Run not found")
        return _run_object(conn, row)


@router.get("/runs/{run_id}/log")
def run_log(run_id: str) -> dict[str, list[dict[str, str | None]]]:
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
    return StreamingResponse(_status_events(run_id), media_type="text/event-stream")


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str) -> dict[str, Any]:
    process = RUN_PROCESSES.get(run_id)
    if process and process.returncode is None:
        process.kill()
    with _connect() as conn:
        conn.execute("UPDATE pipeline_runs SET status=?, finished_at=? WHERE run_id=?", ("cancelled", _now(), run_id))
        conn.commit()
    return {"cancelled": True, "run_id": run_id}
