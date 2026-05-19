from __future__ import annotations

import pytest

from agents.miner.sources.fred_src import fetch


def test_fred_fetch_requires_explicit_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    with pytest.raises(ValueError, match="FRED API key missing"):
        fetch(
            {
                "series_ids": ["DGS10"],
                "start": "2024-01-01",
                "end": "2024-01-31",
            }
        )
