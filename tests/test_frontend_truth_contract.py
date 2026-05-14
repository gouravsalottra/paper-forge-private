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
