from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from api import artifacts, data, guide, runs, sessions
from db.connection import DatabaseUnavailableError, get_db_connection

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"

app = FastAPI(title="Thrivarc API", version="1.0.0")

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
    return FileResponse(FRONTEND / "index.html")


@app.get("/app")
@app.get("/app.html")
def web_app() -> FileResponse:
    return FileResponse(FRONTEND / "app.html")
