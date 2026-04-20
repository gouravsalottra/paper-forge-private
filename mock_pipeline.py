"""Dry-run pipeline execution for Paper Forge (no real API calls)."""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone

from aria.aria import ARIA, ForgeGateError

PHASE_ORDER = [
    "SCOUT",
    "MINER",
    "SIGMA_JOB1",
    "FORGE",
    "SIGMA_JOB2",
    "CODEC",
    "QUILL",
    "HAWK",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main() -> None:
    start = time.perf_counter()

    aria = ARIA("state.db")
    run_id = aria.start_run("PAPER.md")

    for phase_name in PHASE_ORDER:
        print(f"▶ Running [{phase_name}]...")
        time.sleep(0.3)

        if phase_name == "FORGE":
            try:
                aria.dispatch_forge(run_id)
                print("🚀 FORGE gate opened.")
            except ForgeGateError as exc:
                print(f"FORGE gate error: {exc}")
                elapsed = time.perf_counter() - start
                print(f"Total elapsed time: {elapsed:.2f} seconds")
                return

        aria.complete_phase(run_id, phase_name)

        if phase_name == "SIGMA_JOB1":
            with sqlite3.connect("state.db") as conn:
                conn.execute(
                    """
                    INSERT INTO pap_lock (
                        run_id,
                        locked_at,
                        locked_by,
                        pap_sha256,
                        forge_started_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (run_id, now_iso(), "SIGMA_JOB1", "mock-hash-001", None),
                )
                conn.commit()
            print("🔒 PAP locked.")

    with sqlite3.connect("state.db") as conn:
        rows = conn.execute(
            """
            SELECT phase_name, status
            FROM phases
            WHERE run_id = ?
            ORDER BY phase_id ASC
            """,
            (run_id,),
        ).fetchall()

    for phase_name, status in rows:
        print(f"{phase_name}: {status}")

    elapsed = time.perf_counter() - start
    print(f"Total elapsed time: {elapsed:.2f} seconds")


if __name__ == "__main__":
    main()
