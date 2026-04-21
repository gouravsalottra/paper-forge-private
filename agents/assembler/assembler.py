"""Assemble a full LaTeX paper draft from pipeline artifacts."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

OUTPUT_DIR = Path("outputs")

TABLE1_PATH = OUTPUT_DIR / "table1_summary_stats.tex"
TABLE2_PATH = OUTPUT_DIR / "table2_correlation_summary.tex"
NARRATIVE_PATH = OUTPUT_DIR / "findings_narrative.txt"
FIG1_PATH = OUTPUT_DIR / "fig1_rolling_correlations.png"
FIG2_PATH = OUTPUT_DIR / "fig2_correlation_heatmap.png"

PAPER_PATH = OUTPUT_DIR / "paper_draft.tex"
PASSPORT_PATH = OUTPUT_DIR / "assembler_passport.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ensure_inputs() -> list[Path]:
    required = [TABLE1_PATH, TABLE2_PATH, NARRATIVE_PATH, FIG1_PATH, FIG2_PATH]
    missing = [p for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required inputs: {[str(m) for m in missing]}")
    return required


def _read_narrative_paragraphs(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8").strip()
    paragraphs = [p.strip().replace("\n", " ") for p in text.split("\n\n") if p.strip()]
    return paragraphs


def _abstract_from_paras(p1: str, p2: str, max_words: int = 150) -> str:
    words = (p1 + " " + p2).split()
    clipped = words[:max_words]
    return " ".join(clipped)


def build_latex(paragraphs: list[str]) -> str:
    para1 = paragraphs[0] if len(paragraphs) > 0 else "Data description not available."
    para2 = paragraphs[1] if len(paragraphs) > 1 else "Correlation findings not available."
    para3 = paragraphs[2] if len(paragraphs) > 2 else "Regime instability findings not available."

    abstract = _abstract_from_paras(para1, para2, max_words=150)

    # Paths are relative to outputs/paper_draft.tex
    fig1_file = FIG1_PATH.name
    fig2_file = FIG2_PATH.name
    table1_file = TABLE1_PATH.name
    table2_file = TABLE2_PATH.name

    return rf"""\documentclass[11pt]{{article}}
\usepackage[margin=1in]{{geometry}}
\usepackage{{setspace}}
\usepackage{{graphicx}}
\usepackage{{booktabs}}
\usepackage{{longtable}}
\usepackage{{float}}
\usepackage{{hyperref}}
\usepackage{{caption}}

\title{{Dynamic Correlation Regimes in Major Commodity Futures Markets}}
\author{{Paper Forge Research Pipeline}}
\date{{\today}}

\begin{{document}}
\maketitle

\begin{{abstract}}
{abstract}
\end{{abstract}}

\section{{Introduction}}
Understanding time-varying cross-commodity dependence is central to portfolio construction, risk budgeting,
and stress-testing in futures markets. Correlation structure is not static: macro cycles, policy regimes,
and inventory shocks can induce abrupt changes in co-movement. This paper studies dynamic dependence
across key commodity contracts and evaluates both smooth evolution and discrete structural shifts.

\section{{Data}}
{para1}

Table~\ref{{tab:summary_stats}} reports distributional properties of daily log returns for the commodity panel.
\input{{{table1_file}}}

\section{{Methodology}}
We estimate dependence with three complementary approaches. First, we compute rolling 252-day pairwise
correlations to capture medium-horizon variation in co-movement. Second, we apply structural break detection
using the PELT algorithm with an RBF cost and quarterly minimum segment length to identify regime boundaries.
Third, we estimate DCC-GARCH(1,1) dynamics by fitting univariate GARCH(1,1) models to each return series,
extracting standardized residuals, and recursively estimating the dynamic conditional correlation process.

\section{{Results}}
Table~\ref{{tab:correlation_summary}} summarizes average rolling correlations, break counts, and DCC mean correlations.
\input{{{table2_file}}}

\begin{{figure}}[H]
    \centering
    \includegraphics[width=\textwidth]{{{fig1_file}}}
    \caption{{Rolling 252-day pairwise correlations with detected break dates.}}
    \label{{fig:rolling}}
\end{{figure}}

\begin{{figure}}[H]
    \centering
    \includegraphics[width=0.8\textwidth]{{{fig2_file}}}
    \caption{{Average pairwise correlation heatmap.}}
    \label{{fig:heatmap}}
\end{{figure}}

{para2}

\section{{Conclusion}}
{para3}

\begin{{thebibliography}}{{99}}
\bibitem{{engle2002dcc}}
Engle, R. (2002). Dynamic conditional correlation: A simple class of multivariate GARCH models. \emph{{Journal of Business \& Economic Statistics}}, 20(3), 339--350.

\bibitem{{bollerslev1990}}
Bollerslev, T. (1990). Modelling the coherence in short-run nominal exchange rates: A multivariate generalized ARCH model. \emph{{Review of Economics and Statistics}}, 72(3), 498--505.

\bibitem{{killick2012pelt}}
Killick, R., Fearnhead, P., \& Eckley, I. A. (2012). Optimal detection of changepoints with a linear computational cost. \emph{{Journal of the American Statistical Association}}, 107(500), 1590--1598.

\bibitem{{patton2012copula}}
Patton, A. J. (2012). A review of copula models for economic time series. \emph{{Journal of Multivariate Analysis}}, 110, 4--18.

\bibitem{{aielli2013dcc}}
Aielli, G. P. (2013). Dynamic conditional correlation: On properties and estimation. \emph{{Journal of Business \& Economic Statistics}}, 31(3), 282--299.
\end{{thebibliography}}

\end{{document}}
"""


def write_passport(inputs: list[Path]) -> None:
    outputs = [PAPER_PATH]
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {p.name: {"path": str(p), "sha256": _sha256(p)} for p in inputs},
        "outputs": {p.name: {"path": str(p), "sha256": _sha256(p)} for p in outputs},
    }
    PASSPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    inputs = _ensure_inputs()
    paragraphs = _read_narrative_paragraphs(NARRATIVE_PATH)
    paper = build_latex(paragraphs)
    PAPER_PATH.write_text(paper, encoding="utf-8")
    write_passport(inputs)

    print("Generated:", PAPER_PATH)
    print("Generated:", PASSPORT_PATH)


if __name__ == "__main__":
    main()
