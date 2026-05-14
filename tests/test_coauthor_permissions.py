from __future__ import annotations

from pathlib import Path

import pytest

OWNER = "11111111-1111-1111-1111-111111111111"
COAUTHOR = "22222222-2222-2222-2222-222222222222"


def _seed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, locked: bool = False) -> str:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "coauthors.db"))
    from api import sessions

    session_id = "coauthor-session"
    status = "blueprint_locked" if locked else "scope_confirmed"
    bp_status = "locked" if locked else "draft"
    with sessions._with_conn() as conn:
        sessions._execute(
            conn,
            "INSERT INTO sessions (id, topic, domain, research_type, status, created_at, updated_at, user_id, coauthor_id, credits_spent) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, "Coauthor test", "finance_economics", "confirmatory", status, sessions._now(), "2026-05-14T01:00:00+00:00", OWNER, COAUTHOR, 0),
        )
        sessions._execute(
            conn,
            "INSERT INTO blueprints (id, session_id, content, status, locked_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            ("bp-coauthor", session_id, '{"hypothesis":"ETF flows predict returns"}', bp_status, sessions._now() if locked else None, sessions._now()),
        )
        conn.commit()
    return session_id


def test_permission_table_owner_and_coauthor_actions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed(tmp_path, monkeypatch)
    from auth.permissions import check_permission

    assert check_permission(OWNER, session_id, "lock_blueprint") is True
    assert check_permission(COAUTHOR, session_id, "lock_blueprint") is False
    assert check_permission(COAUTHOR, session_id, "view_truth_contract") is True
    assert check_permission(COAUTHOR, session_id, "answer_clarification") is True
    assert check_permission(COAUTHOR, session_id, "approve_safe_repair") is True
    assert check_permission(COAUTHOR, session_id, "approve_blueprint_repair") is False
    assert check_permission(COAUTHOR, session_id, "trigger_fork") is False


def test_invitation_is_pending_before_access(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed(tmp_path, monkeypatch)
    from auth.permissions import accept_invitation, invite_coauthor
    from api import sessions

    invitation = invite_coauthor(session_id, "mentor@example.com", OWNER)
    assert invitation["status"] == "pending"
    with sessions._with_conn() as conn:
        row = sessions._fetchone(conn, "SELECT status, invited_email FROM coauthor_invitations WHERE id=?", (invitation["id"],))
    assert row["status"] == "pending"
    assert row["invited_email"] == "mentor@example.com"

    accepted = accept_invitation(invitation["id"], COAUTHOR)
    assert accepted["status"] == "accepted"


def test_optimistic_blueprint_edit_rejects_concurrent_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed(tmp_path, monkeypatch)
    from api import sessions
    from auth.permissions import ConcurrentEditError, update_blueprint_field

    with sessions._with_conn() as conn:
        original = sessions._session_row(conn, session_id)["updated_at"]

    update_blueprint_field(session_id, COAUTHOR, "hypothesis", "First edit", expected_updated_at=original)
    with pytest.raises(ConcurrentEditError) as exc:
        update_blueprint_field(session_id, OWNER, "hypothesis", "Second edit", expected_updated_at=original)

    assert exc.value.to_error()["error_code"] == "CONCURRENT_EDIT"
    assert exc.value.to_error()["system_state"] == "conflict"


def test_remove_coauthor_before_lock_has_no_deviation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed(tmp_path, monkeypatch, locked=False)
    from api import sessions
    from auth.permissions import remove_coauthor

    remove_coauthor(session_id, OWNER)
    with sessions._with_conn() as conn:
        deviations = sessions._fetchone(conn, "SELECT COUNT(*) AS count FROM deviation_register WHERE session_id=?", (session_id,))
        session = sessions._session_row(conn, session_id)
    assert deviations["count"] == 0
    assert session["coauthor_id"] is None


def test_remove_coauthor_after_lock_writes_deviation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    session_id = _seed(tmp_path, monkeypatch, locked=True)
    from api import sessions
    from auth.permissions import remove_coauthor

    remove_coauthor(session_id, OWNER)
    with sessions._with_conn() as conn:
        deviation = sessions._fetchone(conn, "SELECT field_changed, requires_researcher_approval FROM deviation_register WHERE session_id=?", (session_id,))
    assert deviation["field_changed"] == "coauthor_id"
    assert deviation["requires_researcher_approval"] == 1
