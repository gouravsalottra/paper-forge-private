"""FRED adapter."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from fredapi import Fred

OUTPUT_DIR = Path("outputs")
PASSPORT_PATH = OUTPUT_DIR / "fred_passport.json"


def _sha256_df(df: pd.DataFrame) -> str:
    payload = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_passport(df: pd.DataFrame, series_ids: list[str], start: str, end: str) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    passport = {
        "sha256": _sha256_df(df),
        "row_count": int(len(df)),
        "series_names": series_ids,
        "date_range": {"start": start, "end": end},
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    PASSPORT_PATH.write_text(json.dumps(passport, indent=2), encoding="utf-8")
    return passport


def fetch(config: dict[str, Any]) -> pd.DataFrame:
    """Fetch FRED time series as long DataFrame: [date, series_name, value]."""
    series_ids = list(config.get("series_ids", []))
    start = config.get("start")
    end = config.get("end")
    api_key = config.get('api_key') or os.environ.get('FRED_API_KEY') or 'f75fabefc0fc70f5e9e6e49d824da214'

    if not series_ids:
        raise ValueError("config['series_ids'] is required and must be non-empty.")
    if not start or not end:
        raise ValueError("config['start'] and config['end'] are required.")
    if not api_key:
        raise ValueError("FRED API key missing. Set config['api_key'] or env var FRED_API_KEY.")

    fred = Fred(api_key=api_key)
    frames: list[pd.DataFrame] = []

    for series_id in series_ids:
        s = fred.get_series(series_id, observation_start=start, observation_end=end)
        if s is None:
            continue
        series = pd.Series(s).dropna()
        if series.empty:
            continue
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(series.index).strftime("%Y-%m-%d"),
                "series_name": series_id,
                "value": pd.to_numeric(series.values, errors="coerce"),
            }
        )
        df = df.dropna(subset=["value"])
        frames.append(df)

    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=["date", "series_name", "value"])
    _write_passport(out, series_ids, start, end)
    return out
