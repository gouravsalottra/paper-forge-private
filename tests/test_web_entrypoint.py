from __future__ import annotations

from fastapi.testclient import TestClient

from main import app


def test_root_web_entrypoint_serves_frontend_and_api() -> None:
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "Thrivarc API"

    app_html = client.get("/app.html")
    assert app_html.status_code == 200
    assert "Thrivarc AI - Research Studio" in app_html.text

    validate = client.post("/guide/validate", json={"topic": "Explore sector ETF volatility from 2015 to 2024"})
    assert validate.status_code == 200
    assert "blueprint_summary" in validate.json()
