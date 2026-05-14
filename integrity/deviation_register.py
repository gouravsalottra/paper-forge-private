from __future__ import annotations

from typing import Any

from api import sessions
from integrity.pdf import render_pdf
from storage.blob import write_artifact


def _row_to_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    try:
        return {key: row[key] for key in row.keys()}
    except Exception:
        return {}


def generate_deviation_register(session_id: str) -> dict[str, Any]:
    with sessions._with_conn() as conn:
        rows = [_row_to_dict(row) for row in sessions._fetchall(conn, "SELECT * FROM deviation_register WHERE session_id=? ORDER BY timestamp ASC", (session_id,))]
    automatic = sum(1 for row in rows if not bool(row.get("requires_researcher_approval")))
    researcher_approved = len(rows) - automatic
    doc = {
        "header": (
            "This register records every change made to the research plan after the blueprint was locked. "
            "A clean register (zero entries) certifies that the analysis was conducted exactly as pre-registered."
        ),
        "entries": [
            {
                "timestamp": row.get("timestamp"),
                "field_changed": row.get("field_changed"),
                "changed_from": row.get("changed_from"),
                "changed_to": row.get("changed_to"),
                "reason": row.get("reason"),
                "approval_type": "researcher-approved" if bool(row.get("requires_researcher_approval")) else "automatic",
                "agent_triggered_by": row.get("agent_triggered_by"),
                "requires_researcher_approval": bool(row.get("requires_researcher_approval")),
            }
            for row in rows
        ],
        "footer": {
            "total_deviations": len(rows),
            "automatic": automatic,
            "researcher_approved": researcher_approved,
            "integrity_statement": "Clean register." if not rows else "All deviations are disclosed and ordered by timestamp.",
        },
    }
    lines = [doc["header"], f"Total deviations: {len(rows)}", f"Automatic: {automatic}", f"Researcher-approved: {researcher_approved}"]
    for entry in doc["entries"]:
        lines.append(f"{entry['timestamp']} | {entry['field_changed']}: {entry['changed_from']} -> {entry['changed_to']} | {entry['reason']}")
    return {
        "json": write_artifact(session_id, "01_integrity/deviation_register.json", doc),
        "pdf": write_artifact(session_id, "01_integrity/deviation_register.pdf", render_pdf("Thrivarc Deviation Register", lines)),
    }
