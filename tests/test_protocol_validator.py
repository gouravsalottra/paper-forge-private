from __future__ import annotations

from pathlib import Path

from aria.validate_protocol import ProtocolValidator


def test_protocol_schema_and_template_exist() -> None:
    assert Path("PROTOCOL_SCHEMA.md").exists()
    assert Path("PROTOCOL_SCHEMA.md").stat().st_size > 500
    assert Path("PROTOCOL.md").stat().st_size > 300


def test_protocol_validator_rejects_missing_confirmatory_fields(tmp_path: Path) -> None:
    protocol = tmp_path / "PROTOCOL.md"
    protocol.write_text(
        """
## research_question
Test question

## research_mode
confirmatory
""".strip()
        + "\n",
        encoding="utf-8",
    )
    errors = ProtocolValidator().validate(protocol)
    assert any("claim_type" in e for e in errors)
    assert any("hypothesis" in e for e in errors)
    assert any("primary_metric" in e for e in errors)
    assert any("minimum_effect_size" in e for e in errors)


def test_protocol_validator_accepts_valid_exploratory(tmp_path: Path) -> None:
    protocol = tmp_path / "PROTOCOL.md"
    protocol.write_text(
        """
## research_question
Do concentration states co-move with momentum profitability?

## research_mode
exploratory

## data_source
yfinance CL=F, NG=F

## sample_period
2000-01-01 to 2023-12-31
""".strip()
        + "\n",
        encoding="utf-8",
    )
    errors = ProtocolValidator().validate(protocol)
    assert errors == []
