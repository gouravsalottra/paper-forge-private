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


def test_new_study_flow_uses_inferred_mode_and_draft_autosave_language() -> None:
    html = _html()
    assert "What are you studying?" in html
    assert "Research Stance (Required)" not in html
    assert "How your study looks so far" in html
    assert "Your draft is saved automatically" in html
    assert "Analyzing your brief" in html
    assert "thrivarc_intake_draft" in html


def test_workspace_uses_canonical_api_session_routes_and_refreshes_per_session() -> None:
    html = _html()
    assert "/api/sessions/${id}/compute-cells" in html
    assert "/api/sessions/${currentResearchId}/compute-cells" in html
    assert "/api/sessions/${currentResearchId}/prompt-amplifiers" in html
    assert "/api/sessions/${currentResearchId}/agent-chat" in html
    assert "prompt_amplifier" not in html
    assert "if(!workspaceTopic)" not in html


def test_research_route_is_study_first_cockpit_and_not_agent_shell() -> None:
    html = _html()
    assert "if(h.startsWith('research/')) return renderResearch(h.split('/')[1]);" in html
    assert "Specialist conversations" in html
    assert "Open JupyterLab" in html
    assert "/api/sessions/${id}/specialists/" in html
    assert "/api/sessions/${id}/notebook" in html


def test_dashboard_supports_bulk_cleanup_actions() -> None:
    html = _html()
    assert "Delete completed" in html
    assert "Delete selected" in html
    assert "/api/sessions/bulk/delete-completed" in html
    assert "/api/sessions/bulk/delete" in html


def test_frontend_uses_real_model_registry_and_prompt_layers() -> None:
    html = _html()
    assert "/api/models" in html
    assert "Locked Safety Contract" in html
    assert "Editable Working Prompt" in html
    assert "Session-specific notes" in html
