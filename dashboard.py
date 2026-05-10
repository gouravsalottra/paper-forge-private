from __future__ import annotations

import argparse
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def cleanup_stale(db: str, hours: int = 48) -> int:
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat(timespec="seconds")
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with sqlite3.connect(db) as conn:
        rows = conn.execute(
            """
            SELECT run_id
            FROM pipeline_runs
            WHERE status='running'
              AND started_at IS NOT NULL
              AND started_at < ?
            """,
            (cutoff,),
        ).fetchall()
        for (run_id,) in rows:
            conn.execute(
                """
                UPDATE pipeline_runs
                SET status='stale', finished_at=?
                WHERE run_id=?
                """,
                (now, run_id),
            )
        conn.commit()
    return len(rows)


def _all_runs(db: str) -> str:
    lines = ["RUN ID | STATUS | STARTED | PHASES DONE | COST"]
    status_icon = {
        "running": "RUNNING",
        "done": "DONE",
        "failed": "FAILED",
        "stale": "STALE",
    }
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "pipeline_runs" not in tables:
            return "\n".join(lines + ["(no pipeline data yet)"])
        runs = conn.execute("SELECT run_id, status, started_at FROM pipeline_runs ORDER BY started_at DESC").fetchall()
        for run_id, status, started_at in runs:
            done = conn.execute(
                "SELECT COUNT(*) FROM phases WHERE run_id=? AND status='done'",
                (run_id,),
            ).fetchone()[0]
            total = conn.execute("SELECT COUNT(*) FROM phases WHERE run_id=?", (run_id,)).fetchone()[0]
            cost_row = None
            if "token_limits" in tables:
                cost_row = conn.execute("SELECT total_spent_usd FROM token_limits WHERE run_id=?", (run_id,)).fetchone()
            cost = float(cost_row[0]) if cost_row else 0.0
            pretty_status = status_icon.get(status, status)
            lines.append(f"{run_id} | {pretty_status} | {started_at} | {done}/{total} | ${cost:.2f}")
    return "\n".join(lines)


def _run_detail(db: str, run_id: str) -> str:
    lines = [f"Run: {run_id}"]
    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT status, started_at, COALESCE(completed_at, finished_at) FROM pipeline_runs WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row:
            lines.append(f"Status: {row[0]} | Started: {row[1]} | Finished: {row[2]}")
        phases = conn.execute(
            "SELECT phase_name, status FROM phases WHERE run_id=? ORDER BY id",
            (run_id,),
        ).fetchall()
        lines.append("\nPhase | Status")
        for p, s in phases:
            lines.append(f"{p} | {s}")
    return "\n".join(lines)


def _tail(run_id: str) -> None:
    path = Path("runs") / run_id / "pipeline.log"
    if not path.exists():
        print(f"No log file: {path}")
        return
    with path.open("r", encoding="utf-8", errors="ignore") as f:
        f.seek(0, 2)
        while True:
            line = f.readline()
            if not line:
                time.sleep(0.5)
                continue
            print(line.rstrip())


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper-Forge run dashboard")
    parser.add_argument("--db", default="pipeline.db")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--tail", default=None)
    parser.add_argument("--cleanup-stale", action="store_true")
    args = parser.parse_args()

    if args.cleanup_stale:
        count = cleanup_stale(args.db)
        print(f"Marked {count} runs as stale")
        return
    if args.tail:
        _tail(args.tail)
        return
    if args.run_id:
        print(_run_detail(args.db, args.run_id))
        return
    print(_all_runs(args.db))


if __name__ == "__main__":
    main()
