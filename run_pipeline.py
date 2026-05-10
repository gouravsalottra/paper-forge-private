from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from datetime import datetime, timezone

from agents.aria.aria import ConductorPipeline
from agents.aria.exceptions import PAPTamperError


def main() -> None:
    parser = argparse.ArgumentParser(description="PaperForge pipeline runner")
    parser.add_argument("--resume", type=str, default=None, help="Resume an existing run by run_id")
    parser.add_argument(
        "--from",
        dest="from_phase",
        type=str,
        default=None,
        help="Resume from a specific phase: LITERATURE|DATAPULL|PREREGISTER|COMPUTE|STATSRUN|CODEAUDIT|WRITER|REVIEWER",
    )
    args = parser.parse_args()

    source = os.environ.get("PAPER_COMPUTE_DATAPULL_SOURCE", "yfinance")
    os.environ.setdefault("PAPER_COMPUTE_DATAPULL_SOURCE", source)
    os.environ.setdefault("PAPER_COMPUTE_COMPUTE_EPISODES", "500000")

    if args.resume:
        run_id = args.resume
        print(f"Resuming run: {run_id}")
        if args.from_phase:
            print(f"Resuming from phase: {args.from_phase}")
            _reset_from_phase(run_id, args.from_phase)
    else:
        run_id = "pf-live-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        print(f"Starting new run: {run_id}")

    pipeline = ConductorPipeline(db_path="pipeline.db", run_id=run_id, paper_md_path="PAPER.md")
    print(f"RUN_ID: {run_id}")
    pipeline.run()
    print(f"DONE: {run_id}")


def _reset_from_phase(run_id: str, from_phase: str) -> None:
    """Reset a phase and all downstream phases to pending for resume."""
    phase_order = ["LITERATURE", "DATAPULL", "PREREGISTER", "COMPUTE", "STATSRUN", "CODEAUDIT", "REVIEWER", "WRITER"]
    if from_phase not in phase_order:
        print(f"Unknown phase: {from_phase}")
        print(f"Valid phases: {phase_order}")
        sys.exit(1)

    start_idx = phase_order.index(from_phase)
    phases_to_reset = phase_order[start_idx:]

    with sqlite3.connect("pipeline.db") as conn:
        paper_path = os.environ.get("PAPER_COMPUTE_PAPER_PATH", "PAPER.md")
        paper_bytes = open(paper_path, "rb").read()
        current_hash = hashlib.sha256(paper_bytes).hexdigest()
        lock_row = conn.execute(
            "SELECT pap_sha256 FROM hypothesis_lock WHERE run_id=? LIMIT 1",
            (run_id,),
        ).fetchone()
        stored_hash = (lock_row[0] if lock_row else None) or ""
        override = os.getenv("PAPERCOMPUTE_OVERRIDE_PAP_TAMPER", "0") == "1"
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        if stored_hash and stored_hash != current_hash:
            msg = (
                "PAPER.md has been modified since PAP was locked.\n"
                f"Locked hash: {stored_hash}\n"
                f"Current hash: {current_hash}\n"
                "Resume is blocked to preserve pre-registration integrity.\n"
                "To start fresh: python run_pipeline.py (new run)\n"
                "To acknowledge and override (expert use only): set env var\n"
                "PAPERCOMPUTE_OVERRIDE_PAP_TAMPER=1"
            )
            if not override:
                raise PAPTamperError(msg)

            conn.execute(
                """
                INSERT INTO server_health_log
                (run_id, server_name, status, checked_at, detail, latency_ms, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    "pap_integrity",
                    "CRITICAL",
                    now,
                    (
                        "PAPER.md has been modified since PAP was locked. "
                        f"Locked hash: {stored_hash}; Current hash: {current_hash}; "
                        f"Override accepted at {now}."
                    ),
                    0.0,
                    now,
                ),
            )
            print(
                "CRITICAL: PAPERCOMPUTE_OVERRIDE_PAP_TAMPER=1 set; "
                f"proceeding despite tamper (locked={stored_hash}, current={current_hash})."
            )

        phase_cols = {row[1] for row in conn.execute("PRAGMA table_info(phases)")}
        reset_parts = ["status='pending'"]
        if "started_at" in phase_cols:
            reset_parts.append("started_at=NULL")
        if "completed_at" in phase_cols:
            reset_parts.append("completed_at=NULL")
        if "finished_at" in phase_cols:
            reset_parts.append("finished_at=NULL")
        if "details_json" in phase_cols:
            reset_parts.append("details_json=NULL")
        reset_sql = ", ".join(reset_parts)

        for phase in phases_to_reset:
            conn.execute(
                f"UPDATE phases SET {reset_sql} WHERE run_id=? AND phase_name=?",
                (run_id, phase),
            )

        if from_phase in ("COMPUTE", "STATSRUN", "CODEAUDIT", "WRITER", "REVIEWER"):
            conn.execute("UPDATE pipeline_runs SET status='running' WHERE run_id=?", (run_id,))
        conn.commit()
    print(f"Reset phases {phases_to_reset} to pending.")
    print("PAP lock preserved (hypothesis commitment unchanged).")


if __name__ == "__main__":
    main()
