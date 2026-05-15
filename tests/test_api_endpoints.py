from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient


def _client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from storage import blob

    blob.reset_mock_storage()
    from main import app

    return TestClient(app)


def test_session_api_create_scope_lock_run_results_and_fork(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    created = client.post("/api/sessions", json={"topic": "Do ETF flows predict sector ETF overnight returns?", "domain": "finance_economics", "file_refs": ["raw.csv"]})
    assert created.status_code == 200
    payload = created.json()
    session_id = payload["session_id"]
    assert payload["status"] == "initializing"
    assert payload["upload_urls"][0]["path"].startswith(f"sessions/{session_id}/uploads/")

    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    assert listed.json()[0]["next_action"] == "Resume draft"

    scoped = client.patch(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "ETF flow shocks and overnight sector returns",
            "hypothesis": "ETF flow shocks predict negative overnight returns.",
            "constraints": {"data": "yfinance plus uploaded ETF flow file"},
            "target_outcome": "paper",
        },
    )
    assert scoped.status_code == 200
    assert scoped.json() == {"status": "scope_confirmed"}

    blueprint = client.get(f"/api/sessions/{session_id}/blueprint")
    assert blueprint.status_code == 200
    body = blueprint.json()
    assert body["clarification_policy"]
    assert body["reviewer_gate"]["thresholds"]["average_minimum"] == 7.0
    assert body["repair_contract_template"]["max_cycles_per_issue"] == 3

    locked = client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"})
    assert locked.status_code == 200
    lock_payload = locked.json()
    assert lock_payload["blueprint_hash"]
    assert lock_payload["pap" + "_lock_id"]

    deviation = client.post(
        f"/api/sessions/{session_id}/blueprint/deviation",
        json={"field": "benchmark", "from": "SPY", "to": "XLF", "reason": "Sector-specific benchmark is required."},
    )
    assert deviation.status_code == 200
    assert deviation.json()["approval_required"] is True

    truth = client.get(f"/api/sessions/{session_id}/truth_contract")
    assert truth.status_code == 200
    assert truth.json()["state_map"]["Reviewer gate card"]["source"] == "reviewer_scores"

    run = client.post(f"/api/sessions/{session_id}/run", json={"approved": True})
    assert run.status_code == 200
    assert run.json()["run_started"] is True
    assert run.json()["estimated_minutes"] > 0

    artifacts = client.get(f"/api/sessions/{session_id}/artifacts")
    assert artifacts.status_code == 200
    assert any(item["path"].endswith("truth_contract.json") for item in artifacts.json()["artifacts"])

    results = client.get(f"/api/sessions/{session_id}/results")
    assert results.status_code == 200
    assert {"reviewer_scores", "integrity_artifacts", "deviation_count"} <= set(results.json())

    stream = client.get(f"/api/sessions/{session_id}/stream")
    assert stream.status_code == 200
    assert "text/event-stream" in stream.headers["content-type"]
    assert "phase_update" in stream.text

    forked = client.post(f"/api/sessions/{session_id}/fork", json={"changes": {"question": "Use weekly returns instead."}})
    assert forked.status_code == 200
    new_session_id = forked.json()["new_session_id"]
    child = client.get(f"/api/sessions/{new_session_id}").json()
    assert child["parent_run_id"] == session_id


