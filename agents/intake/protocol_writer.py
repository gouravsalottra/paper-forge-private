from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from aria.validate_protocol import ProtocolValidator


class ProtocolValidationError(ValueError):
    pass


@dataclass
class IntakeSession:
    research_question: str
    research_mode: str
    claim_type: str = ""
    hypothesis: str = ""
    primary_metric: str = ""
    minimum_effect_size: str = ""
    significance_threshold: str = ""
    data_source: str = ""
    sample_period: str = ""
    statistical_tests: list[str] = field(default_factory=list)


class ProtocolWriter:
    def write(self, session: IntakeSession, output_path: Path) -> None:
        text = self._to_protocol_text(session)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = output_path.with_suffix('.tmp')
        tmp.write_text(text, encoding='utf-8')
        errors = ProtocolValidator().validate(tmp)
        if errors:
            tmp.unlink(missing_ok=True)
            raise ProtocolValidationError("\n".join(errors))
        tmp.replace(output_path)

    def _to_protocol_text(self, s: IntakeSession) -> str:
        parts = [
            "## research_question", s.research_question.strip(), "",
            "## research_mode", s.research_mode.strip(), "",
            "## claim_type", s.claim_type.strip(), "",
            "## hypothesis", s.hypothesis.strip(), "",
            "## primary_metric", s.primary_metric.strip(), "",
            "## minimum_effect_size", s.minimum_effect_size.strip(), "",
            "## significance_threshold", s.significance_threshold.strip(), "",
            "## data_source", s.data_source.strip(), "",
            "## sample_period", s.sample_period.strip(), "",
            "## statistical_tests",
        ]
        if s.statistical_tests:
            parts.extend([f"- {t}" for t in s.statistical_tests])
        else:
            parts.append("")
        parts.append("")
        return "\n".join(parts).rstrip() + "\n"
