"""WRDS adapter."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import wrds

OUTPUT_DIR = Path("outputs")
PASSPORT_PATH = OUTPUT_DIR / "wrds_passport.json"


def _sha256_df(df: pd.DataFrame) -> str:
    payload = df.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _write_passport(df: pd.DataFrame, series_names: list[str], start: str, end: str) -> dict[str, Any]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    passport = {
        "sha256": _sha256_df(df),
        "row_count": int(len(df)),
        "series_names": series_names,
        "date_range": {"start": start, "end": end},
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    PASSPORT_PATH.write_text(json.dumps(passport, indent=2), encoding="utf-8")
    return passport


def fetch_crsp(permnos: list[int], start: str, end: str) -> pd.DataFrame:
    """Fetch CRSP daily returns as long DataFrame [date, series_name, value]."""
    if not permnos:
        raise ValueError("permnos must be non-empty")

    conn = wrds.Connection()
    query = """
        SELECT date, permno, ret
        FROM crsp.dsf
        WHERE permno = ANY(%(permnos)s)
          AND date BETWEEN %(start)s AND %(end)s
    """
    df = conn.raw_sql(query, params={"permnos": permnos, "start": start, "end": end}, date_cols=["date"])
    conn.close()

    if df.empty:
        out = pd.DataFrame(columns=["date", "series_name", "value"])
    else:
        out = pd.DataFrame(
            {
                "date": df["date"].dt.strftime("%Y-%m-%d"),
                "series_name": df["permno"].map(lambda x: f"crsp_permno_{int(x)}"),
                "value": pd.to_numeric(df["ret"], errors="coerce"),
            }
        ).dropna(subset=["value"])

    _write_passport(out, sorted(out["series_name"].unique().tolist()) if not out.empty else [], start, end)
    return out


def fetch_compustat(gvkeys: list[str], start: str, end: str) -> pd.DataFrame:
    """Fetch Compustat fundamentals as long DataFrame [date, series_name, value]."""
    if not gvkeys:
        raise ValueError("gvkeys must be non-empty")

    conn = wrds.Connection()
    query = """
        SELECT datadate, gvkey, at, sale, ni
        FROM comp.funda
        WHERE gvkey = ANY(%(gvkeys)s)
          AND datadate BETWEEN %(start)s AND %(end)s
    """
    df = conn.raw_sql(query, params={"gvkeys": gvkeys, "start": start, "end": end}, date_cols=["datadate"])
    conn.close()

    if df.empty:
        out = pd.DataFrame(columns=["date", "series_name", "value"])
    else:
        melted = df.melt(id_vars=["datadate", "gvkey"], value_vars=["at", "sale", "ni"], var_name="metric", value_name="value")
        melted = melted.dropna(subset=["value"])
        out = pd.DataFrame(
            {
                "date": melted["datadate"].dt.strftime("%Y-%m-%d"),
                "series_name": melted.apply(lambda r: f"comp_{r['gvkey']}_{r['metric']}", axis=1),
                "value": pd.to_numeric(melted["value"], errors="coerce"),
            }
        ).dropna(subset=["value"])

    _write_passport(out, sorted(out["series_name"].unique().tolist()) if not out.empty else [], start, end)
    return out


def fetch_ff_factors(start: str, end: str) -> pd.DataFrame:
    """Fetch Fama-French 5-factor daily table as long DataFrame [date, series_name, value]."""
    conn = wrds.Connection()
    query = """
        SELECT date, mktrf, smb, hml, rmw, cma, rf
        FROM ff.fivefactors_daily
        WHERE date BETWEEN %(start)s AND %(end)s
    """
    df = conn.raw_sql(query, params={"start": start, "end": end}, date_cols=["date"])
    conn.close()

    if df.empty:
        out = pd.DataFrame(columns=["date", "series_name", "value"])
    else:
        melted = df.melt(id_vars=["date"], value_vars=["mktrf", "smb", "hml", "rmw", "cma", "rf"], var_name="factor", value_name="value")
        melted = melted.dropna(subset=["value"])
        out = pd.DataFrame(
            {
                "date": melted["date"].dt.strftime("%Y-%m-%d"),
                "series_name": melted["factor"].map(lambda x: f"ff5_{x}"),
                "value": pd.to_numeric(melted["value"], errors="coerce"),
            }
        ).dropna(subset=["value"])

    _write_passport(out, sorted(out["series_name"].unique().tolist()) if not out.empty else [], start, end)
    return out


def fetch(config: dict[str, Any]) -> pd.DataFrame:
    """Dispatch WRDS fetch by config['kind']: 'crsp' | 'compustat' | 'ff_factors'."""
    kind = config.get("kind")
    start = config.get("start")
    end = config.get("end")

    if not start or not end:
        raise ValueError("config['start'] and config['end'] are required.")

    if kind == "crsp":
        return fetch_crsp(permnos=list(config.get("permnos", [])), start=start, end=end)
    if kind == "compustat":
        return fetch_compustat(gvkeys=list(config.get("gvkeys", [])), start=start, end=end)
    if kind == "ff_factors":
        return fetch_ff_factors(start=start, end=end)

    raise ValueError("config['kind'] must be one of: 'crsp', 'compustat', 'ff_factors'.")
