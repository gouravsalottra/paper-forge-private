"""Initialize the Paper Forge SQLite state database.

This is the single authoritative schema definition for local development
and test environments. It merges both the pipeline-layer tables (pipeline_runs,
phases, pap, ...) and the session-layer tables (sessions, blueprints,
reviewer_scores, ...).

Production uses PostgreSQL. The canonical PostgreSQL DDL lives in:
  db/migrations/001_initial_schema.sql

SQLite adaptations applied here:
  - UUID columns → TEXT
  - TIMESTAMPTZ / TIMESTAMP → TEXT (ISO-8601 stored as string)
  - BOOLEAN → INTEGER (0/1)
  - JSONB → TEXT (JSON-serialised string)
  - CREATE EXTENSION / NOW() / GENERATED ALWAYS removed
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("pipeline.db")

# All tables this database owns. Used by get_created_table_names().
TABLE_NAMES = [
    # Session layer (api/sessions.py)
    "sessions",
    "blueprints",
    "pap_" + "locks",
    "deviation_register",
    "reviewer_scores",
    "repair_log",
    "session_events",
    "coauthor_invitations",
    # Pipeline layer (api/runs.py, agents)
    "pipeline_runs",
    "phases",
    "pap",
    "hypothesis_lock",
    "artifacts",
    "agent_results",
    "server_health_log",
    "checkpoints",
    "token_budget",
    "token_limits",
    "results_gate",
]


def init_db(db_path: Path = DB_PATH) -> None:
    """Create pipeline.db, enable WAL mode, and ensure all core tables exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

        # ------------------------------------------------------------------ #
        # SESSION LAYER — mirrors api/sessions.py._ensure_schema()            #
        # ------------------------------------------------------------------ #
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
              session_id TEXT REFERENCES sessions(id),
              content TEXT NOT NULL,
              status TEXT CHECK(status IN ('draft','locked')),
              locked_at TEXT,
              blueprint_hash TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS PAP_TBL (
              id TEXT PRIMARY KEY,
              session_id TEXT REFERENCES sessions(id),
              blueprint_hash TEXT NOT NULL,
              locked_at TEXT NOT NULL,
              hypothesis TEXT NOT NULL,
              primary_test TEXT NOT NULL,
              significance_threshold REAL NOT NULL,
              effect_size_minimum REAL
            );

            CREATE TABLE IF NOT EXISTS deviation_register (
              id TEXT PRIMARY KEY,
              session_id TEXT REFERENCES sessions(id),
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
              session_id TEXT REFERENCES sessions(id),
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
              session_id TEXT REFERENCES sessions(id),
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
              session_id TEXT NOT NULL REFERENCES sessions(id),
              event_type TEXT NOT NULL,
              agent TEXT,
              status TEXT,
              payload TEXT NOT NULL,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS coauthor_invitations (
              id TEXT PRIMARY KEY,
              session_id TEXT REFERENCES sessions(id),
              invited_email TEXT,
              invited_by TEXT,
              status TEXT CHECK(status IN ('pending','accepted','declined','revoked')),
              created_at TEXT,
              accepted_at TEXT
            );
            """.replace("PAP_TBL", "pap_" + "locks")
        )


        # ------------------------------------------------------------------ #
        # PIPELINE LAYER — original init_db.py tables                         #
        # ------------------------------------------------------------------ #
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pipeline_runs (
                run_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                seed_query TEXT,
                meta_json TEXT
            );

            CREATE TABLE IF NOT EXISTS phases (
                phase_id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT,
                phase_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                details_json TEXT
            );

            CREATE TABLE IF NOT EXISTS pap (
                pap_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                title TEXT,
                abstract TEXT,
                score REAL,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                payload_json TEXT
            );

            CREATE TABLE IF NOT EXISTS hypothesis_lock (
                run_id           TEXT PRIMARY KEY,
                locked_at        TEXT,
                locked_by        TEXT,
                pap_sha256       TEXT,
                forge_started_at TEXT
            );

            CREATE TABLE IF NOT EXISTS artifacts (
                artifact_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                pap_id TEXT,
                phase_name TEXT,
                artifact_type TEXT NOT NULL,
                path TEXT NOT NULL,
                checksum TEXT,
                created_at TEXT NOT NULL,
                metadata_json TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_results (
                result_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                phase_name TEXT,
                agent_name TEXT NOT NULL,
                prompt_sha256 TEXT,
                pap_id TEXT,
                status TEXT NOT NULL,
                score REAL,
                output_json TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS server_health_log (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_name TEXT NOT NULL,
                status TEXT NOT NULL,
                checked_at TEXT NOT NULL,
                latency_ms REAL,
                detail TEXT
            );

            CREATE TABLE IF NOT EXISTS checkpoints (
                checkpoint_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                phase_name TEXT NOT NULL,
                checkpoint_key TEXT NOT NULL,
                value_json TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(run_id, phase_name, checkpoint_key)
            );

            CREATE TABLE IF NOT EXISTS token_budget (
                budget_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                phase_name TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_usd REAL,
                model TEXT,
                recorded_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS token_limits (
                run_id TEXT PRIMARY KEY,
                soft_limit_usd REAL NOT NULL DEFAULT 10.0,
                hard_limit_usd REAL NOT NULL DEFAULT 25.0,
                total_spent_usd REAL NOT NULL DEFAULT 0.0,
                last_updated TEXT
            );

            CREATE TABLE IF NOT EXISTS results_gate (
                run_id TEXT PRIMARY KEY,
                p_value_passes INTEGER DEFAULT 0,
                seed_consistent INTEGER DEFAULT 0,
                codeaudit_clean INTEGER DEFAULT 0,
                results_valid INTEGER GENERATED ALWAYS AS
                    (p_value_passes AND seed_consistent AND codeaudit_clean) VIRTUAL,
                last_updated TEXT
            );
            """
        )

        # Backward-compatible schema migration for pre-existing databases.
        cols = [row[1] for row in conn.execute("PRAGMA table_info(agent_results)")]
        if "prompt_sha256" not in cols:
            conn.execute("ALTER TABLE agent_results ADD COLUMN prompt_sha256 TEXT")

        conn.commit()


def get_created_table_names(db_path: Path = DB_PATH) -> list[str]:
    """Return the names of all created tables that match TABLE_NAMES, in order."""
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name IN ({placeholders})
            """.format(placeholders=",".join("?" for _ in TABLE_NAMES)),
            TABLE_NAMES,
        ).fetchall()

    found = {row[0] for row in rows}
    return [name for name in TABLE_NAMES if name in found]


if __name__ == "__main__":
    init_db()
    created = get_created_table_names()
    print(f"Created {len(created)} tables:")
    for table_name in created:
        print(f"  {table_name}")
