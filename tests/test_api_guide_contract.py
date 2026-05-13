from __future__ import annotations

import os

from api import guide


def _blocking_payload() -> dict:
    return {
        "validated": True,
        "research_state": "exploratory",
        "clarifications": [
            {
                "key": "universe",
                "question": "Which universe anchors the study?",
                "reason": "The evidence preview cannot choose identifiers safely without it.",
                "blocking": True,
            }
        ],
        "blueprint_summary": {
            "evidence_source": "yfinance",
            "method_style": "backtest",
            "launch_readiness": {
                "headline": "Blueprint ready for evidence preview",
                "detail": "Incorrect stale state",
                "next_step": "Preview the evidence.",
            },
            "completion_contract": {
                "state": "ready_for_evidence_preview",
                "ready_for_evidence_preview": True,
                "blockers": [],
            },
        },
    }


def test_validate_recomputes_completion_contract_after_blocking_clarifications(monkeypatch) -> None:
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(guide, "_json_call", lambda _system, _payload: _blocking_payload())

    result = guide.validate({"topic": "Test whether sector rotation improves returns"})

    summary = result["blueprint_summary"]
    assert result["validated"] is False
    assert summary["launch_readiness"]["headline"] == "Blueprint needs clarification"
    assert summary["completion_contract"]["state"] == "blocked"
    assert summary["completion_contract"]["ready_for_evidence_preview"] is False
    assert summary["completion_contract"]["blockers"][0]["key"] == "universe"


def test_build_runspec_recomputes_completion_contract_from_client_payload(monkeypatch) -> None:
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    stale_validated = _blocking_payload()

    result = guide.build_runspec({
        "form_data": {"topic": "Test whether sector rotation improves returns"},
        "validated_result": stale_validated,
    })

    blueprint = result["runspecs"][0]["runspec"]["blueprint"]
    assert blueprint["launch_readiness"]["headline"] == "Blueprint needs clarification"
    assert blueprint["completion_contract"]["state"] == "blocked"
    assert blueprint["completion_contract"]["ready_for_evidence_preview"] is False
