from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

ROOT = Path(__file__).resolve().parents[1]
RUN_STORE = ROOT / "research_memory"
LEGACY_RUN_STORE = ROOT / ("paper" + "_memory")


def _run_dir(run_id: str) -> Path:
    path = RUN_STORE / run_id
    if not path.exists():
        path = LEGACY_RUN_STORE / run_id
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run artifacts not found")
    return path


def _read_csv_first(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(newline="", encoding="utf-8", errors="ignore") as handle:
        rows = list(csv.DictReader(handle))
    return rows[0] if rows else {}


def _float(value: Any, default: float | None = None) -> float | None:
    try:
        return float(value)
    except Exception:
        return default


@router.get("/runs/{run_id}/findings")
def findings(run_id: str) -> dict[str, Any]:
    path = _run_dir(run_id)
    stats_dir = path / "stats_tables"
    seed = _read_csv_first(stats_dir / "seed_consistency.csv")
    metric = _read_csv_first(stats_dir / "primary_metric.csv")
    p_value = _float(metric.get("p_value") or metric.get("primary_p_value") or seed.get("p_value"), None)
    significant = bool(p_value is not None and p_value < 0.05)
    validity = "SIGNIFICANT" if significant else "NULL" if p_value is not None else "INCONCLUSIVE"
    return {
        "findings": {
            "validity": validity,
            "summary": f"Primary analysis is {validity.lower()} based on available Paper Forge artifacts.",
            "p_value": p_value,
            "primary_p_value": p_value,
            "key_numbers": {"seed_consistency": seed, "primary_metric": metric},
        }
    }


@router.get("/runs/{run_id}/reviewer_report")
def reviewer_report(run_id: str) -> dict[str, Any]:
    path = _run_dir(run_id)
    text_path = path / "reviewer_report_v1.md"
    if not text_path.exists():
        text_path = path / "hawk_review_v1.md"
    score_path = path / "reviewer_scores_v1.json"
    if not score_path.exists():
        score_path = path / "hawk_scores_v1.json"
    narrative = text_path.read_text(encoding="utf-8", errors="ignore") if text_path.exists() else ""
    scores = json.loads(score_path.read_text(encoding="utf-8")) if score_path.exists() else {}
    score = scores.get("score") or scores.get("overall_score") or scores.get("research_quality_score")
    return {
        "score": score,
        "reviewer_narrative": narrative,
        "strengths": scores.get("strengths") if isinstance(scores.get("strengths"), list) else [],
        "weaknesses": scores.get("weaknesses") if isinstance(scores.get("weaknesses"), list) else [],
    }


@router.get("/runs/{run_id}/charts")
def charts(run_id: str) -> dict[str, list[dict[str, str]]]:
    path = _run_dir(run_id)
    items = []
    for png in sorted(path.glob("*.png")):
        items.append({"title": png.stem.replace("_", " ").title(), "url": f"/runs/{run_id}/files/{png.name}", "alt": png.stem})
    return {"charts": items}


@router.get("/runs/{run_id}/tables")
def tables(run_id: str) -> dict[str, list[dict[str, str]]]:
    stats_dir = _run_dir(run_id) / "stats_tables"
    items = []
    if stats_dir.exists():
        for csv_path in sorted(stats_dir.glob("*.csv")):
            items.append({"caption": csv_path.stem.replace("_", " ").title(), "url": f"/runs/{run_id}/files/stats_tables/{csv_path.name}"})
    return {"tables": items}


@router.get("/runs/{run_id}/paper")
def paper(run_id: str) -> dict[str, Any]:
    path = _run_dir(run_id)
    draft = path / "paper_draft_v2.tex"
    if not draft.exists():
        draft = path / "paper_draft_v1.tex"
    text = draft.read_text(encoding="utf-8", errors="ignore") if draft.exists() else ""
    return {
        "paper": {
            "thrivarc": {
                "methodology": text[:4000],
                "results": text[4000:8000] if len(text) > 4000 else "",
            },
            "researcher": {
                "introduction_prompt": "500-800 words. Motivate the question, contribution, and finance context.",
                "literature_review_prompt": "300-500 words. Position the result against the closest empirical finance literature.",
                "conclusion_prompt": "300-400 words. Summarize evidence, limitations, and next tests.",
            },
        }
    }


@router.get("/runs/{run_id}/files/{filename:path}")
def run_file(run_id: str, filename: str) -> FileResponse:
    base = _run_dir(run_id).resolve()
    target = (base / filename).resolve()
    if not str(target).startswith(str(base)) or not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(target)
