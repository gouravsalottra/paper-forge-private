"""Test configuration: mock all LLM clients to prevent real API calls in tests."""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _block_real_api_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set dummy API keys so OpenAI client can initialize in unit tests."""
    if not os.environ.get("OPENAI_API_KEY"):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-placeholder-key-for-unit-tests")
    if not os.environ.get("OPENAI_API_KEY_PASS2"):
        monkeypatch.setenv("OPENAI_API_KEY_PASS2", "sk-test-placeholder-key-for-unit-tests")
