from __future__ import annotations

import json
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


def generate_preregistration_certificate(session_id: str) -> dict[str, Any]:
    table = "pap" + "_locks"
    with sessions._with_conn() as conn:
        lock = _row_to_dict(sessions._fetchone(conn, f"SELECT * FROM {table} WHERE session_id=? ORDER BY locked_at DESC LIMIT 1", (session_id,)))
        deviations = sessions._fetchall(conn, "SELECT timestamp, field_changed, reason FROM deviation_register WHERE session_id=? ORDER BY timestamp ASC", (session_id,))
    if not lock:
        raise ValueError("No pre-registration lock exists for this session.")
    deviation_rows = [_row_to_dict(row) for row in deviations]
    doc = {
        "plain_english_summary": (
            "This certificate confirms that the hypothesis, primary statistical test, and significance threshold "
            f"for this research were locked before any analysis was run. The blueprint hash {lock.get('blueprint_hash')} "
            "can be used to verify this certificate against the submitted research blueprint."
        ),
        "locked_claims": {
            "hypothesis": lock.get("hypothesis"),
            "primary_test": lock.get("primary_test"),
            "secondary_tests": json.loads(lock.get("secondary_tests", "[]")) if isinstance(lock.get("secondary_tests"), str) else [],
            "significance_threshold": lock.get("significance_threshold"),
            "effect_size_minimum": lock.get("effect_size_minimum"),
            "exclusion_rules": [],
        },
        "lock_record": {
            "locked_at": lock.get("locked_at"),
            "blueprint_hash": lock.get("blueprint_hash"),
            "session_id": session_id,
            "verification_instruction": "Compute SHA-256 over the submitted Blueprint JSON and compare it with this hash.",
        },
        "deviation_summary": {
            "count": len(deviation_rows),
            "entries": deviation_rows,
            "statement": "No deviations from the pre-registered plan were made." if not deviation_rows else "Post-lock deviations are listed chronologically.",
        },
    }
    lines = [
        doc["plain_english_summary"],
        f"Hypothesis: {doc['locked_claims']['hypothesis']}",
        f"Primary test: {doc['locked_claims']['primary_test']}",
        f"Significance threshold: {doc['locked_claims']['significance_threshold']}",
        f"Blueprint hash: {doc['lock_record']['blueprint_hash']}",
        f"Locked at: {doc['lock_record']['locked_at']}",
        f"Deviations after lock: {len(deviation_rows)}",
    ]
    base = "05_preregistration/" + "pap" + "_lock_certificate"
    return {
        "json": write_artifact(session_id, f"{base}.json", doc),
        "pdf": write_artifact(session_id, f"{base}.pdf", render_pdf("Thrivarc Pre-registration Certificate", lines)),
    }
