from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path


class StructuredFormatter(logging.Formatter):
    """Emits JSON log lines for machine parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "agent": getattr(record, "agent", record.name.split(".")[1] if "." in record.name else "SYSTEM"),
            "run_id": getattr(record, "run_id", None),
            "phase": getattr(record, "phase", None),
            "event": record.getMessage(),
            "extra": {
                k: v
                for k, v in record.__dict__.items()
                if k not in logging.LogRecord.__dict__
                and k not in ("agent", "run_id", "phase", "message", "msg", "args")
            },
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)


def get_logger(agent_name: str, run_id: str | None = None) -> logging.Logger:
    logger = logging.getLogger(f"paperforge.{agent_name}.{run_id or 'no-run'}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)
        if run_id:
            log_dir = Path("runs") / run_id
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(log_dir / "pipeline.log")
            fh.setFormatter(StructuredFormatter())
            logger.addHandler(fh)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    return logger
