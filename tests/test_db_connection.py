from __future__ import annotations

import logging
import sqlite3
from types import SimpleNamespace
from pathlib import Path

import pytest


def test_get_db_connection_uses_database_url_for_postgres(monkeypatch: pytest.MonkeyPatch) -> None:
    from db import connection

    calls: list[str] = []

    class _FakeConnection:
        is_postgresql = True

    def fake_connect(url: str, **_kwargs):
        calls.append(url)
        return _FakeConnection()

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:secret@example.com:5432/thrivarc")
    monkeypatch.setattr(connection, "psycopg2", SimpleNamespace(connect=fake_connect))

    conn = connection.get_db_connection()

    assert conn.is_postgresql is True
    assert calls == ["postgresql://user:secret@example.com:5432/thrivarc"]
    assert not isinstance(conn, sqlite3.Connection)


def test_production_refuses_non_postgres_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from db.connection import DatabaseUnavailableError, get_db_connection

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///state.db")

    with pytest.raises(DatabaseUnavailableError) as exc:
        get_db_connection()

    assert exc.value.system_state == "db_unavailable"
    assert "PostgreSQL DATABASE_URL is required" in exc.value.message


def test_database_url_is_never_logged(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    from db import connection

    def fake_connect(_url: str, **_kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:super-secret@example.com:5432/thrivarc")
    monkeypatch.setattr(connection, "psycopg2", SimpleNamespace(connect=fake_connect))

    caplog.set_level(logging.ERROR)
    with pytest.raises(connection.DatabaseUnavailableError):
        connection.get_db_connection()

    assert "super-secret" not in caplog.text
    assert "postgresql://user" not in caplog.text


def test_test_environment_allows_sqlite_for_isolation(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from db.connection import get_db_connection

    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with get_db_connection(tmp_path / "isolated.db") as conn:
        conn.execute("CREATE TABLE demo (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO demo (id) VALUES (?)", ("ok",))
        row = conn.execute("SELECT id FROM demo").fetchone()

    assert row[0] == "ok"


def test_initial_postgres_migration_defines_required_tables() -> None:
    sql = Path("db/migrations/001_initial_schema.sql").read_text(encoding="utf-8")
    for table in [
        "sessions",
        "blueprints",
        "phases",
        "papers",
        "pap" + "_locks",
        "deviation_register",
        "reviewer_scores",
        "repair_log",
    ]:
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql


def test_runtime_code_uses_db_connection_wrapper_instead_of_direct_sqlite_connect() -> None:
    ignored = {"tests", "examples", "db"}
    allowed_files = {Path("init_db.py")}
    offenders: list[str] = []
    for path in Path(".").rglob("*.py"):
        if any(part in {".venv", "venv", "env", "node_modules", "__pycache__", ".git"} for part in path.parts):
            continue
        if any(part in ignored for part in path.parts) or path in allowed_files:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "sqlite3" + ".connect(" in text:
            offenders.append(str(path))

    assert offenders == []
