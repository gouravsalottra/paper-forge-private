from __future__ import annotations

from pathlib import Path

import pytest

DIMENSIONS = [
    "identification_validity",
    "data_integrity",
    "statistical_rigor",
    "economic_significance",
    "benchmark_fairness",
    "robustness_burden",
    "overclaiming_risk",
]


def _seed_session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "reviewer.db"))
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from api import sessions
    from storage import blob

    blob.reset_mock_storage()
    session_id = "review-session"
    with sessions._with_conn() as conn:
        sessions._execute(
            conn,
            "INSERT INTO sessions (id, topic, domain, research_type, status, created_at, updated_at, credits_spent) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, "Reviewer gate test", "finance_economics", "confirmatory", "running", sessions._now(), sessions._now(), 0),
        )
        sessions._execute(
            conn,
            "INSERT INTO blueprints (id, session_id, content, status, created_at) VALUES (?, ?, ?, ?, ?)",
            ("bp-review", session_id, '{"hypothesis":"ETF flows predict returns","benchmark":"SPY"}', "locked", sessions._now()),
        )
        conn.commit()
    return session_id


def _scores(value: float) -> dict[str, float]:
    return {dimension: value for dimension in DIMENSIONS}


def test_gate_passes_only_when_average_and_all_dimensions_clear(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed_session(tmp_path, monkeypatch)
    from agents.reviewer_agent import ReviewerGateAgent
    from api import sessions
    from storage import blob

    result = ReviewerGateAgent().score(session_id, {"scores": _scores(7.5), "findings": {"summary": "defensible"}})

    assert result["gate_passed"] is True
    assert result["average_score"] == 7.5
    assert ReviewerGateAgent().writer_allowed(session_id) is True
    assert b"defensible" in blob.read_artifact(session_id, "09_review/reviewer_scorecard_v1.json")
    with sessions._with_conn() as conn:
        row = sessions._fetchone(conn, "SELECT gate_passed, average_score FROM reviewer_scores WHERE session_id=?", (session_id,))
        event = sessions._fetchone(conn, "SELECT event_type FROM session_events WHERE session_id=? ORDER BY created_at DESC LIMIT 1", (session_id,))
    assert row["gate_passed"] == 1
    assert row["average_score"] == 7.5
    assert event["event_type"] == "writer_unlocked"


def test_gate_fails_when_average_below_threshold(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed_session(tmp_path, monkeypatch)
    from agents.reviewer_agent import ReviewerGateAgent
    from api import sessions

    result = ReviewerGateAgent().score(session_id, {"scores": _scores(6.9), "findings": {"statistical_rigor": "too weak"}})

    assert result["gate_passed"] is False
    assert result["outcome"] == "repair_required"
    assert ReviewerGateAgent().writer_allowed(session_id) is False
    with sessions._with_conn() as conn:
        repair = sessions._fetchone(conn, "SELECT approval_required, cycle_number FROM repair_log WHERE session_id=?", (session_id,))
    assert repair["approval_required"] == 0
    assert repair["cycle_number"] == 1


def test_gate_fails_when_single_dimension_below_floor(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed_session(tmp_path, monkeypatch)
    from agents.reviewer_agent import ReviewerGateAgent

    scores = _scores(8.0)
    scores["data_integrity"] = 5.5
    result = ReviewerGateAgent().score(session_id, {"scores": scores, "findings": {"data_integrity": "hash mismatch"}})

    assert result["gate_passed"] is False
    assert result["floor_failed"] == ["data_integrity"]


def test_after_three_failed_cycles_status_is_paper_locked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed_session(tmp_path, monkeypatch)
    from agents.reviewer_agent import ReviewerGateAgent
    from api import sessions

    agent = ReviewerGateAgent()
    for _ in range(3):
        result = agent.score(session_id, {"scores": _scores(4.5), "findings": {"identification_validity": "fundamental redesign needed"}})

    assert result["outcome"] == "paper_locked"
    assert agent.writer_allowed(session_id) is False
    with sessions._with_conn() as conn:
        session = sessions._fetchone(conn, "SELECT status FROM sessions WHERE id=?", (session_id,))
        repairs = sessions._fetchone(conn, "SELECT COUNT(*) AS count FROM repair_log WHERE session_id=?", (session_id,))
    assert session["status"] == "paper_locked"
    assert repairs["count"] == 2


def test_blueprint_changing_repair_requires_approval_and_deviation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed_session(tmp_path, monkeypatch)
    from agents.reviewer_agent import ReviewerGateAgent
    from api import sessions

    result = ReviewerGateAgent().score(
        session_id,
        {
            "scores": _scores(6.0),
            "findings": {"benchmark_fairness": "benchmark must change"},
            "repair_scope": {"changes_blueprint": True, "field": "benchmark", "from": "SPY", "to": "XLF"},
        },
    )

    assert result["repair_contract"]["approval_required"] is True
    with sessions._with_conn() as conn:
        repair = sessions._fetchone(conn, "SELECT approval_required, deviation_registered FROM repair_log WHERE session_id=?", (session_id,))
        deviation = sessions._fetchone(conn, "SELECT field_changed, requires_researcher_approval FROM deviation_register WHERE session_id=?", (session_id,))
    assert repair["approval_required"] == 1
    assert repair["deviation_registered"] == 1
    assert deviation["field_changed"] == "benchmark"
    assert deviation["requires_researcher_approval"] == 1
