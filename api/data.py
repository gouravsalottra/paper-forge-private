from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, File, UploadFile

router = APIRouter()

ROOT = Path(__file__).resolve().parents[1]
UPLOAD_DIR = ROOT / "research_memory" / "uploads"


@router.post("/data/upload")
async def upload(file: UploadFile = File(...)) -> dict[str, str]:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload.bin").name
    target = UPLOAD_DIR / safe_name
    content = await file.read()
    target.write_bytes(content)
    return {"upload_path": str(target)}


@router.post("/data/preview")
def preview(payload: dict[str, Any]) -> dict[str, Any]:
    symbols = payload.get("symbols") or ["SPY"]
    if isinstance(symbols, str):
        symbols = [s.strip() for s in symbols.split(",") if s.strip()]
    start = payload.get("start_date") or payload.get("date_from") or "2010-01-01"
    end = payload.get("end_date") or payload.get("date_to") or None
    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        hist = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=False)
        if hist is None or hist.empty:
            continue
        if isinstance(hist.columns, pd.MultiIndex):
            hist.columns = [str(col[0]) for col in hist.columns]
        frame = hist.reset_index()
        for _, row in frame.tail(10).iterrows():
            rows.append(
                {
                    "date": str(row.get("Date", ""))[:10],
                    "ticker": symbol,
                    "close": float(row["Close"]) if "Close" in row and pd.notna(row["Close"]) else None,
                    "volume": float(row["Volume"]) if "Volume" in row and pd.notna(row["Volume"]) else None,
                }
            )
    df = pd.DataFrame(rows)
    encoded = df.to_json(orient="records", date_format="iso").encode("utf-8")
    sha = hashlib.sha256(encoded).hexdigest()
    return {
        "preview": {
            "rows": int(len(df)),
            "columns": list(df.columns),
            "date_range": f"{start} to {end or 'latest'}",
            "sha256": sha,
            "sample_rows": df.head(5).to_dict(orient="records"),
            "data_quality": "good" if not df.empty else "missing",
        }
    }
