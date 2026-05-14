from __future__ import annotations

from pathlib import Path

from api import data


def test_upload_preview_returns_schema_profile_and_datapassport(tmp_path: Path) -> None:
    source = tmp_path / "evidence.csv"
    source.write_text(
        "date,ticker,return,signal\n"
        "2024-01-02,SPY,0.01,0.2\n"
        "2024-01-03,SPY,-0.02,0.1\n",
        encoding="utf-8",
    )

    result = data.preview({"data_mode": "upload", "upload_path": str(source)})
    preview = result["preview"]

    assert preview["preview_status"] == "ready"
    assert preview["rows"] == 2
    assert preview["date_range"] == "2024-01-02 to 2024-01-03"
    assert preview["schema_profile"]["date_columns"] == ["date"]
    assert preview["schema_profile"]["identifier_columns"] == ["ticker"]
    assert "return" in preview["schema_profile"]["numeric_columns"]
    assert preview["data_passport"]["source_route"] == "upload"
    assert preview["data_passport"]["sha256"] == preview["sha256"]


def test_upload_preview_blocks_empty_or_unusable_file(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text("date,ticker,return\n", encoding="utf-8")

    result = data.preview({"data_mode": "upload", "upload_path": str(source)})
    preview = result["preview"]

    assert preview["preview_status"] == "blocked"
    assert preview["blocking_issues"]
