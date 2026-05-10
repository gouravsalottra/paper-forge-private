from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.aria.exceptions import StructuredOutputError
from agents.codeaudit.codeaudit import CodeAuditResult, CodecAgent
from agents.reviewer.reviewer import ReviewerAgent, HawkReview


def test_hawk_review_parses_valid_response() -> None:
    raw = json.dumps(
        {
            "result_flag": "REVISION_REQUESTED",
            "methodology_score": 7.8,
            "mandatory_revision_items": ["Clarify identification assumptions."],
            "approved_for_quill": False,
            "reasoning": "Methods are plausible but currently under-justified.",
        }
    )
    parsed = ReviewerAgent._parse_hawk_review_response(raw)
    assert isinstance(parsed, HawkReview)
    assert parsed.result_flag == "REVISION_REQUESTED"


def test_hawk_review_raises_on_malformed_response() -> None:
    with pytest.raises(StructuredOutputError):
        ReviewerAgent._parse_hawk_review_response("not-json")


def test_codeaudit_result_parses_valid_response() -> None:
    raw = json.dumps(
        {
            "verdict": "PASS",
            "mismatches": [
                {
                    "location_in_code": "agents/miner/miner.py:10",
                    "location_in_spec": "PAPER.md:Data Source",
                    "nature": "Documentation mismatch only",
                    "auto_fixable": True,
                }
            ],
            "unverified_params": [],
        }
    )
    parsed = CodecAgent._parse_codeaudit_result(raw)
    assert isinstance(parsed, CodeAuditResult)
    assert parsed.verdict == "PASS"
