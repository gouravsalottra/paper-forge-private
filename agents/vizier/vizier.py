"""VIZIER: publication-ready visualization pipeline."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

OUTPUT_DIR = Path("outputs")
ROLLING_PATH = OUTPUT_DIR / "rolling_correlations.csv"
REGIMES_PATH = OUTPUT_DIR / "correlation_regimes.csv"
SUMMARY_PATH = OUTPUT_DIR / "analyst_summary.csv"
RETURNS_PATH = OUTPUT_DIR / "commodity_returns.csv"

FIG1_PNG = OUTPUT_DIR / "fig1_rolling_correlations.png"
FIG1_PDF = OUTPUT_DIR / "fig1_rolling_correlations.pdf"
FIG2_PNG = OUTPUT_DIR / "fig2_correlation_heatmap.png"
FIG2_PDF = OUTPUT_DIR / "fig2_correlation_heatmap.pdf"
FIG3_PNG = OUTPUT_DIR / "fig3_cumulative_returns.png"
FIG3_PDF = OUTPUT_DIR / "fig3_cumulative_returns.pdf"
PASSPORT_PATH = OUTPUT_DIR / "vizier_passport.json"


def _ensure_inputs() -> None:
    required = [ROLLING_PATH, SUMMARY_PATH, RETURNS_PATH]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError(f"Missing required inputs: {missing}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def figure1_rolling_correlations(rolling: pd.DataFrame, regimes: pd.DataFrame) -> None:
    pairs = sorted(rolling["pair"].dropna().unique().tolist())
    if len(pairs) != 10:
        # Still support plotting whatever is present, but keep a stable 2x5 layout.
        pairs = pairs[:10]

    fig, axes = plt.subplots(2, 5, figsize=(24, 9), sharex=True, sharey=True)
    axes = axes.flatten()

    for i, pair in enumerate(pairs):
        ax = axes[i]
        sub = rolling.loc[rolling["pair"] == pair].sort_values("date")
        ax.plot(sub["date"], sub["correlation"], linewidth=1.4, color="#1f77b4")

        if not regimes.empty:
            rsub = regimes.loc[regimes["pair"] == pair]
            for d in rsub["break_date"]:
                ax.axvline(d, color="#d62728", linestyle="--", linewidth=0.8, alpha=0.6)

        ax.set_title(pair.replace("__", " vs "), fontsize=10)
        ax.grid(alpha=0.25, linewidth=0.6)
        ax.set_ylim(-1.0, 1.0)
        ax.xaxis.set_major_locator(mdates.YearLocator(4))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))

    # Hide unused axes if fewer than 10 pairs.
    for j in range(len(pairs), len(axes)):
        axes[j].axis("off")

    fig.suptitle("Figure 1. Rolling 252-Day Pairwise Correlations", fontsize=16, y=0.99)
    fig.supxlabel("Date")
    fig.supylabel("Correlation")
    fig.tight_layout(rect=[0, 0.02, 1, 0.96])
    fig.savefig(FIG1_PNG, dpi=300, bbox_inches="tight")
    fig.savefig(FIG1_PDF, bbox_inches="tight")
    plt.close(fig)


def _build_corr_matrix(summary: pd.DataFrame, assets: list[str]) -> pd.DataFrame:
    matrix = pd.DataFrame(np.eye(len(assets)), index=assets, columns=assets)
    for _, row in summary.iterrows():
        pair = str(row["pair"])
        if "__" not in pair:
            continue
        a, b = pair.split("__", 1)
        if a in matrix.index and b in matrix.columns:
            v = float(row["mean_rolling_corr"])
            matrix.loc[a, b] = v
            matrix.loc[b, a] = v
    return matrix


def figure2_heatmap(summary: pd.DataFrame, returns: pd.DataFrame) -> None:
    assets = [c for c in returns.columns if c != "date"]
    corr_matrix = _build_corr_matrix(summary, assets)

    fig, ax = plt.subplots(figsize=(9, 7))
    sns.heatmap(
        corr_matrix,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        vmin=-1,
        vmax=1,
        square=True,
        linewidths=0.6,
        cbar_kws={"label": "Average Rolling Correlation"},
        ax=ax,
    )
    ax.set_title("Figure 2. Average Pairwise Correlation Heatmap", fontsize=14)
    plt.xticks(rotation=30, ha="right")
    plt.yticks(rotation=0)
    plt.tight_layout()

    fig.savefig(FIG2_PNG, dpi=300, bbox_inches="tight")
    fig.savefig(FIG2_PDF, bbox_inches="tight")
    plt.close(fig)


def figure3_cumulative_returns(returns: pd.DataFrame) -> None:
    r = returns.copy()
    value_cols = [c for c in r.columns if c != "date"]

    # Input returns are daily log returns; cumulative gross return = exp(cumsum(log returns)).
    cumulative = np.exp(r[value_cols].cumsum())

    fig, ax = plt.subplots(figsize=(12, 7))
    for col in value_cols:
        ax.plot(r["date"], cumulative[col], linewidth=1.5, label=col)

    ax.set_yscale("log")
    ax.set_title("Figure 3. Cumulative Commodity Returns (2010–2023)", fontsize=14)
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative Gross Return (log scale)")
    ax.grid(alpha=0.25, linewidth=0.6)
    ax.legend(frameon=False, ncol=2)
    ax.xaxis.set_major_locator(mdates.YearLocator(2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    plt.tight_layout()

    fig.savefig(FIG3_PNG, dpi=300, bbox_inches="tight")
    fig.savefig(FIG3_PDF, bbox_inches="tight")
    plt.close(fig)


def write_passport(rolling: pd.DataFrame, summary: pd.DataFrame, returns: pd.DataFrame) -> None:
    files = {
        "fig1_png": FIG1_PNG,
        "fig1_pdf": FIG1_PDF,
        "fig2_png": FIG2_PNG,
        "fig2_pdf": FIG2_PDF,
        "fig3_png": FIG3_PNG,
        "fig3_pdf": FIG3_PDF,
    }

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "inputs": {
            "rolling_correlations_rows": int(len(rolling)),
            "analyst_summary_rows": int(len(summary)),
            "commodity_returns_rows": int(len(returns)),
        },
        "files": {
            name: {
                "path": str(path),
                "sha256": _sha256(path),
            }
            for name, path in files.items()
        },
    }

    PASSPORT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    _ensure_inputs()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    rolling = pd.read_csv(ROLLING_PATH, parse_dates=["date"])
    summary = pd.read_csv(SUMMARY_PATH)
    returns = pd.read_csv(RETURNS_PATH, parse_dates=["date"]).sort_values("date")

    if REGIMES_PATH.exists():
        regimes = pd.read_csv(REGIMES_PATH, parse_dates=["break_date"])
    else:
        regimes = pd.DataFrame(columns=["pair", "break_date", "break_index"])

    figure1_rolling_correlations(rolling=rolling, regimes=regimes)
    figure2_heatmap(summary=summary, returns=returns)
    figure3_cumulative_returns(returns=returns)
    write_passport(rolling=rolling, summary=summary, returns=returns)

    print("Generated:", FIG1_PNG)
    print("Generated:", FIG1_PDF)
    print("Generated:", FIG2_PNG)
    print("Generated:", FIG2_PDF)
    print("Generated:", FIG3_PNG)
    print("Generated:", FIG3_PDF)
    print("Generated:", PASSPORT_PATH)


if __name__ == "__main__":
    main()
