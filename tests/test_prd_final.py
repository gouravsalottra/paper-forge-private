from __future__ import annotations

from pathlib import Path

SECTIONS = [
    "1. Product Definition",
    "2. Problem Statements",
    "3. Product Principles",
    "4. Target Users and Willingness to Pay",
    "5. The Research Integrity System",
    "6. The Agent System",
    "7. The Reviewer Agent Gate",
    "8. The Repair Agent Contract",
    "9. Finance Sub-domains",
    "10. Screen-by-Screen User Journey",
    "11. Session History and Resumption",
    "12. Failure State Catalogue",
    "13. Co-Author Permission Model",
    "14. Backend Truth Matrix",
    "15. Agent Execution Graph",
    "16. Research Memory Artifact Store",
    "17. Monetization Architecture",
    "18. Azure Infrastructure Map",
]


def test_final_prd_exists_with_required_sections_in_order() -> None:
    text = Path("THRIVARC_PRD_FINAL.md").read_text(encoding="utf-8")
    positions = []
    for section in SECTIONS:
        assert f"## {section}" in text
        positions.append(text.index(f"## {section}"))
    assert positions == sorted(positions)
    assert "Paper is earned not default. The gate decides." in text
    assert "Writer is last and never invents numbers" in text
    assert "gpt-4o" in text
    assert "PostgreSQL" in text
    assert "Azure Blob Storage" in text
    assert "Server-Sent Events" in text
    assert "[v2]" in text
