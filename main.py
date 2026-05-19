from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from api import artifacts, data, guide, runs, sessions
from db.connection import DatabaseUnavailableError, get_db_connection

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
MIGRATION_SQL = ROOT / "db" / "migrations" / "001_initial_schema.sql"


def _run_migrations() -> None:
    """Apply 001_initial_schema.sql to PostgreSQL on startup.

    Safe to call on every boot — every statement uses IF NOT EXISTS.
    Skipped silently when DATABASE_URL is not set (local SQLite dev).
    """
    try:
        conn = get_db_connection()
    except DatabaseUnavailableError as exc:
        logger.warning("DB unavailable at startup — skipping migration: %s", exc)
        return

    # Only run PostgreSQL migrations. SQLite is handled by init_db.py locally.
    is_pg = getattr(conn, "is_postgresql", False)
    if not is_pg:
        try:
            conn.close()
        except Exception:
            pass
        return

    sql = MIGRATION_SQL.read_text(encoding="utf-8")
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(sql)
        logger.info("DB migration applied: %s", MIGRATION_SQL.name)
    except Exception as exc:
        logger.error("Migration failed — %s: %s", type(exc).__name__, exc)
    finally:
        try:
            conn.close()
        except Exception:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    _run_migrations()
    yield


app = FastAPI(title="Thrivarc API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.thrivarc.studio",
        "https://brave-flower-065fba60f.7.azurestaticapps.net",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(guide.router)
app.include_router(data.router)
app.include_router(runs.router)
app.include_router(artifacts.router)
app.include_router(sessions.router)


def _db_connected() -> bool:
    try:
        with get_db_connection():
            return True
    except DatabaseUnavailableError:
        return False


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "Thrivarc API",
        "version": "1.0.0",
        "db_connected": _db_connected(),
    }


@app.get("/ready")
def ready() -> dict[str, object]:
    return health()


@app.get("/")
def web_root() -> RedirectResponse:
    return RedirectResponse(url="/index.html")


@app.get("/index.html")
def web_index() -> FileResponse:
    return FileResponse(FRONTEND / "index.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})


@app.get("/app")
@app.get("/app.html")
def web_app() -> FileResponse:
    return FileResponse(FRONTEND / "app.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})
