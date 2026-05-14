from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

try:  # pragma: no cover - dependency presence is environment-specific
    import psycopg2
    import psycopg2.extras
except Exception:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class DatabaseUnavailableError(RuntimeError):
    """Structured database failure surfaced as db_unavailable state."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
        self.system_state = "db_unavailable"
        self.error_code = "DB_UNAVAILABLE"
        self.available_actions = ["retry", "check_database_configuration"]

    def to_error(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": self.message,
            "system_state": self.system_state,
            "available_actions": self.available_actions,
        }


def _environment() -> str:
    return os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).strip().lower()


def _database_url() -> str | None:
    return os.getenv("DATABASE_URL")


def _is_postgres_url(value: str | None) -> bool:
    return bool(value and (value.startswith("postgresql://") or value.startswith("postgres://")))


def _sqlite_connection(db_path: str | Path | None = None) -> sqlite3.Connection:
    path = str(db_path or os.getenv("SQLITE_DB_PATH") or "pipeline.db")
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def get_db_connection(db_path: str | Path | None = None):
    """Return a DB connection.

    Production must use PostgreSQL through DATABASE_URL. SQLite is allowed only
    for local development and tests so the legacy test suite remains isolated.
    The DATABASE_URL value is never logged.
    """

    env = _environment()
    url = _database_url()

    if env == "production":
        if not _is_postgres_url(url):
            raise DatabaseUnavailableError("PostgreSQL DATABASE_URL is required in production.")
        if psycopg2 is None:
            raise DatabaseUnavailableError("PostgreSQL driver is unavailable.")
        try:
            extras = getattr(psycopg2, "extras", None)
            cursor_factory = getattr(extras, "RealDictCursor", None) if extras else None
            kwargs = {"cursor_factory": cursor_factory} if cursor_factory else {}
            conn = psycopg2.connect(url, **kwargs)
            try:
                setattr(conn, "is_postgresql", True)
            except Exception:
                pass
            return conn
        except Exception as exc:
            logger.error("PostgreSQL connection failed: %s", exc.__class__.__name__)
            raise DatabaseUnavailableError("Database is unavailable. Please retry after the service reconnects.") from exc

    if _is_postgres_url(url):
        if psycopg2 is None:
            raise DatabaseUnavailableError("PostgreSQL driver is unavailable.")
        try:
            extras = getattr(psycopg2, "extras", None)
            cursor_factory = getattr(extras, "RealDictCursor", None) if extras else None
            kwargs = {"cursor_factory": cursor_factory} if cursor_factory else {}
            conn = psycopg2.connect(url, **kwargs)
            try:
                setattr(conn, "is_postgresql", True)
            except Exception:
                pass
            return conn
        except Exception as exc:
            logger.error("PostgreSQL connection failed: %s", exc.__class__.__name__)
            raise DatabaseUnavailableError("Database is unavailable. Please retry after the service reconnects.") from exc

    return _sqlite_connection(db_path)
