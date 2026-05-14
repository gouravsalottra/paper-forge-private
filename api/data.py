from __future__ import annotations

import hashlib
import io
import os
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf
from fastapi import APIRouter, File, HTTPException, UploadFile
from storage.blob import read_artifact, write_artifact

router = APIRouter()

ROOT = Path(__file__).resolve().parents[1]


@router.post("/api/data/upload")
@router.post("/data/upload")
async def upload(file: UploadFile = File(...), run_id: str | None = None) -> dict[str, Any]:
    safe_name = Path(file.filename or "upload.bin").name
    content = await file.read()
    session_id = run_id or "staged-upload"
    ref = write_artifact(session_id, f"uploads/{safe_name}", content)
    return {
        "upload_path": ref["blob_path"],
        "filename": safe_name,
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "storage_backend": ref["backend"],
    }


def _read_upload(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    return pd.read_csv(path)


def _read_upload_bytes(filename: str, content: bytes) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    buffer = io.BytesIO(content)
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(buffer)
    if suffix == ".parquet":
        return pd.read_parquet(buffer)
    return pd.read_csv(buffer)


def _blob_upload(upload_path: str) -> tuple[str, str] | None:
    clean = str(upload_path).strip().strip("/")
    parts = clean.split("/")
    if len(parts) >= 3 and parts[0] == "sessions":
        return parts[1], "/".join(parts[2:])
    return None


def _date_range(df: pd.DataFrame, fallback: str) -> tuple[str, list[str]]:
    date_columns = [
        col
        for col in df.columns
        if any(token in str(col).lower() for token in ["date", "time", "timestamp", "period"])
    ]
    for col in date_columns:
        parsed = pd.to_datetime(df[col], errors="coerce")
        parsed = parsed.dropna()
        if not parsed.empty:
            return f"{parsed.min().date()} to {parsed.max().date()}", date_columns
    return fallback, date_columns


def _schema_profile(df: pd.DataFrame, date_columns: list[str]) -> dict[str, Any]:
    missingness = {
        str(col): round(float(df[col].isna().mean()), 4)
        for col in df.columns
    }
    identifier_columns = [
        str(col)
        for col in df.columns
        if any(token in str(col).lower() for token in ["ticker", "symbol", "permno", "cusip", "isin", "id"])
    ]
    numeric_columns = [str(col) for col in df.select_dtypes(include="number").columns]
    return {
        "rows": int(len(df)),
        "columns": [str(col) for col in df.columns],
        "dtypes": {str(col): str(dtype) for col, dtype in df.dtypes.items()},
        "missingness": missingness,
        "date_columns": date_columns,
        "identifier_columns": identifier_columns,
        "numeric_columns": numeric_columns,
    }


def _quality_status(df: pd.DataFrame, profile: dict[str, Any]) -> tuple[str, list[str], list[str]]:
    blocking: list[str] = []
    warnings: list[str] = []
    if df.empty:
        blocking.append("No rows were available for preview.")
    if not profile.get("date_columns"):
        warnings.append("No obvious date or timestamp column was detected.")
    if not profile.get("numeric_columns"):
        warnings.append("No numeric measurement columns were detected.")
    missingness = profile.get("missingness") or {}
    high_missing = [col for col, rate in missingness.items() if float(rate) > 0.2]
    warn_missing = [col for col, rate in missingness.items() if 0.05 < float(rate) <= 0.2]
    if high_missing:
        blocking.append(f"High missingness above 20 percent: {', '.join(high_missing[:6])}.")
    if warn_missing:
        warnings.append(f"Moderate missingness above 5 percent: {', '.join(warn_missing[:6])}.")
    return ("blocked" if blocking else "ready"), blocking, warnings


def _preview_payload(df: pd.DataFrame, *, source_route: str, date_range: str, sha: str) -> dict[str, Any]:
    date_columns: list[str]
    date_range, date_columns = _date_range(df, date_range)
    profile = _schema_profile(df, date_columns)
    status, blocking, warnings = _quality_status(df, profile)
    columns = [str(col) for col in df.columns]
    return {
        "rows": int(len(df)),
        "columns": columns,
        "date_range": date_range,
        "sha256": sha,
        "sample_rows": df.head(5).where(pd.notnull(df), None).to_dict(orient="records"),
        "data_quality": "good" if status == "ready" and not warnings else "needs_attention" if status == "ready" else "blocked",
        "preview_status": status,
        "blocking_issues": blocking,
        "warnings": warnings,
        "schema_profile": profile,
        "data_passport": {
            "source_route": source_route,
            "rows": int(len(df)),
            "columns": columns,
            "date_range": date_range,
            "sha256": sha,
            "plain_english_summary": [
                f"Thrivarc previewed {len(df)} rows from {source_route}.",
                f"The evidence fingerprint is {sha[:16]}...",
                "Compute remains blocked until this preview is accepted.",
            ],
        },
    }


@router.post("/api/data/preview")
@router.post("/data/preview")
def preview(payload: dict[str, Any]) -> dict[str, Any]:
    upload_path = payload.get("upload_path")
    data_mode = str(payload.get("data_mode") or payload.get("connector") or "").lower()
    if upload_path or data_mode == "upload":
        if not upload_path:
            return {"preview": _preview_payload(pd.DataFrame(), source_route="upload", date_range="unknown", sha=hashlib.sha256(b"").hexdigest())}
        blob_ref = _blob_upload(str(upload_path))
        if blob_ref:
            session_id, relative_path = blob_ref
            content = read_artifact(session_id, relative_path)
            df = _read_upload_bytes(Path(relative_path).name, content)
            return {"preview": _preview_payload(df, source_route="upload", date_range="uploaded file", sha=hashlib.sha256(content).hexdigest())}
        path = Path(str(upload_path)).expanduser()
        if os.getenv("ENVIRONMENT", os.getenv("APP_ENV", "development")).lower() == "production":
            raise HTTPException(status_code=400, detail="Production upload preview requires a Blob Storage upload path")
        if not path.exists() or not path.is_file():
            raise HTTPException(status_code=404, detail="Uploaded evidence file not found")
        df = _read_upload(path)
        content = path.read_bytes()
        return {"preview": _preview_payload(df, source_route="upload", date_range="uploaded file", sha=hashlib.sha256(content).hexdigest())}

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
    return {"preview": _preview_payload(df, source_route="yfinance", date_range=f"{start} to {end or 'latest'}", sha=sha)}
