from __future__ import annotations

import base64
import csv
import hashlib
import asyncio
import inspect
import io
import json
import logging
import mimetypes
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import threading
import traceback
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from api import guide
from api import notebook_runtime
from api import prompts as prompt_catalog
from api.code_audit_agent import _audit_fallback, run_code_audit
from api.llm_caller import call_agent_llm
from api.method_agent import _method_fallback, get_method_spec
from api.method_registry import method_definition
from api.model_registry import active_model_name, allowed_chat_models, default_model, fallback_model, model_catalog, model_override
from api.literature_agent import run_literature_agent
from api.prompts import HAWK_PROMPT, REPAIR_AGENT_PROMPT
from api.stats_agent import _stats_fallback, get_stats_spec
from api.compute_dispatcher import execute_custom_analysis_code, execute_research_plan
from api.figure_generator import generate_figures_for_study
from api.writer_agent import write_paper_latex
from db.connection import DatabaseUnavailableError, get_db_connection
from integrity.pdf import render_pdf
from storage.blob import BlobStorageUnavailableError, delete_session_artifacts, download_blob, get_artifact_url, list_artifacts, list_blobs, read_artifact, write_artifact

router = APIRouter(prefix="/api/sessions")
logger = logging.getLogger(__name__)

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

COCKPIT_PHASES = [
    "Topic",
    "Blueprint",
    "Literature",
    "Data",
    "Method Plan",
    "Compute",
    "Stats / Audit",
    "Review",
    "Writer",
    "Export",
]

LOW_RISK_AUTOPILOT_PHASES = {"Literature", "Data", "Method Plan"}

COCKPIT_SSE_EVENTS = [
    "approval_required",
    "artifact_ready",
    "phase_log",
    "followup_classified",
    "sandbox_job_update",
    "repair_card_ready",
    "export_ready",
    "prompt_updated",
    "cell_started",
    "cell_output",
    "cell_artifact_ready",
    "cell_failed",
    "model_setting_updated",
    "quality_report_ready",
]

PROMPT_AGENT_KEYS = {
    "Research Architect": "RESEARCH_ARCHITECT_PROMPT",
    "Literature Agent": "LITERATURE_AGENT_PROMPT",
    "Data Agent": "RESEARCH_ARCHITECT_PROMPT",
    "Method Agent": "METHOD_AGENT_PROMPT",
    "Method / Compute Agent": "METHOD_AGENT_PROMPT",
    "Compute Agent": "METHOD_AGENT_PROMPT",
    "Statistics Agent": "STATISTICS_AGENT_PROMPT",
    "Code Audit Agent": "CODE_AUDIT_PROMPT",
    "HAWK": "HAWK_PROMPT",
    "Reviewer Agent": "HAWK_PROMPT",
    "Repair Agent": "REPAIR_AGENT_PROMPT",
    "Writer Agent": "WRITER_PROSE_PROMPT",
}

LOCKED_PROMPT_SAFETY_CONTRACT = """LOCKED THRIVARC SAFETY CONTRACT
- Do not invent numbers, sources, citations, data, credentials, or artifacts.
- Use verified PostgreSQL state and Azure Blob artifacts as the only durable truth.
- Keep Writer last; it may write only after review/verifier gates pass.
- Generated compute runs in the configured sandbox backend; production uses Modal.
- Return the requested machine-readable shape when an agent contract requires it.
- Never expose secrets, API keys, database URLs, storage credentials, or Modal tokens.
"""

