from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from agents.aria.aria import ConductorPipeline


def _mk(tmp_path: Path, run_id: str = "r-audit") -> ConductorPipeline:
    (tmp_path / "PAPER.md").write_text("## Topic\nx\n## Hypothesis\ny\n", encoding="utf-8")
    return ConductorPipeline(db_path=str(tmp_path / "pipeline.db"), run_id=run_id, paper_md_path=str(tmp_path / "PAPER.md"))


def test_next_tool_call_no_hardcoded_commodity_artifact(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = _mk(tmp_path)
    # If DATAPULL already done, missing outputs/commodity_returns.csv must not force DATAPULL.
    p._advance_phase("LITERATURE", "done")
    p._advance_phase("DATAPULL", "done")
    nxt = p._next_tool_call()
    assert nxt != "DATAPULL"


def test_publishability_forbidden_token_override(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = _mk(tmp_path)
    run_dir = Path("runs") / p.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # enough content
    body = " ".join(f"token{i}" for i in range(1800))
    tex = "\\begin{document}\n" + body + "\naria token present\n\\end{document}\n"
    (run_dir / "paper_draft_v1.tex").write_text(tex, encoding="utf-8")
    (run_dir / "hawk_review_v1.md").write_text("x" * 800, encoding="utf-8")
    monkeypatch.setenv("PAPER_COMPUTE_FORBIDDEN_TOKENS_OVERRIDE", "aria")
    monkeypatch.setenv("PAPER_COMPUTE_MIN_REVIEW_CYCLES", "0")
    assert p._paper_is_publishable(run_dir / "paper_draft_v1.tex") is True


def test_similarity_check_capped_to_first_40_paragraphs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = _mk(tmp_path)
    paras = ["para " + ("x " * 80) + str(i) for i in range(60)]
    text = "\n\n".join(paras)
    calls = {"n": 0}
    orig = p._cosine_sim

    def wrapped(a: str, b: str) -> float:
        calls["n"] += 1
        return orig(a, b)

    p._cosine_sim = wrapped  # type: ignore[assignment]
    p._has_high_similarity_paragraphs(text, threshold=0.99)
    # max pairs for 40 paragraphs = 780
    assert calls["n"] <= 780


def test_single_traceability_marker_constant() -> None:
    text = Path("agents/conductor/conductor.py").read_text(encoding="utf-8")
    assert text.count("CODEAUDIT_TRACEABILITY_MARKER") == 1


def test_writer_gate_not_blocked_by_forge_started_at(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    p = _mk(tmp_path)
    with sqlite3.connect(p.db_path) as conn:
        conn.execute(
            """
            INSERT INTO hypothesis_lock (run_id, locked_at, locked_by, pap_sha256, forge_started_at)
            VALUES (?, datetime('now'), 'PREREGISTER', 'abc', datetime('now'))
            """,
            (p.run_id,),
        )
        conn.execute(
            """
            INSERT INTO results_gate (run_id, p_value_passes, seed_consistent, codeaudit_clean, last_updated)
            VALUES (?, 1, 1, 1, datetime('now'))
            """,
            (p.run_id,),
        )
        conn.commit()
    # Should not raise: WRITER gate must depend on results_gate, not COMPUTE gate.
    p._check_writer_gate()
