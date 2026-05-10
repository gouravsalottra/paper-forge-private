from __future__ import annotations

from pathlib import Path

import pytest

from agents.intake.auth_manager import authenticate_wrds
from agents.intake.intake_agent import IntakeAgent
from agents.intake.protocol_writer import IntakeSession, ProtocolValidationError, ProtocolWriter
from agents.intake.recommendation_engine import RecommendationEngine
from aria.validate_protocol import ProtocolValidator


def test_intake_agent_initializes_without_crash(tmp_path: Path) -> None:
    agent = IntakeAgent(output_path=tmp_path / "PROTOCOL.md", no_llm=True)
    assert agent is not None


def test_intake_no_llm_mode_runs_all_stages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(
        [
            "Does LLM sentiment predict overnight ETF returns?",
            "END",
            "predictability",
            "2015-2024",
            "sec_edgar",
            "",
            "commit",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    agent = IntakeAgent(output_path=tmp_path / "PROTOCOL.md", no_llm=True)
    agent.run()
    protocol = tmp_path / "PROTOCOL.md"
    assert protocol.exists()
    assert ProtocolValidator().validate(protocol) == []


def test_intake_generates_valid_confirmatory_protocol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["predictive idea", "END", "predictability", "2015-2024", "sec_edgar", "", "commit"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    agent = IntakeAgent(output_path=tmp_path / "PROTOCOL.md", no_llm=True)
    agent.run()
    text = (tmp_path / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "## research_mode\nconfirmatory" in text
    assert "## hypothesis" in text
    assert "## statistical_tests" in text


def test_intake_generates_valid_exploratory_protocol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    answers = iter(["explore concentration dynamics", "END", "descriptive", "2010-2024", "yfinance", "", "exploratory"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    agent = IntakeAgent(output_path=tmp_path / "PROTOCOL.md", no_llm=True)
    agent.run()
    text = (tmp_path / "PROTOCOL.md").read_text(encoding="utf-8")
    assert "## research_mode\nexploratory" in text


def test_auth_manager_wrds_stores_username_in_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("webbrowser.open", lambda _url: True)
    answers = iter(["", "my_wrds_user"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))
    authenticate_wrds(env_path=tmp_path / ".env")
    content = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "WRDS_USERNAME=my_wrds_user" in content


def test_recommendation_engine_maps_claim_to_tests() -> None:
    r = RecommendationEngine()
    p = r.recommend_tests("predictability")
    assert "fama_macbeth" in p and "out_of_sample_r2" in p
    perf = r.recommend_tests("performance")
    assert "deflated_sharpe" in perf


def test_protocol_writer_validates_before_writing(tmp_path: Path) -> None:
    session = IntakeSession(research_question="", research_mode="confirmatory")
    out = tmp_path / "PROTOCOL.md"
    with pytest.raises(ProtocolValidationError):
        ProtocolWriter().write(session, out)
    assert not out.exists()


def test_upgrade_to_confirmatory_requires_existing_run(tmp_path: Path) -> None:
    agent = IntakeAgent(output_path=tmp_path / "PROTOCOL.md", no_llm=True)
    with pytest.raises((FileNotFoundError, ValueError)):
        agent.upgrade_to_confirmatory("does-not-exist")
