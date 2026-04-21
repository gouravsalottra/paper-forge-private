from __future__ import annotations

from datetime import datetime, timezone
import os

from agents.aria.aria import ARIAPipeline


def main() -> None:
    run_id = "pf-live-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    os.environ.setdefault("PAPER_FORGE_MINER_SOURCE", "yfinance")
    pipeline = ARIAPipeline(db_path="state.db", run_id=run_id, paper_md_path="PAPER.md")
    print("RUN_ID", run_id)
    pipeline.run()
    print("DONE", run_id)


if __name__ == "__main__":
    main()

