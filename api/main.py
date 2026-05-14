from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import artifacts, data, guide, runs

app = FastAPI(title="Thrivarc Research Engine API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.thrivarc.studio"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(guide.router)
app.include_router(data.router)
app.include_router(runs.router)
app.include_router(artifacts.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
