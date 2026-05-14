from __future__ import annotations

import json
import uuid
from typing import Any

from api import sessions

OWNER_ACTIONS = {
    "create_session",
    "edit_scope",
    "answer_clarification",
    "lock_blueprint",
    "approve_blueprint_deviation",
    "approve_safe_repair",
    "approve_blueprint_repair",
    "trigger_fork",
    "download_artifacts",
    "view_deviation_register",
    "view_reviewer_scores",
    "view_truth_contract",
    "invite_coauthor",
    "remove_coauthor",
}

COAUTHOR_ACTIONS = {
    "edit_scope",
    "answer_clarification",
    "approve_safe_repair",
    "download_artifacts",
    "view_deviation_register",
    "view_reviewer_scores",
    "view_truth_contract",
}


class PermissionDeniedError(PermissionError):
    def __init__(self, action: str) -> None:
        super().__init__(f"Permission denied for action: {action}")
        self.action = action
        self.error_code = "PERMISSION_DENIED"
        self.system_state = "forbidden"
        self.available_actions = ["request_owner_action", "return_to_session"]

    def to_error(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "system_state": self.system_state,
            "available_actions": self.available_actions,
        }


class ConcurrentEditError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Another researcher is editing this field. Please refresh and try again.")
        self.error_code = "CONCURRENT_EDIT"
        self.system_state = "conflict"
        self.available_actions = ["refresh", "view_current"]

    def to_error(self) -> dict[str, Any]:
        return {
            "error_code": self.error_code,
            "message": str(self),
            "system_state": self.system_state,
            "available_actions": self.available_actions,
        }


def _role(user_id: str, session_id: str) -> str | None:
    with sessions._with_conn() as conn:
        row = sessions._session_row(conn, session_id)
    if not row:
        return None
    if sessions._row_get(row, "user_id") == user_id:
        return "owner"
    if sessions._row_get(row, "coauthor_id") == user_id:
        return "coauthor"
    return None


def check_permission(user_id: str, session_id: str, action: str) -> bool:
    role = _role(user_id, session_id)
    if role == "owner":
        return action in OWNER_ACTIONS
    if role == "coauthor":
        return action in COAUTHOR_ACTIONS
    return False


def _require(user_id: str, session_id: str, action: str) -> None:
    if not check_permission(user_id, session_id, action):
        raise PermissionDeniedError(action)


def invite_coauthor(session_id: str, invited_email: str, invited_by: str) -> dict[str, Any]:
    _require(invited_by, session_id, "invite_coauthor")
    invitation_id = str(uuid.uuid4())
    with sessions._with_conn() as conn:
        sessions._execute(
            conn,
            "INSERT INTO coauthor_invitations (id, session_id, invited_email, invited_by, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (invitation_id, session_id, invited_email, invited_by, "pending", sessions._now()),
        )
        sessions._commit(conn)
    return {"id": invitation_id, "session_id": session_id, "invited_email": invited_email, "status": "pending"}


def accept_invitation(invitation_id: str, user_id: str) -> dict[str, Any]:
    with sessions._with_conn() as conn:
        invitation = sessions._fetchone(conn, "SELECT * FROM coauthor_invitations WHERE id=?", (invitation_id,))
        if not invitation:
            raise PermissionDeniedError("accept_invitation")
        session_id = sessions._row_get(invitation, "session_id")
        sessions._execute(conn, "UPDATE coauthor_invitations SET status=?, accepted_at=? WHERE id=?", ("accepted", sessions._now(), invitation_id))
        sessions._execute(conn, "UPDATE sessions SET coauthor_id=?, updated_at=? WHERE id=?", (user_id, sessions._now(), session_id))
        sessions._commit(conn)
    return {"id": invitation_id, "session_id": session_id, "status": "accepted"}


def remove_coauthor(session_id: str, owner_id: str) -> dict[str, Any]:
    _require(owner_id, session_id, "remove_coauthor")
    with sessions._with_conn() as conn:
        row = sessions._session_row(conn, session_id)
        blueprint = sessions._blueprint_row(conn, session_id)
        removed = sessions._row_get(row, "coauthor_id")
        locked = sessions._row_get(blueprint, "status") == "locked"
        if locked and removed:
            sessions._execute(
                conn,
                "INSERT INTO deviation_register (id, session_id, field_changed, changed_from, changed_to, reason, timestamp, agent_triggered_by, requires_researcher_approval) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), session_id, "coauthor_id", removed, None, "Owner removed co-author after Blueprint lock.", sessions._now(), "Owner action", 1),
            )
        sessions._execute(conn, "UPDATE sessions SET coauthor_id=?, updated_at=? WHERE id=?", (None, sessions._now(), session_id))
        sessions._commit(conn)
    return {"session_id": session_id, "removed_coauthor_id": removed, "deviation_registered": bool(locked and removed)}


def update_blueprint_field(session_id: str, user_id: str, field: str, value: Any, *, expected_updated_at: str) -> dict[str, Any]:
    _require(user_id, session_id, "edit_scope")
    with sessions._with_conn() as conn:
        session = sessions._session_row(conn, session_id)
        current_updated = sessions._row_get(session, "updated_at")
        if current_updated != expected_updated_at:
            raise ConcurrentEditError()
        blueprint = sessions._blueprint_row(conn, session_id)
        content = sessions._blueprint_content(blueprint)
        old_value = content.get(field)
        content[field] = value
        now = sessions._now()
        sessions._execute(conn, "UPDATE blueprints SET content=? WHERE id=?", (json.dumps(content, sort_keys=True), sessions._row_get(blueprint, "id")))
        sessions._execute(conn, "UPDATE sessions SET updated_at=? WHERE id=?", (now, session_id))
        sessions._commit(conn)
    return {"session_id": session_id, "field": field, "changed_from": old_value, "changed_to": value, "updated_at": now}
