from __future__ import annotations

from pathlib import Path


PRD = Path("THRIVARC_PRD_V1_MENTOR_READY.md")


def test_mentor_ready_prd_exists_and_covers_required_product_layers() -> None:
    text = PRD.read_text(encoding="utf-8")
    required_sections = [
        "## 3. Screen-By-Screen User Journey",
        "## 4. Buyer Segments And Willingness To Pay",
        "## 5. Monetization Architecture",
        "## 6. Co-Author Permission Model",
        "## 7. Session History And Resumption",
        "## 8. Failure State Catalogue",
        "## 9. Pre-Registration Certificate Document",
        "## 10. DataPassport Document",
        "## 11. Deviation Register UI",
        "## 12. Finance Sub-Domains And Agent Behavior",
        "## 13. Agent Execution Graph",
        "## 14. research_memory Write Contracts",
    ]
    for section in required_sections:
        assert section in text


def test_user_journey_specifies_human_moments_not_only_api_contracts() -> None:
    text = PRD.read_text(encoding="utf-8")
    required_phrases = [
        "What the researcher sees:",
        "What the researcher does:",
        "System behavior:",
        "Failure state:",
        "Paper gate state",
        "Final Download Package",
        "Session History",
        "Co-Author Workspace",
    ]
    for phrase in required_phrases:
        assert phrase in text


def test_artifact_documents_are_human_readable_not_raw_json_only() -> None:
    text = PRD.read_text(encoding="utf-8")
    required_phrases = [
        "Plain-English opening:",
        "HTML and PDF for humans.",
        "JSON for machine verification.",
        "Risk-manager/editor language:",
        "Verification instruction:",
        "OSF/AEA compatibility:",
    ]
    for phrase in required_phrases:
        assert phrase in text
