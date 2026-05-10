from __future__ import annotations

import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dashboard import cleanup_stale
from init_db import init_db


def test_cleanup_stale_marks_old_running_runs(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    init_db(db)
    now = datetime.now(timezone.utc)
    old = (now - timedelta(hours=72)).isoformat(timespec="seconds")
    recent = (now - timedelta(hours=1)).isoformat(timespec="seconds")

    with sqlite3.connect(db) as conn:
        for i in range(3):
            conn.execute(
                """
                INSERT INTO pipeline_runs (run_id, status, started_at)
                VALUES (?, 'running', ?)
                """,
                (f"old-{i}", old),
            )
        conn.execute(
            """
            INSERT INTO pipeline_runs (run_id, status, started_at)
            VALUES ('recent-1', 'running', ?)
            """,
            (recent,),
        )
        conn.commit()

    updated = cleanup_stale(str(db))
    assert updated == 3

    with sqlite3.connect(db) as conn:
        stale_count = conn.execute(
            "SELECT COUNT(*) FROM pipeline_runs WHERE status='stale'"
        ).fetchone()[0]
        recent_status = conn.execute(
            "SELECT status FROM pipeline_runs WHERE run_id='recent-1'"
        ).fetchone()[0]

    assert stale_count == 3
    assert recent_status == "running"