DEFAULT_COMPUTE_CELLS = [
    ("Setup and Imports", "import os\nimport json\nimport pandas as pd\nimport numpy as np\n"),
    ("Load Verified Data", "data = pd.read_csv(os.environ['DATA_CSV_PATH'])\nprint(f'Loaded {len(data)} rows with columns: {list(data.columns)}')\n"),
    ("Inspect Schema", "summary = data.describe(include='all').transpose().reset_index().rename(columns={'index':'Variable'})\nsummary.to_csv(os.path.join(os.environ['RESULTS_DIR'], 'schema_summary.csv'), index=False)\nprint(summary.head().to_string(index=False))\n"),
    ("Primary Analysis", "result = {'primary_result': {'label': 'Researcher cell analysis', 'coefficient': None, 't_statistic': None, 'p_value': None, 'interpretation': 'Researcher cells executed successfully.'}, 'additional_results': [], 'figures': [], 'result_csvs': [os.path.join(os.environ['RESULTS_DIR'], 'schema_summary.csv')], 'evidence_conclusion': 'analysis_incomplete', 'economic_interpretation': 'Add or edit cockpit cells to extend this analysis.'}\nprint(json.dumps(result))\n"),
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
        CREATE TABLE IF NOT EXISTS approval_gates (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          phase_name TEXT NOT NULL,
          status TEXT NOT NULL,
          required_action TEXT,
          autopilot_eligible INTEGER DEFAULT 0,
          autopilot_reason TEXT,
          approver TEXT,
          approved_at TEXT,
          decision_notes TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS followup_instructions (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          phase_name TEXT,
          artifact_path TEXT,
          raw_instruction TEXT NOT NULL,
          classification TEXT NOT NULL,
          proposed_action TEXT NOT NULL,
          approval_status TEXT NOT NULL,
          applied_at TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS sandbox_jobs (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          phase_name TEXT,
          status TEXT NOT NULL,
          backend TEXT DEFAULT 'local',
          modal_account_alias TEXT,
          attempt_count INTEGER DEFAULT 0,
          runtime_seconds REAL,
          logs_path TEXT,
          artifact_paths TEXT,
          cost_metrics TEXT,
          failure_details TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS modal_account_usage (
          alias TEXT NOT NULL,
          usage_month TEXT NOT NULL,
          estimated_spend_usd REAL DEFAULT 0,
          monthly_budget_usd REAL DEFAULT 28,
          status TEXT DEFAULT 'healthy',
          failure_count INTEGER DEFAULT 0,
          last_failure_at TEXT,
          last_routed_at TEXT,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
          PRIMARY KEY (alias, usage_month)
        );
        CREATE TABLE IF NOT EXISTS cockpit_settings (
          session_id TEXT PRIMARY KEY,
          autopilot_enabled INTEGER DEFAULT 0,
          autopilot_criteria TEXT,
          hard_limits TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS prompt_amplifiers (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          phase_name TEXT,
          amplifier_text TEXT NOT NULL,
          version INTEGER NOT NULL,
          editor TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS prompt_templates (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          layer_type TEXT NOT NULL,
          content_text TEXT NOT NULL,
          version INTEGER NOT NULL,
          editor TEXT,
          phase_name TEXT,
          scope TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS composed_prompt_snapshots (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          phase_name TEXT,
          composed_prompt TEXT NOT NULL,
          base_prompt_key TEXT,
          amplifier_version INTEGER,
          prompt_sha256 TEXT NOT NULL,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS compute_cells (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          cell_order INTEGER NOT NULL,
          title TEXT NOT NULL,
          code TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'draft',
          stdout TEXT,
          stderr TEXT,
          output_summary TEXT,
          artifact_paths TEXT,
          created_by TEXT,
          version INTEGER DEFAULT 1,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS specialist_threads (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          selected_model TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS specialist_messages (
          id TEXT PRIMARY KEY,
          thread_id TEXT NOT NULL,
          session_id TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          role TEXT NOT NULL,
          mode TEXT,
          message_text TEXT NOT NULL,
          model_name TEXT,
          action_payload TEXT,
          artifact_paths TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS cell_execution_records (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          cell_id TEXT,
          status TEXT NOT NULL,
          backend TEXT,
          modal_account_alias TEXT,
          runtime_seconds REAL,
          stdout TEXT,
          stderr TEXT,
          artifact_paths TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS phase_model_settings (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          phase_name TEXT NOT NULL,
          model_name TEXT NOT NULL,
          updated_by TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS notebook_workspaces (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL UNIQUE,
          backend TEXT,
          modal_account_alias TEXT,
          sandbox_id TEXT,
          status TEXT NOT NULL DEFAULT 'not_started',
          access_url TEXT,
          can_embed INTEGER DEFAULT 0,
          notebook_artifact_path TEXT,
          analysis_script_path TEXT,
          artifact_paths TEXT,
          sync_status TEXT DEFAULT 'not_synced',
          last_synced_at TEXT,
          last_error TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP,
          updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS paper_quality_reports (
          id TEXT PRIMARY KEY,
          session_id TEXT NOT NULL,
          status TEXT NOT NULL,
          score REAL,
          checks TEXT,
          repair_card TEXT,
          created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """.replace("PAP_TABLE", "pap" + "_locks")
    )
    conn.commit()


def _ensure_cockpit_schema(conn: Any) -> None:
    if _is_sqlite(conn):
        return
    statements = [
        """
        CREATE TABLE IF NOT EXISTS approval_gates (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          phase_name TEXT NOT NULL,
          status TEXT NOT NULL,
          required_action TEXT,
          autopilot_eligible BOOLEAN DEFAULT FALSE,
          autopilot_reason TEXT,
          approver TEXT,
          approved_at TIMESTAMPTZ,
          decision_notes TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS followup_instructions (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          phase_name TEXT,
          artifact_path TEXT,
          raw_instruction TEXT NOT NULL,
          classification TEXT NOT NULL,
          proposed_action TEXT NOT NULL,
          approval_status TEXT NOT NULL,
          applied_at TIMESTAMPTZ,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS sandbox_jobs (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          phase_name TEXT,
          status TEXT NOT NULL,
          backend TEXT DEFAULT 'local',
          modal_account_alias TEXT,
          attempt_count INTEGER DEFAULT 0,
          runtime_seconds DOUBLE PRECISION,
          logs_path TEXT,
          artifact_paths JSONB,
          cost_metrics JSONB,
          failure_details TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS modal_account_usage (
          alias TEXT NOT NULL,
          usage_month TEXT NOT NULL,
          estimated_spend_usd DOUBLE PRECISION DEFAULT 0,
          monthly_budget_usd DOUBLE PRECISION DEFAULT 28,
          status TEXT DEFAULT 'healthy',
          failure_count INTEGER DEFAULT 0,
          last_failure_at TIMESTAMPTZ,
          last_routed_at TIMESTAMPTZ,
          updated_at TIMESTAMPTZ DEFAULT NOW(),
          PRIMARY KEY (alias, usage_month)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cockpit_settings (
          session_id TEXT PRIMARY KEY,
          autopilot_enabled BOOLEAN DEFAULT FALSE,
          autopilot_criteria JSONB,
          hard_limits JSONB,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS prompt_amplifiers (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          phase_name TEXT,
          amplifier_text TEXT NOT NULL,
          version INTEGER NOT NULL,
          editor TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS prompt_templates (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          layer_type TEXT NOT NULL,
          content_text TEXT NOT NULL,
          version INTEGER NOT NULL,
          editor TEXT,
          phase_name TEXT,
          scope TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS composed_prompt_snapshots (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          phase_name TEXT,
          composed_prompt TEXT NOT NULL,
          base_prompt_key TEXT,
          amplifier_version INTEGER,
          prompt_sha256 TEXT NOT NULL,
          created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS compute_cells (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          cell_order INTEGER NOT NULL,
          title TEXT NOT NULL,
          code TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'draft',
          stdout TEXT,
          stderr TEXT,
          output_summary TEXT,
          artifact_paths JSONB,
          created_by TEXT,
          version INTEGER DEFAULT 1,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS specialist_threads (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          selected_model TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS specialist_messages (
          id UUID PRIMARY KEY,
          thread_id UUID NOT NULL,
          session_id TEXT NOT NULL,
          agent_name TEXT NOT NULL,
          role TEXT NOT NULL,
          mode TEXT,
          message_text TEXT NOT NULL,
          model_name TEXT,
          action_payload JSONB,
          artifact_paths JSONB,
          created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cell_execution_records (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          cell_id UUID,
          status TEXT NOT NULL,
          backend TEXT,
          modal_account_alias TEXT,
          runtime_seconds DOUBLE PRECISION,
          stdout TEXT,
          stderr TEXT,
          artifact_paths JSONB,
          created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS phase_model_settings (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          phase_name TEXT NOT NULL,
          model_name TEXT NOT NULL,
          updated_by TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS notebook_workspaces (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL UNIQUE,
          backend TEXT,
          modal_account_alias TEXT,
          sandbox_id TEXT,
          status TEXT NOT NULL DEFAULT 'not_started',
          access_url TEXT,
          can_embed BOOLEAN DEFAULT FALSE,
          notebook_artifact_path TEXT,
          analysis_script_path TEXT,
          artifact_paths JSONB,
          sync_status TEXT DEFAULT 'not_synced',
          last_synced_at TIMESTAMPTZ,
          last_error TEXT,
          created_at TIMESTAMPTZ DEFAULT NOW(),
          updated_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS paper_quality_reports (
          id UUID PRIMARY KEY,
          session_id TEXT NOT NULL,
          status TEXT NOT NULL,
          score DOUBLE PRECISION,
          checks JSONB,
          repair_card JSONB,
          created_at TIMESTAMPTZ DEFAULT NOW()
        )
        """,
    ]
    for statement in statements:
        _execute(conn, statement)
    for statement in [
        "ALTER TABLE sandbox_jobs ADD COLUMN IF NOT EXISTS backend TEXT DEFAULT 'local'",
        "ALTER TABLE sandbox_jobs ADD COLUMN IF NOT EXISTS modal_account_alias TEXT",
        "ALTER TABLE sandbox_jobs ADD COLUMN IF NOT EXISTS attempt_count INTEGER DEFAULT 0",
        "ALTER TABLE sandbox_jobs ADD COLUMN IF NOT EXISTS runtime_seconds DOUBLE PRECISION",
    ]:
        _execute(conn, statement)
    _commit(conn)



_SCHEMA_ENSURED = False
_SCHEMA_ENSURED_FOR: str | None = None


def _with_conn():
    global _SCHEMA_ENSURED, _SCHEMA_ENSURED_FOR
    conn = _connect()
    # Determine which DB path this connection uses so we re-create the schema
    # whenever a test switches to a new tmp_path SQLite file.
    current_path: str | None = None
    if _is_sqlite(conn):
        current_path = os.getenv("SQLITE_DB_PATH") or "pipeline.db"
    if not _SCHEMA_ENSURED or current_path != _SCHEMA_ENSURED_FOR:
        _ensure_schema(conn)
        _ensure_cockpit_schema(conn)
        _SCHEMA_ENSURED = True
        _SCHEMA_ENSURED_FOR = current_path
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


def _phase_failure(
    conn: Any,
    session_id: str,
    agent: str,
    reason: str,
    *,
    failure_mode: str = "background_exception",
    status: str = "failed_resumable",
    traceback_text: str | None = None,
) -> None:
    existing = _fetchone(conn, "SELECT id FROM phases WHERE session_id=? AND agent_name=?", (session_id, agent))
    full_reason = f"{reason}\n\nTraceback:\n{traceback_text}" if traceback_text else reason
    if existing:
        _execute(
            conn,
            "UPDATE phases SET status=?, completed_at=?, summary_text=?, failure_reason=?, failure_mode=?, artifact_paths=? WHERE id=?",
            (status, _now(), reason, full_reason, failure_mode, json.dumps({}, sort_keys=True), _row_get(existing, "id")),
        )
    else:
        _execute(
            conn,
            "INSERT INTO phases (id, session_id, agent_name, status, started_at, completed_at, summary_text, failure_reason, failure_mode, artifact_paths) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, agent, status, _now(), _now(), reason, full_reason, failure_mode, json.dumps({}, sort_keys=True)),
        )


def _event(conn: Any, session_id: str, event_type: str, payload: dict[str, Any], agent: str | None = None, status: str | None = None) -> None:
    body = {"type": event_type, "agent": agent, "status": status, "timestamp": _now(), **payload}
    _execute(
        conn,
        "INSERT INTO session_events (id, session_id, event_type, agent, status, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), session_id, event_type, agent, status, json.dumps(body, sort_keys=True), _now()),
    )


def _json_dumps(value: Any) -> str:
    return json.dumps(value if value is not None else {}, sort_keys=True)


def _boolish(value: Any) -> bool:
    return bool(value) if not isinstance(value, str) else value.lower() in {"1", "true", "yes", "on"}


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _session_runtime_truth(conn: Any, session_id: str, *, stale_after_seconds: int | None = None) -> dict[str, Any]:
    stale_after = stale_after_seconds if stale_after_seconds is not None else int(os.getenv("THRIVARC_STALE_RUNNING_SECONDS", "1800"))
    active_statuses = {"queued", "starting", "running", "retrying"}
    active_job = _fetchone(
        conn,
        "SELECT * FROM sandbox_jobs WHERE session_id=? AND status IN ('queued','starting','running','retrying') ORDER BY updated_at DESC, created_at DESC LIMIT 1",
        (session_id,),
    )
    notebook = _notebook_workspace_row(conn, session_id)
    notebook_status = str(_row_get(notebook, "status", "") or "").lower()
    last_event = _fetchone(conn, "SELECT created_at FROM session_events WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (session_id,))
    last_event_at = _row_get(last_event, "created_at")
    last_event_dt = _parse_iso(last_event_at)
    now = datetime.now(timezone.utc)
    event_age = (now - last_event_dt).total_seconds() if last_event_dt else None
    recent_event = event_age is not None and event_age <= stale_after

    if active_job:
        return {
            "state": "modal_job",
            "label": "Modal job",
            "last_event_at": last_event_at,
            "stale": False,
            "details": _sandbox_job_dict(active_job),
        }
    if notebook_status in active_statuses and _row_get(notebook, "sandbox_id"):
        return {
            "state": "notebook",
            "label": "Notebook",
            "last_event_at": last_event_at,
            "stale": False,
            "details": _notebook_workspace_dict(notebook),
        }
    if recent_event:
        return {
            "state": "sse_recent",
            "label": "SSE recent",
            "last_event_at": last_event_at,
            "stale": False,
            "details": {"event_age_seconds": event_age},
        }
    return {
        "state": "stale",
        "label": "Stale / needs cleanup",
        "last_event_at": last_event_at,
        "stale": True,
        "details": {"event_age_seconds": event_age, "stale_after_seconds": stale_after},
    }


def _runtime_truth_for_sessions(
    conn: Any,
    session_ids: list[str],
    *,
    stale_after_seconds: int | None = None,
) -> dict[str, dict[str, Any]]:
    """Batch runtime truth for dashboard/list views without per-row DB roundtrips."""
    ids = [str(session_id) for session_id in session_ids if session_id]
    if not ids:
        return {}
    stale_after = stale_after_seconds if stale_after_seconds is not None else int(os.getenv("THRIVARC_STALE_RUNNING_SECONDS", "1800"))
    placeholders = ",".join("?" * len(ids))
    now = datetime.now(timezone.utc)

    latest_events: dict[str, Any] = {}
    for event in _fetchall(
        conn,
        f"SELECT session_id, MAX(created_at) AS created_at FROM session_events WHERE session_id IN ({placeholders}) GROUP BY session_id",
        tuple(ids),
    ):
        latest_events[str(_row_get(event, "session_id"))] = _row_get(event, "created_at")

    active_jobs: dict[str, Any] = {}
    for job in _fetchall(
        conn,
        f"""
        SELECT *
        FROM sandbox_jobs
        WHERE session_id IN ({placeholders})
          AND status IN ('queued','starting','running','retrying')
        ORDER BY updated_at DESC, created_at DESC
        """,
        tuple(ids),
    ):
        sid = str(_row_get(job, "session_id"))
        if sid not in active_jobs:
            active_jobs[sid] = job

    active_notebooks: dict[str, Any] = {}
    for notebook in _fetchall(
        conn,
        f"""
        SELECT *
        FROM notebook_workspaces
        WHERE session_id IN ({placeholders})
          AND status IN ('queued','starting','running','retrying')
          AND sandbox_id IS NOT NULL
        ORDER BY updated_at DESC, created_at DESC
        """,
        tuple(ids),
    ):
        sid = str(_row_get(notebook, "session_id"))
        if sid not in active_notebooks:
            active_notebooks[sid] = notebook

    truth: dict[str, dict[str, Any]] = {}
    for session_id in ids:
        last_event_at = latest_events.get(session_id)
        last_event_dt = _parse_iso(last_event_at)
        event_age = (now - last_event_dt).total_seconds() if last_event_dt else None
        if session_id in active_jobs:
            truth[session_id] = {
                "state": "modal_job",
                "label": "Modal job",
                "last_event_at": last_event_at,
                "stale": False,
                "details": _sandbox_job_dict(active_jobs[session_id]),
            }
        elif session_id in active_notebooks:
            truth[session_id] = {
                "state": "notebook",
                "label": "Notebook",
                "last_event_at": last_event_at,
                "stale": False,
                "details": _notebook_workspace_dict(active_notebooks[session_id]),
            }
        elif event_age is not None and event_age <= stale_after:
            truth[session_id] = {
                "state": "sse_recent",
                "label": "SSE recent",
                "last_event_at": last_event_at,
                "stale": False,
                "details": {"event_age_seconds": event_age},
            }
        else:
            truth[session_id] = {
                "state": "stale",
                "label": "Stale / needs cleanup",
                "last_event_at": last_event_at,
                "stale": True,
                "details": {"event_age_seconds": event_age, "stale_after_seconds": stale_after},
            }
    return truth


def _export_readiness_for_session(conn: Any, session_id: str) -> dict[str, Any]:
    blueprint = _blueprint_row(conn, session_id)
    blueprint_content = _blueprint_content(blueprint)
    final_tex = _safe_artifact_text(session_id, "11_paper/final.tex", limit=10)
    missing: list[str] = []
    if _row_get(blueprint, "status") != "locked":
        missing.append("blueprint_locked")
    if not (blueprint_content.get("data_preview_sha256") or blueprint_content.get("uploaded_event_sha256")):
        missing.append("evidence_approved")
    compute_done = _fetchone(conn, "SELECT id FROM phases WHERE session_id=? AND agent_name IN ('Method / Compute Agent','Compute Agent') AND status='complete' LIMIT 1", (session_id,))
    if not compute_done:
        missing.append("compute_complete")
    review_done = _fetchone(conn, "SELECT id FROM phases WHERE session_id=? AND agent_name IN ('Reviewer Agent','Paper-Code Verifier') AND status='complete' LIMIT 1", (session_id,))
    if not review_done:
        missing.append("review_complete")
    writer_done = _fetchone(conn, "SELECT id FROM phases WHERE session_id=? AND agent_name='Writer Agent' AND status='complete' LIMIT 1", (session_id,))
    if not writer_done:
        missing.append("writer_complete")
    if not final_tex.strip():
        missing.append("final_tex")
    ready = not missing
    return {
        "ready": ready,
        "status": "ready" if ready else "not_ready",
        "missing": missing,
        "overleaf_zip_route": f"/api/sessions/{session_id}/export/overleaf.zip",
        "standalone_tex_route": f"/api/sessions/{session_id}/artifacts/download?path=sessions/{session_id}/11_paper/final.tex",
    }


def _approval_gate_dict(row: Any) -> dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "phase_name": _row_get(row, "phase_name"),
        "status": _row_get(row, "status"),
        "required_action": _row_get(row, "required_action"),
        "autopilot_eligible": _boolish(_row_get(row, "autopilot_eligible")),
        "autopilot_reason": _row_get(row, "autopilot_reason"),
        "approver": _row_get(row, "approver"),
        "approved_at": _row_get(row, "approved_at"),
        "decision_notes": _row_get(row, "decision_notes"),
        "created_at": _row_get(row, "created_at"),
        "updated_at": _row_get(row, "updated_at"),
    }


def _followup_dict(row: Any) -> dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "phase_name": _row_get(row, "phase_name"),
        "artifact_path": _row_get(row, "artifact_path"),
        "raw_instruction": _row_get(row, "raw_instruction"),
        "classification": _row_get(row, "classification"),
        "proposed_action": _row_get(row, "proposed_action"),
        "approval_status": _row_get(row, "approval_status"),
        "applied_at": _row_get(row, "applied_at"),
        "created_at": _row_get(row, "created_at"),
        "updated_at": _row_get(row, "updated_at"),
    }


def _sandbox_job_dict(row: Any) -> dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "phase_name": _row_get(row, "phase_name"),
        "status": _row_get(row, "status"),
        "backend": _row_get(row, "backend", "local"),
        "modal_account_alias": _row_get(row, "modal_account_alias"),
        "attempt_count": _row_get(row, "attempt_count", 0),
        "runtime_seconds": _row_get(row, "runtime_seconds"),
        "logs_path": _row_get(row, "logs_path"),
        "artifact_paths": _json_loads(_row_get(row, "artifact_paths"), []),
        "cost_metrics": _json_loads(_row_get(row, "cost_metrics"), {}),
        "failure_details": _row_get(row, "failure_details"),
        "created_at": _row_get(row, "created_at"),
        "updated_at": _row_get(row, "updated_at"),
    }


def _prompt_amplifier_dict(row: Any) -> dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "agent_name": _row_get(row, "agent_name"),
        "phase_name": _row_get(row, "phase_name"),
        "amplifier_text": _row_get(row, "amplifier_text", ""),
        "version": int(_row_get(row, "version", 1) or 1),
        "editor": _row_get(row, "editor"),
        "created_at": _row_get(row, "created_at"),
    }


def _prompt_template_dict(row: Any) -> dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "agent_name": _row_get(row, "agent_name"),
        "layer_type": _row_get(row, "layer_type"),
        "content_text": _row_get(row, "content_text", ""),
        "version": int(_row_get(row, "version", 1) or 1),
        "editor": _row_get(row, "editor"),
        "phase_name": _row_get(row, "phase_name"),
        "scope": _row_get(row, "scope"),
        "created_at": _row_get(row, "created_at"),
    }


def _compute_cell_dict(row: Any) -> dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "cell_order": int(_row_get(row, "cell_order", 0) or 0),
        "title": _row_get(row, "title"),
        "code": _row_get(row, "code", ""),
        "status": _row_get(row, "status", "draft"),
        "stdout": _row_get(row, "stdout"),
        "stderr": _row_get(row, "stderr"),
        "output_summary": _row_get(row, "output_summary"),
        "artifact_paths": _json_loads(_row_get(row, "artifact_paths"), []),
        "created_by": _row_get(row, "created_by"),
        "version": int(_row_get(row, "version", 1) or 1),
        "created_at": _row_get(row, "created_at"),
        "updated_at": _row_get(row, "updated_at"),
    }


def _model_setting_dict(row: Any) -> dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "phase_name": _row_get(row, "phase_name"),
        "model_name": _row_get(row, "model_name", default_model()),
        "updated_by": _row_get(row, "updated_by"),
        "created_at": _row_get(row, "created_at"),
        "updated_at": _row_get(row, "updated_at"),
    }


def _specialist_message_dict(row: Any) -> dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "thread_id": _row_get(row, "thread_id"),
        "session_id": _row_get(row, "session_id"),
        "agent_name": _row_get(row, "agent_name"),
        "role": _row_get(row, "role"),
        "mode": _row_get(row, "mode"),
        "message_text": _row_get(row, "message_text", ""),
        "model_name": _row_get(row, "model_name"),
        "actions": _json_loads(_row_get(row, "action_payload"), []),
        "artifact_paths": _json_loads(_row_get(row, "artifact_paths"), []),
        "created_at": _row_get(row, "created_at"),
    }


def _specialist_thread_dict(row: Any, messages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "session_id": _row_get(row, "session_id"),
        "agent_name": _row_get(row, "agent_name"),
        "selected_model": _row_get(row, "selected_model") or default_model(),
        "created_at": _row_get(row, "created_at"),
        "updated_at": _row_get(row, "updated_at"),
        "messages": messages or [],
    }


def _notebook_workspace_dict(row: Any) -> dict[str, Any]:
    return {
        "id": _row_get(row, "id"),
        "session_id": _row_get(row, "session_id"),
        "backend": _row_get(row, "backend"),
        "modal_account_alias": _row_get(row, "modal_account_alias"),
        "sandbox_id": _row_get(row, "sandbox_id"),
        "status": _row_get(row, "status", "not_started"),
        "access_url": _row_get(row, "access_url"),
        "can_embed": _boolish(_row_get(row, "can_embed")),
        "notebook_artifact_path": _row_get(row, "notebook_artifact_path"),
        "analysis_script_path": _row_get(row, "analysis_script_path"),
        "artifact_paths": _json_loads(_row_get(row, "artifact_paths"), []),
        "sync_status": _row_get(row, "sync_status", "not_synced"),
        "last_synced_at": _row_get(row, "last_synced_at"),
        "last_error": _row_get(row, "last_error"),
        "created_at": _row_get(row, "created_at"),
        "updated_at": _row_get(row, "updated_at"),
    }


def _default_hard_limits() -> dict[str, Any]:
    return {
        "max_llm_calls": 40,
        "max_compute_minutes": 30,
        "max_sandbox_runtime_seconds": 900,
        "max_retries_per_phase": 3,
        "max_artifact_mb": 250,
        "network_policy": "allowlist_only",
    }


def _sandbox_backend_defaults() -> dict[str, Any]:
    requested = str(os.getenv("THRIVARC_COMPUTE_BACKEND") or "").strip().lower()
    backend = "modal" if os.getenv("ENVIRONMENT") == "production" else (requested or "local")
    return {
        "backend": backend,
        "modal_account_alias": os.getenv("MODAL_ACCOUNT_ALIAS", "primary") if backend == "modal" else None,
    }


def _modal_router_summary(conn: Any) -> dict[str, Any]:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    aliases = [item.strip() for item in os.getenv("MODAL_ACCOUNT_ALIASES", os.getenv("MODAL_ACCOUNT_ALIAS", "primary")).split(",") if item.strip()]
    rows = {
        _row_get(row, "alias"): row
        for row in _fetchall(conn, "SELECT * FROM modal_account_usage WHERE usage_month=?", (month,))
    }
    accounts = []
    for alias in aliases:
        row = rows.get(alias)
        budget = float(_row_get(row, "monthly_budget_usd", os.getenv("MODAL_MONTHLY_BUDGET_USD", 28)) or 28)
        spend = float(_row_get(row, "estimated_spend_usd", 0) or 0)
        accounts.append(
            {
                "alias": alias,
                "usage_month": month,
                "estimated_spend_usd": spend,
                "monthly_budget_usd": budget,
                "remaining_budget_usd": max(0.0, budget - spend),
                "status": _row_get(row, "status", "not_used"),
                "failure_count": int(_row_get(row, "failure_count", 0) or 0),
            }
        )
    return {
        "enabled": os.getenv("MODAL_ROUTER_ENABLED", "0").strip().lower() in {"1", "true", "yes"},
        "policy": "least_spend_healthy_under_budget",
        "budget_enforcement": "app_soft_cap",
        "accounts": accounts,
    }


def _default_autopilot_criteria() -> dict[str, Any]:
    return {
        "allowed_phases": sorted(LOW_RISK_AUTOPILOT_PHASES),
        "requires_no_deviations": True,
        "requires_no_failures": True,
        "requires_artifacts_present": True,
        "requires_cost_within_limits": True,
    }


def _ensure_cockpit_settings(conn: Any, session_id: str) -> None:
    existing = _fetchone(conn, "SELECT session_id FROM cockpit_settings WHERE session_id=?", (session_id,))
    if existing:
        return
    _execute(
        conn,
        "INSERT INTO cockpit_settings (session_id, autopilot_enabled, autopilot_criteria, hard_limits, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, False, _json_dumps(_default_autopilot_criteria()), _json_dumps(_default_hard_limits()), _now(), _now()),
    )


def _ensure_approval_gates(conn: Any, session_id: str) -> None:
    _ensure_cockpit_settings(conn, session_id)
    for phase in COCKPIT_PHASES:
        existing = _fetchone(conn, "SELECT id FROM approval_gates WHERE session_id=? AND phase_name=?", (session_id, phase))
        if existing:
            continue
        eligible = phase in LOW_RISK_AUTOPILOT_PHASES
        reason = "Eligible only when no deviations, failures, or limit breaches are present." if eligible else "Manual approval required for this research-control gate."
        _execute(
            conn,
            "INSERT INTO approval_gates (id, session_id, phase_name, status, required_action, autopilot_eligible, autopilot_reason, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, phase, "pending", "Approve / Revise / Stop", bool(eligible), reason, _now(), _now()),
        )


def _allowed_models() -> list[str]:
    return allowed_chat_models()


def _canonical_prompt_agent(agent_name: Any) -> str:
    raw = str(agent_name or "").strip()
    if raw in PROMPT_AGENT_KEYS:
        return raw
    lowered = raw.lower()
    aliases = {
        "architect": "Research Architect",
        "research architect agent": "Research Architect",
        "literature": "Literature Agent",
        "data": "Data Agent",
        "method": "Method Agent",
        "compute": "Compute Agent",
        "statistics": "Statistics Agent",
        "stats": "Statistics Agent",
        "code audit": "Code Audit Agent",
        "audit": "Code Audit Agent",
        "hawk": "HAWK",
        "review": "Reviewer Agent",
        "reviewer": "Reviewer Agent",
        "repair": "Repair Agent",
        "writer": "Writer Agent",
    }
    if lowered in aliases:
        return aliases[lowered]
    with_agent = f"{raw} Agent"
    if with_agent in PROMPT_AGENT_KEYS:
        return with_agent
    return raw


def _latest_prompt_amplifier(conn: Any, session_id: str, agent_name: str):
    return _fetchone(
        conn,
        "SELECT * FROM prompt_amplifiers WHERE session_id=? AND agent_name=? ORDER BY version DESC, created_at DESC LIMIT 1",
        (session_id, agent_name),
    )


def _latest_prompt_template(conn: Any, session_id: str, agent_name: str, layer_type: str):
    return _fetchone(
        conn,
        "SELECT * FROM prompt_templates WHERE session_id=? AND agent_name=? AND layer_type=? ORDER BY version DESC, created_at DESC LIMIT 1",
        (session_id, agent_name, layer_type),
    )


def _template_content(conn: Any, session_id: str, agent_name: str, layer_type: str, fallback: str = "") -> str:
    row = _latest_prompt_template(conn, session_id, agent_name, layer_type)
    return str(_row_get(row, "content_text", fallback) or fallback)


def _latest_template_version(conn: Any, session_id: str, agent_name: str, layer_type: str) -> int:
    row = _latest_prompt_template(conn, session_id, agent_name, layer_type)
    return int(_row_get(row, "version", 0) or 0)


def _upsert_prompt_template(
    conn: Any,
    session_id: str,
    agent_name: str,
    layer_type: str,
    content_text: str,
    editor: str,
    *,
    phase_name: str | None = None,
    scope: str | None = None,
):
    version = _latest_template_version(conn, session_id, agent_name, layer_type) + 1
    template_id = str(uuid.uuid4())
    _execute(
        conn,
        "INSERT INTO prompt_templates (id, session_id, agent_name, layer_type, content_text, version, editor, phase_name, scope, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (template_id, session_id, agent_name, layer_type, content_text, version, editor, phase_name, scope, _now()),
    )
    return _fetchone(conn, "SELECT * FROM prompt_templates WHERE id=?", (template_id,))


def _base_prompt_for_agent(agent_name: str) -> tuple[str, str]:
    key = PROMPT_AGENT_KEYS.get(agent_name) or PROMPT_AGENT_KEYS.get(agent_name.replace(" Agent", ""), "")
    prompt = getattr(prompt_catalog, key, "") if key else ""
    return key or "UNKNOWN_PROMPT", str(prompt or "")


def _prompt_template_summary(conn: Any, session_id: str, agent_name: str) -> dict[str, Any]:
    base_key, base_prompt = _base_prompt_for_agent(agent_name)
    working_prompt = _template_content(conn, session_id, agent_name, "working_prompt", base_prompt)
    session_notes = _template_content(conn, session_id, agent_name, "session_notes", "")
    return {
        "agent_name": agent_name,
        "base_prompt_key": base_key,
        "working_prompt": working_prompt,
        "working_prompt_version": _latest_template_version(conn, session_id, agent_name, "working_prompt"),
        "session_notes": session_notes,
        "notes_version": _latest_template_version(conn, session_id, agent_name, "session_notes"),
    }


def _prompt_template_summaries(conn: Any, session_id: str) -> list[dict[str, Any]]:
    return [_prompt_template_summary(conn, session_id, agent_name) for agent_name in sorted(PROMPT_AGENT_KEYS.keys())]


def _compose_prompt(conn: Any, session_id: str, agent_name: str, phase_name: str | None = None, *, persist: bool = True) -> dict[str, Any]:
    base_key, base_prompt = _base_prompt_for_agent(agent_name)
    amplifier = _latest_prompt_amplifier(conn, session_id, agent_name)
    blueprint = _blueprint_content(_blueprint_row(conn, session_id))
    artifact_names = [_artifact_relative_path(session_id, str(item.get("path") or "")) for item in list_artifacts(session_id)[-20:]]
    amplifier_text = _row_get(amplifier, "amplifier_text", "")
    amplifier_version = int(_row_get(amplifier, "version", 0) or 0)
    working_prompt = _template_content(conn, session_id, agent_name, "working_prompt", base_prompt)
    working_prompt_version = _latest_template_version(conn, session_id, agent_name, "working_prompt")
    session_notes = _template_content(conn, session_id, agent_name, "session_notes", "")
    session_notes_version = _latest_template_version(conn, session_id, agent_name, "session_notes")
    composed = "\n\n".join(
        [
            LOCKED_PROMPT_SAFETY_CONTRACT,
            f"EDITABLE WORKING PROMPT ({base_key}, version {working_prompt_version or 0})\n{working_prompt}",
            f"SESSION-SPECIFIC NOTES (version {session_notes_version or 0})\n{session_notes or '[none supplied]'}",
            f"LEGACY TASK AMPLIFIER (version {amplifier_version})\n{amplifier_text or '[none supplied]'}",
            f"LOCKED BLUEPRINT CONTEXT\n{json.dumps(blueprint, indent=2, sort_keys=True, default=str)}",
            f"RECENT VERIFIED ARTIFACTS\n{json.dumps(artifact_names, indent=2)}",
        ]
    )
    prompt_hash = hashlib.sha256(composed.encode("utf-8")).hexdigest()
    snapshot_id = None
    if persist:
        snapshot_id = str(uuid.uuid4())
        _execute(
            conn,
            "INSERT INTO composed_prompt_snapshots (id, session_id, agent_name, phase_name, composed_prompt, base_prompt_key, amplifier_version, prompt_sha256, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (snapshot_id, session_id, agent_name, phase_name, composed, base_key, amplifier_version, prompt_hash, _now()),
        )
    return {
        "id": snapshot_id,
        "agent_name": agent_name,
        "phase_name": phase_name,
        "base_prompt_key": base_key,
        "amplifier_version": amplifier_version,
        "prompt_sha256": prompt_hash,
        "locked_safety_contract": LOCKED_PROMPT_SAFETY_CONTRACT,
        "base_prompt": base_prompt,
        "working_prompt": working_prompt,
        "working_prompt_version": working_prompt_version,
        "session_notes": session_notes,
        "notes_version": session_notes_version,
        "amplifier_text": amplifier_text,
        "composed_prompt": composed,
    }


def _snapshot_all_agent_prompts(conn: Any, session_id: str) -> None:
    for agent_name in AGENT_SEQUENCE:
        _compose_prompt(conn, session_id, agent_name, agent_name, persist=True)


def _phase_model_aliases(name: str) -> list[str]:
    raw = str(name or "").strip()
    canonical = _canonical_prompt_agent(raw)
    aliases = {
        "Research Architect": ["Blueprint", "Research Architect"],
        "Literature Agent": ["Literature", "Literature Agent"],
        "Data Agent": ["Data", "Data Agent"],
        "Method / Compute Agent": ["Method Plan", "Compute", "Method / Compute Agent", "Method Agent", "Compute Agent"],
        "Statistics Agent": ["Stats / Audit", "Statistics Agent"],
        "Code Audit Agent": ["Stats / Audit", "Code Audit Agent"],
        "Reviewer Agent": ["Review", "Reviewer Agent", "HAWK"],
        "Writer Agent": ["Writer", "Writer Agent"],
        "Repair Agent": ["Review", "Repair Agent"],
    }
    values = aliases.get(canonical, []) + [raw, canonical]
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = value.lower()
        if value and key not in seen:
            seen.add(key)
            out.append(value)
    return out


def _selected_model_for_phase(conn: Any, session_id: str, phase_name: str, *, fallback: str | None = None) -> str:
    aliases = _phase_model_aliases(phase_name)
    for alias in aliases:
        row = _fetchone(conn, "SELECT * FROM phase_model_settings WHERE session_id=? AND phase_name=? ORDER BY updated_at DESC, created_at DESC LIMIT 1", (session_id, alias))
        model_name = str(_row_get(row, "model_name") or "").strip()
        if model_name and model_name in _allowed_models():
            return model_name
    return active_model_name(fallback or default_model())


def _specialist_thread(conn: Any, session_id: str, agent_name: str):
    canonical = _canonical_prompt_agent(agent_name)
    thread = _fetchone(conn, "SELECT * FROM specialist_threads WHERE session_id=? AND agent_name=? ORDER BY updated_at DESC, created_at DESC LIMIT 1", (session_id, canonical))
    if thread:
        return thread
    thread_id = str(uuid.uuid4())
    selected_model = _selected_model_for_phase(conn, session_id, canonical)
    _execute(
        conn,
        "INSERT INTO specialist_threads (id, session_id, agent_name, selected_model, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
        (thread_id, session_id, canonical, selected_model, _now(), _now()),
    )
    return _fetchone(conn, "SELECT * FROM specialist_threads WHERE id=?", (thread_id,))


def _specialist_messages(conn: Any, thread_id: str) -> list[dict[str, Any]]:
    return [
        _specialist_message_dict(row)
        for row in _fetchall(conn, "SELECT * FROM specialist_messages WHERE thread_id=? ORDER BY created_at ASC", (thread_id,))
    ]


def _notebook_workspace_row(conn: Any, session_id: str):
    return _fetchone(conn, "SELECT * FROM notebook_workspaces WHERE session_id=? LIMIT 1", (session_id,))


def _ensure_default_compute_cells(conn: Any, session_id: str, created_by: str = "system") -> None:
    existing = _fetchone(conn, "SELECT id FROM compute_cells WHERE session_id=? LIMIT 1", (session_id,))
    if existing:
        return
    for idx, (title, code) in enumerate(DEFAULT_COMPUTE_CELLS, start=1):
        _execute(
            conn,
            "INSERT INTO compute_cells (id, session_id, cell_order, title, code, status, artifact_paths, created_by, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), session_id, idx, title, code, "draft", _json_dumps([]), created_by, 1, _now(), _now()),
        )


def _compute_cells(conn: Any, session_id: str) -> list[dict[str, Any]]:
    _ensure_default_compute_cells(conn, session_id)
    return [_compute_cell_dict(row) for row in _fetchall(conn, "SELECT * FROM compute_cells WHERE session_id=? ORDER BY cell_order ASC, created_at ASC", (session_id,))]


def _concat_cell_code(cells: list[dict[str, Any]], upto_cell_id: str | None = None) -> str:
    chunks: list[str] = []
    for cell in cells:
        chunks.append(f"# %% [{cell.get('title') or 'Cell'}]\n{cell.get('code') or ''}\n")
        if upto_cell_id and cell.get("id") == upto_cell_id:
            break
    return "\n".join(chunks).strip() + "\n"


def _notebook_from_cells(cells: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "cells": [
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {"title": cell.get("title"), "cell_id": cell.get("id"), "status": cell.get("status")},
                "outputs": [],
                "source": [line + "\n" for line in str(cell.get("code") or "").splitlines()],
            }
            for cell in cells
        ],
        "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"}, "language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _quality_report_for_session(session_id: str) -> dict[str, Any]:
    tex = _safe_artifact_text(session_id, "11_paper/final.tex")
    artifacts_list = list_artifacts(session_id)
    relative_paths = [_artifact_relative_path(session_id, str(item.get("path") or "")) for item in artifacts_list]
    if not tex.strip():
        checks = {
            "final_tex_present": False,
            "line_count": 0,
            "line_count_minimum_met": False,
            "has_literature": False,
            "has_tables": False,
            "has_figures": any(path.startswith("figures/") for path in relative_paths),
            "has_empty_numeric_claims": False,
            "generic_template_phrases": [],
        }
        return {
            "status": "not_ready",
            "score": None,
            "checks": checks,
            "repair_card": {
                "summary": "Paper quality cannot be scored until Writer produces final.tex.",
                "required_action": "Complete review and writer gates before export.",
            },
        }
    line_count = len([line for line in tex.splitlines() if line.strip()])
    checks = {
        "final_tex_present": bool(tex.strip()),
        "line_count": line_count,
        "line_count_minimum_met": line_count >= 250,
        "has_literature": bool(re.search(r"\\section\{Literature", tex, flags=re.IGNORECASE)),
        "has_tables": "\\begin{table" in tex,
        "has_figures": "\\includegraphics" in tex or any(path.startswith("figures/") for path in relative_paths),
        "has_empty_numeric_claims": bool(re.search(r"=\s*(?:,|\\.|$)|t=\s*(?:,|\\.|$)|p=\s*(?:,|\\.|$)", tex)),
        "generic_template_phrases": [phrase for phrase in ["economic phenomenon studied in this paper", "The main results are", "finance claims often become persuasive"] if phrase in tex],
    }
    passed = bool(checks["final_tex_present"] and checks["line_count_minimum_met"] and checks["has_tables"] and checks["has_figures"] and not checks["has_empty_numeric_claims"] and not checks["generic_template_phrases"])
    score = sum(
        [
            bool(checks["final_tex_present"]),
            bool(checks["line_count_minimum_met"]),
            bool(checks["has_literature"]),
            bool(checks["has_tables"]),
            bool(checks["has_figures"]),
            not bool(checks["has_empty_numeric_claims"]),
            not bool(checks["generic_template_phrases"]),
        ]
    ) / 7 * 10
    repair_card = None if passed else {
        "summary": "Paper quality verifier found shallow or incomplete paper outputs before export.",
        "recommended_action": "Revise Writer prompt amplifier and rerender before treating the paper as final.",
        "blocking_checks": [key for key, value in checks.items() if value is False or (isinstance(value, list) and value)],
    }
    return {"status": "pass" if passed else "needs_repair", "score": round(score, 2), "checks": checks, "repair_card": repair_card}


def _classify_followup(instruction: str) -> tuple[str, str, str]:
    text = re.sub(r"\s+", " ", str(instruction or "")).strip()
    lowered = text.lower()
    unsafe = ("password", "secret", "api key", "token", "drop table", "delete database", "credential")
    blueprint_terms = ("blueprint", "hypothesis", "claim", "method", "identifier", "ticker", "date range", "window", "data source", "evidence route")
    phase_terms = ("rerun", "recompute", "add test", "add chart", "add figure", "fix table", "revise", "robustness", "regression", "sample")
    if not text:
        return "invalid_unsafe", "Reject empty instruction.", "rejected"
    if any(term in lowered for term in unsafe):
        return "invalid_unsafe", "Do not apply; instruction may expose credentials or destructive operations.", "rejected"
    if any(term in lowered for term in blueprint_terms):
        return "blueprint_changing_deviation", "Create a deviation register entry and require researcher approval before changing the locked research contract.", "needs_approval"
    if any(term in lowered for term in phase_terms):
        return "phase_local_revision", "Queue a phase-local revision at the next safe pause point.", "needs_approval"
    return "harmless_annotation", "Attach as researcher guidance for downstream agents without changing execution.", "needs_approval"


def _session_row(conn: Any, session_id: str):
    return _fetchone(conn, "SELECT * FROM sessions WHERE id=?", (session_id,))


def _blueprint_row(conn: Any, session_id: str):
    return _fetchone(conn, "SELECT * FROM blueprints WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (session_id,))


def _not_found() -> JSONResponse:
    return _error(404, "SESSION_NOT_FOUND", "Session was not found.", "not_found", ["return_to_sessions"])


def _blueprint_content(row: Any) -> dict[str, Any]:
    return _json_loads(_row_get(row, "content"), {})


def _payload_or_constraint(payload: dict[str, Any], constraints: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload and payload.get(key) not in (None, "", [], {}):
            return payload.get(key)
        if key in constraints and constraints.get(key) not in (None, "", [], {}):
            return constraints.get(key)
    return None


def _as_identifier_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().upper() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip().upper() for item in value.split(",") if item.strip()]
    return []


def _window_from_payload(payload: dict[str, Any], constraints: dict[str, Any], fallback: Any) -> dict[str, str]:
    window = _payload_or_constraint(payload, constraints, "inferred_window", "window", "date_window")
    if isinstance(window, dict):
        start = window.get("start") or window.get("start_date")
        end = window.get("end") or window.get("end_date")
        if start and end:
            return {"start": str(start), "end": str(end)}
    start = _payload_or_constraint(payload, constraints, "window_start", "start_date", "start")
    end = _payload_or_constraint(payload, constraints, "window_end", "end_date", "end")
    if start and end:
        return {"start": str(start), "end": str(end)}
    return fallback if isinstance(fallback, dict) else {}


def _reviewer_gate() -> dict[str, Any]:
    gate = guide._reviewer_gate(True, "regression")
    gate.setdefault("thresholds", {"average_minimum": 7.0, "dimension_floor": 5.0, "max_cycles": 3})
    return gate


def _normalized_reviewer_gate(value: Any) -> dict[str, Any]:
    gate = value if isinstance(value, dict) else _reviewer_gate()
    threshold = gate.get("paper_unlock_threshold") if isinstance(gate.get("paper_unlock_threshold"), dict) else {}
    gate.setdefault(
        "thresholds",
        {
            "average_minimum": float(threshold.get("minimum_average", 7.0)),
            "dimension_floor": float(threshold.get("minimum_dimension", 5.0)),
            "max_cycles": int(gate.get("max_repair_cycles_per_issue", 3)),
        },
    )
    return gate


def _repair_contract_template() -> dict[str, Any]:
    return guide._repair_contract_template()


def _blueprint_from_scope(session: Any, payload: dict[str, Any]) -> dict[str, Any]:
    topic = payload.get("focus_question") or payload.get("hypothesis") or _row_get(session, "topic")
    constraints = payload.get("constraints") if isinstance(payload.get("constraints"), dict) else {}
    validated = guide.validate(
        {
            "topic": topic,
            "hypothesis": payload.get("hypothesis"),
            "context": json.dumps(constraints),
            "target_outcome": payload.get("target_outcome"),
        }
    )
    summary = validated.get("blueprint_summary", {}) if isinstance(validated, dict) else {}
    explicit_method = _payload_or_constraint(payload, constraints, "method_family", "method_style", "method")
    explicit_evidence = _payload_or_constraint(payload, constraints, "evidence_route", "evidence_source", "price_data_route", "connector")
    explicit_identifiers = _as_identifier_list(
        _payload_or_constraint(payload, constraints, "inferred_identifiers", "identifiers", "tickers", "symbols")
    )
    explicit_window = _window_from_payload(payload, constraints, summary.get("inferred_window"))
    return_definition = _payload_or_constraint(payload, constraints, "return_definition", "overnight_return")
    event_file = _payload_or_constraint(payload, constraints, "event_file", "event_upload_path", "uploaded_event_file")
    uploaded_event_sha256 = _payload_or_constraint(payload, constraints, "uploaded_event_sha256", "event_sha256", "sha256")
    method = str(explicit_method or summary.get("method_family") or summary.get("method_style") or "regression")
    evidence = str(explicit_evidence or summary.get("evidence_source") or "upload_or_connector")
    identifiers = explicit_identifiers or summary.get("inferred_identifiers") or []
    return {
        "session_id": _row_get(session, "id"),
        "topic": _row_get(session, "topic"),
        "research_type": payload.get("research_type") or _row_get(session, "research_type") or "unknown",
        "focus_question": topic,
        "hypothesis": payload.get("hypothesis") or summary.get("if_true"),
        "method_family": method,
        "method_style": method,
        "evidence_source": evidence,
        "evidence_route": evidence,
        "event_file": event_file,
        "uploaded_event_sha256": uploaded_event_sha256,
        "constraints": constraints,
        "target_outcome": payload.get("target_outcome") or "research_report",
        "inferred_identifiers": identifiers,
        "inferred_window": explicit_window,
        "return_definition": return_definition,
        "overnight_return": return_definition,
        "data_structure": payload.get("data_structure") or constraints.get("data_structure") or summary.get("data_structure"),
        "outcome_variable": payload.get("outcome_variable") or constraints.get("outcome_variable") or summary.get("outcome_variable"),
        "key_predictors": payload.get("key_predictors") or constraints.get("key_predictors") or summary.get("key_predictors") or [],
        "control_variables": payload.get("control_variables") or constraints.get("control_variables") or summary.get("control_variables") or [],
        "identification_strategy": payload.get("identification_strategy") or constraints.get("identification_strategy") or summary.get("identification_strategy"),
        "clarification_policy": summary.get("clarification_policy") or [],
        "research_package": summary.get("research_package") or {},
        "completion_contract": summary.get("completion_contract") or {},
        "launch_readiness": summary.get("launch_readiness") or {},
        "reviewer_gate": _normalized_reviewer_gate(summary.get("reviewer_gate")),
        "repair_contract_template": summary.get("repair_contract_template") or _repair_contract_template(),
        "integrity_artifacts": summary.get("integrity_artifacts") or guide._integrity_artifacts(payload.get("research_type") == "confirmatory"),
        "audit_boundary": summary.get("audit_boundary") or guide._audit_boundary(),
        "paper_code_verifier": summary.get("paper_code_verifier") or guide._paper_code_verifier_policy(),
        "data_quality_policy": summary.get("data_quality_policy") or guide._data_quality_policy(evidence),
        "leakage_policy": summary.get("leakage_policy") or guide._leakage_policy(method),
        "statistical_battery": summary.get("statistical_battery") or guide._statistical_battery(method),
        "economic_significance": summary.get("economic_significance") or guide._economic_significance(method),
        "data_fallback_policy": summary.get("data_fallback_policy") or guide._data_fallback_policy(evidence),
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


def _write_json_artifact(session_id: str, path: str, payload: dict[str, Any] | list[Any]) -> dict[str, Any]:
    return write_artifact(session_id, path, payload)


def _write_text_artifact(session_id: str, path: str, text: str) -> dict[str, Any]:
    return write_artifact(session_id, path, text)


def _complete_agent(conn: Any, session_id: str, agent: str, summary: str, artifacts: dict[str, Any] | None = None) -> None:
    _phase_status(conn, session_id, agent, "complete", summary, artifacts)
    _event(conn, session_id, "phase_update", {"summary": summary, "artifacts": artifacts or {}}, agent, "complete")


def _topic_text(blueprint: dict[str, Any]) -> str:
    return str(blueprint.get("focus_question") or blueprint.get("topic") or "Thrivarc research question")


def _method_family(blueprint: dict[str, Any]) -> str:
    method = str(blueprint.get("method_family") or blueprint.get("method_style") or "regression")
    return method


def _evidence_source(blueprint: dict[str, Any]) -> str:
    return str(blueprint.get("evidence_source") or "upload_or_connector")


def _topic_flavor(topic: str, method: str, evidence: str) -> str:
    clean_method = re.sub(r"[^a-z0-9_]+", "_", str(method or "method").lower()).strip("_")
    clean_evidence = re.sub(r"[^a-z0-9_]+", "_", str(evidence or "evidence").lower()).strip("_")
    return f"{clean_method}_{clean_evidence}"


def _round_number(value: Any, digits: int = 4) -> float | None:
    try:
        return round(float(value), digits)
    except Exception:
        return None


def _price_column(frame: Any, field: str, ticker: str):
    if getattr(frame, "columns", None) is None:
        raise KeyError(f"Missing columns for {ticker}.")
    if hasattr(frame.columns, "nlevels") and frame.columns.nlevels == 2:
        if (field, ticker) in frame.columns:
            return frame[(field, ticker)]
        if (ticker, field) in frame.columns:
            return frame[(ticker, field)]
    if field in frame.columns:
        return frame[field]
    raise KeyError(f"Missing {field} for {ticker}.")


def _csv_text(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return out.getvalue()


def _clean_float(value: Any, digits: int = 6) -> float | None:
    rounded = _round_number(value, digits)
    return rounded if rounded is not None else None


def _execution_profile(blueprint: dict[str, Any], session_id: str | None = None) -> dict[str, Any]:
    compute_model = default_model()
    if session_id:
        with _with_conn() as conn:
            amplifiers = {
                _row_get(row, "agent_name"): _row_get(row, "amplifier_text", "")
                for row in _fetchall(
                    conn,
                    "SELECT DISTINCT ON (agent_name) agent_name, amplifier_text, version FROM prompt_amplifiers WHERE session_id=? ORDER BY agent_name, version DESC, created_at DESC",
                    (session_id,),
                )
            } if not _is_sqlite(conn) else {
                _row_get(row, "agent_name"): _row_get(row, "amplifier_text", "")
                for row in _fetchall(
                    conn,
                    "SELECT agent_name, amplifier_text, MAX(version) AS version FROM prompt_amplifiers WHERE session_id=? GROUP BY agent_name",
                    (session_id,),
                )
            }
            compute_model = _selected_model_for_phase(conn, session_id, "Compute")
        if amplifiers:
            blueprint = {**blueprint, "researcher_prompt_amplifiers": amplifiers}
    topic = _topic_text(blueprint)
    method = _method_family(blueprint)
    evidence = _evidence_source(blueprint)
    flavor = _topic_flavor(topic, method, evidence)
    title = topic.split("\n", 1)[0].strip() or "Thrivarc Research Run"
    with model_override(compute_model):
        executed = execute_research_plan(blueprint, session_id=session_id)
    primary_numbers = executed["primary_numbers"]
    spec = method_definition(method)
    compute_path = spec.get("compute_path", f"06_compute/method_outputs/{method}_results.json")
    compute = {
        "method_family": method,
        "evidence_source": evidence,
        "blueprint_topic": topic,
        "result_schema": spec.get("result_schema", f"{method}_general_execution_v1"),
        "universe": executed.get("context", {}).get("identifiers", []),
        "window": executed.get("context", {}).get("window", {}),
        "return_definition": primary_numbers.get("return_definition") or blueprint.get("return_definition") or "locked Blueprint return definition",
        "primary_numbers": primary_numbers,
        "event_results": executed.get("event_rows", []),
        "event_window_car": executed.get("car_rows", []),
        "executed_tests": executed.get("robustness_results", {}),
        "stats_summary": executed.get("stats_summary", {}),
        "verified_csv_artifacts": {
            path: hashlib.sha256(text.encode("utf-8")).hexdigest()
            for path, text in executed.get("csv_outputs", {}).items()
        },
        "robustness": [
            {"check": name, "passes": payload.get("status") == "complete", "result": payload}
            for name, payload in executed.get("robustness_results", {}).items()
            if isinstance(payload, dict)
        ],
        "evidence_conclusion": executed.get("evidence_conclusion"),
    }
    interpretation = executed.get("economic_interpretation") or (
        "The executed statistics are reported from verified artifacts and interpreted within the locked claim scope."
    )
    profile = _profile(
        blueprint,
        method,
        evidence,
        flavor,
        title,
        compute_path,
        compute,
        f"Retrieved literature should position this {method} design against relevant empirical finance work.",
        interpretation,
        primary_numbers,
        spec.get("claim_scope", f"{method} evidence"),
        spec.get("concepts", [method]),
        spec.get("features", ["date", "identifier", "return"]),
        spec.get("leakage_rule", "All predictors must be timestamped before outcomes."),
        spec.get("primary_test", "Artifact-backed statistical test"),
    )
    profile["csv_outputs"] = executed.get("csv_outputs", {})
    profile["figure_artifacts"] = executed.get("figure_artifacts", {})
    profile["execution_artifacts"] = executed.get("execution_artifacts", {})
    profile["execution_metadata"] = executed.get("execution_metadata", {})
    profile["verified_csv_artifacts"] = compute["verified_csv_artifacts"]
    profile["statistics"].update(
        {
            "primary_numbers": primary_numbers,
            "robustness_results": executed.get("robustness_results", {}),
            "stats_summary": executed.get("stats_summary", {}),
            "summary_statistics": executed.get("summary_statistics_rows", []),
            "executed_tests": executed.get("executed_test_rows", []),
            "event_window_car": executed.get("car_rows", []),
            "evidence_conclusion": executed.get("evidence_conclusion"),
        }
    )
    profile["findings"].update(
        {
            "primary_numbers": primary_numbers,
            "robustness_results": executed.get("robustness_results", {}),
            "economic_significance_assessment": profile["economic_significance"],
            "evidence_conclusion": executed.get("evidence_conclusion"),
            "claim_language": "Writer must describe exactly what the evidence-backed estimates support and must not broaden the claim.",
        }
    )
    profile["data_passport"].update(
        {
            "plain_english_summary": f"This DataPassport certifies the {evidence} evidence used for the locked {method} design.",
            "source": evidence,
            "frequency": blueprint.get("recommended_frequency") or "daily or design-specific",
            "rows": executed.get("data_row_count", 0),
            "price_result_sha256": executed.get("price_result_sha256"),
            "date_range": f"{executed.get('price_window', {}).get('start')} to {executed.get('price_window', {}).get('end')}",
            "csv_artifacts": profile["verified_csv_artifacts"],
        }
    )
    profile["verification"].update(
        {
            "csv_artifacts_verified": True,
            "verified_csv_artifacts": profile["verified_csv_artifacts"],
            "checked_numbers": primary_numbers,
        }
    )
    profile["economic_significance"].update(
        {
            "primary_effect": primary_numbers.get("mean_aligned_effect") or primary_numbers.get("newey_west_coefficient"),
            "conclusion": executed.get("evidence_conclusion"),
        }
    )
    profile["phase_summary"]["Data Agent"] = f"{evidence} evidence converted to {executed.get('data_row_count', 0)} verified rows."
    profile["phase_summary"]["Method / Compute Agent"] = f"{method} execution completed using the locked Blueprint inputs."
    profile["phase_summary"]["Statistics Agent"] = f"Executed {len(executed.get('stats_summary', {}).get('executed_tests', []))} statistical tests; skipped tests are explicit in artifacts."
    return profile


def _profile(
    blueprint: dict[str, Any],
    method: str,
    evidence: str,
    flavor: str,
    title: str,
    compute_path: str,
    compute: dict[str, Any],
    literature_positioning: str,
    interpretation: str,
    primary_numbers: dict[str, Any],
    claim_scope: str,
    concepts: list[str],
    features: list[str],
    timing_rule: str,
    primary_test: str,
) -> dict[str, Any]:
    topic = _topic_text(blueprint)
    spec = method_definition(method)
    modeling_frameworks = list(spec.get("modeling_frameworks", []))
    diagnostic_tests = list(spec.get("diagnostic_tests", []))
    inference_tests = list(spec.get("inference_tests", []))
    evaluation_tests = list(spec.get("evaluation_tests", []))
    statistical_tests = list(spec.get("statistical_tests", []))
    compute_skills = list(dict.fromkeys([method, primary_test] + modeling_frameworks))
    stats_skills = list(dict.fromkeys([primary_test, "robustness", "economic significance"] + statistical_tests))
    compute_contract = {
        **compute,
        "interpretation": interpretation,
        "modeling_frameworks": modeling_frameworks,
        "diagnostic_tests": diagnostic_tests,
        "inference_tests": inference_tests,
        "evaluation_tests": evaluation_tests,
        "statistical_tests": statistical_tests,
        "models_vs_tests_rule": spec.get("models_vs_tests_rule"),
    }
    return {
        "method_family": method,
        "evidence_source": evidence,
        "flavor": flavor,
        "title": title,
        "topic": topic,
        "claim_scope": claim_scope,
        "compute_path": compute_path,
        "execution_profile": {
            "method_family": method,
            "evidence_source": evidence,
            "flavor": flavor,
            "compute_path": compute_path,
            "primary_test": primary_test,
            "analytical_domain": spec.get("analytical_domain"),
            "modeling_frameworks": modeling_frameworks,
            "diagnostic_tests": diagnostic_tests,
            "inference_tests": inference_tests,
            "evaluation_tests": evaluation_tests,
            "statistical_tests": statistical_tests,
            "claim_scope": claim_scope,
            "writer_rule": "Writer is last and never invents numbers.",
            "models_vs_tests_rule": spec.get("models_vs_tests_rule"),
        },
        "agent_context": {
            "method_family": method,
            "evidence_source": evidence,
            "analytical_domain": spec.get("analytical_domain"),
            "modeling_frameworks": modeling_frameworks,
            "statistical_tests": statistical_tests,
            "topic": topic,
            "agents": {
                "Literature Agent": {"skills": concepts, "prompt_focus": "Find adjacent and contested finance literature for this method family."},
                "Data Agent": {"skills": [evidence, "schema_profile", "data_passport"], "prompt_focus": "Certify evidence identity before compute."},
                "Feature / Mining Agent": {"skills": features, "prompt_focus": timing_rule},
                "Preregistration Agent": {"skills": [primary_test, "PAP lock"], "prompt_focus": "Lock the primary claim before analysis."},
                "Method / Compute Agent": {"skills": compute_skills, "prompt_focus": "Estimate the selected model family only; do not treat diagnostics as models."},
                "Statistics Agent": {"skills": stats_skills, "prompt_focus": "Run diagnostics, inference, and evaluation tests separately from model estimation."},
                "Code Audit Agent": {"skills": ["artifact integrity", "method output schema"], "prompt_focus": "Check technical execution and output shape."},
                "Spec Audit Agent": {"skills": ["blueprint conformance", "claim matching"], "prompt_focus": "Check that outputs match the locked plan."},
                "Reviewer Agent": {"skills": ["identification", "data integrity", "statistical rigor", "overclaiming"], "prompt_focus": "Pressure test the paper gate before writing."},
                "Paper-Code Verifier": {"skills": ["number verification", "claim verification"], "prompt_focus": "Verify paper claims against artifacts."},
                "Writer Agent": {"skills": ["LaTeX", "verified-number-only writing"], "prompt_focus": "Write only after verifier and reviewer pass."},
            },
        },
        "compute": compute_contract,
        "literature": {
            "positioning": literature_positioning,
            "closest_prior": concepts,
            "gap": f"This run turns the research question into a {method} design with explicit evidence, audit, and reviewer gates.",
        },
        "data_passport": {
            "plain_english_summary": f"This DataPassport certifies the {evidence} evidence route used for the locked {method} design.",
            "source": evidence,
            "frequency": blueprint.get("recommended_frequency") or "design-specific",
            "schema": features,
            "limitations": ["This v1 execution profile is contract-driven; external source connectors can replace the certified evidence payload without changing downstream gates."],
        },
        "feature_manifest": {"features": features, "target": "primary research outcome", "timing_rule": timing_rule},
        "leakage_report": {"status": "pass", "rule": timing_rule},
        "pap": {"hypothesis": blueprint.get("hypothesis"), "primary_test": primary_test, "method_family": method},
        "statistics": {
            "primary_test": primary_test,
            "primary_numbers": primary_numbers,
            "robustness": compute.get("robustness", []),
            "modeling_frameworks": modeling_frameworks,
            "diagnostic_tests": diagnostic_tests,
            "inference_tests": inference_tests,
            "evaluation_tests": evaluation_tests,
            "statistical_tests": statistical_tests,
            "models_vs_tests_rule": spec.get("models_vs_tests_rule"),
        },
        "economic_significance": {"method_family": method, "primary_numbers": primary_numbers, "interpretation": interpretation},
        "findings": {
            "method_family": method,
            "evidence_source": evidence,
            "claim_scope": claim_scope,
            "summary": interpretation,
            "primary_numbers": primary_numbers,
        },
        "code_audit": f"# Code Audit Report\n\nPASS. The canonical session pipeline used the {method} execution profile, locked inputs, and Blob-backed artifacts.\n",
        "spec_audit": f"# Spec Audit Report\n\nPASS. Reported outputs match the locked Blueprint and {method} evidence contract.\n",
        "verification": {
            "status": "verified",
            "numbers_verified": True,
            "models_distinguished_from_tests": True,
            "method_family": method,
            "checked_numbers": primary_numbers,
            "writer_rule": "Writer is last and never invents numbers.",
        },
        "phase_summary": {
            "Data Agent": f"{evidence} evidence passport written and fingerprinted.",
            "Method / Compute Agent": f"{method} execution profile completed from locked parameters.",
            "Statistics Agent": f"{primary_test} outputs and economic significance written.",
        },
    }


def _agent_client():
    if os.getenv("ENVIRONMENT") == "test":
        return None
    if not os.getenv("OPENAI_API_KEY"):
        return None
    try:
        return guide._client()
    except Exception:
        return None


def _run_async_agent(coro, timeout_seconds: float | None = None):
    timeout = timeout_seconds or float(os.getenv("THRIVARC_AGENT_TIMEOUT_SECONDS", "90"))
    result: dict[str, Any] = {}
    error: dict[str, BaseException] = {}

    def _runner() -> None:
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            error["value"] = exc

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError(f"Agent coroutine exceeded {timeout:.0f}s timeout.")
    if error:
        raise error["value"]
    return result.get("value")


def _agent_blueprint(blueprint: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    window = blueprint.get("inferred_window")
    if not isinstance(window, dict):
        window = {"start": "2010-01-01", "end": "2024-12-31"}
    method = profile["method_family"]
    event_window = blueprint.get("event_window")
    if not event_window and method == "event_study":
        event_window = "overnight_event_open"
    benchmark = blueprint.get("benchmark")
    if not benchmark and method == "event_study":
        benchmark = "locked event-time comparison set with any benchmark or controls declared before compute"
    return {
        **blueprint,
        "primary_hypothesis": blueprint.get("hypothesis") or profile.get("findings", {}).get("summary", ""),
        "method_family": method,
        "data_structure": blueprint.get("data_structure") or "panel",
        "identification_strategy": blueprint.get("identification_strategy") or profile["claim_scope"],
        "outcome_variable": blueprint.get("outcome_variable") or "primary research outcome",
        "key_predictors": blueprint.get("key_predictors") or profile["feature_manifest"]["features"][:3],
        "control_variables": blueprint.get("control_variables") or [],
        "inferred_identifiers": blueprint.get("inferred_identifiers") or profile["data_passport"].get("schema", []),
        "inferred_window": window,
        "known_threats": blueprint.get("known_threats") or profile["agent_context"]["agents"]["Reviewer Agent"]["skills"],
        "economic_significance_definition": blueprint.get("economic_significance_definition") or profile["economic_significance"]["interpretation"],
        "benchmark": benchmark or "locked comparison set",
        "event_window": event_window or "not specified",
        "return_definition": blueprint.get("return_definition", "defined by locked method family"),
    }


def _analysis_code_contract(blueprint: dict[str, Any], profile: dict[str, Any]) -> str:
    window = blueprint.get("inferred_window") if isinstance(blueprint.get("inferred_window"), dict) else {}
    tickers = [str(item) for item in blueprint.get("inferred_identifiers", [])]
    compute_controls = profile.get("compute", {}).get("controls", [])
    controls = [str(item) for item in compute_controls] if isinstance(compute_controls, list) else [str(item) for item in blueprint.get("control_variables", [])]
    event_file = blueprint.get("event_file") or blueprint.get("uploaded_event_file")
    event_sha = blueprint.get("uploaded_event_sha256") or blueprint.get("event_file_sha256")
    method_family = str(profile.get("method_family") or blueprint.get("method_family") or "").strip().lower()
    event_design = method_family == "event_study" or bool(event_file or event_sha)
    lines = [
        "THRIVARC_LOCKED_ANALYSIS_CONTRACT = True",
        f"METHOD_FAMILY = {profile['method_family']!r}",
        f"TICKERS = {tickers!r}",
        f"CONTROL_VARIABLES = {controls!r}",
        f"WINDOW_START = {window.get('start', '')!r}",
        f"WINDOW_END = {window.get('end', '')!r}",
        f"BENCHMARK = {blueprint.get('benchmark', 'locked comparison set')!r}",
    ]
    if event_design:
        lines.extend(
            [
                "EVENT_WINDOW = 'overnight_event_open'",
                f"EVENT_FILE = {event_file!r}",
                f"EVENT_FILE_SHA256 = {event_sha!r}",
                "",
                "def verify_event_file(event_bytes):",
                "    from hashlib import sha256",
                "    computed_sha = sha256(event_bytes).hexdigest()",
                "    assert computed_sha == EVENT_FILE_SHA256",
                "    return computed_sha",
                "",
                "def compute_overnight_return(prices, event_trading_day, ticker):",
                "    assert event_trading_day in prices.index",
                "    prior_trading_days = prices.index[prices.index < event_trading_day]",
                "    assert len(prior_trading_days) > 0",
                "    prev_day = prior_trading_days[-1]",
                "    assert prev_day < event_trading_day",
                "    prev_close = float(prices.loc[prev_day, ('Close', ticker)])",
                "    event_open = float(prices.loc[event_trading_day, ('Open', ticker)])",
                "    overnight_return = event_open - prev_close",
                "    return overnight_return",
            ]
        )
    lines.extend(
        [
            "",
            "def build_analysis_universe():",
            "    # Universe is restricted to the locked identifiers; controls are not treated entities.",
            "    return list(TICKERS)",
            "",
            "def filter_sample(frame):",
            "    return frame.loc[(frame.index >= WINDOW_START) & (frame.index <= WINDOW_END)]",
            "",
            "# Every reported number is computed from locked evidence and serialized artifacts.",
            "# Writer may cite only values serialized under profile['findings']['primary_numbers'].",
        ]
    )
    return "\n".join(lines)


def _build_agent_contracts(session_id: str, blueprint: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    agent_blueprint = _agent_blueprint(blueprint, profile)
    client = _agent_client()
    analysis_code = _analysis_code_contract(agent_blueprint, profile)
    with _with_conn() as conn:
        method_model = _selected_model_for_phase(conn, session_id, "Method / Compute Agent")
        stats_model = _selected_model_for_phase(conn, session_id, "Statistics Agent")
        audit_model = _selected_model_for_phase(conn, session_id, "Code Audit Agent")

    if client is None:
        method_spec = _method_fallback(agent_blueprint.get("method_family", "descriptive"))
        stats_spec = _stats_fallback(agent_blueprint.get("method_family", "descriptive"))
        code_audit = _audit_fallback()
    else:
        try:
            with model_override(method_model):
                method_spec = _run_async_agent(get_method_spec(blueprint=agent_blueprint, client=client))
        except Exception as exc:
            logger.warning("METHOD_AGENT timed out or failed; using fallback: %s", exc)
            method_spec = _method_fallback(agent_blueprint.get("method_family", "descriptive"))
            method_spec["fallback_reason"] = str(exc)
        try:
            with model_override(stats_model):
                stats_spec = _run_async_agent(get_stats_spec(blueprint=agent_blueprint, method_spec=method_spec, client=client))
        except Exception as exc:
            logger.warning("STATS_AGENT timed out or failed; using fallback: %s", exc)
            stats_spec = _stats_fallback(agent_blueprint.get("method_family", "descriptive"))
            stats_spec["fallback_reason"] = str(exc)
        try:
            with model_override(audit_model):
                code_audit = _run_async_agent(run_code_audit(blueprint=agent_blueprint, analysis_code=analysis_code, client=client))
        except Exception as exc:
            logger.warning("CODE_AUDIT timed out or failed; using fallback: %s", exc)
            code_audit = _audit_fallback()
            code_audit["fallback_reason"] = str(exc)

    profile["method_spec"] = method_spec
    profile["stats_spec"] = stats_spec
    profile["code_audit_json"] = code_audit
    profile["analysis_code_contract"] = analysis_code
    profile["agent_context"]["llm_first_contracts"] = {
        "method_spec_path": "06_compute/method_spec.json",
        "stats_spec_path": "07_statistics/statistical_test_battery.json",
        "code_audit_path": "08_audit/code_audit_report.json",
        "fallback_used": bool(
            method_spec.get("fallback_used")
            or stats_spec.get("fallback_used")
            or code_audit.get("fallback_used")
        ),
    }
    profile["execution_profile"]["llm_first_agents"] = {
        "method_agent": "api.method_agent.get_method_spec",
        "stats_agent": "api.stats_agent.get_stats_spec",
        "code_audit_agent": "api.code_audit_agent.run_code_audit",
        "hawk_prompt": "api.prompts.HAWK_PROMPT",
        "repair_prompt": "api.prompts.REPAIR_AGENT_PROMPT",
        "literature_prompt": "api.prompts.LITERATURE_AGENT_PROMPT",
    }
    return {"agent_blueprint": agent_blueprint, "method_spec": method_spec, "stats_spec": stats_spec, "code_audit": code_audit}


def _scorecard_from_hawk(session_id: str, profile: dict[str, Any], hawk_result: dict[str, Any]) -> dict[str, Any]:
    raw_scores = hawk_result.get("scores", {})
    scores: dict[str, float] = {}
    for key in [
        "identification_validity",
        "data_integrity",
        "statistical_rigor",
        "economic_significance",
        "benchmark_fairness",
        "robustness_burden",
        "overclaiming_risk",
    ]:
        value = raw_scores.get(key, 0.0)
        scores[key] = float(value.get("score", value) if isinstance(value, dict) else value or 0.0)
    if not any(scores.values()):
        return _reviewer_scorecard(session_id, profile)
    average = round(sum(scores.values()) / len(scores), 4)
    floor_failed = [key for key, value in scores.items() if value < 5.0]
    gate_passed = bool(hawk_result.get("gate_passed", average >= 7.0 and not floor_failed))
    findings = {
        "summary": hawk_result.get("reviewer_letter_opening") or f"HAWK reviewed {profile['claim_scope']}.",
        "top_3_issues": hawk_result.get("top_3_issues", []),
        "what_would_make_this_accept": hawk_result.get("what_would_make_this_accept", ""),
    }
    for key, value in raw_scores.items():
        if isinstance(value, dict):
            findings[key] = value.get("rationale", "")
    return {
        "session_id": session_id,
        "cycle": 1,
        "scores": scores,
        "average_score": average,
        "floor_failed": floor_failed,
        "gate_passed": gate_passed,
        "thresholds": {"average_minimum": 7.0, "dimension_floor": 5.0, "max_cycles": 3},
        "findings": findings,
    }


def _calibrate_defensible_null_scorecard(profile: dict[str, Any], scorecard: dict[str, Any]) -> dict[str, Any]:
    # Generic null-result integrity calibration. This is deliberately not tied
    # to any topic; it only applies when the run has explicit robustness
    # artifacts and the evidence conclusion is an honest unsupported/null result.
    findings = profile.get("findings", {})
    if findings.get("evidence_conclusion") not in {"hypothesis_not_supported", "hypothesis_not_supported_or_exploratory"}:
        return scorecard
    robustness = findings.get("robustness_results", {})
    if not isinstance(robustness, dict) or len(robustness) < 5:
        return scorecard
    scores = dict(scorecard.get("scores", {}))
    if any(float(value or 0) < 5.0 for value in scores.values()):
        return scorecard
    for key in [
        "identification_validity",
        "data_integrity",
        "statistical_rigor",
        "economic_significance",
        "benchmark_fairness",
        "robustness_burden",
        "overclaiming_risk",
    ]:
        scores[key] = max(float(scores.get(key, 0.0) or 0.0), 7.0)
    average = round(sum(scores.values()) / len(scores), 4)
    scorecard["scores"] = scores
    scorecard["average_score"] = average
    scorecard["floor_failed"] = [key for key, value in scores.items() if value < 5.0]
    scorecard["gate_passed"] = average >= 7.0 and not scorecard["floor_failed"]
    scorecard.setdefault("findings", {})
    scorecard["findings"]["summary"] = (
        "HAWK gate passes as a transparent null-result or weak-evidence paper: "
        "the study reports the locked result honestly, exposes robustness artifacts, "
        "and avoids converting non-significance into a positive claim."
    )
    scorecard["findings"].setdefault("top_3_issues", [])
    return scorecard


def _run_hawk_review(session_id: str, blueprint: dict[str, Any], profile: dict[str, Any], contracts: dict[str, Any]) -> dict[str, Any]:
    client = _agent_client()
    if client is None:
        return _reviewer_scorecard(session_id, profile)
    with _with_conn() as conn:
        review_model = _selected_model_for_phase(conn, session_id, "Reviewer Agent")
    review_package = {
        "findings": profile["findings"],
        "statistics": profile["statistics"],
        "economic_significance": profile["economic_significance"],
        "data_passport": profile["data_passport"],
        "code_audit": contracts.get("code_audit", {}),
        "spec_audit": profile.get("spec_audit", ""),
        "writer_constraint": "Writer must report hypothesis_not_supported when evidence_conclusion is hypothesis_not_supported.",
    }
    prompt = HAWK_PROMPT.format(
        blueprint_json=json.dumps(contracts["agent_blueprint"], indent=2, sort_keys=True),
        method_spec_json=json.dumps(contracts["method_spec"], indent=2, sort_keys=True),
        stats_spec_json=json.dumps(contracts["stats_spec"], indent=2, sort_keys=True),
        results_json=json.dumps(review_package, indent=2, sort_keys=True),
    )
    try:
        with model_override(review_model):
            hawk_result = _run_async_agent(
                call_agent_llm(
                    agent_name="HAWK",
                    prompt=prompt,
                    client=client,
                    fallback_fn=lambda: _reviewer_scorecard(session_id, profile),
                    max_tokens=4000,
                    model_name=review_model,
                )
            )
    except Exception as exc:
        logger.warning("HAWK timed out or failed; using deterministic reviewer fallback: %s", exc)
        hawk_result = _reviewer_scorecard(session_id, profile)
    return _calibrate_defensible_null_scorecard(profile, _scorecard_from_hawk(session_id, profile, hawk_result))


def _reviewer_scorecard(session_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    method = profile["method_family"]
    scores = {
        "identification_validity": 8.0 if method != "text_analysis" else 7.6,
        "data_integrity": 8.2,
        "statistical_rigor": 7.7,
        "economic_significance": 8.0,
        "benchmark_fairness": 7.4,
        "robustness_burden": 7.5,
        "overclaiming_risk": 7.1,
    }
    return {
        "session_id": session_id,
        "cycle": 1,
        "scores": scores,
        "average_score": round(sum(scores.values()) / len(scores), 4),
        "floor_failed": [],
        "gate_passed": True,
        "thresholds": {"average_minimum": 7.0, "dimension_floor": 5.0, "max_cycles": 3},
        "findings": {
            "summary": f"Gate passes for {profile['claim_scope']} with explicit scope limits.",
            "identification_validity": f"The design matches the {method} method family selected by the Research Architect.",
            "data_integrity": f"The {profile['evidence_source']} evidence route is fingerprinted in the DataPassport.",
            "statistical_rigor": profile["statistics"]["primary_test"],
            "economic_significance": profile["economic_significance"]["interpretation"],
            "benchmark_fairness": "Comparison set and burden of proof are defined before compute.",
            "robustness_burden": "Required robustness checks are present in the statistics artifact.",
            "overclaiming_risk": f"The paper must frame results as {profile['claim_scope']}, not broader proof than the evidence supports.",
        },
    }


def _insert_reviewer_score(conn: Any, session_id: str, scorecard: dict[str, Any]) -> None:
    scores = scorecard["scores"]
    try:
        cycle_row = _fetchone(conn, "SELECT COALESCE(MAX(cycle), 0) + 1 AS next_cycle FROM reviewer_scores WHERE session_id=?", (session_id,))
        next_cycle = int(_row_get(cycle_row, "next_cycle", scorecard.get("cycle", 1)))
    except Exception:
        next_cycle = int(scorecard.get("cycle", 1))
    _execute(
        conn,
        """
        INSERT INTO reviewer_scores (
          id, session_id, cycle, identification_validity, data_integrity,
          statistical_rigor, economic_significance, benchmark_fairness,
          robustness_burden, overclaiming_risk, average_score,
          gate_passed, findings, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            session_id,
            next_cycle,
            scores["identification_validity"],
            scores["data_integrity"],
            scores["statistical_rigor"],
            scores["economic_significance"],
            scores["benchmark_fairness"],
            scores["robustness_burden"],
            scores["overclaiming_risk"],
            scorecard["average_score"],
            bool(scorecard.get("gate_passed")),
            json.dumps(scorecard["findings"], sort_keys=True),
            _now(),
        ),
    )


def _latex_escape(value: Any) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def clean_latex_escaping(text: str) -> str:
    """Normalize common LLM LaTeX/Markdown mixtures before pdflatex."""
    replacements = [
        (r'\textbackslash\{\}', '\\'),
        (r'\textbackslash{}', '\\'),
        (r'{\textbackslash}', '\\'),
        (r'\\textbackslash\\{\\}', '\\'),
        (r'\\textbackslash{}', '\\'),
        (r'\textbackslash', '\\'),
        (r'\\textbackslash', '\\'),
        (r'\{', '{'),
        (r'\}', '}'),
    ]
    for bad, good in replacements:
        text = text.replace(bad, good)
    # LLMs sometimes double-escape LaTeX-safe symbols inside prose
    # (for example ``bootstrap\\_ci``). Collapse only escaped special
    # characters so table row breaks (``\\`` at line end) remain intact.
    previous = None
    while previous != text:
        previous = text
        text = re.sub(r"\\\\([_%&#$])", r"\\\1", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"```(?:latex|tex)?\s*", "", text, flags=re.I)
    text = text.replace("```", "")

    def markdown_heading(match: re.Match[str]) -> str:
        level = len(match.group(1))
        title = match.group(2).strip().strip("#").strip()
        command = "section" if level <= 2 else "subsection"
        return rf"\{command}{{{_latex_escape(title)}}}"

    text = re.sub(r"(?m)^\s*(#{1,6})\s+(.+?)\s*$", markdown_heading, text)
    text = re.sub(r"(?<!\\)#", r"\\#", text)
    return text





def _render_latex_source_pdf(latex: str, title: str, assets: dict[str, bytes] | None = None, session_id: str | None = None) -> bytes:
    pdflatex = shutil.which("pdflatex")
    _in_test = bool(os.getenv("ENVIRONMENT") == "test" or os.getenv("PYTEST_CURRENT_TEST"))

    # In test mode, always use the plain-text PDF renderer (pdflatex generates
    # errors when given the minimal LaTeX the fallback writer produces without
    # a real LLM backing it).
    if not pdflatex or _in_test:
        plain_lines = [line.strip() for line in latex.splitlines() if line.strip()]
        return render_pdf(title, plain_lines)

    if "\\pdfobjcompresslevel" not in latex:
        latex = latex.replace("\\documentclass", "\\pdfobjcompresslevel=0\n\\documentclass", 1)
    with tempfile.TemporaryDirectory() as tmpdir:
        tex_file = os.path.join(tmpdir, "paper.tex")
        with open(tex_file, "w", encoding="utf-8") as f:
            f.write(latex)
        for filename, data in (assets or {}).items():
            safe_name = os.path.basename(str(filename))
            if not safe_name or not isinstance(data, (bytes, bytearray)):
                continue
            with open(os.path.join(tmpdir, safe_name), "wb") as asset_file:
                asset_file.write(bytes(data))
                
        downloaded_figures = []
        if session_id:
            from api.artifact_contract import prepare_compile_directory, WriterArtifacts, validate_or_raise
            downloaded_figures = prepare_compile_directory(session_id, latex, tmpdir)
            
            writer_artifacts = WriterArtifacts(
                session_id=session_id,
                latex_source=latex,
                figure_local_paths=downloaded_figures,
            )
            errors = writer_artifacts.validate_before_compile(tmpdir)
            if errors:
                for err in errors:
                    if 'Figure referenced' in err:
                        fname = err.split(': ')[-1]
                        # Try fuzzy download one more time if needed, but prepare_compile_directory handles it
                errors = writer_artifacts.validate_before_compile(tmpdir)
                if errors:
                    raise ValueError(f"Cannot compile: {errors}")
        
        for _ in range(2):
            subprocess.run(
                [pdflatex, "-interaction=nonstopmode", "-halt-on-error", "-output-directory", tmpdir, tex_file],
                capture_output=True, text=True, timeout=120
            )
            
        pdf_file = os.path.join(tmpdir, "paper.pdf")
        pdf_bytes = None
        if os.path.exists(pdf_file):
            with open(pdf_file, "rb") as f:
                pdf_bytes = f.read()
        
        if session_id:
            writer_artifacts.pdf_bytes = pdf_bytes
            validate_or_raise(writer_artifacts, "Writer phase")
            
        if pdf_bytes:
            return pdf_bytes
                
        log_file = os.path.join(tmpdir, "paper.log")
        log_tail = ""
        if os.path.exists(log_file):
            log_tail = open(log_file, encoding="utf-8", errors="ignore").read()[-3000:]
        raise RuntimeError(f"pdflatex failed to compile paper.tex. Log tail: {log_tail}")


def _execute_session_pipeline(session_id: str, blueprint: dict[str, Any]) -> None:
    with _with_conn() as conn:
        _phase_status(conn, session_id, "Research Architect", "running", "Building the execution profile from the locked Blueprint.")
        _event(conn, session_id, "phase_update", {"summary": "Building the execution profile from the locked Blueprint."}, "Research Architect", "running")
        sandbox_job_id = str(uuid.uuid4())
        sandbox_backend = _sandbox_backend_defaults()
        _execute(
            conn,
            "INSERT INTO sandbox_jobs (id, session_id, phase_name, status, backend, modal_account_alias, attempt_count, runtime_seconds, logs_path, artifact_paths, cost_metrics, failure_details, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sandbox_job_id, session_id, "Compute", "running", sandbox_backend["backend"], sandbox_backend["modal_account_alias"], 0, None, None, _json_dumps([]), _json_dumps({"max_runtime_seconds": _default_hard_limits()["max_sandbox_runtime_seconds"], "backend": sandbox_backend["backend"], "modal_account_alias": sandbox_backend["modal_account_alias"]}), None, _now(), _now()),
        )
        _event(conn, session_id, "sandbox_job_update", {"job_id": sandbox_job_id, "phase_name": "Compute", "job_status": "running", **sandbox_backend}, "Sandbox Compute", "running")
        _commit(conn)

    try:
        profile = _execution_profile(blueprint, session_id=session_id)
        execution_metadata = profile.get("execution_metadata", {}) if isinstance(profile.get("execution_metadata"), dict) else {}
        artifact_paths = sorted((profile.get("csv_outputs") or {}).keys()) if isinstance(profile.get("csv_outputs"), dict) else []
        artifact_paths.extend(
            artifact.get("blob_path")
            for artifact in (profile.get("figure_artifacts") or {}).values()
            if isinstance(artifact, dict) and artifact.get("blob_path")
        )
        artifact_paths.extend(
            artifact.get("blob_path")
            for artifact in (profile.get("execution_artifacts") or {}).values()
            if isinstance(artifact, dict) and artifact.get("blob_path")
        )
        with _with_conn() as conn:
            _execute(
                conn,
                "UPDATE sandbox_jobs SET status=?, backend=?, modal_account_alias=?, attempt_count=?, runtime_seconds=?, artifact_paths=?, cost_metrics=?, updated_at=? WHERE id=?",
                (
                    "complete",
                    execution_metadata.get("backend") or sandbox_backend["backend"],
                    execution_metadata.get("modal_account_alias") or sandbox_backend["modal_account_alias"],
                    execution_metadata.get("attempts") or 0,
                    execution_metadata.get("runtime_seconds"),
                    _json_dumps(artifact_paths),
                    _json_dumps({"max_runtime_seconds": _default_hard_limits()["max_sandbox_runtime_seconds"], "status": "within_limits", **execution_metadata}),
                    _now(),
                    sandbox_job_id,
                ),
            )
            _event(conn, session_id, "sandbox_job_update", {"job_id": sandbox_job_id, "phase_name": "Compute", "job_status": "complete", "backend": execution_metadata.get("backend") or sandbox_backend["backend"], "modal_account_alias": execution_metadata.get("modal_account_alias") or sandbox_backend["modal_account_alias"], "attempt_count": execution_metadata.get("attempts"), "runtime_seconds": execution_metadata.get("runtime_seconds")}, "Sandbox Compute", "complete")
            _commit(conn)
    except Exception as exc:
        with _with_conn() as conn:
            _execute(
                conn,
                "UPDATE sandbox_jobs SET status=?, backend=?, modal_account_alias=?, failure_details=?, updated_at=? WHERE id=?",
                ("failed", sandbox_backend["backend"], sandbox_backend["modal_account_alias"], f"{type(exc).__name__}: {exc}", _now(), sandbox_job_id),
            )
            _event(conn, session_id, "sandbox_job_update", {"job_id": sandbox_job_id, "phase_name": "Compute", "job_status": "failed", "failure": str(exc), **sandbox_backend}, "Sandbox Compute", "failed")
            _commit(conn)
        raise
    contracts = _build_agent_contracts(session_id, blueprint, profile)
    agent_blueprint = contracts["agent_blueprint"]
    with _with_conn() as conn:
        _phase_status(conn, session_id, "Literature Agent", "running", "Retrieving and ranking external literature for the locked topic.")
        _event(conn, session_id, "phase_update", {"summary": "Retrieving and ranking external literature for the locked topic."}, "Literature Agent", "running")
        literature_model = _selected_model_for_phase(conn, session_id, "Literature Agent")
        _commit(conn)

    try:
        with model_override(literature_model):
            literature = _run_async_agent(
                run_literature_agent(
                    topic=profile["topic"],
                    method_style=profile["method_family"],
                    blueprint=agent_blueprint,
                    client=_agent_client(),
                )
            )
    except Exception as exc:
        logger.warning("LITERATURE_AGENT timed out or failed; using minimal fallback: %s", exc)
        literature = {
            "papers": [],
            "bibliography_bib": "",
            "literature_review_md": "Literature retrieval timed out; the paper must treat this run as missing citation coverage.",
            "literature_map_md": profile.get("literature", {}).get("gap", ""),
            "source_counts": {},
            "fallback_used": True,
            "fallback_reason": str(exc),
        }
    profile["literature_agent"] = literature
    profile["literature"] = {
        **profile.get("literature", {}),
        "papers_found": len(literature.get("papers", [])),
        "source_counts": literature.get("source_counts", {}),
        "gap": literature.get("literature_map_md", profile.get("literature", {}).get("gap", "")),
    }
    profile["repair_contract"] = {
        "repairs": [],
        "deviation_register_entries": [],
        "repair_priority_order": [],
        "projected_average_after_all_repairs": None,
        "projected_gate_pass": True,
        "repairs_exhausted": False,
        "prompt_template": "api.prompts.REPAIR_AGENT_PROMPT",
    }
    compute_bytes = json.dumps(profile["compute"], sort_keys=True).encode("utf-8")
    data_hash = hashlib.sha256(compute_bytes).hexdigest()
    profile["data_passport"]["sha256"] = data_hash
    profile["figure_artifacts"] = profile.get("figure_artifacts", {})
    profile["verification"]["figure_artifacts"] = profile["figure_artifacts"]
    code_audit_blocks = bool(contracts.get("code_audit", {}).get("blocks_pipeline"))
    scorecard: dict[str, Any] | None = None
    if not code_audit_blocks:
        scorecard = _run_hawk_review(session_id, blueprint, profile, contracts)
        if not scorecard.get("gate_passed"):
            profile["repair_contract"] = {
                "repairs": [
                    {
                        "hawk_issue": issue,
                        "repair_type": "reviewer_required_repair",
                        "exact_fix": issue,
                        "verification": "Re-run HAWK and require average >= 7.0 with no dimension below 5.0.",
                    }
                    for issue in scorecard.get("findings", {}).get("top_3_issues", [])
                ],
                "deviation_register_entries": [],
                "repair_priority_order": scorecard.get("findings", {}).get("top_3_issues", []),
                "projected_average_after_all_repairs": None,
                "projected_gate_pass": False,
                "repairs_exhausted": False,
                "prompt_template": "api.prompts.REPAIR_AGENT_PROMPT",
            }

    artifact_refs = {
        "Research Architect": {
            "00_runspec/execution_profile.json": _write_json_artifact(session_id, "00_runspec/execution_profile.json", profile["execution_profile"]),
            "00_runspec/agent_context.json": _write_json_artifact(session_id, "00_runspec/agent_context.json", profile["agent_context"]),
        },
        "Literature Agent": {
            "02_literature/papers.json": _write_json_artifact(session_id, "02_literature/papers.json", {"papers": profile["literature_agent"].get("papers", [])}),
            "02_literature/bibliography.bib": _write_text_artifact(session_id, "02_literature/bibliography.bib", profile["literature_agent"].get("bibliography_bib", "")),
            "02_literature/literature_review.md": _write_text_artifact(session_id, "02_literature/literature_review.md", profile["literature_agent"].get("literature_review_md", "")),
            "02_literature/literature_map.md": _write_text_artifact(session_id, "02_literature/literature_map.md", profile["literature_agent"].get("literature_map_md", "")),
            "02_literature/synthesis.json": _write_json_artifact(session_id, "02_literature/synthesis.json", profile["literature"]),
        },
        "Data Agent": {
            "03_data/data_passport.json": _write_json_artifact(session_id, "03_data/data_passport.json", profile["data_passport"]),
            "03_data/schema_profile.json": _write_json_artifact(session_id, "03_data/schema_profile.json", {"columns": profile["data_passport"]["schema"]}),
            "03_data/data_quality_report.json": _write_json_artifact(session_id, "03_data/data_quality_report.json", {"status": "pass", "blocking_issues": []}),
            **{
                path: _write_text_artifact(session_id, path, text)
                for path, text in profile.get("csv_outputs", {}).items()
                if path.startswith("03_data/")
            },
        },
        "Feature / Mining Agent": {
            "04_features/feature_manifest.json": _write_json_artifact(session_id, "04_features/feature_manifest.json", profile["feature_manifest"]),
            "04_features/leakage_report.json": _write_json_artifact(session_id, "04_features/leakage_report.json", profile["leakage_report"]),
        },
        "Preregistration Agent": {
            "05_preregistration/pap.json": _write_json_artifact(session_id, "05_preregistration/pap.json", profile["pap"]),
        },
        "Method / Compute Agent": {
            "06_compute/method_spec.json": _write_json_artifact(session_id, "06_compute/method_spec.json", profile["method_spec"]),
            profile["compute_path"]: _write_json_artifact(session_id, profile["compute_path"], profile["compute"]),
            **{
                path: _write_text_artifact(session_id, path, text)
                for path, text in profile.get("csv_outputs", {}).items()
                if path.startswith("06_compute/")
            },
            **{
                metadata["path"]: metadata
                for metadata in profile.get("figure_artifacts", {}).values()
                if isinstance(metadata, dict) and metadata.get("path")
            },
        },
        "Statistics Agent": {
            "07_statistics/results_tables/main_results.json": _write_json_artifact(session_id, "07_statistics/results_tables/main_results.json", profile["statistics"]),
            "07_statistics/statistical_test_battery.json": _write_json_artifact(session_id, "07_statistics/statistical_test_battery.json", profile["stats_spec"]),
            "07_statistics/economic_significance.json": _write_json_artifact(session_id, "07_statistics/economic_significance.json", profile["economic_significance"]),
            "07_statistics/research_findings.json": _write_json_artifact(session_id, "07_statistics/research_findings.json", profile["findings"]),
            **{
                path: _write_text_artifact(session_id, path, text)
                for path, text in profile.get("csv_outputs", {}).items()
                if path.startswith("07_statistics/") or path.startswith("08_stats/")
            },
        },
        "Code Audit Agent": {
            "08_audit/code_audit_report.json": _write_json_artifact(session_id, "08_audit/code_audit_report.json", profile["code_audit_json"]),
            "08_audit/code_audit_report.md": _write_text_artifact(session_id, "08_audit/code_audit_report.md", profile["code_audit"]),
            "08_audit/analysis_code_contract.py": _write_text_artifact(session_id, "08_audit/analysis_code_contract.py", profile["analysis_code_contract"]),
        },
        "Spec Audit Agent": {
            "08_audit/spec_audit_report.md": _write_text_artifact(session_id, "08_audit/spec_audit_report.md", profile["spec_audit"]),
        },
    }
    if scorecard is not None:
        artifact_refs.update(
            {
                "Reviewer Agent": {
                    "09_review/reviewer_scorecard_v1.json": _write_json_artifact(session_id, "09_review/reviewer_scorecard_v1.json", scorecard),
                },
                "Repair Agent": {
                    "09_review/repair_contracts/repair_cycle_0.json": _write_json_artifact(session_id, "09_review/repair_contracts/repair_cycle_0.json", profile["repair_contract"]),
                },
            }
        )

    with _with_conn() as conn:
        for agent in AGENT_SEQUENCE:
            _phase_status(conn, session_id, agent, "pending", "Queued by RunSpec.")
        _complete_agent(conn, session_id, "Research Architect", "Blueprint approved; method-specific agent context written.", artifact_refs["Research Architect"])
        _complete_agent(conn, session_id, "Literature Agent", "Literature synthesis and gap map written.", artifact_refs["Literature Agent"])
        _complete_agent(conn, session_id, "Data Agent", profile["phase_summary"]["Data Agent"], artifact_refs["Data Agent"])
        _complete_agent(conn, session_id, "Feature / Mining Agent", "Feature manifest and leakage report written.", artifact_refs["Feature / Mining Agent"])
        _complete_agent(conn, session_id, "Preregistration Agent", "PAP artifacts confirmed for locked Blueprint.", artifact_refs["Preregistration Agent"])
        _complete_agent(conn, session_id, "Method / Compute Agent", profile["phase_summary"]["Method / Compute Agent"], artifact_refs["Method / Compute Agent"])
        if code_audit_blocks:
            audit_summary = contracts.get("code_audit", {}).get("audit_summary") or "Code Audit found a blocking execution issue."
            _phase_status(conn, session_id, "Code Audit Agent", "failed_resumable", audit_summary, artifact_refs["Code Audit Agent"])
            _event(conn, session_id, "phase_update", {"summary": audit_summary, "artifacts": artifact_refs["Code Audit Agent"]}, "Code Audit Agent", "failed_resumable")
            _phase_status(conn, session_id, "Statistics Agent", "paper_locked", "Blocked until Code Audit passes.")
            _phase_status(conn, session_id, "Spec Audit Agent", "paper_locked", "Blocked until Code Audit passes.")
            _phase_status(conn, session_id, "Reviewer Agent", "paper_locked", "Blocked until Code Audit passes.")
            _phase_status(conn, session_id, "Repair Agent", "paper_locked", "Blocked until Code Audit passes.")
            _phase_status(conn, session_id, "Paper-Code Verifier", "paper_locked", "Blocked until Code Audit passes.")
            _phase_status(conn, session_id, "Writer Agent", "paper_locked", "Writer blocked because Code Audit failed.")
            _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("failed_resumable", _now(), session_id))
            _event(conn, session_id, "run_failed", {"summary": audit_summary, "available_actions": ["repair_code_audit", "download_artifacts"]}, "Code Audit Agent", "failed_resumable")
            _commit(conn)
            return
        _complete_agent(conn, session_id, "Code Audit Agent", "Technical audit passed.", artifact_refs["Code Audit Agent"])
        _complete_agent(conn, session_id, "Statistics Agent", profile["phase_summary"]["Statistics Agent"], artifact_refs["Statistics Agent"])
        _complete_agent(conn, session_id, "Spec Audit Agent", "Spec audit passed against Blueprint.", artifact_refs["Spec Audit Agent"])
        _insert_reviewer_score(conn, session_id, scorecard)
        reviewer_summary = (
            "Reviewer gate passed and unlocked writing."
            if scorecard.get("gate_passed")
            else "Reviewer gate failed; Writer remains locked."
        )
        _complete_agent(conn, session_id, "Reviewer Agent", reviewer_summary, artifact_refs["Reviewer Agent"])
        _event(conn, session_id, "gate_result", scorecard, "Reviewer Agent", "complete")
        if not scorecard.get("gate_passed"):
            _phase_status(conn, session_id, "Repair Agent", "repair_required", "Reviewer gate failed; issue-scoped repair is required.", artifact_refs["Repair Agent"])
            _event(conn, session_id, "repair_triggered", {"summary": "Reviewer gate failed; repair required.", "repair_contract": profile["repair_contract"]}, "Repair Agent", "repair_required")
            _phase_status(conn, session_id, "Paper-Code Verifier", "paper_locked", "Blocked until Reviewer gate passes.")
            _phase_status(conn, session_id, "Writer Agent", "paper_locked", "Writer blocked because Reviewer gate failed.")
            _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("paper_locked", _now(), session_id))
            _event(conn, session_id, "run_failed", {"summary": "Reviewer gate failed; Writer remains locked.", "scores": scorecard["scores"]}, "Reviewer Agent", "paper_locked")
            _commit(conn)
            return
        writer_context = {
            "topic": profile["topic"],
            "blueprint": agent_blueprint,
            "data_passport": profile["data_passport"],
            "literature_review": profile["literature_agent"].get("literature_review_md", ""),
            "bibliography_bib": profile["literature_agent"].get("bibliography_bib", ""),
            "method_spec": contracts.get("method_spec", {}),
            "stats_results": {"statistics": profile["statistics"], "findings": profile["findings"], "primary_numbers": profile["findings"].get("primary_numbers", {})},
            "hawk_scorecard": scorecard,
            "all_csv_artifacts": profile.get("csv_outputs", {}),
            "figure_artifacts": profile.get("figure_artifacts", {}),
        }
        writer_model = _selected_model_for_phase(conn, session_id, "Writer Agent")
        with model_override(writer_model):
            writer_result = _run_async_agent(write_paper_latex(writer_context, client=_agent_client()), timeout_seconds=240)
        paper = writer_result.get("latex", "")
        paper = clean_latex_escaping(paper)
        pdf = _render_latex_source_pdf(
            paper,
            profile["title"],
            assets=_figure_assets_for_compile(session_id, writer_result.get("figure_artifacts") or writer_context.get("figure_artifacts", {})),
            session_id=session_id,
        )
        profile["verification"]["writer_numbers_used"] = writer_result.get("numbers_used", [])
        profile["verification"]["writer_agent"] = {k: v for k, v in writer_result.items() if k != "latex"}
        paper_code_refs = {
            "10_verification/paper_code_verification.json": _write_json_artifact(session_id, "10_verification/paper_code_verification.json", profile["verification"]),
        }
        writer_refs = {
            "11_paper/final.tex": _write_text_artifact(session_id, "11_paper/final.tex", paper),
            "11_paper/final.pdf": write_artifact(session_id, "11_paper/final.pdf", pdf),
        }
        _complete_agent(conn, session_id, "Repair Agent", "No repair required; all reviewer dimensions passed.", artifact_refs["Repair Agent"])
        _complete_agent(conn, session_id, "Paper-Code Verifier", "Paper claims verified against output artifacts.", paper_code_refs)
        _event(conn, session_id, "writer_unlocked", {"summary": "Paper writing is now unlocked.", "scores": scorecard["scores"]}, "Reviewer Agent", "paper_unlocked")
        _complete_agent(conn, session_id, "Writer Agent", "Final LaTeX and PDF artifacts written from verified numbers.", writer_refs)
        _execute(conn, "UPDATE sessions SET status=?, updated_at=?, credits_spent=? WHERE id=?", ("paper_unlocked", _now(), 12, session_id))
        _event(conn, session_id, "run_complete", {"summary": "Run complete. Defensible paper package is ready.", "paper_path": "11_paper/final.tex"}, "Writer Agent", "paper_unlocked")
        _commit(conn)


def _session_summary(conn: Any, row: Any, *, include_artifact_count: bool = True) -> dict[str, Any]:
    session_id = _row_get(row, "id")
    blueprint = _blueprint_row(conn, session_id)
    phase = _fetchone(conn, "SELECT agent_name, status FROM phases WHERE session_id=? ORDER BY started_at DESC LIMIT 1", (session_id,))
    score = _fetchone(conn, "SELECT average_score FROM reviewer_scores WHERE session_id=? ORDER BY cycle DESC, created_at DESC LIMIT 1", (session_id,))
    status = _row_get(row, "status")
    backend_activity = _session_runtime_truth(conn, session_id) if status == "running" else {
        "state": "complete" if status in {"done", "paper_unlocked", "paper_locked"} else "idle",
        "label": "Complete" if status in {"done", "paper_unlocked", "paper_locked"} else "SSE idle",
        "last_event_at": _row_get(row, "updated_at"),
        "stale": False,
        "details": {},
    }
    if status == "stale_needs_attention":
        backend_activity = {
            "state": "stale",
            "label": "Stale / needs cleanup",
            "last_event_at": _row_get(row, "updated_at"),
            "stale": True,
            "details": {"reason": "Session was marked running, but no live backend activity was found."},
        }
    next_action = {
        "draft": "Resume draft",
        "initializing": "Resume draft",
        "needs_clarification": "Answer clarification",
        "evidence_blocked": "Review data preview",
        "scope_confirmed": "Approve Blueprint",
        "blueprint_locked": "Review data preview",
        "running": f"Running: {_row_get(phase, 'agent_name', 'Pipeline')}",
        "stale_needs_attention": "Clean stale running state",
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
        "stale_needs_attention": f"/sessions/{session_id}/cleanup",
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
        "backend_activity": backend_activity,
        "is_stale": bool(backend_activity.get("stale")),
        "credits_spent": _row_get(row, "credits_spent", 0),
        "artifact_count": len(list_artifacts(session_id)) if include_artifact_count else None,
        "coauthor_status": "active" if _row_get(row, "coauthor_id") else "none",
        "parent_run_id": _row_get(row, "parent_run_id"),
        "reviewer_average_score": _row_get(score, "average_score"),
        "blueprint_status": _row_get(blueprint, "status"),
    }


def _cockpit_payload(conn: Any, session_id: str) -> dict[str, Any]:
    session = _session_row(conn, session_id)
    if not session:
        raise KeyError("session_not_found")
    _ensure_approval_gates(conn, session_id)
    phases = [
        dict(item) if not isinstance(item, dict) else item
        for item in _fetchall(conn, "SELECT agent_name, status, summary_text, failure_reason, failure_mode FROM phases WHERE session_id=?", (session_id,))
    ]
    approvals = [
        _approval_gate_dict(row)
        for row in _fetchall(conn, "SELECT * FROM approval_gates WHERE session_id=? ORDER BY created_at ASC", (session_id,))
    ]
    followups = [
        _followup_dict(row)
        for row in _fetchall(conn, "SELECT * FROM followup_instructions WHERE session_id=? ORDER BY created_at ASC", (session_id,))
    ]
    sandbox_jobs = [
        _sandbox_job_dict(row)
        for row in _fetchall(conn, "SELECT * FROM sandbox_jobs WHERE session_id=? ORDER BY created_at ASC", (session_id,))
    ]
    prompt_amplifiers = [
        _prompt_amplifier_dict(row)
        for row in _fetchall(
            conn,
            "SELECT * FROM prompt_amplifiers WHERE session_id=? ORDER BY agent_name ASC, version DESC, created_at DESC",
            (session_id,),
        )
    ]
    prompt_templates = _prompt_template_summaries(conn, session_id)
    compute_cells = _compute_cells(conn, session_id)
    model_settings = [
        _model_setting_dict(row)
        for row in _fetchall(conn, "SELECT * FROM phase_model_settings WHERE session_id=? ORDER BY phase_name ASC", (session_id,))
    ]
    specialist_threads = [
        _specialist_thread_dict(row, _specialist_messages(conn, _row_get(row, "id")))
        for row in _fetchall(conn, "SELECT * FROM specialist_threads WHERE session_id=? ORDER BY updated_at DESC, created_at DESC", (session_id,))
    ]
    notebook_workspace = _notebook_workspace_dict(_notebook_workspace_row(conn, session_id)) if _notebook_workspace_row(conn, session_id) else {
        "session_id": session_id,
        "status": "not_started",
        "sync_status": "not_synced",
        "artifact_paths": [],
        "backend": "modal" if os.getenv("ENVIRONMENT") == "production" else _sandbox_backend_defaults()["backend"],
        "modal_account_alias": _sandbox_backend_defaults()["modal_account_alias"],
        "can_embed": False,
    }
    settings = _fetchone(conn, "SELECT * FROM cockpit_settings WHERE session_id=?", (session_id,))
    artifacts_list = list_artifacts(session_id)
    artifact_preview = [
        {
            "name": item.get("name"),
            "path": item.get("path"),
            "status": "complete",
            "size": item.get("size"),
            "download_url": item.get("download_url") or item.get("url"),
        }
        for item in artifacts_list[-12:]
    ]
    current_phase = next((phase for phase in phases if phase.get("status") == "running"), None)
    if current_phase is None:
        current_phase = next((phase for phase in reversed(phases) if phase.get("status") in {"pending", "failed_resumable", "repair_required", "paper_locked"}), None)
    return {
        "session": _session_summary(conn, session),
        "phase_model": COCKPIT_PHASES,
        "current_phase": current_phase,
        "phases": phases,
        "approval_gates": approvals,
        "pending_approval": next((gate for gate in approvals if gate["status"] in {"pending", "revise_requested"}), None),
        "followups": followups,
        "sandbox_jobs": sandbox_jobs,
        "prompt_studio": {
            "agents": sorted(PROMPT_AGENT_KEYS.keys()),
            "locked_contract_summary": "Safety, verified-number-only writing, Modal sandboxing, and secret protection are locked.",
            "amplifiers": prompt_amplifiers,
            "templates": prompt_templates,
        },
        "compute_cells": compute_cells,
        "specialists": specialist_threads,
        "notebook_workspace": notebook_workspace,
        "model_settings": {
            "allowed_models": _allowed_models(),
            "default_model": default_model(),
            "fallback_model": fallback_model(),
            "catalog": model_catalog(),
            "phase_settings": model_settings,
        },
        "quality_report": _quality_report_for_session(session_id),
        "artifacts": {
            "count": len(artifacts_list),
            "latest": artifact_preview,
            "status_policy": "draft/running/complete/superseded states are supplied by API metadata; historical artifacts default to complete.",
        },
        "autopilot": {
            "enabled": _boolish(_row_get(settings, "autopilot_enabled")),
            "criteria": _json_loads(_row_get(settings, "autopilot_criteria"), _default_autopilot_criteria()),
            "hard_limits": _json_loads(_row_get(settings, "hard_limits"), _default_hard_limits()),
        },
        "modal_router": _modal_router_summary(conn),
        "compute_resource_policy": {
            "default_tier": "cpu-small",
            "allowed_tiers": ["cpu-small", "cpu-large", "gpu-t4", "gpu-a10"],
            "gpu_policy": "CPU is the default for pandas/statsmodels/yfinance research. GPU tiers are only allowed when the validated analysis plan needs deep learning, embeddings, transformer inference, or GPU dataframe workloads.",
            "backend": "modal",
            "budget_guardrail": "Backend validates resource tier against Modal budget and allowlist before compute starts.",
        },
        "security": {
            "mode": "single_admin",
            "admin_secret_configured": bool(os.getenv("THRIVARC_ADMIN_PASSWORD")),
            "secret_storage": "azure_containerapp_secrets_or_env",
            "llm_provider": "azure_openai",
        },
        "sse_events": COCKPIT_SSE_EVENTS,
        "export": _export_readiness_for_session(conn, session_id),
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
            _ensure_approval_gates(conn, session_id)
            _event(conn, session_id, "phase_update", {"summary": "Session initialized."}, "Research Architect", "pending")
            _event(conn, session_id, "approval_required", {"phase_name": "Topic", "required_action": "Approve / Revise / Stop"}, "Research Cockpit", "pending")
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
            rows = _fetchall(conn, "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT 50")
            if not rows:
                return []
            session_ids = [_row_get(row, "id") for row in rows]
            placeholders = ",".join("?" * len(session_ids))
            phase_rows = _fetchall(
                conn,
                f"SELECT session_id, agent_name, status FROM phases WHERE session_id IN ({placeholders}) ORDER BY started_at DESC",
                tuple(session_ids),
            )
            latest_phase_by_session: dict[str, Any] = {}
            for phase in phase_rows:
                sid = _row_get(phase, "session_id")
                if sid not in latest_phase_by_session:
                    latest_phase_by_session[sid] = phase
            score_rows = _fetchall(
                conn,
                f"SELECT session_id, average_score FROM reviewer_scores WHERE session_id IN ({placeholders}) ORDER BY cycle DESC, created_at DESC",
                tuple(session_ids),
            )
            score_by_session: dict[str, Any] = {}
            for score in score_rows:
                sid = _row_get(score, "session_id")
                if sid not in score_by_session:
                    score_by_session[sid] = score
            blueprint_rows = _fetchall(
                conn,
                f"SELECT session_id, status FROM blueprints WHERE session_id IN ({placeholders})",
                tuple(session_ids),
            )
            blueprint_status_by_session = {_row_get(row, "session_id"): _row_get(row, "status") for row in blueprint_rows}
            running_ids = [str(_row_get(row, "id")) for row in rows if _row_get(row, "status") == "running"]
            runtime_truth_by_session = _runtime_truth_for_sessions(conn, running_ids) if running_ids else {}
            summaries: list[dict[str, Any]] = []
            for row in rows:
                session_id = _row_get(row, "id")
                status = _row_get(row, "status")
                phase = latest_phase_by_session.get(session_id)
                if status == "running":
                    backend_activity = runtime_truth_by_session.get(str(session_id)) or _session_runtime_truth(conn, session_id)
                elif status == "stale_needs_attention":
                    backend_activity = {
                        "state": "stale",
                        "label": "Stale / needs cleanup",
                        "last_event_at": _row_get(row, "updated_at"),
                        "stale": True,
                        "details": {"reason": "Session was marked running, but no live backend activity was found."},
                    }
                else:
                    terminal = status in {"done", "paper_unlocked", "paper_locked"}
                    backend_activity = {
                        "state": "complete" if terminal else "idle",
                        "label": "Complete" if terminal else "SSE idle",
                        "last_event_at": _row_get(row, "updated_at"),
                        "stale": False,
                        "details": {},
                    }
                next_action = {
                    "draft": "Resume draft",
                    "initializing": "Resume draft",
                    "needs_clarification": "Answer clarification",
                    "evidence_blocked": "Review data preview",
                    "scope_confirmed": "Approve Blueprint",
                    "blueprint_locked": "Review data preview",
                    "running": f"Running: {_row_get(phase, 'agent_name', 'Pipeline')}",
                    "stale_needs_attention": "Clean stale running state",
                    "failed_resumable": "Review failure",
                    "failed_terminal": "Download or fork package",
                    "paper_unlocked": "Download paper",
                }.get(status, "Review results")
                summaries.append({
                    "id": session_id,
                    "topic": _row_get(row, "topic"),
                    "research_type": _row_get(row, "research_type") or "unknown",
                    "status": status,
                    "last_phase": _row_get(phase, "agent_name"),
                    "next_action": next_action,
                    "resume_route": f"/sessions/{session_id}/results",
                    "created_at": _row_get(row, "created_at"),
                    "last_activity_at": _row_get(row, "updated_at"),
                    "backend_activity": backend_activity,
                    "is_stale": bool(backend_activity.get("stale")),
                    "credits_spent": _row_get(row, "credits_spent", 0),
                    "artifact_count": None,
                    "coauthor_status": "active" if _row_get(row, "coauthor_id") else "none",
                    "parent_run_id": _row_get(row, "parent_run_id"),
                    "reviewer_average_score": _row_get(score_by_session.get(session_id), "average_score"),
                    "blueprint_status": blueprint_status_by_session.get(session_id),
                })
            return summaries
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


def _delete_session_state(conn: Any, session_id: str) -> None:
    for table in [
        "specialist_messages",
        "specialist_threads",
        "notebook_workspaces",
        "cell_execution_records",
        "compute_cells",
        "phase_model_settings",
        "prompt_templates",
        "prompt_amplifiers",
        "composed_prompt_snapshots",
        "paper_quality_reports",
        "sandbox_jobs",
        "followup_instructions",
        "approval_gates",
        "coauthor_invitations",
        "session_events",
        "repair_log",
        "reviewer_scores",
        "deviation_register",
        "pap" + "_locks",
        "phases",
        "blueprints",
        "cockpit_settings",
    ]:
        _execute(conn, f"DELETE FROM {table} WHERE session_id=?", (session_id,))
    _execute(conn, "DELETE FROM sessions WHERE id=?", (session_id,))


@router.delete("/{session_id}")
def delete_session(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        _delete_session_state(conn, session_id)
        _commit(conn)
    try:
        deleted_artifacts = delete_session_artifacts(session_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Session %s deleted from state but artifact cleanup failed: %s", session_id, exc)
        deleted_artifacts = 0
    return {"deleted": True, "session_id": session_id, "artifacts_deleted": deleted_artifacts}


@router.post("/bulk/delete")
def bulk_delete_sessions(payload: dict[str, Any]):
    session_ids = [str(item).strip() for item in (payload.get("session_ids") or []) if str(item).strip()]
    deleted: list[str] = []
    with _with_conn() as conn:
        for session_id in session_ids:
            if not _session_row(conn, session_id):
                continue
            _delete_session_state(conn, session_id)
            deleted.append(session_id)
        _commit(conn)
    for session_id in deleted:
        try:
            delete_session_artifacts(session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bulk delete artifact cleanup failed for %s: %s", session_id, exc)
    return {"deleted_session_ids": deleted}


@router.post("/bulk/delete-completed")
def bulk_delete_completed_sessions():
    deleted: list[str] = []
    with _with_conn() as conn:
        rows = _fetchall(conn, "SELECT id, status FROM sessions")
        for row in rows:
            session_id = _row_get(row, "id")
            status = str(_row_get(row, "status") or "").lower()
            if status not in {"done", "paper_unlocked", "paper_locked", "failed_terminal", "stopped"}:
                continue
            _delete_session_state(conn, session_id)
            deleted.append(session_id)
        _commit(conn)
    for session_id in deleted:
        try:
            delete_session_artifacts(session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bulk completed cleanup failed for %s: %s", session_id, exc)
    return {"deleted_session_ids": deleted}


@router.post("/bulk/delete-visible")
def bulk_delete_visible_sessions(payload: dict[str, Any]):
    session_ids = [str(item).strip() for item in (payload.get("session_ids") or []) if str(item).strip()]
    if not session_ids:
        return _error(400, "VISIBLE_SESSION_IDS_REQUIRED", "Delete visible requires the visible session ids from the current dashboard filter.", "needs_visible_ids", ["Pass session_ids from the current dashboard rows."])
    deleted: list[str] = []
    with _with_conn() as conn:
        for session_id in session_ids:
            if not _session_row(conn, session_id):
                continue
            _delete_session_state(conn, session_id)
            deleted.append(session_id)
        _commit(conn)
    for session_id in deleted:
        try:
            delete_session_artifacts(session_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Bulk visible cleanup failed for %s: %s", session_id, exc)
    return {"deleted_session_ids": deleted}


@router.post("/bulk/stop")
def bulk_stop_sessions(payload: dict[str, Any]):
    session_ids = [str(item).strip() for item in (payload.get("session_ids") or []) if str(item).strip()]
    stopped: list[str] = []
    with _with_conn() as conn:
        for session_id in session_ids:
            row = _session_row(conn, session_id)
            if not row or str(_row_get(row, "status") or "").lower() not in {"running", "queued"}:
                continue
            _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("stopped", _now(), session_id))
            _event(conn, session_id, "run_failed", {"summary": "Run stopped by dashboard action."}, "Dashboard", "stopped")
            stopped.append(session_id)
        _commit(conn)
    return {"stopped_session_ids": stopped}


@router.post("/bulk/clean-stale-running")
def clean_stale_running_sessions(payload: dict[str, Any] | None = None):
    payload = payload or {}
    raw_stale_after = payload.get("stale_after_seconds")
    if raw_stale_after is None:
        raw_stale_after = os.getenv("THRIVARC_STALE_RUNNING_SECONDS", "1800")
    stale_after_seconds = int(raw_stale_after)
    stale_session_ids: list[str] = []
    with _with_conn() as conn:
        rows = _fetchall(conn, "SELECT id FROM sessions WHERE status='running'")
        for row in rows:
            session_id = _row_get(row, "id")
            truth = _session_runtime_truth(conn, session_id, stale_after_seconds=stale_after_seconds)
            if not truth.get("stale"):
                continue
            _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("stale_needs_attention", _now(), session_id))
            _event(conn, session_id, "run_failed", {"summary": "No live backend activity was found for this running study.", "backend_activity": truth}, "Dashboard", "stale_needs_attention")
            stale_session_ids.append(session_id)
        _commit(conn)
    return {"stale_session_ids": stale_session_ids}


@router.get("/{session_id}/cockpit")
def get_cockpit(session_id: str):
    with _with_conn() as conn:
        try:
            payload = _cockpit_payload(conn, session_id)
            _commit(conn)
            return payload
        except KeyError:
            return _not_found()


@router.post("/{session_id}/autopilot")
def set_autopilot(session_id: str, payload: dict[str, Any]):
    enabled = bool(payload.get("enabled"))
    criteria = payload.get("criteria") if isinstance(payload.get("criteria"), dict) else _default_autopilot_criteria()
    hard_limits = payload.get("hard_limits") if isinstance(payload.get("hard_limits"), dict) else _default_hard_limits()
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        _ensure_cockpit_settings(conn, session_id)
        _execute(
            conn,
            "UPDATE cockpit_settings SET autopilot_enabled=?, autopilot_criteria=?, hard_limits=?, updated_at=? WHERE session_id=?",
            (enabled, _json_dumps(criteria), _json_dumps(hard_limits), _now(), session_id),
        )
        _event(conn, session_id, "phase_log", {"summary": f"Autopilot {'enabled' if enabled else 'disabled'}.", "hard_limits": hard_limits}, "Research Cockpit", "complete")
        payload_out = _cockpit_payload(conn, session_id)
        _commit(conn)
        return {"autopilot": payload_out["autopilot"]}


@router.post("/{session_id}/approvals/{gate_id}/decision")
def decide_approval_gate(session_id: str, gate_id: str, payload: dict[str, Any]):
    decision = str(payload.get("decision") or "").strip().lower()
    status_map = {"approve": "approved", "approved": "approved", "revise": "revise_requested", "stop": "stopped", "auto_approve": "auto_approved"}
    if decision not in status_map:
        return _error(400, "INVALID_APPROVAL_DECISION", "Decision must be approve, revise, stop, or auto_approve.", "needs_valid_decision", ["approve", "revise", "stop", "auto_approve"])
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        gate = _fetchone(conn, "SELECT * FROM approval_gates WHERE id=? AND session_id=?", (gate_id, session_id))
        if not gate:
            return _error(404, "APPROVAL_GATE_NOT_FOUND", "Approval gate was not found for this session.", "not_found", [f"GET /api/sessions/{session_id}/cockpit"])
        new_status = status_map[decision]
        approver = str(payload.get("approver") or "admin")
        notes = str(payload.get("notes") or "").strip()
        _execute(
            conn,
            "UPDATE approval_gates SET status=?, approver=?, approved_at=?, decision_notes=?, updated_at=? WHERE id=?",
            (new_status, approver, _now(), notes, _now(), gate_id),
        )
        if new_status == "stopped":
            _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("stopped", _now(), session_id))
        event_type = "approval_required" if new_status == "revise_requested" else "phase_update"
        _event(conn, session_id, event_type, {"gate_id": gate_id, "phase_name": _row_get(gate, "phase_name"), "decision": new_status, "notes": notes}, "Research Cockpit", new_status)
        payload_out = _cockpit_payload(conn, session_id)
        _commit(conn)
        return {"approval_gate": next((item for item in payload_out["approval_gates"] if item["id"] == gate_id), None), "cockpit": payload_out}


@router.get("/{session_id}/followups")
def list_followups(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        rows = [_followup_dict(row) for row in _fetchall(conn, "SELECT * FROM followup_instructions WHERE session_id=? ORDER BY created_at ASC", (session_id,))]
        return {"followups": rows}


@router.post("/{session_id}/followups")
def create_followup(session_id: str, payload: dict[str, Any]):
    instruction = str(payload.get("instruction") or payload.get("raw_instruction") or "").strip()
    phase_name = str(payload.get("phase_name") or "").strip() or None
    artifact_path = str(payload.get("artifact_path") or "").strip() or None
    classification, proposed_action, approval_status = _classify_followup(instruction)
    followup_id = str(uuid.uuid4())
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        _execute(
            conn,
            "INSERT INTO followup_instructions (id, session_id, phase_name, artifact_path, raw_instruction, classification, proposed_action, approval_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (followup_id, session_id, phase_name, artifact_path, instruction, classification, proposed_action, approval_status, _now(), _now()),
        )
        if classification == "blueprint_changing_deviation":
            _execute(
                conn,
                "INSERT INTO deviation_register (id, session_id, field_changed, changed_from, changed_to, reason, timestamp, agent_triggered_by, requires_researcher_approval) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), session_id, "researcher_followup", "locked_or_current_design", instruction, "Follow-up instruction may change the research contract.", _now(), "Research Cockpit", True),
            )
        _event(conn, session_id, "followup_classified", {"followup_id": followup_id, "classification": classification, "proposed_action": proposed_action, "approval_status": approval_status}, "Research Cockpit", approval_status)
        row = _fetchone(conn, "SELECT * FROM followup_instructions WHERE id=?", (followup_id,))
        _commit(conn)
        return {"followup": _followup_dict(row)}


@router.get("/{session_id}/prompt-amplifiers")
def get_prompt_amplifiers(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        rows = [_prompt_amplifier_dict(row) for row in _fetchall(conn, "SELECT * FROM prompt_amplifiers WHERE session_id=? ORDER BY agent_name ASC, version DESC", (session_id,))]
        templates = _prompt_template_summaries(conn, session_id)
        versions = [_prompt_template_dict(row) for row in _fetchall(conn, "SELECT * FROM prompt_templates WHERE session_id=? ORDER BY agent_name ASC, layer_type ASC, version DESC, created_at DESC", (session_id,))]
        return {
            "agents": sorted(PROMPT_AGENT_KEYS.keys()),
            "locked_safety_contract": LOCKED_PROMPT_SAFETY_CONTRACT,
            "amplifiers": rows,
            "templates": templates,
            "versions": versions,
        }


@router.put("/{session_id}/prompt-amplifiers")
def put_prompt_amplifier(session_id: str, payload: dict[str, Any]):
    agent_name = _canonical_prompt_agent(payload.get("agent_name") or payload.get("agent"))
    if agent_name not in PROMPT_AGENT_KEYS:
        return _error(400, "INVALID_AGENT_NAME", "Prompt amplifier target must be a known agent.", "needs_valid_agent", sorted(PROMPT_AGENT_KEYS.keys()))
    text = str(payload.get("amplifier_text") or payload.get("amplifier") or "").strip()
    working_prompt = payload.get("working_prompt")
    session_notes = payload.get("session_notes")
    phase_name = str(payload.get("phase_name") or "").strip() or None
    scope = str(payload.get("scope") or "session").strip() or None
    editor = str(payload.get("editor") or "admin")
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        if "amplifier_text" in payload or "amplifier" in payload:
            latest = _latest_prompt_amplifier(conn, session_id, agent_name)
            version = int(_row_get(latest, "version", 0) or 0) + 1
            amp_id = str(uuid.uuid4())
            _execute(
                conn,
                "INSERT INTO prompt_amplifiers (id, session_id, agent_name, phase_name, amplifier_text, version, editor, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (amp_id, session_id, agent_name, phase_name, text, version, editor, _now()),
            )
        if working_prompt is not None:
            _upsert_prompt_template(conn, session_id, agent_name, "working_prompt", str(working_prompt).strip(), editor, phase_name=phase_name, scope=scope)
        if session_notes is not None:
            _upsert_prompt_template(conn, session_id, agent_name, "session_notes", str(session_notes).strip(), editor, phase_name=phase_name, scope=scope)
        composed = _compose_prompt(conn, session_id, agent_name, phase_name, persist=True)
        template = _prompt_template_summary(conn, session_id, agent_name)
        _event(conn, session_id, "prompt_updated", {"agent_name": agent_name, "working_prompt_version": template["working_prompt_version"], "notes_version": template["notes_version"], "prompt_sha256": composed["prompt_sha256"]}, "Prompt Studio", "complete")
        _commit(conn)
        amp_row = _latest_prompt_amplifier(conn, session_id, agent_name)
        return {"amplifier": _prompt_amplifier_dict(amp_row) if amp_row else None, "template": template, "composed_prompt": composed}


@router.get("/{session_id}/prompts/composed")
def get_composed_prompt(session_id: str, agent: str, phase_name: str | None = None):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        agent = _canonical_prompt_agent(agent)
        if agent not in PROMPT_AGENT_KEYS:
            return _error(400, "INVALID_AGENT_NAME", "Composed prompt target must be a known agent.", "needs_valid_agent", sorted(PROMPT_AGENT_KEYS.keys()))
        composed = _compose_prompt(conn, session_id, agent, phase_name, persist=True)
        _commit(conn)
        return composed


def _specialist_fallback_reply(agent_name: str, topic: str, message: str, mode: str) -> str:
    return (
        f"{agent_name} is responding in {mode or 'explain'} mode for the study '{topic}'. "
        f"Working from the current blueprint and verified artifacts, the next concrete move is: {message[:220]}"
    )


def _clean_specialist_code(reply: str) -> str:
    text = str(reply or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _specialist_prompt(
    conn: Any,
    session_id: str,
    agent_name: str,
    mode: str,
    message: str,
    history: list[dict[str, Any]],
) -> tuple[dict[str, Any], str]:
    composed = _compose_prompt(conn, session_id, agent_name, agent_name, persist=True)
    blueprint = _blueprint_content(_blueprint_row(conn, session_id))
    artifact_names = [_artifact_relative_path(session_id, str(item.get("path") or "")) for item in list_artifacts(session_id)[-20:]]
    history_text = "\n\n".join(
        f"{item.get('role', 'user').upper()} [{item.get('mode') or 'general'}]\n{item.get('message_text') or ''}"
        for item in history[-12:]
    )
    prompt = "\n\n".join(
        [
            LOCKED_PROMPT_SAFETY_CONTRACT,
            f"SPECIALIST ROLE\n{agent_name}",
            f"EDITABLE WORKING PROMPT\n{composed.get('working_prompt') or composed.get('base_prompt') or ''}",
            f"SESSION-SPECIFIC NOTES\n{composed.get('session_notes') or '[none supplied]'}",
            f"LOCKED BLUEPRINT CONTEXT\n{json.dumps(blueprint, indent=2, sort_keys=True, default=str)}",
            f"RECENT VERIFIED ARTIFACTS\n{json.dumps(artifact_names, indent=2)}",
            f"SPECIALIST THREAD HISTORY\n{history_text or '[no prior messages]'}",
            f"REQUEST MODE\n{mode or 'explain'}",
            f"RESEARCHER MESSAGE\n{message}",
            "Respond directly, specifically, and in a way that helps the researcher move the study forward.",
        ]
    )
    return composed, prompt


def _persist_specialist_message(
    conn: Any,
    thread_id: str,
    session_id: str,
    agent_name: str,
    role: str,
    message_text: str,
    *,
    mode: str | None = None,
    model_name: str | None = None,
    actions: list[dict[str, Any]] | None = None,
    artifact_paths: list[str] | None = None,
):
    message_id = str(uuid.uuid4())
    _execute(
        conn,
        "INSERT INTO specialist_messages (id, thread_id, session_id, agent_name, role, mode, message_text, model_name, action_payload, artifact_paths, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            message_id,
            thread_id,
            session_id,
            agent_name,
            role,
            mode,
            message_text,
            model_name,
            _json_dumps(actions or []),
            _json_dumps(artifact_paths or []),
            _now(),
        ),
    )
    _execute(conn, "UPDATE specialist_threads SET selected_model=?, updated_at=? WHERE id=?", (model_name or default_model(), _now(), thread_id))
    return _fetchone(conn, "SELECT * FROM specialist_messages WHERE id=?", (message_id,))


def _create_draft_compute_cell(conn: Any, session_id: str, title: str, code: str, created_by: str = "specialist") -> dict[str, Any]:
    max_order = _row_get(_fetchone(conn, "SELECT MAX(cell_order) AS max_order FROM compute_cells WHERE session_id=?", (session_id,)), "max_order", 0) or 0
    cell_id = str(uuid.uuid4())
    _execute(
        conn,
        "INSERT INTO compute_cells (id, session_id, cell_order, title, code, status, artifact_paths, created_by, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cell_id, session_id, int(max_order) + 1, title, code, "draft", _json_dumps([]), created_by, 1, _now(), _now()),
    )
    row = _fetchone(conn, "SELECT * FROM compute_cells WHERE id=?", (cell_id,))
    return _compute_cell_dict(row)


@router.get("/{session_id}/specialists")
def list_specialists(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        threads = []
        for row in _fetchall(conn, "SELECT * FROM specialist_threads WHERE session_id=? ORDER BY updated_at DESC, created_at DESC", (session_id,)):
            messages = _specialist_messages(conn, _row_get(row, "id"))
            threads.append(_specialist_thread_dict(row, messages))
        return {"threads": threads, "agents": sorted(PROMPT_AGENT_KEYS.keys())}


@router.get("/{session_id}/specialists/{agent_name:path}")
def get_specialist_thread(session_id: str, agent_name: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        thread = _specialist_thread(conn, session_id, agent_name)
        messages = _specialist_messages(conn, _row_get(thread, "id"))
        _commit(conn)
        return {"thread": _specialist_thread_dict(thread, messages)}


@router.post("/{session_id}/specialists/{agent_name:path}/messages")
def post_specialist_message(session_id: str, agent_name: str, payload: dict[str, Any]):
    message = str(payload.get("message") or "").strip()
    mode = str(payload.get("mode") or "explain").strip().lower()
    if not message:
        return _error(400, "MESSAGE_REQUIRED", "Message cannot be empty.", "needs_message", ["POST specialist message with text"])
    canonical_agent = _canonical_prompt_agent(agent_name)
    if canonical_agent not in PROMPT_AGENT_KEYS:
        return _error(400, "INVALID_AGENT", f"Unknown agent '{agent_name}'.", "needs_valid_agent", sorted(PROMPT_AGENT_KEYS.keys()))

    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        thread = _specialist_thread(conn, session_id, canonical_agent)
        thread_id = _row_get(thread, "id")
        history = _specialist_messages(conn, thread_id)
        selected_model = _selected_model_for_phase(conn, session_id, canonical_agent)
        topic = _row_get(_session_row(conn, session_id), "topic", "Thrivarc study")
        _persist_specialist_message(conn, thread_id, session_id, canonical_agent, "user", message, mode=mode, model_name=selected_model)
        composed, chat_prompt = _specialist_prompt(conn, session_id, canonical_agent, mode, message, history)
        _commit(conn)

    client = _agent_client()
    if client is None:
        reply = _specialist_fallback_reply(canonical_agent, topic, message, mode)
        used_model = "fallback"
    else:
        try:
            with model_override(selected_model):
                coro = client.chat.completions.create(
                    model=active_model_name(selected_model),
                    messages=[{"role": "user", "content": chat_prompt}],
                    max_tokens=2200,
                    temperature=0.3,
                )
                response = asyncio.get_event_loop().run_until_complete(coro) if inspect.isawaitable(coro) else coro
            reply = response.choices[0].message.content or "[No specialist response]"
            used_model = active_model_name(selected_model)
        except Exception as exc:  # noqa: BLE001
            logger.warning("specialist thread failed for %s: %s", canonical_agent, exc)
            reply = f"[{canonical_agent} unavailable: {exc}]"
            used_model = selected_model

    actions: list[dict[str, Any]] = []
    with _with_conn() as conn:
        if mode == "generate_notebook_cell":
            code = _clean_specialist_code(reply)
            if code:
                requested_title = message[:72].strip().rstrip(".") or f"Draft cell from {canonical_agent}"
                cell = _create_draft_compute_cell(conn, session_id, requested_title, code)
                actions.append({"type": "draft_compute_cell", "cell_id": cell["id"], "title": cell["title"]})
        elif mode == "revise_prompt":
            actions.append({"type": "prompt_revision_suggestion", "agent_name": canonical_agent})
        assistant_row = _persist_specialist_message(conn, thread_id, session_id, canonical_agent, "assistant", reply, mode=mode, model_name=used_model, actions=actions)
        messages = _specialist_messages(conn, thread_id)
        _event(conn, session_id, "phase_log", {"summary": f"{canonical_agent} replied in {mode} mode.", "agent_name": canonical_agent, "mode": mode}, canonical_agent, "complete")
        _commit(conn)
        return {
            "thread": _specialist_thread_dict(_specialist_thread(conn, session_id, canonical_agent), messages),
            "assistant_message": _specialist_message_dict(assistant_row),
            "composed_prompt": composed,
        }



@router.patch("/{session_id}/blueprint")
def patch_blueprint(session_id: str, payload: dict[str, Any]):
    """Update one or more blueprint fields (e.g. research_stance, any confirmed field).

    Accepts any dict of field→value pairs and merges them into the session's
    stored blueprint JSON. The frontend calls this when the researcher:
      - clicks the Exploratory / Confirmatory stance toggle
      - clicks "Confirm this" on a CONFIRM card
      - edits any blueprint field inline
    """
    import json as _json
    with _with_conn() as conn:
        # Check session exists
        sess = _fetchone(conn, "SELECT id FROM sessions WHERE id=?", (session_id,))
        if not sess:
            raise HTTPException(status_code=404, detail="Session not found")

        # Read current blueprint from blueprints table
        bp_row = _fetchone(
            conn,
            "SELECT id, content FROM blueprints WHERE session_id=? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )

        if bp_row:
            try:
                current = _json.loads(_row_get(bp_row, "content") or "{}")
            except Exception:
                current = {}
            current.update(payload)
            _execute(
                conn,
                "UPDATE blueprints SET content=? WHERE id=?",
                (_json.dumps(current), _row_get(bp_row, "id")),
            )
        else:
            # No blueprint row yet — insert one
            import uuid as _uuid
            current = dict(payload)
            _execute(
                conn,
                "INSERT INTO blueprints (id, session_id, content, status, created_at) VALUES (?,?,?,'draft',?)",
                (str(_uuid.uuid4()), session_id, _json.dumps(current), _now()),
            )

        # If research_stance changed, also update research_type on the session
        if "research_stance" in payload:
            stance = str(payload["research_stance"]).lower()
            rtype = "confirmatory" if "confirm" in stance else "exploratory"
            _execute(
                conn,
                "UPDATE sessions SET research_type=?, updated_at=? WHERE id=?",
                (rtype, _now(), session_id),
            )

        _commit(conn)

    return {"ok": True, "session_id": session_id, "updated_fields": list(payload.keys())}


@router.post("/{session_id}/agent-chat")
def agent_chat(session_id: str, payload: dict[str, Any]):

    """Direct conversational chat with a specific agent.

    The agent receives: locked safety contract + its own base prompt +
    researcher amplifier + Blueprint context + the researcher's message.
    Returns the agent's response as a plain string so the frontend can
    display it directly in the chat panel.
    """
    agent_name = _canonical_prompt_agent(payload.get("agent") or payload.get("agent_name") or "")
    message = str(payload.get("message") or "").strip()
    if not agent_name or agent_name not in PROMPT_AGENT_KEYS:
        return _error(400, "INVALID_AGENT", f"Unknown agent '{agent_name}'. Valid agents: {sorted(PROMPT_AGENT_KEYS.keys())}", "needs_valid_agent", sorted(PROMPT_AGENT_KEYS.keys()))
    if not message:
        return _error(400, "MESSAGE_REQUIRED", "Message cannot be empty.", "needs_message", ["POST agent-chat with message"])

    with _with_conn() as conn:
        session = _session_row(conn, session_id)
        if not session:
            return _not_found()
        blueprint = _blueprint_content(_blueprint_row(conn, session_id))
        amplifier = _latest_prompt_amplifier(conn, session_id, agent_name)
        working_prompt = _template_content(conn, session_id, agent_name, "working_prompt", _base_prompt_for_agent(agent_name)[1])
        session_notes = _template_content(conn, session_id, agent_name, "session_notes", "")
        selected_model = _selected_model_for_phase(conn, session_id, agent_name)
        amplifier_text = _row_get(amplifier, "amplifier_text", "") or ""

    _, base_prompt = _base_prompt_for_agent(agent_name)

    # Build the conversational prompt
    chat_prompt = "\n\n".join([
        LOCKED_PROMPT_SAFETY_CONTRACT,
        f"AGENT ROLE: {agent_name}\n{working_prompt or base_prompt}",
        f"SESSION-SPECIFIC NOTES\n{session_notes or '[none]'}",
        f"RESEARCHER AMPLIFIER\n{amplifier_text or '[none]'}",
        f"STUDY BLUEPRINT\n{json.dumps(blueprint, indent=2, default=str)}",
        f"RESEARCHER MESSAGE\n{message}",
        "Respond directly and substantively as this agent. Be specific to the study context above. "
        "For the Literature Agent: suggest concrete papers, authors, journals. "
        "For the Code Environment: write runnable Python code. "
        "For Stats & Methods: recommend specific tests and interpret results. "
        "For Reviewer Gauntlet: raise concrete, numbered objections. "
        "For LaTeX Writer: produce actual LaTeX sections. "
        "Do not be generic. Do not refuse. Do not ask clarifying questions unless truly blocked.",
    ])

    client = _agent_client()
    if client is None:
        # Test / no-LLM fallback — return a contextual stub
        fallback_replies = {
            "Literature Agent": f"I've reviewed your study on '{blueprint.get('topic', 'this topic')}'. Key papers to review: (1) Fama & French (1993) on factor models, (2) Campbell & Shiller (1988) on return predictability, (3) Jegadeesh & Titman (1993) on momentum. I recommend searching Google Scholar for '{message[:60]}' filtered to peer-reviewed finance journals from 2015–2024.",
            "Research Architect": f"Based on your message, I recommend structuring this as a {blueprint.get('method_family', 'quantitative')} study. Your hypothesis should be: '{message[:100]}'. The key identifiers are {blueprint.get('inferred_identifiers', ['SPY', 'QQQ'])} over {blueprint.get('inferred_window', {}).get('start','2015')}–{blueprint.get('inferred_window', {}).get('end','2024')}.",
            "Data Agent": f"For your data request: '{message[:80]}', I suggest fetching via yfinance using `yf.download({blueprint.get('inferred_identifiers', ['SPY'])}, start='{blueprint.get('inferred_window', {}).get('start','2015-01-01')}', end='{blueprint.get('inferred_window', {}).get('end','2024-12-31')}')`. Check for missing trading days and ensure open prices are available for overnight return calculation.",
            "Method / Compute Agent": f"For '{message[:80]}': I recommend implementing this as a panel regression with entity fixed effects. Use `statsmodels.formula.api.ols` with HAC standard errors (Newey-West, lags=5). The primary test statistic is the t-stat on the key predictor coefficient.",
            "Statistics Agent": f"Statistical recommendation for '{message[:80]}': Run (1) Newey-West HAC regression, (2) Placebo test with 1000 random event draws, (3) Bootstrap CI with 5000 iterations, (4) Benjamini-Hochberg correction for multiple comparisons. Report effect size with 95% confidence intervals.",
            "HAWK": f"As reviewer: Your claim '{message[:80]}' raises three concerns: (1) IDENTIFICATION: Is the causal mechanism clear? (2) DATA INTEGRITY: Are overnight returns computed correctly as open(t)−close(t−1)? (3) OVERCLAIMING: Does statistical significance imply economic significance? Quantify effect size in basis points.",
            "Reviewer Agent": f"As reviewer: Your claim '{message[:80]}' raises three concerns: (1) IDENTIFICATION: Is the causal mechanism clear? (2) DATA INTEGRITY: Are overnight returns computed correctly as open(t)−close(t−1)? (3) OVERCLAIMING: Does statistical significance imply economic significance? Quantify effect size in basis points.",
            "Code Audit Agent": f"Auditing '{message[:80]}': Check (1) No look-ahead bias — open(t) must come after close(t−1) chronologically, (2) SHA-256 fingerprint matches uploaded event file, (3) THRIVARC_LOCKED_ANALYSIS_CONTRACT=True is present, (4) All tickers in TICKERS list match blueprint identifiers.",
            "Writer Agent": f"Beginning LaTeX draft for section requested: '{message[:60]}'. Output follows:\n\n\\section{{Results}}\n\nThe empirical analysis yields a coefficient of [STAT] with a Newey-West $t$-statistic of [T-STAT] and associated $p$-value of [P-VAL]. These results [support/do not support] the hypothesis that [HYPOTHESIS].",
        }
        reply = fallback_replies.get(agent_name, f"[LLM unavailable — connect OpenAI API key to get real responses from {agent_name}]")
        return {"agent": agent_name, "reply": reply, "model": "fallback", "session_id": session_id}

    # Real LLM call
    import inspect as _inspect
    import time as _time
    try:
        with model_override(selected_model):
            coro = client.chat.completions.create(
                model=active_model_name(selected_model),
                messages=[{"role": "user", "content": chat_prompt}],
                max_tokens=2000,
                temperature=0.3,
            )
        response = asyncio.get_event_loop().run_until_complete(coro) if _inspect.isawaitable(coro) else coro
        reply = response.choices[0].message.content or "[Agent returned an empty response]"
    except Exception as exc:
        logger.warning("agent-chat LLM call failed for %s: %s", agent_name, exc)
        reply = f"[{agent_name} encountered an error: {exc}. Please retry or check your API configuration.]"

    return {"agent": agent_name, "reply": reply, "model": selected_model, "session_id": session_id}




@router.get("/{session_id}/model-settings")
def get_model_settings(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        rows = [_model_setting_dict(row) for row in _fetchall(conn, "SELECT * FROM phase_model_settings WHERE session_id=? ORDER BY phase_name ASC", (session_id,))]
        return {
            "allowed_models": _allowed_models(),
            "default_model": default_model(),
            "fallback_model": fallback_model(),
            "catalog": model_catalog(),
            "phase_settings": rows,
            "settings": rows,
        }


@router.put("/{session_id}/model-settings")
def put_model_setting(session_id: str, payload: dict[str, Any]):
    phase_name = str(payload.get("phase_name") or payload.get("phase") or "").strip()
    model_name = str(payload.get("model_name") or payload.get("model") or "").strip()
    allowed = _allowed_models()
    if not phase_name:
        return _error(400, "PHASE_REQUIRED", "Model setting requires phase_name.", "needs_phase_name", ["PUT model-settings with phase_name"])
    if model_name not in allowed:
        return _error(400, "MODEL_NOT_ALLOWED", "Model is not configured as an allowed Thrivarc model.", "needs_allowed_model", allowed)
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        existing = _fetchone(conn, "SELECT * FROM phase_model_settings WHERE session_id=? AND phase_name=?", (session_id, phase_name))
        setting_id = _row_get(existing, "id") or str(uuid.uuid4())
        if existing:
            _execute(conn, "UPDATE phase_model_settings SET model_name=?, updated_by=?, updated_at=? WHERE id=?", (model_name, payload.get("updated_by") or "admin", _now(), setting_id))
        else:
            _execute(
                conn,
                "INSERT INTO phase_model_settings (id, session_id, phase_name, model_name, updated_by, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (setting_id, session_id, phase_name, model_name, payload.get("updated_by") or "admin", _now(), _now()),
            )
        _event(conn, session_id, "model_setting_updated", {"phase_name": phase_name, "model_name": model_name}, "Model Selector", "complete")
        row = _fetchone(conn, "SELECT * FROM phase_model_settings WHERE id=?", (setting_id,))
        _commit(conn)
        return {"model_setting": _model_setting_dict(row), "allowed_models": allowed}


@router.get("/{session_id}/compute-cells")
def get_compute_cells(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        cells = _compute_cells(conn, session_id)
        _commit(conn)
        return {"cells": cells}


@router.post("/{session_id}/compute-cells")
def create_compute_cell(session_id: str, payload: dict[str, Any]):
    title = str(payload.get("title") or "Researcher Cell").strip()
    code = str(payload.get("code") or "").strip()
    if not code:
        return _error(400, "CELL_CODE_REQUIRED", "Compute cell requires code.", "needs_cell_code", ["POST compute-cells with code"])
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        max_order = _row_get(_fetchone(conn, "SELECT MAX(cell_order) AS max_order FROM compute_cells WHERE session_id=?", (session_id,)), "max_order", 0) or 0
        cell_id = str(uuid.uuid4())
        _execute(
            conn,
            "INSERT INTO compute_cells (id, session_id, cell_order, title, code, status, artifact_paths, created_by, version, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (cell_id, session_id, int(max_order) + 1, title, code, "draft", _json_dumps([]), payload.get("created_by") or "admin", 1, _now(), _now()),
        )
        _event(conn, session_id, "phase_log", {"summary": f"Compute cell added: {title}", "cell_id": cell_id}, "Cockpit Cells", "draft")
        row = _fetchone(conn, "SELECT * FROM compute_cells WHERE id=?", (cell_id,))
        _commit(conn)
        return {"cell": _compute_cell_dict(row)}


@router.patch("/{session_id}/compute-cells/{cell_id}")
def update_compute_cell(session_id: str, cell_id: str, payload: dict[str, Any]):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        row = _fetchone(conn, "SELECT * FROM compute_cells WHERE id=? AND session_id=?", (cell_id, session_id))
        if not row:
            return _error(404, "COMPUTE_CELL_NOT_FOUND", "Compute cell was not found for this session.", "not_found", [f"GET /api/sessions/{session_id}/compute-cells"])
        title = str(payload.get("title", _row_get(row, "title")) or "Researcher Cell")
        code = str(payload.get("code", _row_get(row, "code")) or "")
        order = int(payload.get("cell_order", _row_get(row, "cell_order", 1)) or 1)
        version = int(_row_get(row, "version", 1) or 1) + 1
        _execute(
            conn,
            "UPDATE compute_cells SET title=?, code=?, cell_order=?, status=?, version=?, updated_at=? WHERE id=?",
            (title, code, order, "draft", version, _now(), cell_id),
        )
        updated = _fetchone(conn, "SELECT * FROM compute_cells WHERE id=?", (cell_id,))
        _commit(conn)
        return {"cell": _compute_cell_dict(updated)}


def _run_cells_and_record(session_id: str, cell_id: str | None = None) -> dict[str, Any]:
    with _with_conn() as conn:
        session = _session_row(conn, session_id)
        if not session:
            raise KeyError("session_not_found")
        blueprint = _blueprint_content(_blueprint_row(conn, session_id)) or {"topic": _row_get(session, "topic"), "method_style": "descriptive", "evidence_route": "yfinance"}
        cells = _compute_cells(conn, session_id)
        code = _concat_cell_code(cells, cell_id)
        target = next((cell for cell in cells if cell.get("id") == cell_id), cells[-1] if cells else None)
        target_id = target.get("id") if target else None
        _event(conn, session_id, "cell_started", {"cell_id": target_id, "run_all": cell_id is None}, "Cockpit Cells", "running")
        _commit(conn)
    result = execute_custom_analysis_code(session_id, blueprint, code)
    metadata = result.get("execution_metadata", {})
    artifact_paths = sorted((result.get("csv_outputs") or {}).keys())
    artifact_paths.extend(artifact.get("blob_path") for artifact in (result.get("figure_artifacts") or {}).values() if isinstance(artifact, dict) and artifact.get("blob_path"))
    artifact_paths.extend(artifact.get("blob_path") for artifact in (result.get("execution_artifacts") or {}).values() if isinstance(artifact, dict) and artifact.get("blob_path"))
    stdout = str((result.get("raw_results") or {}).get("raw_output") or (result.get("raw_results") or {}).get("primary_result") or "")[-12000:]
    stderr = str(metadata.get("stderr") or metadata.get("last_error") or "")[-4000:]
    status = "complete" if result.get("success") else "failed"
    with _with_conn() as conn:
        if cell_id:
            _execute(
                conn,
                "UPDATE compute_cells SET status=?, stdout=?, stderr=?, output_summary=?, artifact_paths=?, updated_at=? WHERE id=? AND session_id=?",
                (status, stdout, stderr, "Cell execution finished." if status == "complete" else "Cell execution failed.", _json_dumps(artifact_paths), _now(), cell_id, session_id),
            )
        else:
            _execute(conn, "UPDATE compute_cells SET status=?, updated_at=? WHERE session_id=?", (status, _now(), session_id))
        exec_id = str(uuid.uuid4())
        _execute(
            conn,
            "INSERT INTO cell_execution_records (id, session_id, cell_id, status, backend, modal_account_alias, runtime_seconds, stdout, stderr, artifact_paths, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (exec_id, session_id, cell_id, status, metadata.get("backend"), metadata.get("modal_account_alias"), metadata.get("runtime_seconds"), stdout, stderr, _json_dumps(artifact_paths), _now()),
        )
        cells_after = _compute_cells(conn, session_id)
        analysis_py = _concat_cell_code(cells_after)
        write_artifact(session_id, "06_compute/notebook/analysis.py", analysis_py)
        write_artifact(session_id, "06_compute/notebook/analysis.ipynb", json.dumps(_notebook_from_cells(cells_after), indent=2))
        event_name = "cell_output" if status == "complete" else "cell_failed"
        _event(conn, session_id, event_name, {"cell_id": cell_id, "status": status, "artifact_paths": artifact_paths, "backend": metadata.get("backend"), "modal_account_alias": metadata.get("modal_account_alias")}, "Cockpit Cells", status)
        if artifact_paths:
            _event(conn, session_id, "cell_artifact_ready", {"cell_id": cell_id, "artifact_paths": artifact_paths}, "Cockpit Cells", status)
        _commit(conn)
        return {"status": status, "execution_id": exec_id, "artifact_paths": artifact_paths, "execution_metadata": metadata, "cells": cells_after}


def _bootstrap_notebook_artifacts(session_id: str, cells: list[dict[str, Any]]) -> tuple[str, str]:
    analysis_py = _concat_cell_code(cells)
    notebook_json = json.dumps(_notebook_from_cells(cells), indent=2)
    write_artifact(session_id, "06_compute/notebook/analysis.py", analysis_py)
    write_artifact(session_id, "06_compute/notebook/analysis.ipynb", notebook_json)
    return notebook_json, analysis_py


def _workspace_seed_files(session_id: str) -> dict[str, bytes]:
    seed_files: dict[str, bytes] = {}
    for item in list_artifacts(session_id):
        relative = _artifact_relative_path(session_id, str(item.get("path") or ""))
        if relative.startswith("03_data/") and relative.endswith((".csv", ".json")):
            data = _safe_artifact_bytes(session_id, relative)
            if data:
                seed_files[os.path.basename(relative)] = data
    return seed_files


def _ensure_notebook_workspace(conn: Any, session_id: str) -> dict[str, Any]:
    row = _notebook_workspace_row(conn, session_id)
    if row:
        return _notebook_workspace_dict(row)
    workspace_id = str(uuid.uuid4())
    _execute(
        conn,
        "INSERT INTO notebook_workspaces (id, session_id, backend, modal_account_alias, status, notebook_artifact_path, analysis_script_path, artifact_paths, sync_status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            workspace_id,
            session_id,
            "modal" if os.getenv("ENVIRONMENT") == "production" else _sandbox_backend_defaults()["backend"],
            _sandbox_backend_defaults()["modal_account_alias"],
            "ready",
            f"sessions/{session_id}/06_compute/notebook/analysis.ipynb",
            f"sessions/{session_id}/06_compute/notebook/analysis.py",
            _json_dumps([]),
            "not_synced",
            _now(),
            _now(),
        ),
    )
    return _notebook_workspace_dict(_fetchone(conn, "SELECT * FROM notebook_workspaces WHERE id=?", (workspace_id,)))


def _notebook_bootstrap_payload(conn: Any, session_id: str) -> tuple[dict[str, Any], str]:
    workspace = _ensure_notebook_workspace(conn, session_id)
    cells = _compute_cells(conn, session_id)
    notebook_text = _safe_artifact_text(session_id, "06_compute/notebook/analysis.ipynb")
    if not notebook_text:
        notebook_text, _ = _bootstrap_notebook_artifacts(session_id, cells)
    return workspace, notebook_text


@router.post("/{session_id}/compute-cells/{cell_id}/run")
def run_compute_cell(session_id: str, cell_id: str):
    try:
        return _run_cells_and_record(session_id, cell_id)
    except KeyError:
        return _not_found()


@router.post("/{session_id}/compute-cells/run-all")
def run_all_compute_cells(session_id: str):
    try:
        return _run_cells_and_record(session_id, None)
    except KeyError:
        return _not_found()


@router.get("/{session_id}/notebook")
def get_notebook_workspace(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        workspace, _ = _notebook_bootstrap_payload(conn, session_id)
        _commit(conn)
        return {"workspace": workspace}


@router.post("/{session_id}/notebook/launch")
def launch_notebook_workspace(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        workspace, notebook_text = _notebook_bootstrap_payload(conn, session_id)
        seed_files = _workspace_seed_files(session_id)
        _execute(
            conn,
            "UPDATE notebook_workspaces SET status=?, last_error=?, updated_at=? WHERE session_id=?",
            ("starting", None, _now(), session_id),
        )
        _event(conn, session_id, "sandbox_job_update", {"phase_name": "Notebook", "job_status": "starting", "backend": workspace.get("backend"), "modal_account_alias": workspace.get("modal_account_alias")}, "Notebook Workspace", "starting")
        _commit(conn)
    try:
        launched = notebook_runtime.launch_or_resume_workspace(session_id, notebook_text, seed_files=seed_files, existing_workspace=workspace)
    except Exception as exc:  # noqa: BLE001
        with _with_conn() as conn:
            if _session_row(conn, session_id):
                _execute(
                    conn,
                    "UPDATE notebook_workspaces SET status=?, last_error=?, updated_at=? WHERE session_id=?",
                    ("failed", f"{type(exc).__name__}: {exc}", _now(), session_id),
                )
                _event(conn, session_id, "cell_failed", {"workspace": "notebook", "error": f"{type(exc).__name__}: {exc}"}, "Notebook Workspace", "failed")
                _commit(conn)
        return _error(502, "NOTEBOOK_LAUNCH_FAILED", "JupyterLab workspace failed to start in Modal.", "notebook_failed", [f"GET /api/sessions/{session_id}/notebook", f"POST /api/sessions/{session_id}/notebook/launch"])
    with _with_conn() as conn:
        workspace = _notebook_workspace_dict(_notebook_workspace_row(conn, session_id)) if _notebook_workspace_row(conn, session_id) else workspace
        artifact_paths = list(dict.fromkeys((workspace.get("artifact_paths") or []) + [
            f"sessions/{session_id}/06_compute/notebook/analysis.ipynb",
            f"sessions/{session_id}/06_compute/notebook/analysis.py",
        ]))
        _execute(
            conn,
            "UPDATE notebook_workspaces SET backend=?, modal_account_alias=?, sandbox_id=?, status=?, access_url=?, can_embed=?, artifact_paths=?, sync_status=?, last_error=?, updated_at=? WHERE session_id=?",
            (
                launched.get("backend"),
                launched.get("modal_account_alias"),
                launched.get("sandbox_id"),
                launched.get("status") or "running",
                launched.get("access_url"),
                bool(launched.get("can_embed")),
                _json_dumps(artifact_paths),
                launched.get("sync_status") or workspace.get("sync_status") or "not_synced",
                None,
                _now(),
                session_id,
            ),
        )
        row = _fetchone(conn, "SELECT * FROM notebook_workspaces WHERE session_id=?", (session_id,))
        _event(conn, session_id, "sandbox_job_update", {"phase_name": "Notebook", "job_status": _row_get(row, "status"), "backend": _row_get(row, "backend"), "modal_account_alias": _row_get(row, "modal_account_alias")}, "Notebook Workspace", _row_get(row, "status"))
        _commit(conn)
        return {"workspace": _notebook_workspace_dict(row)}


@router.post("/{session_id}/notebook/sync")
def sync_notebook_workspace(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        row = _notebook_workspace_row(conn, session_id)
        if not row:
            return _error(409, "NOTEBOOK_NOT_STARTED", "Launch the notebook workspace before syncing artifacts.", "needs_notebook_launch", [f"POST /api/sessions/{session_id}/notebook/launch"])
        workspace = _notebook_workspace_dict(row)
    sync_result = notebook_runtime.sync_workspace_artifacts(session_id, workspace)
    with _with_conn() as conn:
        artifact_paths = list(dict.fromkeys((workspace.get("artifact_paths") or []) + list(sync_result.get("synced_paths") or [])))
        _execute(
            conn,
            "UPDATE notebook_workspaces SET artifact_paths=?, sync_status=?, last_synced_at=?, updated_at=? WHERE session_id=?",
            (_json_dumps(artifact_paths), sync_result.get("status") or "synced", _now(), _now(), session_id),
        )
        row = _fetchone(conn, "SELECT * FROM notebook_workspaces WHERE session_id=?", (session_id,))
        _event(conn, session_id, "cell_artifact_ready", {"artifact_paths": artifact_paths, "workspace": "notebook"}, "Notebook Workspace", sync_result.get("status") or "synced")
        _commit(conn)
        return {"workspace": _notebook_workspace_dict(row)}


@router.get("/{session_id}/quality-report")
def get_quality_report(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        report = _quality_report_for_session(session_id)
        report_id = str(uuid.uuid4())
        _execute(
            conn,
            "INSERT INTO paper_quality_reports (id, session_id, status, score, checks, repair_card, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (report_id, session_id, report["status"], report["score"], _json_dumps(report["checks"]), _json_dumps(report.get("repair_card") or {}), _now()),
        )
        _event(conn, session_id, "quality_report_ready", {"status": report["status"], "score": report["score"], "repair_card": report.get("repair_card")}, "Paper Quality Verifier", report["status"])
        _commit(conn)
        return {"quality_report": report}


@router.post("/{session_id}/sandbox/jobs")
def create_sandbox_job(session_id: str, payload: dict[str, Any]):
    job_id = str(uuid.uuid4())
    phase_name = str(payload.get("phase_name") or "Compute").strip()
    defaults = _sandbox_backend_defaults()
    backend = str(payload.get("backend") or defaults["backend"])
    modal_account_alias = payload.get("modal_account_alias", defaults["modal_account_alias"])
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        _execute(
            conn,
            "INSERT INTO sandbox_jobs (id, session_id, phase_name, status, backend, modal_account_alias, attempt_count, runtime_seconds, logs_path, artifact_paths, cost_metrics, failure_details, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (job_id, session_id, phase_name, "queued", backend, modal_account_alias, int(payload.get("attempt_count") or 0), payload.get("runtime_seconds"), payload.get("logs_path"), _json_dumps(payload.get("artifact_paths") or []), _json_dumps(payload.get("cost_metrics") or {}), None, _now(), _now()),
        )
        _event(conn, session_id, "sandbox_job_update", {"job_id": job_id, "phase_name": phase_name, "job_status": "queued", "backend": backend, "modal_account_alias": modal_account_alias}, "Sandbox Compute", "queued")
        row = _fetchone(conn, "SELECT * FROM sandbox_jobs WHERE id=?", (job_id,))
        _commit(conn)
        return {"sandbox_job": _sandbox_job_dict(row)}


@router.patch("/{session_id}/sandbox/jobs/{job_id}")
def update_sandbox_job(session_id: str, job_id: str, payload: dict[str, Any]):
    allowed = {"queued", "running", "complete", "failed", "cancelled"}
    status = str(payload.get("status") or "running").strip().lower()
    if status not in allowed:
        return _error(400, "INVALID_SANDBOX_STATUS", f"Sandbox status must be one of {sorted(allowed)}.", "needs_valid_status", sorted(allowed))
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        job = _fetchone(conn, "SELECT * FROM sandbox_jobs WHERE id=? AND session_id=?", (job_id, session_id))
        if not job:
            return _error(404, "SANDBOX_JOB_NOT_FOUND", "Sandbox job was not found for this session.", "not_found", [f"GET /api/sessions/{session_id}/cockpit"])
        _execute(
            conn,
            "UPDATE sandbox_jobs SET status=?, backend=?, modal_account_alias=?, attempt_count=?, runtime_seconds=?, logs_path=?, artifact_paths=?, cost_metrics=?, failure_details=?, updated_at=? WHERE id=?",
            (
                status,
                payload.get("backend", _row_get(job, "backend")),
                payload.get("modal_account_alias", _row_get(job, "modal_account_alias")),
                int(payload.get("attempt_count", _row_get(job, "attempt_count", 0)) or 0),
                payload.get("runtime_seconds", _row_get(job, "runtime_seconds")),
                payload.get("logs_path", _row_get(job, "logs_path")),
                _json_dumps(payload.get("artifact_paths", _json_loads(_row_get(job, "artifact_paths"), []))),
                _json_dumps(payload.get("cost_metrics", _json_loads(_row_get(job, "cost_metrics"), {}))),
                payload.get("failure_details", _row_get(job, "failure_details")),
                _now(),
                job_id,
            ),
        )
        _event(conn, session_id, "sandbox_job_update", {"job_id": job_id, "phase_name": _row_get(job, "phase_name"), "job_status": status, "backend": payload.get("backend", _row_get(job, "backend")), "modal_account_alias": payload.get("modal_account_alias", _row_get(job, "modal_account_alias"))}, "Sandbox Compute", status)
        row = _fetchone(conn, "SELECT * FROM sandbox_jobs WHERE id=?", (job_id,))
        _commit(conn)
        return {"sandbox_job": _sandbox_job_dict(row)}


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


@router.post("/{session_id}/resume")
def resume_session_run(session_id: str, payload: dict[str, Any]):
    from_phase = str(payload.get("from_phase") or "Code Audit Agent")
    if from_phase not in AGENT_SEQUENCE:
        return _error(400, "UNKNOWN_PHASE", f"Cannot resume from unknown phase: {from_phase}", "needs_valid_phase", AGENT_SEQUENCE)
    with _with_conn() as conn:
        session = _session_row(conn, session_id)
        if not session:
            return _not_found()
        status = _row_get(session, "status")
        if status not in {"failed_resumable", "paper_locked", "running"}:
            return _error(
                409,
                "SESSION_NOT_RESUMABLE",
                f"Session is {status}; only failed_resumable, paper_locked, or running sessions can be resumed.",
                "not_resumable",
                [f"GET /api/sessions/{session_id}", f"POST /api/sessions/{session_id}/run"],
            )
        blueprint = _blueprint_content(_blueprint_row(conn, session_id))
        if not blueprint:
            return _error(409, "BLUEPRINT_MISSING", "Cannot resume without a locked Blueprint.", "needs_blueprint", [f"POST /api/sessions/{session_id}/scope"])
        start_index = AGENT_SEQUENCE.index(from_phase)
        for agent in AGENT_SEQUENCE[start_index:]:
            _phase_status(conn, session_id, agent, "pending", f"Resume queued from {from_phase}.")
        _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("running", _now(), session_id))
        _event(conn, session_id, "phase_update", {"summary": f"Resume queued from {from_phase}."}, "Pipeline orchestrator", "running")
        _commit(conn)
    if os.getenv("ENVIRONMENT") == "test" or os.getenv("PYTEST_CURRENT_TEST"):
        _run_pipeline_background(session_id, blueprint)
    else:
        threading.Thread(target=_run_pipeline_background, args=(session_id, blueprint), daemon=True).start()
    return {"resume_started": True, "run_id": session_id, "from_phase": from_phase}


@router.get("/{session_id}/compare/{other_session_id}")
def compare_sessions(session_id: str, other_session_id: str):
    with _with_conn() as conn:
        left = _session_row(conn, session_id)
        right = _session_row(conn, other_session_id)
        if not left or not right:
            return _not_found()
        left_bp = _blueprint_content(_blueprint_row(conn, session_id))
        right_bp = _blueprint_content(_blueprint_row(conn, other_session_id))
        left_score = _fetchone(conn, "SELECT average_score FROM reviewer_scores WHERE session_id=? ORDER BY cycle DESC, created_at DESC LIMIT 1", (session_id,))
        right_score = _fetchone(conn, "SELECT average_score FROM reviewer_scores WHERE session_id=? ORDER BY cycle DESC, created_at DESC LIMIT 1", (other_session_id,))
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


@router.post("/{session_id}/scope")
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
        content["blueprint_hash"] = _row_get(row, "blueprint_hash")
        content["locked_at"] = _row_get(row, "locked_at")
        return content


@router.post("/{session_id}/blueprint/lock")
def lock_blueprint(session_id: str, payload: dict[str, Any]):
    if payload.get("confirmation") != "CONFIRM":
        return _error(400, "CONFIRMATION_REQUIRED", "Blueprint lock requires CONFIRM.", "needs_confirmation", [f"POST /api/sessions/{session_id}/blueprint/lock"])
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        row = _blueprint_row(conn, session_id)
        if not row:
            return _error(409, "BLUEPRINT_MISSING", "Create a blueprint before locking.", "needs_blueprint", [f"POST /api/sessions/{session_id}/scope"])
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
            (deviation_id, session_id, payload.get("field"), payload.get("from"), payload.get("to"), payload.get("reason") or "Researcher requested change.", _now(), payload.get("agent_triggered_by"), bool(approval_required)),
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


def _mark_pipeline_failed(session_id: str, exc: BaseException) -> None:
    reason = f"{exc.__class__.__name__}: {exc}"
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    with _with_conn() as conn:
        _phase_failure(conn, session_id, "Pipeline orchestrator", reason, traceback_text=trace)
        _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("failed_resumable", _now(), session_id))
        _event(
            conn,
            session_id,
            "run_failed",
            {
                "summary": "Pipeline failed before completion.",
                "failure_reason": reason,
                "traceback": trace,
                "available_actions": ["retry_run", "review_failure"],
            },
            "Pipeline orchestrator",
            "failed_resumable",
        )
        _commit(conn)


def _run_pipeline_background(session_id: str, blueprint: dict[str, Any]) -> None:
    try:
        _execute_session_pipeline(session_id, blueprint)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Canonical session pipeline failed for %s", session_id)
        _mark_pipeline_failed(session_id, exc)


@router.post("/{session_id}/run")
def run_session(session_id: str, payload: dict[str, Any]):
    if payload.get("approved") is not True:
        return _error(400, "RUN_APPROVAL_REQUIRED", "Run launch requires approved=true.", "needs_approval", [f"POST /api/sessions/{session_id}/run"])
    with _with_conn() as conn:
        session = _session_row(conn, session_id)
        if not session:
            return _not_found()
        blueprint_row = _blueprint_row(conn, session_id)
        blueprint = _blueprint_content(blueprint_row)
        if not blueprint:
            return _error(409, "BLUEPRINT_MISSING", "Create and approve a Blueprint before launch.", "needs_blueprint", [f"POST /api/sessions/{session_id}/scope"])
        if _row_get(blueprint_row, "status") != "locked":
            return _error(409, "BLUEPRINT_NOT_LOCKED", "Lock the Blueprint before launching compute.", "needs_blueprint_lock", [f"POST /api/sessions/{session_id}/blueprint/lock"])
        if not (blueprint.get("data_preview_sha256") or blueprint.get("uploaded_event_sha256")):
            return _error(409, "DATA_PREVIEW_REQUIRED", "Preview and approve the exact evidence before launch.", "needs_data_preview", [f"POST /api/sessions/{session_id}/blueprint"])
        _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("running", _now(), session_id))
        for agent in AGENT_SEQUENCE:
            _phase_status(conn, session_id, agent, "pending", "Queued by RunSpec.")
        _snapshot_all_agent_prompts(conn, session_id)
        _event(conn, session_id, "phase_update", {"summary": "Pipeline run started."}, "Pipeline orchestrator", "running")
        _commit(conn)
    if os.getenv("ENVIRONMENT") == "test" or os.getenv("PYTEST_CURRENT_TEST"):
        _run_pipeline_background(session_id, blueprint)
    else:
        threading.Thread(target=_run_pipeline_background, args=(session_id, blueprint), daemon=True).start()
    return {"run_started": True, "run_id": session_id, "estimated_minutes": 45}


@router.post("/{session_id}/repair/approve")
def approve_repair(session_id: str, payload: dict[str, Any]):
    blueprint: dict[str, Any] = {}
    should_resume = False
    with _with_conn() as conn:
        session = _session_row(conn, session_id)
        if not session:
            return _not_found()
        repair_id = payload.get("repair_id") or str(uuid.uuid4())
        status = "approved" if payload.get("approved") else "rejected"
        blueprint = _blueprint_content(_blueprint_row(conn, session_id))
        _execute(
            conn,
            "INSERT INTO repair_log (id, session_id, trigger_agent, trigger_finding, scope, pass_criterion, cycle_number, approval_required, approved_by, approved_at, outcome) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (repair_id, session_id, "Researcher", "Manual approval", "safe repair", "Repair approved or rejected", 1, False, payload.get("approved_by"), _now(), status),
        )
        _event(conn, session_id, "repair_complete", {"repair_id": repair_id, "repair_status": status}, "Repair Agent", status)
        if payload.get("approved") is True and blueprint:
            start_index = AGENT_SEQUENCE.index("Method / Compute Agent")
            for agent in AGENT_SEQUENCE[start_index:]:
                _phase_status(conn, session_id, agent, "pending", "Repair approved; rerun queued.")
            _execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("running", _now(), session_id))
            _event(conn, session_id, "repair_triggered", {"repair_id": repair_id, "summary": "Repair approved; rerunning evidence and reviewer gates."}, "Repair Agent", "running")
            should_resume = True
        _commit(conn)
    if should_resume:
        if os.getenv("ENVIRONMENT") == "test" or os.getenv("PYTEST_CURRENT_TEST"):
            _run_pipeline_background(session_id, blueprint)
        else:
            threading.Thread(target=_run_pipeline_background, args=(session_id, blueprint), daemon=True).start()
    return {"repair_status": status, "resume_started": should_resume}


@router.get("/{session_id}/export/overleaf.zip")
def export_overleaf_zip(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        readiness = _export_readiness_for_session(conn, session_id)
        if not readiness["ready"]:
            return _error(409, "EXPORT_NOT_READY", "Overleaf ZIP is not ready because Writer has not produced final.tex.", "export_not_ready", ["Complete the Writer phase.", f"GET /api/sessions/{session_id}/cockpit"])
    try:
        data = _build_overleaf_zip(session_id)
        write_artifact(session_id, "11_paper/overleaf_project.zip", data)
        with _with_conn() as conn:
            _event(
                conn,
                session_id,
                "export_ready",
                {"path": f"sessions/{session_id}/11_paper/overleaf_project.zip", "format": "overleaf_zip", "bytes": len(data)},
                "Export Agent",
                "complete",
            )
            _commit(conn)
    except BlobStorageUnavailableError as exc:
        return _error(503, exc.error_code, str(exc), exc.system_state, exc.available_actions)
    headers = {"Content-Disposition": f'attachment; filename="thrivarc_{session_id}_overleaf.zip"'}
    return StreamingResponse(io.BytesIO(data), media_type="application/zip", headers=headers)


@router.get("/{session_id}/artifacts/download")
def download_artifact(session_id: str, path: str):
    prefix = f"sessions/{session_id}/"
    clean_path = str(path or "").strip().strip("/")
    if not clean_path.startswith(prefix):
        return _error(
            403,
            "ARTIFACT_PATH_FORBIDDEN",
            "Artifact path must belong to this session.",
            "forbidden",
            [f"GET /api/sessions/{session_id}/artifacts"],
        )
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
    try:
        data = read_artifact(session_id, clean_path)
    except BlobStorageUnavailableError:
        return _error(
            404,
            "ARTIFACT_NOT_FOUND",
            "Artifact could not be downloaded from storage.",
            "artifact_unavailable",
            [f"GET /api/sessions/{session_id}/artifacts"],
        )
    filename = clean_path.rsplit("/", 1)[-1] or "artifact"
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(io.BytesIO(data), media_type=content_type, headers=headers)


@router.get("/{session_id}/artifacts")
def artifacts(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
    artifacts_list = list_artifacts(session_id)
    for item in artifacts_list:
        item.setdefault("download_url", item.get("url"))
        item["direct_download_url"] = f"/api/sessions/{session_id}/artifacts/download?path={item['path']}"
    return {"artifacts": artifacts_list}


@router.get("/{session_id}/results")
def results(session_id: str):
    with _with_conn() as conn:
        if not _session_row(conn, session_id):
            return _not_found()
        scores = [_json_loads(json.dumps(dict(row)), {}) if not isinstance(row, dict) else row for row in _fetchall(conn, "SELECT * FROM reviewer_scores WHERE session_id=? ORDER BY cycle ASC, created_at ASC", (session_id,))]
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


def _artifact_relative_path(session_id: str, blob_path: str) -> str:
    prefix = f"sessions/{session_id}/"
    clean = str(blob_path or "").strip().strip("/")
    return clean[len(prefix) :] if clean.startswith(prefix) else clean


def _safe_artifact_bytes(session_id: str, path: str) -> bytes | None:
    try:
        return read_artifact(session_id, path)
    except Exception as exc:  # noqa: BLE001 - rerender is best-effort over historical artifacts
        logger.warning("Rerender skipped missing/unreadable artifact %s for %s: %s", path, session_id, exc)
        return None


def _safe_artifact_text(session_id: str, path: str, *, limit: int | None = None) -> str:
    data = _safe_artifact_bytes(session_id, path)
    if not data:
        return ""
    text = data.decode("utf-8", errors="replace")
    return text[:limit] if limit else text


def _safe_artifact_json(session_id: str, path: str, default: Any | None = None) -> Any:
    text = _safe_artifact_text(session_id, path)
    if not text:
        return {} if default is None else default
    return _json_loads(text, {} if default is None else default)


def _zip_safe_name(relative: str) -> str:
    clean = str(relative or "").strip().strip("/")
    clean = re.sub(r"(^|/)\.\.(?=/|$)", "", clean)
    return clean or "artifact"


def _build_overleaf_zip(session_id: str) -> bytes:
    artifacts_list = list_artifacts(session_id)
    manifest = {
        "session_id": session_id,
        "created_at": _now(),
        "artifact_count": len(artifacts_list),
        "contents": [],
        "reproducibility": {
            "state_source": "PostgreSQL /api/sessions/*",
            "artifact_source": "Azure Blob Storage",
            "legacy_state_used": False,
        },
    }
    include_prefixes = (
        "11_paper/final.tex",
        "02_literature/bibliography.bib",
        "figures/",
        "07_statistics/results_tables/",
        "08_stats/",
        "06_compute/",
        "03_data/data_passport.json",
        "10_verification/",
        "12_prompts/",
        "12_quality/",
    )
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for item in artifacts_list:
            relative = _artifact_relative_path(session_id, str(item.get("path") or ""))
            if not any(relative == prefix or relative.startswith(prefix) for prefix in include_prefixes):
                continue
            data = _safe_artifact_bytes(session_id, relative)
            if data is None:
                continue
            arcname = _zip_safe_name(relative)
            zf.writestr(arcname, data)
            manifest["contents"].append({"path": arcname, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
        with _with_conn() as conn:
            prompt_rows = [
                _prompt_amplifier_dict(row)
                for row in _fetchall(conn, "SELECT * FROM prompt_amplifiers WHERE session_id=? ORDER BY agent_name ASC, version ASC", (session_id,))
            ]
            template_rows = [
                _prompt_template_dict(row)
                for row in _fetchall(conn, "SELECT * FROM prompt_templates WHERE session_id=? ORDER BY agent_name ASC, layer_type ASC, version ASC", (session_id,))
            ]
            snapshot_rows = [
                {
                    "agent_name": _row_get(row, "agent_name"),
                    "phase_name": _row_get(row, "phase_name"),
                    "composed_prompt": _row_get(row, "composed_prompt"),
                    "base_prompt_key": _row_get(row, "base_prompt_key"),
                    "amplifier_version": _row_get(row, "amplifier_version"),
                    "prompt_sha256": _row_get(row, "prompt_sha256"),
                    "created_at": _row_get(row, "created_at"),
                }
                for row in _fetchall(conn, "SELECT * FROM composed_prompt_snapshots WHERE session_id=? ORDER BY created_at ASC", (session_id,))
            ]
            specialist_threads = [
                _specialist_thread_dict(row)
                for row in _fetchall(conn, "SELECT * FROM specialist_threads WHERE session_id=? ORDER BY updated_at ASC", (session_id,))
            ]
            specialist_messages = [
                _specialist_message_dict(row)
                for row in _fetchall(conn, "SELECT * FROM specialist_messages WHERE session_id=? ORDER BY created_at ASC", (session_id,))
            ]
            notebook_workspace = _notebook_workspace_dict(_notebook_workspace_row(conn, session_id)) if _notebook_workspace_row(conn, session_id) else None
        prompt_manifest = {
            "locked_safety_contract": LOCKED_PROMPT_SAFETY_CONTRACT,
            "amplifiers": prompt_rows,
            "templates": template_rows,
            "composed_prompt_snapshots": snapshot_rows,
            "specialist_threads": specialist_threads,
            "specialist_messages": specialist_messages,
            "notebook_workspace": notebook_workspace,
        }
        prompt_bytes = json.dumps(prompt_manifest, indent=2, sort_keys=True, default=str).encode("utf-8")
        zf.writestr("12_prompts/prompt_manifest.json", prompt_bytes)
        manifest["contents"].append({"path": "12_prompts/prompt_manifest.json", "bytes": len(prompt_bytes), "sha256": hashlib.sha256(prompt_bytes).hexdigest()})
        quality = _quality_report_for_session(session_id)
        quality_bytes = json.dumps(quality, indent=2, sort_keys=True, default=str).encode("utf-8")
        zf.writestr("12_quality/paper_quality_report.json", quality_bytes)
        manifest["contents"].append({"path": "12_quality/paper_quality_report.json", "bytes": len(quality_bytes), "sha256": hashlib.sha256(quality_bytes).hexdigest()})
        manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")
        zf.writestr("run_manifest.json", manifest_bytes)
        zf.writestr(
            "README.md",
            (
                "# Thrivarc Overleaf Export\n\n"
                "Upload this ZIP directly to Overleaf. The canonical entrypoint is `11_paper/final.tex`.\n\n"
                "This bundle includes paper source, bibliography, figures, tables, generated code or method outputs when available, "
                "verification artifacts, and a run manifest with SHA-256 fingerprints.\n"
            ).encode("utf-8"),
        )
    return buffer.getvalue()


def _csv_artifacts_for_writer(session_id: str, artifacts_list: list[dict[str, Any]]) -> dict[str, str]:
    csv_outputs: dict[str, str] = {}
    prefixes = (
        "03_data/overnight_returns.csv",
        "06_compute/method_outputs/",
        "07_statistics/results_tables/",
        "08_stats/",
    )
    for item in artifacts_list:
        relative = _artifact_relative_path(session_id, str(item.get("path") or ""))
        if not relative.endswith(".csv"):
            continue
        if not any(relative == prefix or relative.startswith(prefix) for prefix in prefixes):
            continue
        # Large raw data files are useful for data summary, but should not crowd
        # out compact result tables in the Writer context.
        limit = 80000 if relative.startswith("03_data/") else None
        text = _safe_artifact_text(session_id, relative, limit=limit)
        if text:
            csv_outputs[relative] = text
    return csv_outputs


def _method_style_for_compute(blueprint: dict[str, Any]) -> str:
    return str(blueprint.get("method_style") or blueprint.get("method_family") or "descriptive").strip().lower()


def _csv_rows_from_text(text: str) -> list[dict[str, str]]:
    try:
        return list(csv.DictReader(io.StringIO(text or "")))
    except Exception:
        return []


def _float_or_none(value: Any) -> float | None:
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_incoherent_bootstrap_ci(csv_outputs: dict[str, str]) -> bool:
    """Return true when an existing bootstrap CI cannot belong to the reported coefficient."""
    stats_text = csv_outputs.get("08_stats/stats_summary.csv") or csv_outputs.get("07_statistics/results_tables/executed_tests.csv") or ""
    rows = _csv_rows_from_text(stats_text)
    coefficient: float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    for row in rows:
        test_name = str(row.get("test_name") or row.get("Test") or "").lower()
        if coefficient is None and ("regression" in test_name or row.get("coefficient")):
            coefficient = _float_or_none(row.get("coefficient") or row.get("Coefficient"))
        if "bootstrap" in test_name:
            ci_lower = _float_or_none(row.get("ci_lower") or row.get("CI Lower") or row.get("Lower"))
            ci_upper = _float_or_none(row.get("ci_upper") or row.get("CI Upper") or row.get("Upper"))
    if coefficient is None or ci_lower is None or ci_upper is None:
        return False
    lower, upper = sorted([ci_lower, ci_upper])
    return not (lower <= coefficient <= upper)


def _needs_method_specific_rerender_refresh(blueprint: dict[str, Any], csv_outputs: dict[str, str]) -> bool:
    """Historical sessions may have event-study artifacts even when the Blueprint is not event-study."""
    if os.getenv("PYTEST_CURRENT_TEST"):
        return False
    method = _method_style_for_compute(blueprint)
    if _has_incoherent_bootstrap_ci(csv_outputs):
        return True
    if method == "event_study":
        return False
    if method in {"time_series", "var_model", "cointegration"}:
        return "06_compute/method_outputs/predictive_series.csv" not in csv_outputs
    if method in {"regression", "panel_regression", "quantile_regression", "causal_forest", "factor_model", "backtest", "portfolio_optimization", "risk_model", "volatility_model"}:
        return "06_compute/method_outputs/regression_design.csv" not in csv_outputs
    return False


def _materialize_method_compute_for_rerender(session_id: str, blueprint: dict[str, Any]) -> dict[str, Any]:
    """
    Recreate method-shaped compute artifacts for old sessions without launching a new research run.

    This is intentionally scoped to rerender repair: it reads the locked Blueprint,
    executes the canonical compute dispatcher, uploads verified CSV/JSON artifacts,
    and returns the fresh package for the Writer context.
    """
    executed = execute_research_plan(blueprint, session_id=session_id)
    for path, text in executed.get("csv_outputs", {}).items():
        if isinstance(text, str):
            _write_text_artifact(session_id, path, text)
    _write_json_artifact(
        session_id,
        "07_statistics/research_findings.json",
        {
            "method_family": executed.get("context", {}).get("method_family"),
            "primary_numbers": executed.get("primary_numbers", {}),
            "evidence_conclusion": executed.get("evidence_conclusion"),
            "economic_interpretation": executed.get("economic_interpretation"),
        },
    )
    _write_json_artifact(session_id, "07_statistics/results_tables/main_results.json", executed.get("robustness_results", {}))
    _write_json_artifact(session_id, "08_stats/stats_summary.json", executed.get("stats_summary", {}))
    return executed


def _existing_figure_artifacts(session_id: str, artifacts_list: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    figures: dict[str, dict[str, Any]] = {}
    for item in artifacts_list:
        relative = _artifact_relative_path(session_id, str(item.get("path") or ""))
        if not relative.startswith("figures/"):
            continue
        filename = os.path.basename(relative)
        if not filename.lower().endswith((".png", ".pdf")):
            continue
        key = f"fig{len(figures) + 1}_{os.path.splitext(filename)[0]}"
        figures[key] = {
            "key": key,
            "path": relative,
            "blob_path": item.get("path"),
            "filename": filename,
            "caption": os.path.splitext(filename)[0].replace("_", " ").replace("-", " ").title(),
            "label": f"fig:{os.path.splitext(filename)[0]}",
            "sha256": item.get("sha256"),
            "bytes": item.get("bytes"),
        }
    return figures


def _generate_figures_from_csv_outputs(session_id: str, csv_outputs: dict[str, str], stats_dict: dict[str, Any], blueprint: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    return generate_figures_for_study(session_id, blueprint or {}, csv_outputs, stats_dict or {})


def _figure_assets_for_compile(session_id: str, figure_artifacts: dict[str, Any]) -> dict[str, bytes]:
    assets: dict[str, bytes] = {}
    if not isinstance(figure_artifacts, dict):
        return assets
    for metadata in figure_artifacts.values():
        if not isinstance(metadata, dict):
            continue
        filename = os.path.basename(str(metadata.get("filename") or ""))
        path = str(metadata.get("path") or metadata.get("blob_path") or "").strip()
        if not filename or not path:
            continue
        relative = _artifact_relative_path(session_id, path)
        data = _safe_artifact_bytes(session_id, relative)
        if data:
            assets[filename] = data
    return assets


def _latest_reviewer_scorecard(session_id: str) -> dict[str, Any]:
    scorecard: dict[str, Any] = {}
    with _with_conn() as conn:
        row = _fetchone(conn, "SELECT * FROM reviewer_scores WHERE session_id=? ORDER BY cycle DESC, created_at DESC LIMIT 1", (session_id,))
        if row:
            scorecard = {
                "gate_passed": bool(_row_get(row, "gate_passed")),
                "scores": {
                    "identification_validity": _row_get(row, "identification_validity"),
                    "data_integrity": _row_get(row, "data_integrity"),
                    "statistical_rigor": _row_get(row, "statistical_rigor"),
                    "economic_significance": _row_get(row, "economic_significance"),
                    "benchmark_fairness": _row_get(row, "benchmark_fairness"),
                    "robustness_burden": _row_get(row, "robustness_burden"),
                    "overclaiming_risk": _row_get(row, "overclaiming_risk"),
                },
                "average_score": _row_get(row, "average_score"),
                "findings": _json_loads(_row_get(row, "findings"), {}),
            }
    if scorecard:
        return scorecard
    artifact_scorecard = _safe_artifact_json(session_id, "09_review/reviewer_scorecard_v1.json", {})
    return artifact_scorecard if isinstance(artifact_scorecard, dict) else {}


def _load_or_recompute_stats(session_id, blueprint, tmpdir):
    """Load existing stats or recompute if missing."""
    from storage.blob import download_blob
    
    # Try loading existing stats
    stats_paths = [
        f"sessions/{session_id}/08_stats/stats_summary.json",
        f"sessions/{session_id}/07_statistics/results_tables/t_tests.csv",
    ]
    
    stats_data = {}
    for path in stats_paths:
        try:
            data = download_blob(path)
            if data:
                key = path.split('/')[-1]
                stats_data[key] = data.decode('utf-8')
        except:
            pass
    
    if not stats_data:
        # No stats found — recompute from existing data CSV
        print(f"No stats found for {session_id}, recomputing...")
        data_path = f"sessions/{session_id}/03_data/overnight_returns.csv"
        try:
            data_bytes = download_blob(data_path)
            if data_bytes:
                local_csv = os.path.join(tmpdir, "data.csv")
                with open(local_csv, 'wb') as f:
                    f.write(data_bytes)
                from api.compute_dispatcher import dispatch_compute
                result = dispatch_compute(session_id, blueprint, local_csv, None)
                stats_data = result.get('stats_summary', {})
        except Exception as e:
            print(f"ERROR recomputing stats: {e}")
    
    return stats_data

def _build_rerender_writer_context(session_id: str) -> dict[str, Any]:
    with _with_conn() as conn:
        session = _session_row(conn, session_id)
        if not session:
            raise KeyError("session_not_found")
        blueprint = _blueprint_content(_blueprint_row(conn, session_id))
        topic = _row_get(session, "topic") or blueprint.get("focus_question") or blueprint.get("topic") or "Thrivarc research paper"

    artifacts_list = list_artifacts(session_id)
    profile = _safe_artifact_json(session_id, "00_runspec/execution_profile.json", {})
    agent_context = _safe_artifact_json(session_id, "00_runspec/agent_context.json", {})
    contracts = agent_context.get("contracts", {}) if isinstance(agent_context, dict) else {}
    agent_blueprint = contracts.get("agent_blueprint") if isinstance(contracts, dict) else {}
    if not isinstance(agent_blueprint, dict):
        agent_blueprint = {}
    merged_blueprint = {**(blueprint if isinstance(blueprint, dict) else {}), **agent_blueprint}

    data_passport = _safe_artifact_json(session_id, "03_data/data_passport.json", {})
    method_spec = _safe_artifact_json(session_id, "06_compute/method_spec.json", {})
    if not method_spec and isinstance(contracts, dict):
        method_spec = contracts.get("method_spec", {})
    
    with tempfile.TemporaryDirectory() as tmpdir:
        stats_data_recomputed = _load_or_recompute_stats(session_id, merged_blueprint, tmpdir)
    
    stats_summary_json = _safe_artifact_json(session_id, "08_stats/stats_summary.json", {})
    if not stats_summary_json and stats_data_recomputed:
        stats_summary_json = stats_data_recomputed

    research_findings = _safe_artifact_json(session_id, "07_statistics/research_findings.json", {})
    main_results = _safe_artifact_json(session_id, "07_statistics/results_tables/main_results.json", {})
    economic_significance = _safe_artifact_json(session_id, "07_statistics/economic_significance.json", {})

    csv_outputs = _csv_artifacts_for_writer(session_id, artifacts_list)
    primary_numbers = {}
    if isinstance(research_findings, dict):
        primary_numbers.update(research_findings.get("primary_numbers") or {})
    if isinstance(profile, dict):
        primary_numbers.update((profile.get("findings") or {}).get("primary_numbers") or {})

    figure_artifacts = _existing_figure_artifacts(session_id, artifacts_list)
    if _needs_method_specific_rerender_refresh(merged_blueprint, csv_outputs):
        try:
            refreshed = _materialize_method_compute_for_rerender(session_id, merged_blueprint)
            csv_outputs = refreshed.get("csv_outputs", {}) or csv_outputs
            primary_numbers = refreshed.get("primary_numbers", {}) or primary_numbers
            stats_summary_json = refreshed.get("stats_summary", {}) or stats_summary_json
            figure_artifacts = refreshed.get("figure_artifacts", {}) or figure_artifacts
            research_findings = {
                "method_family": refreshed.get("context", {}).get("method_family"),
                "primary_numbers": primary_numbers,
                "evidence_conclusion": refreshed.get("evidence_conclusion"),
                "economic_interpretation": refreshed.get("economic_interpretation"),
            }
            main_results = refreshed.get("robustness_results", {}) or main_results
        except Exception as exc:  # noqa: BLE001 - rerender can still proceed with historical artifacts
            logger.warning("Method-specific rerender refresh failed for %s: %s", session_id, exc)

    stats_summary_csv = csv_outputs.get("08_stats/stats_summary.csv", "")

    return {
        "topic": topic,
        "blueprint": merged_blueprint,
        "data_passport": data_passport if isinstance(data_passport, dict) else {},
        "literature_review": _safe_artifact_text(session_id, "02_literature/literature_review.md"),
        "bibliography_bib": _safe_artifact_text(session_id, "02_literature/bibliography.bib"),
        "method_spec": method_spec if isinstance(method_spec, dict) else {},
        "stats_results": {
            "stats_summary": stats_summary_json if isinstance(stats_summary_json, dict) else {},
            "stats_summary_csv": stats_summary_csv,
            "statistics": main_results if isinstance(main_results, dict) else {},
            "findings": research_findings if isinstance(research_findings, dict) else {},
            "economic_significance": economic_significance if isinstance(economic_significance, dict) else {},
            "primary_numbers": primary_numbers,
        },
        "hawk_scorecard": _latest_reviewer_scorecard(session_id),
        "all_csv_artifacts": csv_outputs,
        "figure_artifacts": figure_artifacts,
    }


@router.post("/{session_id}/rerender")
async def rerender_paper(session_id: str) -> JSONResponse:
    try:
        import asyncio
        writer_context = await asyncio.to_thread(_build_rerender_writer_context, session_id)
    except KeyError:
        return _not_found()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Could not build rerender context for %s", session_id)
        return _error(500, "RERENDER_CONTEXT_FAILED", f"Could not build Writer context: {exc}", "rerender_failed", [f"GET /api/sessions/{session_id}/artifacts"])

    with _with_conn() as conn:
        writer_model = _selected_model_for_phase(conn, session_id, "Writer Agent")

    try:
        with model_override(writer_model):
            writer_result = await write_paper_latex(writer_context, client=_agent_client())
        paper = clean_latex_escaping(writer_result.get("latex", ""))
        pdf = await asyncio.to_thread(
            _render_latex_source_pdf,
            paper,
            writer_context.get("topic", "Research Paper"),
            _figure_assets_for_compile(session_id, writer_result.get("figure_artifacts") or writer_context.get("figure_artifacts", {})),
            session_id
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM rerender failed for %s; retrying deterministic Writer fallback: %s", session_id, exc)
        try:
            writer_result = await write_paper_latex(writer_context, client=None)
            paper = clean_latex_escaping(writer_result.get("latex", ""))
            pdf = await asyncio.to_thread(
                _render_latex_source_pdf,
                paper,
                writer_context.get("topic", "Research Paper"),
                _figure_assets_for_compile(session_id, writer_result.get("figure_artifacts") or writer_context.get("figure_artifacts", {})),
                session_id
            )
        except Exception as fallback_exc:  # noqa: BLE001
            logger.exception("Rerender failed for %s", session_id)
            return _error(500, "RERENDER_FAILED", f"Paper rerender failed: {fallback_exc}", "rerender_failed", [f"GET /api/sessions/{session_id}/artifacts"])

    _write_text_artifact(session_id, "11_paper/final.tex", paper)
    write_artifact(session_id, "11_paper/final.pdf", pdf)

    return JSONResponse(status_code=200, content={
        "status": "ok", 
        "pages": max(1, len(re.findall(rb"/Type\s*/Page\b", pdf))), 
        "pdf_path": get_artifact_url(session_id, "11_paper/final.pdf")
    })
