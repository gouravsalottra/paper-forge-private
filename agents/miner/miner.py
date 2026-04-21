"""Download commodity futures data and produce returns + data passport."""

from __future__ import annotations

import hashlib
import json
import importlib.metadata
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

TICKERS = {
    "CL=F": "crude_oil_wti",
    "GC=F": "gold",
    "ZC=F": "corn",
    "NG=F": "natural_gas",
    "HG=F": "copper",
}

START_DATE = "2010-01-01"
END_DATE_EXCLUSIVE = "2024-01-01"  # includes data through 2023-12-31
START = START_DATE
END = END_DATE_EXCLUSIVE
OUTPUT_DIR = Path("outputs")
RETURNS_CSV = OUTPUT_DIR / "commodity_returns.csv"
PASSPORT_JSON = OUTPUT_DIR / "data_passport.json"


def download_close_series(ticker: str) -> pd.Series:
    df = yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        close = df["Close"].iloc[:, 0]
    else:
        close = df["Close"]
    close.name = ticker
    return close.dropna()


def build_returns_frame() -> pd.DataFrame:
    close_df = pd.concat([download_close_series(t) for t in TICKERS], axis=1, join="inner")
    close_df = close_df.sort_index()

    returns = np.log(close_df / close_df.shift(1)).dropna()
    returns = returns.rename(columns=TICKERS)
    returns.index.name = "date"
    return returns


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_data_passport(returns: pd.DataFrame) -> dict:
    passport = {
        "file": str(RETURNS_CSV),
        "sha256": sha256_file(RETURNS_CSV),
        "row_count": int(len(returns)),
        "date_range": {
            "start": START_DATE,
            "end": "2023-12-31",
        },
        "actual_date_range": {
            "start": returns.index.min().strftime("%Y-%m-%d") if not returns.empty else None,
            "end": returns.index.max().strftime("%Y-%m-%d") if not returns.empty else None,
        },
        "download_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "tickers": TICKERS,
        "library_versions": {
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "yfinance": _get_version("yfinance"),
        },
        "roll_convention": "ratio_backward",
        "adjustment_method": "ratio_backward",
    }
    PASSPORT_JSON.write_text(json.dumps(passport, indent=2), encoding="utf-8")
    return passport


def write_data_passport_generic(df: pd.DataFrame, path: Path, source: str) -> dict:
    passport = {
        "file": str(path),
        "sha256": sha256_file(path),
        "row_count": int(len(df)),
        "source": source,
        "download_timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "library_versions": {
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    PASSPORT_JSON.write_text(json.dumps(passport, indent=2), encoding="utf-8")
    return passport


def select_data_source(require_wrds: bool = True, wrds_available: bool = False) -> str:
    """Choose miner source with WRDS-first policy.

    If require_wrds is True and WRDS is unavailable, this raises to avoid silent fallback.
    """
    if require_wrds and not wrds_available:
        raise RuntimeError("WRDS required by policy but unavailable.")
    return "wrds" if wrds_available else "yfinance"


def run_miner_pipeline(run_id: str, output_dir: str = "paper_memory", source: str = "wrds") -> dict:
    """Run miner stage with explicit source contract."""
    if source not in {"wrds", "yfinance"}:
        raise ValueError("source must be 'wrds' or 'yfinance'")

    out_dir = Path(output_dir) / run_id
    out_dir.mkdir(parents=True, exist_ok=True)
    if source == "wrds":
        try:
            from agents.miner.sources.wrds_src import fetch as wrds_fetch

            config = {
                "kind": "ff_factors",
                "start": START_DATE,
                "end": END_DATE_EXCLUSIVE,
            }
            df = wrds_fetch(config)
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            returns_path = OUTPUT_DIR / "commodity_returns_wrds.csv"
            df.to_csv(returns_path, index=False)
            write_data_passport_generic(df, returns_path, source="wrds")
            return {"result_flag": "DONE", "source": "wrds", "path": str(returns_path)}
        except Exception as exc:
            raise RuntimeError(
                f"WRDS fetch failed: {exc}. "
                "Set PAPER_FORGE_MINER_SOURCE=yfinance to use the yfinance fallback."
            ) from exc

    returns = build_returns_frame()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    returns.to_csv(RETURNS_CSV)
    write_data_passport(returns)
    return {"result_flag": "DONE", "source": source, "path": str(RETURNS_CSV)}


def _get_version(pkg: str) -> str:
    try:
        return importlib.metadata.version(pkg)
    except Exception:
        return "unknown"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    returns = build_returns_frame()
    returns.to_csv(RETURNS_CSV)
    write_data_passport(returns)

    print("Saved:", RETURNS_CSV)
    print("Saved:", PASSPORT_JSON)
    print("\nSummary Stats (daily log returns):")
    print(returns.describe().T[["mean", "std", "min", "max"]])

    print("\nCorrelation Matrix:")
    print(returns.corr())


if __name__ == "__main__":
    main()
