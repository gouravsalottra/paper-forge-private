from __future__ import annotations

from pathlib import Path


def test_blueprint_screen_exposes_product_truth_contracts() -> None:
    html = Path("frontend/app.html").read_text(encoding="utf-8")
    required = [
        "Research Architect clarification policy",
        "Conditional paper gate",
        "Repair Contract",
        "Integrity artifacts",
        "Execution truth contract",
        "Writer is last and never invents numbers",
        "DataPassport",
        "Pre-registration certificate",
        "Paper-Code Verifier",
    ]
    for phrase in required:
        assert phrase in html


def test_frontend_renders_backend_contract_fields() -> None:
    html = Path("frontend/app.html").read_text(encoding="utf-8")
    required_fields = [
        "research_package",
        "clarification_policy",
        "reviewer_gate",
        "repair_contract_template",
        "integrity_artifacts",
        "data_quality_policy",
        "leakage_policy",
        "statistical_battery",
        "economic_significance",
        "data_fallback_policy",
    ]
    for field in required_fields:
        assert field in html

def _html() -> str:
    return Path("frontend/app.html").read_text(encoding="utf-8")


def test_frontend_truth_state_map_declares_sources() -> None:
    html = _html()
    required = [
        "const FRONTEND_TRUTH_STATE_MAP",
        "Session status badge",
        "sessions.status",
        "Blueprint lock button",
        "blueprints.status",
        "Phase indicators",
        "phases.status",
        "Reviewer gate card",
        "reviewer_scores",
        "Repair approval card",
        "repair_log",
        "Writer unlock banner",
        "reviewer_scores.gate_passed",
        "Paper download link",
        "sessions.status=paper_unlocked",
        "Deviation badge",
        "COUNT(deviation_register)",
        "Credits spent",
        "sessions.credits_spent",
    ]
    for phrase in required:
        assert phrase in html


def test_frontend_uses_sse_for_session_phase_updates() -> None:
    html = _html()
    assert "new EventSource" in html
    assert "/api/sessions/${sessionId}/stream" in html
    assert "handleSessionEvent" in html
    assert "phase_update" in html
    assert "gate_result" in html


def test_frontend_gates_buttons_from_backend_state() -> None:
    html = _html()
    assert "function blueprintLockDisabled(sessionState)" in html
    assert "sessionState?.blueprint_status !== 'draft'" in html
    assert "function writerButtonDisabled(sessionState)" in html
    assert "sessionState?.reviewer_gate?.passed !== true" in html
    assert "function paperDownloadAllowed(sessionState)" in html
    assert "sessionState?.status === 'paper_unlocked'" in html
    assert "data-truth-source=\"blueprints.status\"" in html


def test_frontend_renders_scores_and_downloads_from_api_sources() -> None:
    html = _html()
    assert "data-truth-source=\"reviewer_scores\"" in html
    assert "data-truth-source=\"phases.status\"" in html
    assert "data-truth-source=\"sessions.status\"" in html
    assert "data-truth-source=\"Blob Storage signed URL\"" in html
    assert "reviewer_scores table" in html
