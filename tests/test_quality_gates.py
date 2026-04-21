from __future__ import annotations

from agents.quill.quill import QuillAgent
from agents.scout.scout import ScoutAgent


def _doc_with_counts(refs: int, visuals: int) -> str:
    lines = [r"\section{Results} 1.23 4.56 7.89 10 11 12 13 14 15 16 17 18 19 20 21 22 23 24 25 26 27 28"]
    lines.extend([r"\begin{table}[htbp]\end{table}" for _ in range(visuals)])
    lines.extend([rf"\bibitem{{r{i}}} Reference {i}" for i in range(refs)])
    lines.append(r"\appendix")
    return "\n".join(lines)


def test_quill_quality_gate_passes() -> None:
    doc = _doc_with_counts(refs=25, visuals=8)
    QuillAgent._quality_gate(doc)


def test_quill_quality_gate_fails_on_references() -> None:
    doc = _doc_with_counts(refs=4, visuals=8)
    try:
        QuillAgent._quality_gate(doc)
    except ValueError as exc:
        assert "references too low" in str(exc)
    else:
        raise AssertionError("Expected quality gate failure")


def test_scout_rank_penalizes_irrelevant_domains(tmp_path) -> None:
    agent = ScoutAgent(run_id="r", paper_md_path=str(tmp_path / "PAPER.md"), output_dir=str(tmp_path))
    papers = [
        {
            "title": "Dynamic commodity futures momentum and liquidity risk",
            "abstract": "Empirical asset pricing study in commodity futures with volatility and correlation.",
            "year": 2022,
            "venue": "Review of Financial Studies",
        },
        {
            "title": "Non-relativistic conformal field theory in momentum space",
            "abstract": "Quantum and particle physics theoretical framework.",
            "year": 2024,
            "venue": "Physics Letters",
        },
    ]
    ranked = agent._rank_papers(papers)
    assert "commodity futures" in ranked[0]["title"].lower()
