"""SEC EDGAR search adapter."""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

OUTPUT_DIR = Path("outputs")
PASSPORT_PATH = OUTPUT_DIR / "sec_passport.json"
BASE_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
USER_AGENT = "paper-forge/1.0 (research@paper-forge.local)"

_LAST_REQUEST_TS = 0.0


def _throttle() -> None:
    global _LAST_REQUEST_TS
    now = time.monotonic()
    wait = 0.11 - (now - _LAST_REQUEST_TS)  # <= 10 req/sec
    if wait > 0:
        time.sleep(wait)
    _LAST_REQUEST_TS = time.monotonic()


def _rate_limited_get_json(url: str, params: dict[str, Any]) -> dict[str, Any]:
    _throttle()

    full_url = f"{url}?{urlencode(params)}"
    req = Request(full_url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload


def _fetch_text(url: str) -> str:
    if not url:
        return ""
    _throttle()
    req = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/plain, application/xml"})
    with urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8", errors="ignore")
    return text[:20000]


def _sha256_payload(records: list[dict[str, Any]]) -> str:
    raw = json.dumps(records, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _write_passport(records: list[dict[str, Any]], series_names: list[str], start: str, end: str) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dates = [r.get("date") for r in records if r.get("date")]
    passport = {
        "sha256": _sha256_payload(records),
        "row_count": int(len(records)),
        "series_names": series_names,
        "date_range": {
            "start": min(dates) if dates else start,
            "end": max(dates) if dates else end,
        },
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    PASSPORT_PATH.write_text(json.dumps(passport, indent=2), encoding="utf-8")
    return passport


def fetch_filing_text(cik: str, form_type: str, start: str, end: str) -> list[dict[str, str]]:
    """Return filings as list of {date, text, url}."""
    records: list[dict[str, str]] = []
    offset = 0
    page_size = 100

    while True:
        params = {
            "q": f"cik:{cik} AND formType:{form_type}",
            "dateRange": "custom",
            "startdt": start,
            "enddt": end,
            "from": offset,
            "size": page_size,
        }
        payload = _rate_limited_get_json(BASE_SEARCH_URL, params)
        hits = payload.get("hits", {}).get("hits", [])
        if not hits:
            break

        for hit in hits:
            src = hit.get("_source", {})
            filed_at = src.get("filedAt", "")
            filing_url = src.get("linkToFilingDetails") or src.get("linkToTxt") or ""
            text = _fetch_text(filing_url) if filing_url else ""
            if not text and isinstance(src, dict):
                text = json.dumps(src)

            # Basic cleanup for very noisy html-like payloads
            text = re.sub(r"\s+", " ", text).strip()
            records.append(
                {
                    "date": filed_at[:10] if filed_at else "",
                    "text": text,
                    "url": filing_url,
                }
            )

        if len(hits) < page_size:
            break
        offset += page_size

    _write_passport(records, [f"sec_{cik}_{form_type}"], start, end)
    return records


def fetch(config: dict[str, Any]) -> pd.DataFrame:
    """Fetch SEC filings and return DataFrame [date, series_name, value]."""
    cik = str(config.get("cik", "")).strip()
    form_type = str(config.get("form_type", "")).strip()
    start = config.get("start")
    end = config.get("end")

    if not cik or not form_type or not start or not end:
        raise ValueError("config requires 'cik', 'form_type', 'start', and 'end'.")

    records = fetch_filing_text(cik=cik, form_type=form_type, start=start, end=end)
    if not records:
        return pd.DataFrame(columns=["date", "series_name", "value"])

    df = pd.DataFrame(records)
    out = pd.DataFrame(
        {
            "date": df["date"],
            "series_name": f"sec_{cik}_{form_type}",
            "value": df["text"],
        }
    )
    return out
