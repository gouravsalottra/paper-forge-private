from __future__ import annotations

import re
from pathlib import Path


class ProtocolValidator:
    REQUIRED_ALWAYS = {"research_question", "research_mode", "data_source", "sample_period"}
    REQUIRED_CONFIRMATORY = {"claim_type", "hypothesis", "primary_metric", "minimum_effect_size", "significance_threshold"}
    ALLOWED_RESEARCH_MODES = {"confirmatory", "exploratory"}
    ALLOWED_CLAIM_TYPES = {"predictability", "performance", "causal", "descriptive"}

    def validate(self, path: Path) -> list[str]:
        errors: list[str] = []
        if not path.exists():
            return [f"protocol file not found: {path}"]

        sections = self._parse_sections(path.read_text(encoding="utf-8", errors="ignore"))

        for key in self.REQUIRED_ALWAYS:
            if not sections.get(key, "").strip():
                errors.append(f"missing required field: {key}")
        for value in sections.values():
            v = value.strip()
            if v.startswith("[FILL IN"):
                errors.append(
                    "PROTOCOL.md contains unfilled template placeholders. "
                    "Run python intake.py to generate your research protocol, "
                    "or fill in the placeholders manually."
                )
                break

        mode = sections.get("research_mode", "").strip().lower()
        if mode and mode not in self.ALLOWED_RESEARCH_MODES:
            errors.append(f"research_mode must be one of {sorted(self.ALLOWED_RESEARCH_MODES)}")

        if mode == "confirmatory":
            for key in self.REQUIRED_CONFIRMATORY:
                if not sections.get(key, "").strip():
                    errors.append(f"missing required field for confirmatory mode: {key}")
            claim_type = sections.get("claim_type", "").strip().lower()
            if claim_type and claim_type not in self.ALLOWED_CLAIM_TYPES:
                errors.append(f"claim_type must be one of {sorted(self.ALLOWED_CLAIM_TYPES)}")

        return errors

    @staticmethod
    def _parse_sections(text: str) -> dict[str, str]:
        sections: dict[str, str] = {}
        matches = list(re.finditer(r"^##\s+([a-zA-Z0-9_ -]+)\s*$", text, flags=re.MULTILINE))
        if not matches:
            return sections

        for i, m in enumerate(matches):
            name = m.group(1).strip().lower().replace(" ", "_").replace("-", "_")
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            sections[name] = text[start:end].strip()
        return sections
