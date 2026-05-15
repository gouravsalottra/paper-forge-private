from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


def test_write_artifact_uses_mock_blob_storage_not_local_filesystem(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.chdir(tmp_path)

    from storage import blob

    blob.reset_mock_storage()
    ref = blob.write_artifact("session-1", "00_runspec/runspec.json", {"ok": True})

    assert ref["backend"] == "mock"
    assert ref["blob_path"] == "sessions/session-1/00_runspec/runspec.json"
    assert not (tmp_path / "sessions" / "session-1" / "00_runspec" / "runspec.json").exists()
    assert blob.read_artifact("session-1", "00_runspec/runspec.json") == b'{"ok":true}'


def test_get_artifact_url_returns_one_hour_signed_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")

    from storage import blob

    blob.reset_mock_storage()
    blob.write_artifact("session-2", "01_integrity/truth_contract.json", b"truth")

    url = blob.get_artifact_url("session-2", "01_integrity/truth_contract.json")
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.path.endswith("/sessions/session-2/01_integrity/truth_contract.json")
    assert "se" in params
    expires = datetime.fromisoformat(params["se"][0])
    remaining = (expires - datetime.now(timezone.utc)).total_seconds()
    assert 3500 <= remaining <= 3700


def test_get_download_url_returns_user_facing_signed_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")

    from storage import blob

    blob.reset_mock_storage()
    blob_path = "sessions/session-2/11_paper/final.pdf"
    url = blob.get_download_url(blob_path, expiry_hours=24)
    assert url is not None

    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.path.endswith("/sessions/session-2/11_paper/final.pdf")
    assert "se" in params
    assert params["sig"] == ["mock"]


def test_write_artifact_fails_gracefully(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")

    from storage import blob

    def boom(*_args, **_kwargs):
        raise RuntimeError("provider exploded")

    monkeypatch.setattr(blob, "_upload_bytes", boom)

    with pytest.raises(blob.BlobStorageUnavailableError) as exc:
        blob.write_artifact("session-3", "02_literature/papers.json", "[]")

    assert exc.value.system_state == "blob_unavailable"
    assert exc.value.error_code == "BLOB_UNAVAILABLE"
    assert "provider exploded" not in str(exc.value)


def test_run_contract_artifacts_are_written_to_blob_in_test(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")

    from api import runs
    from storage import blob
    from tests.test_api_runs_truth_contract import _meta

    blob.reset_mock_storage()
    runs._write_contract_artifacts("run-blob", _meta())

    truth = blob.read_artifact("run-blob", "01_integrity/truth_contract.json")
    deviation = blob.read_artifact("run-blob", "01_integrity/deviation_register.json")
    runspec = blob.read_artifact("run-blob", "00_runspec/runspec.json")

    assert b"Writer is last and never invents numbers" in truth
    assert b"entries" in deviation
    assert b"research" in runspec
