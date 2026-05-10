"""Validation helpers for PAPER.md."""

from __future__ import annotations

from pathlib import Path


class ValidationError(ValueError):
    """Raised when PAPER.md is missing required fields or content."""


REQUIRED_FIELDS = [
    "Hypothesis",
    "Primary Metric",
    "Statistical Tests",
    "Minimum Effect Size",
    "Data Source",
    "Roll Convention",
    "Seed Policy",
    "Exclusion Rules",
    "Simulation Agents",
    "Passive Capital Scenarios",
    "Significance Threshold",
]


def validate_paper(path: str | Path) -> bool:
    """Validate that required PAPER.md sections exist and are non-empty."""
    paper_path = Path(path)
    if not paper_path.exists():
        raise ValidationError(f"PAPER file not found: {paper_path}")

    text = paper_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    sections: dict[str, list[str]] = {}
    current_section: str | None = None

    for line in lines:
        if line.startswith("## "):
            current_section = line[3:].strip()
            sections[current_section] = []
            continue

        if current_section is not None:
            sections[current_section].append(line)

    for field in REQUIRED_FIELDS:
        if field not in sections:
            raise ValidationError(f"Missing required field: {field}")

        content = "\n".join(sections[field]).strip()
        if not content:
            raise ValidationError(f"Field is empty: {field}")

    print("✅ PAPER.md valid")
    return True
