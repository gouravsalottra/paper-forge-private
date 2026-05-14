from __future__ import annotations

from pathlib import Path

from api import data


def test_upload_preview_returns_schema_profile_and_datapassport(tmp_path: Path) -> None:
    source = tmp_path / "evidence.csv"
    source.write_text(
        "date,ticker,return,signal\n"
        "2024-01-02,SPY,0.01,0.2\n"
        "2024-01-03,SPY,-0.02,0.1\n",
        encoding="utf-8",
    )

    result = data.preview({"data_mode": "upload", "upload_path": str(source)})
    preview = result["preview"]

    assert preview["preview_status"] == "ready"
    assert preview["rows"] == 2
    assert preview["date_range"] == "2024-01-02 to 2024-01-03"
    assert preview["schema_profile"]["date_columns"] == ["date"]
    assert preview["schema_profile"]["identifier_columns"] == ["ticker"]
    assert "return" in preview["schema_profile"]["numeric_columns"]
    assert preview["data_passport"]["source_route"] == "upload"
    assert preview["data_passport"]["sha256"] == preview["sha256"]


def test_upload_preview_blocks_empty_or_unusable_file(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text("date,ticker,return\n", encoding="utf-8")

    result = data.preview({"data_mode": "upload", "upload_path": str(source)})
    preview = result["preview"]

    assert preview["preview_status"] == "blocked"
    assert preview["blocking_issues"]


def test_api_upload_writes_to_blob_not_local_filesystem(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    monkeypatch.chdir(tmp_path)
    from fastapi.testclient import TestClient
    from main import app
    from storage import blob

    blob.reset_mock_storage()
    response = TestClient(app).post(
        "/api/data/upload?run_id=data-session",
        files={"file": ("evidence.csv", b"date,ticker,return\n2024-01-02,SPY,0.01\n", "text/csv")},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["upload_path"] == "sessions/data-session/uploads/evidence.csv"
    assert not (tmp_path / "research_memory").exists()
    assert blob.read_artifact("data-session", "uploads/evidence.csv").startswith(b"date,ticker")


def test_blob_upload_preview_reads_blob_payload(monkeypatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from api import data
    from storage import blob

    blob.reset_mock_storage()
    blob.write_artifact("preview-session", "uploads/evidence.csv", b"date,ticker,return\n2024-01-02,SPY,0.01\n")
    result = data.preview({"data_mode": "upload", "upload_path": "sessions/preview-session/uploads/evidence.csv"})
    assert result["preview"]["rows"] == 1
    assert result["preview"]["schema_profile"]["date_columns"] == ["date"]