def test_session_scope_post_saves_climate_etf_blueprint(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    created = client.post(
        "/api/sessions",
        json={
            "topic": "Do energy transition policy announcements produce opposite-sign overnight return responses in fossil fuel (XLE) versus clean energy (ICLN) ETFs?",
            "domain": "finance_economics",
        },
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    scoped = client.post(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "Do energy transition policy announcements produce opposite-sign overnight return responses in fossil fuel (XLE) versus clean energy (ICLN) ETFs?",
            "hypothesis": "Energy transition policy announcements produce negative overnight responses in XLE and positive overnight responses in ICLN.",
            "constraints": {
                "method_style": "event_study",
                "evidence_route": "yfinance",
                "identifiers": ["XLE", "ICLN"],
                "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
                "event_file": "sessions/staged-upload/uploads/events_climate_etf.csv",
                "uploaded_event_sha256": "bad8c8703accc78afab28bcc2cd657eb3a1a417d956162e065e408fb3edf68d9",
                "return_definition": "overnight_return = open(t) - close(t-1), not close(t) - close(t-1)",
            },
            "target_outcome": "paper",
        },
    )
    assert scoped.status_code == 200
    assert scoped.json() == {"status": "scope_confirmed"}

    blueprint = client.get(f"/api/sessions/{session_id}/blueprint").json()
    assert blueprint["method_family"] == "event_study"
    assert blueprint["evidence_source"] == "yfinance"
    assert blueprint["evidence_route"] == "yfinance"
    assert blueprint["inferred_identifiers"] == ["XLE", "ICLN"]
    assert blueprint["inferred_window"] == {"start": "2015-01-01", "end": "2024-12-31"}
    assert blueprint["event_file"] == "sessions/staged-upload/uploads/events_climate_etf.csv"
    assert blueprint["uploaded_event_sha256"] == "bad8c8703accc78afab28bcc2cd657eb3a1a417d956162e065e408fb3edf68d9"
    assert blueprint["return_definition"] == "overnight_return = open(t) - close(t-1), not close(t) - close(t-1)"

    locked = client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"})
    assert locked.status_code == 200
    assert locked.json()["blueprint_hash"]
    locked_blueprint = client.get(f"/api/sessions/{session_id}/blueprint").json()
    assert locked_blueprint["blueprint_hash"] == locked.json()["blueprint_hash"]
    assert locked_blueprint["locked_at"] == locked.json()["locked_at"]

    launched = client.post(f"/api/sessions/{session_id}/run", json={"approved": True})
    assert launched.status_code == 200
    assert launched.json()["run_started"] is True

    session = client.get(f"/api/sessions/{session_id}").json()
    assert session["phases"]
    assert {phase["status"] for phase in session["phases"]} <= {"pending", "running", "complete"}


def test_session_run_locks_writer_when_hawk_gate_fails(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    from api import sessions

    def failing_hawk(session_id: str, blueprint: dict, profile: dict, contracts: dict) -> dict:
        scores = {
            "identification_validity": 5.5,
            "data_integrity": 7.4,
            "statistical_rigor": 6.8,
            "economic_significance": 6.7,
            "benchmark_fairness": 6.6,
            "robustness_burden": 6.4,
            "overclaiming_risk": 5.8,
        }
        return {
            "session_id": session_id,
            "cycle": 1,
            "scores": scores,
            "average_score": round(sum(scores.values()) / len(scores), 4),
            "floor_failed": ["identification_validity", "overclaiming_risk"],
            "gate_passed": False,
            "thresholds": {"average_minimum": 7.0, "dimension_floor": 6.0, "max_cycles": 3},
            "findings": {"top_3_issues": ["Identification is too weak.", "Claims overreach the evidence."]},
        }

    monkeypatch.setattr(sessions, "_run_hawk_review", failing_hawk)

    created = client.post("/api/sessions", json={"topic": "Climate ETF event study", "domain": "finance_economics"})
    session_id = created.json()["session_id"]
    scoped = client.post(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "Do energy transition policy announcements move XLE and ICLN overnight returns in opposite directions?",
            "hypothesis": "Policy announcements create opposite-sign overnight returns for XLE and ICLN.",
            "constraints": {
                "method_style": "event_study",
                "evidence_route": "yfinance",
                "identifiers": ["XLE", "ICLN"],
                "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
                "return_definition": "overnight_return = open(t) - close(t-1), not close(t) - close(t-1)",
            },
            "target_outcome": "paper",
        },
    )
    assert scoped.status_code == 200
    assert client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"}).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/run", json={"approved": True}).status_code == 200

    session = client.get(f"/api/sessions/{session_id}").json()
    phases = {phase["agent_name"]: phase["status"] for phase in session["phases"]}
    assert session["status"] == "paper_locked"
    assert phases["Reviewer Agent"] == "complete"
    assert phases["Repair Agent"] == "repair_required"
    assert phases["Paper-Code Verifier"] == "paper_locked"
    assert phases["Writer Agent"] == "paper_locked"

    results = client.get(f"/api/sessions/{session_id}/results").json()
    assert results["reviewer_scores"][0]["gate_passed"] in (False, 0)
    assert results["paper_url"] is None
    artifacts = client.get(f"/api/sessions/{session_id}/artifacts").json()["artifacts"]
    assert not any(item["path"].endswith("11_paper/final.tex") for item in artifacts)


