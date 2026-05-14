from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "integrity.db"))
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from api import sessions
    from storage import blob

    blob.reset_mock_storage()
    session_id = "integrity-session"
    with sessions._with_conn() as conn:
        sessions._execute(
            conn,
            "INSERT INTO sessions (id, topic, domain, research_type, status, created_at, updated_at, credits_spent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, "Integrity artifact test", "finance_economics", "confirmatory", "blueprint_locked", sessions._now(), sessions._now(), 0),
        )
        sessions._execute(
            conn,
            "INSERT INTO blueprints (id, session_id, content, status, locked_at, blueprint_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("bp-integrity", session_id, '{"hypothesis":"ETF flows predict returns"}', "locked", sessions._now(), "abc123", sessions._now()),
        )
        sessions._execute(
            conn,
            "INSERT INTO " + "pap" + "_locks (id, session_id, blueprint_hash, locked_at, hypothesis, primary_test, significance_threshold, effect_size_minimum) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            ("cert-1", session_id, "abc123", sessions._now(), "ETF flows predict returns", "Newey-West regression", 0.05, 0.001),
        )
        sessions._execute(
            conn,
            "INSERT INTO deviation_register (id, session_id, field_changed, changed_from, changed_to, reason, timestamp, agent_triggered_by, requires_researcher_approval) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("dev-2", session_id, "benchmark", "SPY", "XLF", "Sector benchmark required", "2026-05-14T02:00:00+00:00", "Reviewer Agent", 1),
        )
        sessions._execute(
            conn,
            "INSERT INTO deviation_register (id, session_id, field_changed, changed_from, changed_to, reason, timestamp, agent_triggered_by, requires_researcher_approval) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ("dev-1", session_id, "window", "2015", "2010", "Coverage repair", "2026-05-14T01:00:00+00:00", "Data Agent", 0),
        )
        conn.commit()
    return session_id


def test_data_passport_contains_required_fields_and_matching_hash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed(tmp_path, monkeypatch)
    from integrity.data_passport import generate_data_passport
    from storage import blob

    data = b"date,ticker,return\n2020-01-01,SPY,0.01\n"
    refs = generate_data_passport(session_id, data, {"sources": ["upload"], "frequency": "daily", "universe": ["SPY"], "row_count_after_exclusions": 1})

    doc = json.loads(blob.read_artifact(session_id, "03_data/data_passport.json"))
    assert doc["plain_english_summary"].startswith("This DataPassport certifies")
    assert doc["hashes"]["raw_data_sha256"] == hashlib.sha256(data).hexdigest()
    assert doc["data_identity"]["frequency"] == "daily"
    assert blob.read_artifact(session_id, "03_data/data_passport.pdf").startswith(b"%PDF")
    assert refs["json"]["blob_path"].endswith("data_passport.json")


def test_preregistration_certificate_contains_lock_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed(tmp_path, monkeypatch)
    from integrity.preregistration_certificate import generate_preregistration_certificate
    from storage import blob

    generate_preregistration_certificate(session_id)
    doc = json.loads(blob.read_artifact(session_id, "05_preregistration/" + "pap" + "_lock_certificate.json"))

    assert doc["plain_english_summary"].startswith("This certificate confirms")
    assert doc["lock_record"]["blueprint_hash"] == "abc123"
    assert doc["locked_claims"]["primary_test"] == "Newey-West regression"
    assert doc["locked_claims"]["significance_threshold"] == 0.05
    assert blob.read_artifact(session_id, "05_preregistration/" + "pap" + "_lock_certificate.pdf").startswith(b"%PDF")


def test_deviation_register_pdf_lists_chronologically(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed(tmp_path, monkeypatch)
    from integrity.deviation_register import generate_deviation_register
    from storage import blob

    generate_deviation_register(session_id)
    doc = json.loads(blob.read_artifact(session_id, "01_integrity/deviation_register.json"))

    assert [entry["field_changed"] for entry in doc["entries"]] == ["window", "benchmark"]
    assert doc["footer"]["total_deviations"] == 2
    assert blob.read_artifact(session_id, "01_integrity/deviation_register.pdf").startswith(b"%PDF")


def test_integrity_artifacts_returned_by_session_artifacts_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed(tmp_path, monkeypatch)
    from integrity.data_passport import generate_data_passport
    from integrity.deviation_register import generate_deviation_register
    from integrity.preregistration_certificate import generate_preregistration_certificate
    from main import app

    generate_data_passport(session_id, b"x,y\n1,2\n", {"sources": ["upload"]})
    generate_preregistration_certificate(session_id)
    generate_deviation_register(session_id)

    response = TestClient(app).get(f"/api/sessions/{session_id}/artifacts")
    assert response.status_code == 200
    paths = {item["path"] for item in response.json()["artifacts"]}
    assert any(path.endswith("03_data/data_passport.pdf") for path in paths)
    assert any(path.endswith("01_integrity/deviation_register.pdf") for path in paths)
    assert any(path.endswith("05_preregistration/" + "pap" + "_lock_certificate.pdf") for path in paths)
