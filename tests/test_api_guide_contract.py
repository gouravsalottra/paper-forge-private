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
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(guide, "_json_call", lambda _system, _payload: _blocking_payload())

    result = guide.validate({"topic": "Test whether sector rotation improves returns"})

    summary = result["blueprint_summary"]
    assert result["validated"] is False
    assert summary["launch_readiness"]["headline"] == "Blueprint needs clarification"
    assert summary["completion_contract"]["state"] == "blocked"
    assert summary["completion_contract"]["ready_for_evidence_preview"] is False
    assert summary["completion_contract"]["blockers"][0]["key"] == "universe"


def test_validate_sanitizes_all_agent_stack_engine_labels(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    payload = _blocking_payload()
    payload["clarifications"] = []
    payload["blueprint_summary"]["agent_stack_preview"] = [
        {"phase": "DATAPULL", "engine": "Thrivarc evidence connector"},
        {"phase": "COMPUTE", "engine": "Thrivarc compute adapter"},
        {"phase": "STATSRUN", "engine": "existing stats agents"},
        {"phase": "WRITER", "engine": "existing writer"},
    ]
    monkeypatch.setattr(guide, "_json_call", lambda _system, _payload: payload)

    result = guide.validate({"topic": "Test whether sector ETF momentum predicts future returns from 2015 to 2024"})

    engines = [
        item["engine"]
        for item in result["blueprint_summary"]["agent_stack_preview"]
    ]
    assert engines == ["gpt-4o", "gpt-4o", "gpt-4o", "gpt-4o"]


def test_build_runspec_recomputes_completion_contract_from_client_payload(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    stale_validated = _blocking_payload()

    result = guide.build_runspec({
        "form_data": {"topic": "Test whether sector rotation improves returns"},
        "validated_result": stale_validated,
    })

    blueprint = result["runspecs"][0]["runspec"]["blueprint"]
    assert blueprint["launch_readiness"]["headline"] == "Blueprint needs clarification"
    assert blueprint["completion_contract"]["state"] == "blocked"
    assert blueprint["completion_contract"]["ready_for_evidence_preview"] is False


def test_validate_surfaces_reviewer_repair_and_integrity_contracts(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = guide.validate({
        "topic": "Explore whether SEC filing language shifts map to sector ETF overnight volatility using EDGAR and yfinance data from 2015 to 2024",
    })

    summary = result["blueprint_summary"]
    assert summary["research_package"]["track"] == "exploratory"
    assert summary["reviewer_gate"]["paper_unlock_threshold"]["minimum_average"] == 7.0
    assert summary["reviewer_gate"]["paper_unlock_threshold"]["minimum_dimension"] == 6.0
    assert summary["repair_contract_template"]["max_cycles_per_issue"] == 3
    assert "data_passport" in summary["integrity_artifacts"]
    assert summary["integrity_artifacts"]["preregistration_certificate"]["enabled"] is False
    assert summary["audit_boundary"]["code_audit_agent"]["definition"] == "Technical correctness check."
    assert summary["paper_code_verifier"]["final_position"] == "immediately before Writer export"
    assert summary["data_fallback_policy"]["wrds_status"] == "not default in v1 because access is currently paused"


def test_backtest_blueprint_blocks_missing_design_details(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = guide.validate({
        "topic": "Test whether a trading strategy can outperform a benchmark",
    })

    summary = result["blueprint_summary"]
    blockers = {item["key"] for item in summary["completion_contract"]["blockers"]}
    assert result["validated"] is False
    assert summary["method_style"] == "backtest"
    assert summary["statistical_battery"]["tests"] == [
        "net_return",
        "annualized_sharpe",
        "max_drawdown",
        "turnover_cost",
        "deflated_sharpe",
        "block_bootstrap",
    ]
    assert {"universe", "time_horizon", "cadence"}.issubset(blockers)


def test_build_runspec_embeds_guide_truth_contracts(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    result = guide.build_runspec({
        "form_data": {"topic": "Test whether a trading strategy can outperform a benchmark"},
        "validated_result": _blocking_payload(),
    })

    runspec = result["runspecs"][0]["runspec"]
    blueprint = runspec["blueprint"]
    assert blueprint["reviewer_gate"]["writer_rule"] == "Writer is last and never invents numbers."
    assert blueprint["repair_contract_template"]["contract_fields"] == [
        "trigger",
        "scope",
        "pass_criterion",
        "approval_required",
        "deviation_register_entry",
    ]
    assert blueprint["integrity_artifacts"]["data_passport"]["visible_name"] == "DataPassport"
    assert blueprint["leakage_policy"]["method"] == "backtest"
    assert "deflated_sharpe" in runspec["statsrun"]["test_battery"]