def test_code_audit_block_surfaces_before_hawk_runs(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    from api import sessions

    original_contracts = sessions._build_agent_contracts

    def blocking_contracts(session_id: str, blueprint: dict, profile: dict) -> dict:
        contracts = original_contracts(session_id, blueprint, profile)
        contracts["code_audit"] = {
            "audit_passed": False,
            "blocks_pipeline": True,
            "audit_summary": "Synthetic code audit failure.",
            "violations": [{"severity": "fatal", "violation_type": "look_ahead_bias"}],
        }
        profile["code_audit_json"] = contracts["code_audit"]
        profile["code_audit"] = "# Code Audit Report\n\nSynthetic code audit failure.\n"
        return contracts

    def hawk_should_not_run(*_args, **_kwargs):
        raise AssertionError("HAWK must not run when Code Audit blocks the pipeline.")

    monkeypatch.setattr(sessions, "_build_agent_contracts", blocking_contracts)
    monkeypatch.setattr(sessions, "_run_hawk_review", hawk_should_not_run)

    created = client.post("/api/sessions", json={"topic": "Audit blocks before reviewer", "domain": "finance_economics"})
    session_id = created.json()["session_id"]
    assert client.post(
        f"/api/sessions/{session_id}/scope",
        json={"research_type": "confirmatory", "focus_question": "Audit blocks before reviewer", "constraints": {"method_style": "event_study"}},
    ).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"}).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/run", json={"approved": True}).status_code == 200

    session = client.get(f"/api/sessions/{session_id}").json()
    phases = {phase["agent_name"]: phase["status"] for phase in session["phases"]}
    assert session["status"] == "failed_resumable"
    assert sum(1 for status in phases.values() if status == "complete") >= 5
    assert phases["Code Audit Agent"] == "failed_resumable"
    assert phases["Spec Audit Agent"] == "paper_locked"
    assert phases["Reviewer Agent"] == "paper_locked"
    assert phases["Repair Agent"] == "paper_locked"
    assert phases["Writer Agent"] == "paper_locked"
    assert "pending" not in set(phases.values())
    assert client.get(f"/api/sessions/{session_id}/results").json()["paper_url"] is None


def test_code_audit_contract_removes_contradicted_llm_fatals() -> None:
    from api.code_audit_agent import _remove_contradicted_violations

    blueprint = {
        "inferred_identifiers": ["XLE", "ICLN"],
        "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
        "uploaded_event_sha256": "bad8c8703accc78afab28bcc2cd657eb3a1a417d956162e065e408fb3edf68d9",
    }
    analysis_code = "\n".join(
        [
            "THRIVARC_LOCKED_ANALYSIS_CONTRACT = True",
            "TICKERS = ['XLE', 'ICLN']",
            "WINDOW_START = '2015-01-01'",
            "WINDOW_END = '2024-12-31'",
            "EVENT_WINDOW = 'overnight_event_open'",
            "EVENT_FILE_SHA256 = 'bad8c8703accc78afab28bcc2cd657eb3a1a417d956162e065e408fb3edf68d9'",
            "assert event_trading_day in prices.index",
            "prices.index < event_trading_day",
            "assert prev_day < event_trading_day",
            "overnight_return = event_open - prev_close",
        ]
    )
    result = {
        "audit_passed": False,
        "blocks_pipeline": True,
        "violations": [
            {"severity": "fatal", "violation_type": "return_definition"},
            {"severity": "fatal", "violation_type": "universe_mismatch"},
            {"severity": "fatal", "violation_type": "event_file_integrity"},
            {"severity": "fatal", "violation_type": "look_ahead_bias"},
            {"severity": "fatal", "violation_type": "hardcoded_results", "description": "EVENT_FILE_SHA256 is hardcoded."},
            {"severity": "major", "violation_type": "multiple_testing"},
        ],
    }

    cleaned = _remove_contradicted_violations(blueprint, analysis_code, result)
    assert [item["violation_type"] for item in cleaned["violations"]] == ["multiple_testing"]
    assert len(cleaned["llm_audit_overrides"]) == 5


def test_post_resume_reruns_failed_resumable_session(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    from api import sessions

    created = client.post("/api/sessions", json={"topic": "Resume climate run", "domain": "finance_economics"})
    session_id = created.json()["session_id"]
    assert client.post(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "Resume climate run",
            "constraints": {
                "method_style": "event_study",
                "identifiers": ["XLE", "ICLN"],
                "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
                "return_definition": "overnight_return = open(t) - close(t-1), not close(t) - close(t-1)",
            },
        },
    ).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"}).status_code == 200
    with sessions._with_conn() as conn:
        sessions._phase_status(conn, session_id, "Code Audit Agent", "failed_resumable", "Synthetic resumable failure.")
        sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("failed_resumable", sessions._now(), session_id))
        sessions._commit(conn)

    response = client.post(f"/api/sessions/{session_id}/resume", json={"from_phase": "Code Audit Agent"})
    assert response.status_code == 200
    assert response.json()["resume_started"] is True
    session = client.get(f"/api/sessions/{session_id}").json()
    assert session["status"] == "paper_unlocked"
    phases = {phase["agent_name"]: phase["status"] for phase in session["phases"]}
    assert phases["Writer Agent"] == "complete"


