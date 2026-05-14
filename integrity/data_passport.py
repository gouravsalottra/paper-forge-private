from __future__ import annotations

import hashlib
from typing import Any

from integrity.pdf import render_pdf
from storage.blob import write_artifact


def generate_data_passport(session_id: str, raw_data: bytes, metadata: dict[str, Any]) -> dict[str, Any]:
    raw_hash = hashlib.sha256(raw_data).hexdigest()
    clean_data = metadata.get("clean_data") if isinstance(metadata.get("clean_data"), bytes) else raw_data
    clean_hash = hashlib.sha256(clean_data).hexdigest()
    locked_at = str(metadata.get("locked_at") or "not yet locked")
    source_list = metadata.get("sources") or metadata.get("source") or ["researcher provided"]
    if not isinstance(source_list, list):
        source_list = [str(source_list)]
    row_count_before = int(metadata.get("row_count_before_exclusions", metadata.get("row_count", metadata.get("row_count_after_exclusions", 0))))
    row_count_after = int(metadata.get("row_count_after_exclusions", row_count_before))
    doc = {
        "plain_english_summary": (
            f"This DataPassport certifies that the data used in this research was locked on {locked_at} "
            f"and has not been modified since. The SHA-256 hash of the dataset is {clean_hash}. Any editor, "
            "reviewer, or compliance officer can verify that the data matches this certificate by computing "
            "the hash of the provided dataset file."
        ),
        "data_identity": {
            "sources": source_list,
            "source_parameters": metadata.get("source_parameters", {}),
            "date_range": metadata.get("date_range", "unknown"),
            "universe": metadata.get("universe", metadata.get("tickers", [])),
            "frequency": metadata.get("frequency", "unknown"),
            "row_count_before_exclusions": row_count_before,
            "row_count_after_exclusions": row_count_after,
            "exclusions_applied": metadata.get("exclusions_applied", []),
        },
        "hashes": {
            "raw_data_sha256": raw_hash,
            "clean_data_sha256": clean_hash,
            "locked_at": locked_at,
        },
        "schema_profile": metadata.get("schema_profile", {"columns": metadata.get("columns", []), "missingness": metadata.get("missingness", {})}),
    }
    lines = [
        doc["plain_english_summary"],
        f"Sources: {', '.join(source_list)}",
        f"Date range: {doc['data_identity']['date_range']}",
        f"Frequency: {doc['data_identity']['frequency']}",
        f"Rows before exclusions: {row_count_before}",
        f"Rows after exclusions: {row_count_after}",
        f"Raw SHA-256: {raw_hash}",
        f"Clean SHA-256: {clean_hash}",
    ]
    return {
        "json": write_artifact(session_id, "03_data/data_passport.json", doc),
        "pdf": write_artifact(session_id, "03_data/data_passport.pdf", render_pdf("Thrivarc DataPassport", lines)),
    }
