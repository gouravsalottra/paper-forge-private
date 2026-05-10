"""WRDS futures + concentration adapter aligned to PAPER.md."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import wrds
import pandas_datareader.data as web

from agents.aria.exceptions import ServerUnavailableError

OUTPUT_DIR = Path("outputs")
PASSPORT_PATH = OUTPUT_DIR / "wrds_passport.json"


def _sha256_df(df: pd.DataFrame) -> str:
    payload = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_passport(df: pd.DataFrame, series_names: list[str], start: str, end: str, table_used: str) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    passport = {
        "sha256": _sha256_df(df),
        "row_count": int(len(df)),
        "series_names": series_names,
        "date_range": {"start": start, "end": end},
        "table_used": table_used,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    PASSPORT_PATH.write_text(json.dumps(passport, indent=2), encoding="utf-8")
    return passport


def fetch_futures(start: str, end: str) -> pd.DataFrame:
    """Fetch WRDS commodity futures proxy for CL/NG and return long frame [date, series_name, value]."""
    conn = wrds.Connection()
    queries: list[tuple[str, str]] = [
        (
            "comp.futures",
            """
            SELECT
                date,
                CASE
                    WHEN UPPER(contract_symbol) LIKE 'CL%%' THEN 'crude_oil_wti'
                    WHEN UPPER(contract_symbol) LIKE 'NG%%' THEN 'natural_gas'
                    ELSE UPPER(contract_symbol)
                END AS series_name,
                close AS settle
            FROM comp.futures
            WHERE date BETWEEN %(start)s AND %(end)s
              AND (UPPER(contract_symbol) LIKE 'CL%%' OR UPPER(contract_symbol) LIKE 'NG%%')
            ORDER BY date
            """,
        ),
        (
            "wrdssec.futures",
            """
            SELECT
                date,
                CASE
                    WHEN UPPER(ticker) LIKE 'CL%%' THEN 'crude_oil_wti'
                    WHEN UPPER(ticker) LIKE 'NG%%' THEN 'natural_gas'
                    ELSE UPPER(ticker)
                END AS series_name,
                settle AS settle
            FROM wrdssec.futures
            WHERE date BETWEEN %(start)s AND %(end)s
              AND (UPPER(ticker) LIKE 'CL%%' OR UPPER(ticker) LIKE 'NG%%')
            ORDER BY date
            """,
        ),
    ]
    params = {"start": start, "end": end}
    try:
        for table, query in queries:
            try:
                df = conn.raw_sql(query, params=params, date_cols=["date"])
            except Exception:
                continue
            if df.empty:
                continue
            out = pd.DataFrame(
                {
                    "date": pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"),
                    "series_name": df["series_name"].astype(str),
                    "value": pd.to_numeric(df["settle"], errors="coerce"),
                }
            ).dropna(subset=["value"])
            _write_passport(out, sorted(out["series_name"].unique().tolist()), start, end, table)
            return out
    finally:
        conn.close()

    out = pd.DataFrame(columns=["date", "series_name", "value"])
    _write_passport(out, [], start, end, "none")
    return out


def fetch_concentration(start: str, end: str) -> pd.DataFrame:
    """Fetch passive concentration series from COT-style WRDS tables."""
    conn = wrds.Connection()
    queries: list[tuple[str, str]] = [
        (
            "tfdata.tfnbrpt",
            """
            SELECT
                report_date AS date,
                CASE
                    WHEN open_interest_all = 0 THEN NULL
                    ELSE money_manager_long_all::float / open_interest_all::float
                END AS passive_concentration
            FROM tfdata.tfnbrpt
            WHERE report_date BETWEEN %(start)s AND %(end)s
              AND (
                    UPPER(market_and_exchange_names) LIKE '%%CRUDE OIL%%'
                 OR UPPER(market_and_exchange_names) LIKE '%%NATURAL GAS%%'
              )
            ORDER BY report_date
            """,
        ),
        (
            "cftc.tfnbrpt",
            """
            SELECT
                report_date AS date,
                CASE
                    WHEN open_interest_all = 0 THEN NULL
                    ELSE money_manager_long_all::float / open_interest_all::float
                END AS passive_concentration
            FROM cftc.tfnbrpt
            WHERE report_date BETWEEN %(start)s AND %(end)s
              AND (
                    UPPER(market_and_exchange_names) LIKE '%%CRUDE OIL%%'
                 OR UPPER(market_and_exchange_names) LIKE '%%NATURAL GAS%%'
              )
            ORDER BY report_date
            """,
        ),
    ]
    params = {"start": start, "end": end}
    try:
        for table, query in queries:
            try:
                df = conn.raw_sql(query, params=params, date_cols=["date"])
            except Exception:
                continue
            if df.empty:
                continue
            out = pd.DataFrame(
                {
                    "date": pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d"),
                    "series_name": "passive_concentration",
                    "value": pd.to_numeric(df["passive_concentration"], errors="coerce"),
                }
            ).dropna(subset=["value"])
            _write_passport(out, ["passive_concentration"], start, end, table)
            return out
    finally:
        conn.close()

    out = pd.DataFrame(columns=["date", "series_name", "value"])
    _write_passport(out, [], start, end, "none")
    return out


def fetch(config: dict[str, Any]) -> pd.DataFrame:
    """Dispatch WRDS fetch by config['kind']: 'futures' | 'concentration'."""
    kind = config.get("kind")
    start = config.get("start")
    end = config.get("end")

    if not start or not end:
        raise ValueError("config['start'] and config['end'] are required.")

    if kind == "futures":
        return fetch_futures(start=start, end=end)
    if kind == "concentration":
        return fetch_concentration(start=start, end=end)

    raise ValueError("config['kind'] must be one of: 'futures', 'concentration'.")


def fetch_ff_factors(start: str, end: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Fetch Fama-French daily factors from WRDS with Kenneth French fallback for dev mode."""
    source_mode = (__import__("os").environ.get("PAPER_FORGE_MINER_SOURCE", "wrds") or "wrds").lower()
    try:
        conn = wrds.Connection()
        try:
            df = conn.raw_sql(
                """
                SELECT date, mktrf, smb, hml, rf
                FROM ff.factors_daily
                WHERE date BETWEEN %(start)s AND %(end)s
                ORDER BY date
                """,
                params={"start": start, "end": end},
                date_cols=["date"],
            )
        finally:
            conn.close()
        out = pd.DataFrame(
            {
                "date": pd.to_datetime(df["date"]),
                "mkt_rf": pd.to_numeric(df["mktrf"], errors="coerce"),
                "smb": pd.to_numeric(df["smb"], errors="coerce"),
                "hml": pd.to_numeric(df["hml"], errors="coerce"),
                "rf": pd.to_numeric(df["rf"], errors="coerce"),
            }
        ).dropna()
        return out, {"ff_source": "wrds_ff_factors_daily"}
    except Exception as exc:
        if source_mode == "yfinance":
            ff = web.DataReader("F-F_Research_Data_Factors_daily", "famafrench", start, end)[0] / 100.0
            ff = ff.reset_index()
            date_col = ff.columns[0]
            out = pd.DataFrame(
                {
                    "date": pd.to_datetime(ff[date_col]),
                    "mkt_rf": pd.to_numeric(ff["Mkt-RF"], errors="coerce"),
                    "smb": pd.to_numeric(ff["SMB"], errors="coerce"),
                    "hml": pd.to_numeric(ff["HML"], errors="coerce"),
                    "rf": pd.to_numeric(ff["RF"], errors="coerce"),
                }
            ).dropna()
            return out, {"ff_source": "kenneth_french_library"}
        raise ServerUnavailableError(
            server_name="wrds_ff_factors",
            detail=f"WRDS unavailable and fallback disabled: {exc}",
            latency_ms=None,
        ) from exc
