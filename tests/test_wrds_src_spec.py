from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

import agents.miner.sources.wrds_src as wrds_src


class _FakeConn:
    def raw_sql(self, query, params=None, date_cols=None):
        q = query.lower()
        if "from" in q and ("futures" in q or "wrds_fut_contract" in q):
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2000-01-03", "2000-01-03", "2000-01-04", "2000-01-04"]),
                    "series_name": ["crude_oil_wti", "natural_gas", "crude_oil_wti", "natural_gas"],
                    "settle": [25.0, 2.1, 25.5, 2.0],
                }
            )
        if "tfnbrpt" in q or "cot" in q:
            return pd.DataFrame(
                {
                    "date": pd.to_datetime(["2000-01-03", "2000-01-10"]),
                    "passive_concentration": [0.12, 0.18],
                }
            )
        return pd.DataFrame()

    def close(self):
        return None


def test_wrds_src_fetch_supports_futures_and_concentration(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wrds_src.wrds, "Connection", lambda *a, **k: _FakeConn(), raising=True)
    monkeypatch.setattr(wrds_src, "OUTPUT_DIR", tmp_path / "outputs", raising=False)
    monkeypatch.setattr(wrds_src, "PASSPORT_PATH", (tmp_path / "outputs" / "wrds_passport.json"), raising=False)

    fut = wrds_src.fetch({"kind": "futures", "start": "2000-01-01", "end": "2000-01-31"})
    assert not fut.empty
    assert {"date", "series_name", "value"}.issubset(fut.columns)
    assert set(fut["series_name"].unique()) == {"crude_oil_wti", "natural_gas"}

    conc = wrds_src.fetch({"kind": "concentration", "start": "2000-01-01", "end": "2000-01-31"})
    assert not conc.empty
    assert {"date", "series_name", "value"}.issubset(conc.columns)
    assert set(conc["series_name"].unique()) == {"passive_concentration"}
