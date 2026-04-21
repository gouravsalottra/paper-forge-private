import sqlite3
from datetime import datetime, timezone

from agents.aria.aria import ARIAPipeline


def main() -> None:
    run_id = "pf-quick-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    aria = ARIAPipeline(db_path="state.db", run_id=run_id, paper_md_path="PAPER.md")
    del aria
    with sqlite3.connect("state.db") as conn:
        rows = conn.execute(
            "SELECT phase_name FROM phases WHERE run_id=? AND status='pending' ORDER BY phase_id ASC",
            (run_id,),
        ).fetchall()
    print(rows[0][0] if rows else "NONE")


if __name__ == "__main__":
    main()
