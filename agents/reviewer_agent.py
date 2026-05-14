from __future__ import annotations

import json
import uuid
from typing import Any, Callable

from api import sessions
from storage.blob import write_artifact

REVIEWER_DIMENSIONS = [
    "identification_validity",
    "data_integrity",
    "statistical_rigor",
    "economic_significance",
    "benchmark_fairness",
    "robustness_burden",
    "overclaiming_risk",
]

AVERAGE_MINIMUM = 7.0
DIMENSION_FLOOR = 6.0
MAX_REPAIR_CYCLES = 3

DimensionScorer = Callable[[str, dict[str, Any]], dict[str, Any]]


class ReviewerGateAgent:
    """Conditional paper gate: paper is earned, never default."""

    def __init__(self, dimension_scorer: DimensionScorer | None = None) -> None:
        self.dimension_scorer = dimension_scorer

    def _next_cycle(self, session_id: str) -> int:
        with sessions._with_conn() as conn:
            row = sessions._fetchone(conn, "SELECT MAX(cycle) AS max_cycle FROM reviewer_scores WHERE session_id=?", (session_id,))
        return int(sessions._row_get(row, "max_cycle", 0) or 0) + 1

    def _score_dimension(self, dimension: str, evidence: dict[str, Any]) -> tuple[float, Any]:
        if self.dimension_scorer:
            scored = self.dimension_scorer(dimension, evidence)
            return float(scored.get("score", 0.0)), scored.get("finding")
        scores = evidence.get("scores") if isinstance(evidence.get("scores"), dict) else {}
        findings = evidence.get("findings") if isinstance(evidence.get("findings"), dict) else {}
        return float(scores.get(dimension, 0.0)), findings.get(dimension) or findings.get("summary") or "No finding supplied."

    def _score_all_dimensions(self, evidence: dict[str, Any]) -> tuple[dict[str, float], dict[str, Any]]:
        scores: dict[str, float] = {}
        findings: dict[str, Any] = {}
        for dimension in REVIEWER_DIMENSIONS:
            score, finding = self._score_dimension(dimension, evidence)
            scores[dimension] = max(0.0, min(10.0, score))
            findings[dimension] = finding
        return scores, findings

    def _write_score(self, session_id: str, cycle: int, scores: dict[str, float], average: float, gate_passed: bool, findings: dict[str, Any]) -> None:
        with sessions._with_conn() as conn:
            sessions._execute(
                conn,
                """
                INSERT INTO reviewer_scores (
                  id, session_id, cycle, identification_validity, data_integrity,
                  statistical_rigor, economic_significance, benchmark_fairness,
                  robustness_burden, overclaiming_risk, average_score,
                  gate_passed, findings, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    str(uuid.uuid4()),
                    session_id,
                    cycle,
                    scores["identification_validity"],
                    scores["data_integrity"],
                    scores["statistical_rigor"],
                    scores["economic_significance"],
                    scores["benchmark_fairness"],
                    scores["robustness_burden"],
                    scores["overclaiming_risk"],
                    average,
                    int(gate_passed),
                    json.dumps(findings, sort_keys=True),
                    sessions._now(),
                ),
            )
            sessions._commit(conn)

    def _repair_contract(self, session_id: str, cycle: int, findings: dict[str, Any], repair_scope: dict[str, Any]) -> dict[str, Any]:
        changes_blueprint = bool(repair_scope.get("changes_blueprint"))
        repair_id = str(uuid.uuid4())
        deviation_registered = False
        with sessions._with_conn() as conn:
            if changes_blueprint:
                deviation_registered = True
                sessions._execute(
                    conn,
                    """
                    INSERT INTO deviation_register (
                      id, session_id, field_changed, changed_from, changed_to,
                      reason, timestamp, agent_triggered_by, requires_researcher_approval
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(uuid.uuid4()),
                        session_id,
                        repair_scope.get("field") or "blueprint",
                        repair_scope.get("from"),
                        repair_scope.get("to"),
                        repair_scope.get("reason") or "Reviewer gate repair would change the locked Blueprint.",
                        sessions._now(),
                        "Reviewer Agent",
                        1,
                    ),
                )
            sessions._execute(
                conn,
                """
                INSERT INTO repair_log (
                  id, session_id, trigger_agent, trigger_finding, scope,
                  pass_criterion, cycle_number, approval_required,
                  outcome, deviation_registered, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repair_id,
                    session_id,
                    "Reviewer Agent",
                    json.dumps(findings, sort_keys=True),
                    repair_scope.get("scope") or ("blueprint" if changes_blueprint else "evidence"),
                    repair_scope.get("pass_criterion") or "Raise reviewer score above threshold without overclaiming.",
                    cycle,
                    int(changes_blueprint),
                    "pending_approval" if changes_blueprint else "queued",
                    int(deviation_registered),
                    sessions._now(),
                ),
            )
            sessions._phase_status(conn, session_id, "Repair Agent", "repair_required", "Reviewer gate created a bounded Repair Contract.")
            sessions._event(
                conn,
                session_id,
                "repair_triggered",
                {"repair_id": repair_id, "approval_required": changes_blueprint, "cycle": cycle},
                "Repair Agent",
                "repair_required",
            )
            sessions._commit(conn)
        return {
            "repair_id": repair_id,
            "trigger_agent": "Reviewer Agent",
            "scope": repair_scope.get("scope") or ("blueprint" if changes_blueprint else "evidence"),
            "pass_criterion": repair_scope.get("pass_criterion") or "Raise reviewer score above threshold without overclaiming.",
            "cycle_number": cycle,
            "approval_required": changes_blueprint,
            "deviation_registered": deviation_registered,
        }

    def _set_session_status(self, session_id: str, status: str, event_type: str, payload: dict[str, Any]) -> None:
        with sessions._with_conn() as conn:
            sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", (status, sessions._now(), session_id))
            sessions._phase_status(conn, session_id, "Reviewer Agent", "complete" if status != "paper_locked" else "paper_locked", payload.get("summary"))
            sessions._event(conn, session_id, event_type, payload, "Reviewer Agent", status)
            sessions._commit(conn)

    def score(self, session_id: str, evidence: dict[str, Any]) -> dict[str, Any]:
        cycle = self._next_cycle(session_id)
        scores, findings = self._score_all_dimensions(evidence)
        average = round(sum(scores.values()) / len(REVIEWER_DIMENSIONS), 4)
        floor_failed = [name for name, score in scores.items() if score < DIMENSION_FLOOR]
        gate_passed = average >= AVERAGE_MINIMUM and not floor_failed
        scorecard = {
            "session_id": session_id,
            "cycle": cycle,
            "scores": scores,
            "average_score": average,
            "floor_failed": floor_failed,
            "gate_passed": gate_passed,
            "findings": findings,
            "thresholds": {"average_minimum": AVERAGE_MINIMUM, "dimension_floor": DIMENSION_FLOOR, "max_cycles": MAX_REPAIR_CYCLES},
        }
        self._write_score(session_id, cycle, scores, average, gate_passed, findings)
        write_artifact(session_id, f"09_review/reviewer_scorecard_v{cycle}.json", scorecard)

        with sessions._with_conn() as conn:
            sessions._phase_status(conn, session_id, "Reviewer Agent", "complete" if gate_passed else "repair_required", "Reviewer gate scored evidence.")
            sessions._event(conn, session_id, "gate_result", scorecard, "Reviewer Agent", "complete" if gate_passed else "repair_required")
            sessions._commit(conn)

        if gate_passed:
            self._set_session_status(session_id, "writer_unlocked", "writer_unlocked", {"summary": "Paper writing is now unlocked.", **scorecard})
            return {**scorecard, "outcome": "writer_unlocked"}

        if cycle >= MAX_REPAIR_CYCLES:
            self._set_session_status(session_id, "paper_locked", "paper_locked", {"summary": "Reviewer gate failed after three cycles.", **scorecard})
            return {**scorecard, "outcome": "paper_locked"}

        repair = self._repair_contract(session_id, cycle, findings, evidence.get("repair_scope") if isinstance(evidence.get("repair_scope"), dict) else {})
        with sessions._with_conn() as conn:
            sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("repair_required", sessions._now(), session_id))
            sessions._commit(conn)
        return {**scorecard, "outcome": "repair_required", "repair_contract": repair}

    def writer_allowed(self, session_id: str) -> bool:
        with sessions._with_conn() as conn:
            session = sessions._session_row(conn, session_id)
            latest = sessions._fetchone(conn, "SELECT gate_passed FROM reviewer_scores WHERE session_id=? ORDER BY cycle DESC LIMIT 1", (session_id,))
        return sessions._row_get(session, "status") != "paper_locked" and bool(sessions._row_get(latest, "gate_passed", 0))
