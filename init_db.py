"""Initialize the Paper Forge SQLite state database."""

from __future__ import annotations

import sqlite3
from pathlib import Path

DB_PATH = Path("state.db")
TABLE_NAMES = [
    "pipeline_runs",
    "phases",
    "pap",
    "pap_lock",
    "artifacts",
    "agent_results",
    "server_health_log",
    "checkpoints",
]


def init_db(db_path: Path = DB_PATH) -> None:
    """Create state.db, enable WAL mode, and ensure all core tables exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")

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
                run_id TEXT NOT NULL,
                phase_name TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT,
                details_json TEXT,
                FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
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
                payload_json TEXT,
                FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
            );

            CREATE TABLE IF NOT EXISTS pap_lock (
                run_id           TEXT PRIMARY KEY,
                locked_at        TIMESTAMP,
                locked_by        TEXT,
                pap_sha256       TEXT,
                forge_started_at TIMESTAMP
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
                metadata_json TEXT,
                FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id),
                FOREIGN KEY (pap_id) REFERENCES pap(pap_id)
            );

            CREATE TABLE IF NOT EXISTS agent_results (
                result_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                phase_name TEXT,
                agent_name TEXT NOT NULL,
                pap_id TEXT,
                status TEXT NOT NULL,
                score REAL,
                output_json TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id),
                FOREIGN KEY (pap_id) REFERENCES pap(pap_id)
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
                UNIQUE(run_id, phase_name, checkpoint_key),
                FOREIGN KEY (run_id) REFERENCES pipeline_runs(run_id)
            );
            """
        )

        conn.commit()


def get_created_table_names(db_path: Path = DB_PATH) -> list[str]:
    """Return created target table names in the canonical order."""
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
    for table_name in get_created_table_names():
        print(table_name)
