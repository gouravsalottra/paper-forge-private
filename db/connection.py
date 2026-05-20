from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any

try:  # pragma: no cover - dependency presence is environment-specific
    import psycopg2
    import psycopg2.extras
    import psycopg2.extensions
    import psycopg2.pool

    # PostgreSQL UUID columns (OID 2950/2951) return uuid.UUID objects by default.
    # The app was designed for SQLite which stores UUIDs as plain TEXT strings.
    # Register a type adapter so psycopg2 returns strings for UUID columns,
    # ensuring json.dumps() works without a custom encoder throughout the codebase.
    _uuid_as_str = psycopg2.extensions.new_type(
        (2950,), "UUID_AS_STR",
        lambda v, c: str(v) if v is not None else None,
    )
    _uuid_arr_as_str = psycopg2.extensions.new_array_type(
        (2951,), "UUID_ARR_AS_STR", _uuid_as_str,
    )
    psycopg2.extensions.register_type(_uuid_as_str)
    psycopg2.extensions.register_type(_uuid_arr_as_str)
except Exception:  # pragma: no cover
    psycopg2 = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# ── Persistent connection pool ────────────────────────────────────────────────
# Opening a new TCP+TLS connection to Azure Postgres on every request costs
# 6-8 seconds. The pool keeps 2-10 connections alive across requests so each
# request just borrows one (~1ms) instead of paying the handshake cost.
_pg_pool: Any = None


def _get_or_create_pool(url: str) -> Any:
    global _pg_pool
    if _pg_pool is not None:
        return _pg_pool
    if psycopg2 is None:
        raise DatabaseUnavailableError("PostgreSQL driver is unavailable.")
    try:
        extras = getattr(psycopg2, "extras", None)
        cursor_factory = getattr(extras, "RealDictCursor", None) if extras else None
        kwargs: dict[str, Any] = {"cursor_factory": cursor_factory} if cursor_factory else {}
        _pg_pool = psycopg2.pool.ThreadedConnectionPool(2, 10, url, **kwargs)
        logger.info("PostgreSQL connection pool created (min=2, max=10).")
        return _pg_pool
    except Exception as exc:
        logger.error("Failed to create PostgreSQL connection pool: %s", exc.__class__.__name__)
        raise DatabaseUnavailableError(
            "Database is unavailable. Please retry after the service reconnects."
        ) from exc


class _PooledConnection:
    """Thin wrapper that returns the connection to the pool on close()."""

    def __init__(self, pg_pool: Any, conn: Any) -> None:
        self._pool = pg_pool
        self._conn = conn
        try:
            setattr(self._conn, "is_postgresql", True)
        except Exception:
            pass

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def close(self) -> None:
        try:
            self._pool.putconn(self._conn)
        except Exception:
            pass

    def __enter__(self) -> "_PooledConnection":
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ─────────────────────────────────────────────────────────────────────────────


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


def get_db_connection(db_path: str | Path | None = None) -> Any:
    """Return a DB connection.

    Production must use PostgreSQL through DATABASE_URL. SQLite is allowed only
    for local development and tests. In Postgres mode, connections are drawn
    from a persistent ThreadedConnectionPool so we never pay the ~6-second
    TCP+TLS handshake cost on every request.
    """
    env = _environment()
    url = _database_url()

    if env == "production":
        if not _is_postgres_url(url):
            raise DatabaseUnavailableError("PostgreSQL DATABASE_URL is required in production.")
        pg_pool = _get_or_create_pool(url)
        try:
            raw = pg_pool.getconn()
            return _PooledConnection(pg_pool, raw)
        except DatabaseUnavailableError:
            raise
        except Exception as exc:
            logger.error("Failed to get connection from pool: %s", exc.__class__.__name__)
            raise DatabaseUnavailableError(
                "Database is unavailable. Please retry after the service reconnects."
            ) from exc

    if _is_postgres_url(url):
        pg_pool = _get_or_create_pool(url)
        try:
            raw = pg_pool.getconn()
            return _PooledConnection(pg_pool, raw)
        except DatabaseUnavailableError:
            raise
        except Exception as exc:
            logger.error("Failed to get connection from pool: %s", exc.__class__.__name__)
            raise DatabaseUnavailableError(
                "Database is unavailable. Please retry after the service reconnects."
            ) from exc

    return _sqlite_connection(db_path)