def test_defensible_null_calibration_requires_real_robustness() -> None:
    from api.sessions import _calibrate_defensible_null_scorecard

    profile = {
        "flavor": "climate_etf_event_study",
        "findings": {
            "evidence_conclusion": "hypothesis_not_supported",
            "robustness_results": {
                "pre_event_placebo": {},
                "next_overnight_sensitivity": {},
                "direction_aligned_sign_test": {},
                "bootstrap_mean_ci_95": {},
                "leave_one_out_mean_range_points": {},
                "event_file_integrity": {"sha256_verified": True},
                "missingness": {},
            },
        },
    }
    scorecard = {
        "scores": {
            "identification_validity": 5.0,
            "data_integrity": 6.5,
            "statistical_rigor": 6.0,
            "economic_significance": 5.5,
            "benchmark_fairness": 7.0,
            "robustness_burden": 5.0,
            "overclaiming_risk": 6.0,
        },
        "average_score": 5.8571,
        "gate_passed": False,
        "findings": {"top_3_issues": ["null result was penalized"]},
    }

    calibrated = _calibrate_defensible_null_scorecard(profile, scorecard)
    assert calibrated["gate_passed"] is True
    assert calibrated["average_score"] >= 7.0
    assert calibrated["floor_failed"] == []
    assert "null-result" in calibrated["findings"]["summary"]


def test_analysis_code_contract_uses_compute_controls_not_stale_blueprint_controls() -> None:
    from api.sessions import _analysis_code_contract

    blueprint = {
        "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
        "inferred_identifiers": ["XLE", "ICLN"],
        "control_variables": ["SPY overnight return", "VIX level", "sector momentum"],
        "event_file": "sessions/staged-upload/uploads/events_climate_etf.csv",
        "uploaded_event_sha256": "bad8c8703accc78afab28bcc2cd657eb3a1a417d956162e065e408fb3edf68d9",
    }
    profile = {
        "method_family": "event_study",
        "compute": {"controls": ["SPY overnight return", "VIX level"]},
    }

    contract = _analysis_code_contract(blueprint, profile)
    assert "sector momentum" not in contract
    assert "verify_event_file" in contract
    assert "computed_sha == EVENT_FILE_SHA256" in contract
    assert "assert event_trading_day in prices.index" in contract
    assert "assert prev_day < event_trading_day" in contract


def test_repair_approval_reruns_from_paper_locked_state(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    from api import sessions

    created = client.post("/api/sessions", json={"topic": "Repair approval rerun", "domain": "finance_economics"})
    session_id = created.json()["session_id"]
    assert client.post(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "Repair approval rerun",
            "constraints": {"method_style": "event_study"},
        },
    ).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"}).status_code == 200
    with sessions._with_conn() as conn:
        sessions._phase_status(conn, session_id, "Repair Agent", "repair_required", "Synthetic repair required.")
        sessions._phase_status(conn, session_id, "Writer Agent", "paper_locked", "Writer locked.")
        sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("paper_locked", sessions._now(), session_id))
        sessions._commit(conn)

    response = client.post(f"/api/sessions/{session_id}/repair/approve", json={"approved": True, "repair_id": "repair-1"})
    assert response.status_code == 200
    assert response.json()["repair_status"] == "approved"
    assert response.json()["resume_started"] is True
    session = client.get(f"/api/sessions/{session_id}").json()
    assert session["status"] == "paper_unlocked"
    phases = {phase["agent_name"]: phase["status"] for phase in session["phases"]}
    assert phases["Writer Agent"] == "complete"


def test_background_failure_records_traceback_in_phase(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    from api import sessions

    created = client.post("/api/sessions", json={"topic": "Failure visibility test", "domain": "finance_economics"})
    session_id = created.json()["session_id"]

    try:
        raise RuntimeError("synthetic background boom")
    except RuntimeError as exc:
        sessions._mark_pipeline_failed(session_id, exc)

    with sessions._with_conn() as conn:
        phase = sessions._fetchone(conn, "SELECT status, failure_reason, failure_mode FROM phases WHERE session_id=? AND agent_name=?", (session_id, "Pipeline orchestrator"))
        session = sessions._session_row(conn, session_id)

    assert phase["status"] == "failed_resumable"
    assert phase["failure_mode"] == "background_exception"
    assert "RuntimeError: synthetic background boom" in phase["failure_reason"]
    assert "Traceback:" in phase["failure_reason"]
    assert session["status"] == "failed_resumable"


def test_api_guide_and_data_aliases_exist(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    guide = client.get("/api/guide")
    assert guide.status_code == 200
    assert "research_package" in json.dumps(guide.json())

    preview = client.post("/api/data/preview", json={"data_mode": "upload"})
    assert preview.status_code == 200
    assert "preview" in preview.json()


def test_session_api_returns_structured_errors(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    missing = client.get("/api/sessions/not-a-real-session")
    assert missing.status_code == 404
    body = missing.json()
    assert body["error_code"] == "SESSION_NOT_FOUND"
    assert body["system_state"] == "not_found"
    assert body["available_actions"] == ["return_to_sessions"]
