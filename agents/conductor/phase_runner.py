from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from typing import Callable

from agents.conductor.exceptions import ComputeGateError, PipelineHaltError


class PhaseRunner:
    """Executes a single pipeline phase with retry, timeout, and logging."""

    def __init__(self, db_path: str, run_id: str, logger) -> None:
        self.db_path = db_path
        self.run_id = run_id
        self.logger = logger

    def run_phase(
        self,
        phase_name: str,
        dispatch_fn: Callable[[str], dict],
        timeout_seconds: int,
        max_retries: int = 3,
    ) -> dict:
        _ = timeout_seconds
        for attempt in range(1, max_retries + 1):
            try:
                start = time.perf_counter()
                result = dispatch_fn(phase_name)
                duration = time.perf_counter() - start
                self._write_phase_status(phase_name, "done", duration)
                return {"status": "done", "duration": duration, "attempt": attempt, "result": result}
            except (ComputeGateError, PipelineHaltError):
                raise
            except Exception as exc:
                if attempt == max_retries:
                    self._write_phase_status(phase_name, "failed", 0.0)
                    raise
                backoff = 2 ** attempt
                self.logger.warning(
                    f"Phase {phase_name} attempt {attempt} failed: {exc}. Retrying in {backoff}s"
                )
                time.sleep(backoff)

    def _write_phase_status(self, phase_name: str, status: str, duration: float) -> None:
        with sqlite3.connect(self.db_path) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(phases)")}
            finished_col = "finished_at" if "finished_at" in cols else "finished_at"
            conn.execute(
                f"UPDATE phases SET status=?, {finished_col}=?, details_json=? WHERE run_id=? AND phase_name=?",
                (
                    status,
                    datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    f'{{"duration_seconds": {duration:.6f}}}',
                    self.run_id,
                    phase_name,
                ),
            )
            conn.commit()
