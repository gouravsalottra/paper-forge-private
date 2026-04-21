"""Writer stage: generate publication tables and findings narrative."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

INPUT_ANALYST_SUMMARY = Path("outputs/analyst_summary.csv")
INPUT_ROLLING = Path("outputs/rolling_correlations.csv")
INPUT_RETURNS = Path("outputs/commodity_returns.csv")

OUTPUT_TABLE1 = Path("outputs/table1_summary_stats.tex")
OUTPUT_TABLE2 = Path("outputs/table2_correlation_summary.tex")
OUTPUT_NARRATIVE = Path("outputs/findings_narrative.txt")
OUTPUT_PASSPORT = Path("outputs/writer_passport.json")


def _format_commodity_name(name: str) -> str:
    return name.replace("_", " ").title()


def _format_pair_name(pair: str) -> str:
    if "__" not in pair:
        return pair.replace("_", " ")
    left, right = pair.split("__", 1)
    return f"{_format_commodity_name(left)} / {_format_commodity_name(right)}"


def _ensure_inputs() -> None:
    for path in (INPUT_ANALYST_SUMMARY, INPUT_ROLLING, INPUT_RETURNS):
        if not path.exists():
            raise FileNotFoundError(f"Missing required input: {path}")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_table1_summary_stats(returns: pd.DataFrame) -> pd.DataFrame:
    value_cols = [c for c in returns.columns if c != "date"]
    rows = []
    for col in value_cols:
        s = pd.to_numeric(returns[col], errors="coerce").dropna()
        rows.append(
            {
                "Series": _format_commodity_name(col),
                "Mean": s.mean(),
                "Std": s.std(ddof=1),
                "Min": s.min(),
                "Max": s.max(),
                "Skew": s.skew(),
                "Kurtosis": s.kurt(),
            }
        )
    return pd.DataFrame(rows)


def to_latex_table(df: pd.DataFrame, caption: str, label: str, float_fmt: str = "%.4f") -> str:
    return df.to_latex(
        index=False,
        escape=True,
        caption=caption,
        label=label,
        float_format=(lambda x: float_fmt % x),
        na_rep="",
        longtable=False,
    )


def build_narrative(returns: pd.DataFrame, rolling: pd.DataFrame, analyst_summary: pd.DataFrame) -> str:
    returns = returns.copy()
    returns["date"] = pd.to_datetime(returns["date"])

    start_date = returns["date"].min().strftime("%Y-%m-%d")
    end_date = returns["date"].max().strftime("%Y-%m-%d")
    n_days = int(len(returns))
    n_assets = int(len([c for c in returns.columns if c != "date"]))

    top_corr = analyst_summary.sort_values("mean_rolling_corr", ascending=False).head(1).iloc[0]
    low_corr = analyst_summary.sort_values("mean_rolling_corr", ascending=True).head(1).iloc[0]
    top_pair = _format_pair_name(str(top_corr["pair"]))
    low_pair = _format_pair_name(str(low_corr["pair"]))

    avg_breaks = analyst_summary["regime_breaks"].mean()
    max_break_row = analyst_summary.sort_values("regime_breaks", ascending=False).head(1).iloc[0]
    max_break_pair = _format_pair_name(str(max_break_row["pair"]))

    p1 = (
        f"We analyze daily log returns for {n_assets} commodity futures contracts from {start_date} to {end_date}, "
        f"covering {n_days} synchronized trading observations. The sample includes energy, metals, and agricultural "
        f"markets, enabling cross-sector comparison of return distributions and dependence structure."
    )

    p2 = (
        f"Correlation evidence indicates meaningful cross-commodity heterogeneity. The highest average rolling correlation "
        f"is observed for {top_pair} (mean rolling correlation {top_corr['mean_rolling_corr']:.3f}; "
        f"mean DCC correlation {top_corr['dcc_mean_corr']:.3f}), while the weakest pair is {low_pair} "
        f"(mean rolling correlation {low_corr['mean_rolling_corr']:.3f}; mean DCC correlation {low_corr['dcc_mean_corr']:.3f}). "
        f"This suggests that market integration is concentrated in specific pair linkages rather than uniform across the panel."
    )

    p3 = (
        f"Regime diagnostics reveal persistent instability in correlation dynamics: pairs exhibit an average of {avg_breaks:.1f} "
        f"detected breakpoints, with the highest instability in {max_break_pair} ({int(max_break_row['regime_breaks'])} breaks). "
        f"These structural shifts imply that static correlation assumptions are likely misspecified over long horizons, and that "
        f"time-varying dependence models are necessary for robust risk estimation."
    )

    return f"{p1}\n\n{p2}\n\n{p3}\n"


def write_passport(row_counts: dict[str, int]) -> None:
    files = {
        "table1_summary_stats": OUTPUT_TABLE1,
        "table2_correlation_summary": OUTPUT_TABLE2,
        "findings_narrative": OUTPUT_NARRATIVE,
    }

    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": {
            key: {
                "path": str(path),
                "sha256": _sha256_file(path),
                "row_count": int(row_counts.get(key, 0)),
            }
            for key, path in files.items()
        },
    }

    OUTPUT_PASSPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> None:
    _ensure_inputs()

    analyst_summary = pd.read_csv(INPUT_ANALYST_SUMMARY)
    rolling = pd.read_csv(INPUT_ROLLING)
    returns = pd.read_csv(INPUT_RETURNS)

    table1 = build_table1_summary_stats(returns)
    table1_tex = to_latex_table(
        table1,
        caption="Summary statistics for daily commodity log returns.",
        label="tab:summary_stats",
        float_fmt="%.5f",
    )
    OUTPUT_TABLE1.write_text(table1_tex, encoding="utf-8")

    table2 = analyst_summary[["pair", "mean_rolling_corr", "regime_breaks", "dcc_mean_corr"]].copy()
    table2 = table2.sort_values("pair").reset_index(drop=True)
    table2["pair"] = table2["pair"].map(lambda p: _format_pair_name(str(p)))
    table2 = table2.rename(
        columns={
            "pair": "Pair",
            "mean_rolling_corr": "Mean Rolling Corr",
            "regime_breaks": "Regime Breaks",
            "dcc_mean_corr": "Mean DCC Corr",
        }
    )
    table2_tex = to_latex_table(
        table2,
        caption="Pairwise correlation diagnostics with regime break counts.",
        label="tab:correlation_summary",
        float_fmt="%.4f",
    )
    OUTPUT_TABLE2.write_text(table2_tex, encoding="utf-8")

    narrative = build_narrative(returns=returns, rolling=rolling, analyst_summary=analyst_summary)
    OUTPUT_NARRATIVE.write_text(narrative, encoding="utf-8")

    write_passport(
        {
            "table1_summary_stats": len(table1),
            "table2_correlation_summary": len(table2),
            "findings_narrative": 3,
        }
    )

    print("Generated:", OUTPUT_TABLE1)
    print("Generated:", OUTPUT_TABLE2)
    print("Generated:", OUTPUT_NARRATIVE)
    print("Generated:", OUTPUT_PASSPORT)


if __name__ == "__main__":
    main()
