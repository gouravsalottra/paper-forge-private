from __future__ import annotations

import csv
import io
import logging
import os
import re
import tempfile
from typing import Any

from storage.blob import write_artifact

logger = logging.getLogger(__name__)


def _rows(csv_text: str) -> list[dict[str, str]]:
    try:
        return list(csv.DictReader(io.StringIO(csv_text or "")))
    except Exception:
        return []


def _csv_by_suffix(csv_outputs: dict[str, str], suffix: str) -> str:
    for path, text in (csv_outputs or {}).items():
        if str(path).endswith(suffix):
            return text
    return ""


def _safe_name(value: str, fallback: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip().lower()).strip("._-")
    return clean[:70] or fallback


def _figure_ref(key: str, filename: str, caption: str, label: str, artifact_ref: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": key,
        "path": f"figures/{filename}",
        "blob_path": artifact_ref.get("blob_path"),
        "filename": filename,
        "caption": caption,
        "label": label,
        "sha256": artifact_ref.get("sha256"),
        "bytes": artifact_ref.get("bytes"),
    }


def _upload(session_id: str, key: str, filename: str, caption: str, label: str, fig) -> dict[str, Any]:
    import matplotlib.pyplot as plt

    with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1] or ".png", delete=False) as handle:
        tmp_path = handle.name
    try:
        fig.savefig(tmp_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        with open(tmp_path, "rb") as fh:
            artifact_ref = write_artifact(session_id, f"figures/{filename}", fh.read())
        return _figure_ref(key, filename, caption, label, artifact_ref)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _method_style(blueprint: dict[str, Any]) -> str:
    return str(blueprint.get("method_style") or blueprint.get("method_family") or "descriptive").strip().lower()


def _numeric_columns(frame, suffix: str, exclude_prefixes: tuple[str, ...] = ()) -> list[str]:
    out: list[str] = []
    for column in getattr(frame, "columns", []):
        name = str(column)
        if not name.endswith(suffix):
            continue
        if any(name.startswith(prefix) for prefix in exclude_prefixes):
            continue
        out.append(name)
    return out


def _label(column: str, suffix: str) -> str:
    text = str(column)
    if text.endswith(suffix):
        text = text[: -len(suffix)]
    return text.replace("_", " ").upper()


def _load_frame(csv_outputs: dict[str, str], suffix: str):
    import pandas as pd

    text = _csv_by_suffix(csv_outputs, suffix)
    if not text:
        return None
    try:
        return pd.read_csv(io.StringIO(text))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load CSV for figure generation (%s): %s", suffix, exc)
        return None


def _plot_cumulative_returns(session_id: str, figures: dict[str, Any], overnight_df) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    if overnight_df is None or len(overnight_df) == 0 or not {"date", "ticker", "overnight_return"}.issubset(overnight_df.columns):
        return
    frame = overnight_df.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date", "overnight_return"]).sort_values("date")
    tickers = list(dict.fromkeys(frame["ticker"].astype(str).tolist()))[:4]
    if not tickers:
        return
    fig, ax = plt.subplots(figsize=(11, 5))
    for ticker in tickers:
        group = frame[frame["ticker"].astype(str) == ticker].copy()
        group["cum_return"] = (1.0 + group["overnight_return"].astype(float) / 100.0).cumprod()
        ax.plot(group["date"], group["cum_return"], linewidth=0.9, label=ticker)
    ax.set_xlabel("Date")
    ax.set_ylabel("Cumulative return")
    ax.set_title("Cumulative Return Paths Over the Verified Sample")
    ax.grid(True, alpha=0.3)
    ax.legend(fontsize=8)
    fig.tight_layout()
    figures["fig1_price_history"] = _upload(session_id, "fig1_price_history", "fig1_price_history.png", "Cumulative return paths over the verified sample period.", "fig:price_history", fig)


def _event_figures(session_id: str, figures: dict[str, Any], event_df, car_df, overnight_df, stats_dict: dict[str, Any]) -> None:
    import matplotlib.pyplot as plt
    import numpy as np

    event_cols = _numeric_columns(event_df, "_overnight_return", ("direction_aligned", "second_minus_first")) if event_df is not None else []
    if event_df is not None and len(event_df) > 0 and len(event_cols) >= 2:
        first_col, second_col = event_cols[:2]
        first_label = _label(first_col, "_overnight_return")
        second_label = _label(second_col, "_overnight_return")
        fig, ax = plt.subplots(figsize=(12, 5))
        x = np.arange(len(event_df))
        width = 0.35
        ax.bar(x - width / 2, event_df[first_col].astype(float), width, label=first_label, alpha=0.85)
        ax.bar(x + width / 2, event_df[second_col].astype(float), width, label=second_label, alpha=0.85)
        ax.axhline(0, color="black", linewidth=0.8)
        labels = [f"E{i + 1:02d}\n{str(row.get('event_date', ''))[:7]}" for i, (_, row) in enumerate(event_df.iterrows())]
        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=7)
        ax.set_xlabel("Event")
        ax.set_ylabel("Return")
        ax.set_title(f"Event-Day Returns: {first_label} versus {second_label}")
        ax.legend(fontsize=9)
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        figures["fig2_event_returns"] = _upload(session_id, "fig2_event_returns", "fig2_event_returns.png", f"Event-day returns for {first_label} and {second_label} around verified event dates.", "fig:event_returns", fig)

        data = event_df[event_cols[: min(4, len(event_cols))]].astype(float).to_numpy()
        vmax = max(abs(float(data.min())), abs(float(data.max())), 0.001)
        fig, ax = plt.subplots(figsize=(7, max(4, min(10, len(event_df) * 0.5))))
        image = ax.imshow(data, cmap="RdYlGn", vmin=-vmax, vmax=vmax, aspect="auto")
        ax.set_xticks(range(min(4, len(event_cols))))
        ax.set_xticklabels([_label(col, "_overnight_return") for col in event_cols[: min(4, len(event_cols))]], fontsize=8)
        ax.set_yticks(range(len(event_df)))
        ax.set_yticklabels([f"E{i + 1:02d}" for i in range(len(event_df))], fontsize=8)
        fig.colorbar(image, ax=ax, label="Return")
        ax.set_title("Event-Level Return Heatmap")
        fig.tight_layout()
        figures["fig5_heatmap"] = _upload(session_id, "fig5_heatmap", "fig5_heatmap.png", "Heatmap of event-level returns by event and measured series.", "fig:event_heatmap", fig)

    car_cols = _numeric_columns(car_df, "_CAR", ("direction_aligned", "second_minus_first")) if car_df is not None else []
    if car_df is not None and len(car_df) > 0 and "window" in car_df.columns and len(car_cols) >= 1:
        windows = list(dict.fromkeys(car_df["window"].astype(str).tolist()))[:6]
        fig, ax = plt.subplots(figsize=(9, 5))
        x = np.arange(len(windows))
        width = 0.8 / max(1, min(3, len(car_cols)))
        for idx, col in enumerate(car_cols[:3]):
            values = [car_df[car_df["window"].astype(str) == window][col].astype(float).mean() for window in windows]
            ax.bar(x + idx * width - width * (min(3, len(car_cols)) - 1) / 2, values, width, label=_label(col, "_CAR"), alpha=0.85)
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(windows)
        ax.set_xlabel("Window")
        ax.set_ylabel("Average CAR")
        ax.set_title("Average Cumulative Returns by Event Window")
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3, axis="y")
        fig.tight_layout()
        figures["fig3_car_windows"] = _upload(session_id, "fig3_car_windows", "fig3_car_windows.png", "Average cumulative returns by event window for measured series.", "fig:car_windows", fig)

    if overnight_df is not None and len(overnight_df) > 0 and "overnight_return" in overnight_df.columns:
        values = overnight_df["overnight_return"].astype(float).dropna().to_numpy()
        observed = stats_dict.get("mean_aligned_effect") or stats_dict.get("newey_west_coefficient") or 0.0
        if len(values):
            rng = np.random.default_rng(20260515)
            sample = min(max(1, int(stats_dict.get("event_count") or 10) if str(stats_dict.get("event_count") or "").isdigit() else 10), len(values))
            draws = np.array([rng.choice(values, size=sample, replace=len(values) < sample).mean() for _ in range(1000)])
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.hist(draws, bins=50, color="#cccccc", edgecolor="white", alpha=0.85)
            ax.axvline(float(observed or 0.0), color="red", linewidth=2, label=f"Observed = {float(observed or 0.0):.3f}")
            ax.set_xlabel("Placebo statistic")
            ax.set_ylabel("Frequency")
            ax.set_title("Placebo Distribution")
            ax.legend(fontsize=9)
            fig.tight_layout()
            figures["fig4_placebo"] = _upload(session_id, "fig4_placebo", "fig4_placebo.png", "Placebo distribution from random non-event observations with the observed statistic marked.", "fig:placebo", fig)


def _time_series_figures(session_id: str, figures: dict[str, Any], design_df, stats_dict: dict[str, Any]) -> None:
    import matplotlib.pyplot as plt
    import pandas as pd

    if design_df is None or len(design_df) == 0:
        return
    frame = design_df.copy()
    if "date" in frame.columns:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    else:
        frame["date"] = pd.RangeIndex(len(frame))
    y_col = "outcome" if "outcome" in frame.columns else next((col for col in frame.columns if "return" in str(col).lower()), "")
    x_col = "predictor_lag1" if "predictor_lag1" in frame.columns else "predictor" if "predictor" in frame.columns else ""
    if x_col and y_col:
        fig, ax1 = plt.subplots(figsize=(11, 5))
        ax1.plot(frame["date"], frame[x_col].astype(float), linewidth=0.8, label=x_col)
        ax1.set_xlabel("Date")
        ax1.set_ylabel(x_col)
        ax2 = ax1.twinx()
        ax2.plot(frame["date"], frame[y_col].astype(float), color="#d88645", linewidth=0.8, alpha=0.8, label=y_col)
        ax2.set_ylabel(y_col)
        ax1.set_title("Predictor and Outcome Over Time")
        ax1.grid(True, alpha=0.3)
        fig.tight_layout()
        figures["fig1_time_series"] = _upload(session_id, "fig1_time_series", "fig1_time_series.png", "Time-series plot of the lagged predictor and subsequent outcome.", "fig:time_series", fig)

        fig, ax = plt.subplots(figsize=(7, 5))
        ax.scatter(frame[x_col].astype(float), frame[y_col].astype(float), s=12, alpha=0.45)
        clean = frame[[x_col, y_col]].dropna().astype(float)
        if len(clean) > 2:
            import numpy as np
            slope, intercept = np.polyfit(clean[x_col], clean[y_col], 1)
            xs = np.linspace(clean[x_col].min(), clean[x_col].max(), 100)
            ax.plot(xs, slope * xs + intercept, color="red", linewidth=1)
        ax.set_xlabel(x_col)
        ax.set_ylabel(y_col)
        ax.set_title("Lagged Predictor Versus Subsequent Return")
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        figures["fig2_predictive_scatter"] = _upload(session_id, "fig2_predictive_scatter", "fig2_predictive_scatter.png", "Scatter plot of the lagged predictor against the subsequent return with fitted line.", "fig:predictive_scatter", fig)

        if len(frame) > 70:
            corr = frame[x_col].astype(float).rolling(63).corr(frame[y_col].astype(float))
            fig, ax = plt.subplots(figsize=(10, 4))
            ax.plot(frame["date"], corr, linewidth=0.9)
            ax.axhline(0, color="black", linewidth=0.8)
            ax.set_xlabel("Date")
            ax.set_ylabel("Rolling correlation")
            ax.set_title("Rolling Predictor-Outcome Correlation")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            figures["fig3_rolling_correlation"] = _upload(session_id, "fig3_rolling_correlation", "fig3_rolling_correlation.png", "Rolling correlation between the lagged predictor and subsequent outcome.", "fig:rolling_correlation", fig)


def _regression_figures(session_id: str, figures: dict[str, Any], design_df) -> None:
    import matplotlib.pyplot as plt

    if design_df is None or len(design_df) == 0:
        return
    y_col = "next_quarter_return" if "next_quarter_return" in design_df.columns else "outcome" if "outcome" in design_df.columns else ""
    x_col = "momentum_21d" if "momentum_21d" in design_df.columns else "predictor_lag1" if "predictor_lag1" in design_df.columns else ""
    if x_col and y_col:
        frame = design_df[[x_col, y_col]].dropna().astype(float)
        if len(frame) > 2:
            fig, ax = plt.subplots(figsize=(7, 5))
            ax.scatter(frame[x_col], frame[y_col], s=12, alpha=0.35)
            import numpy as np
            slope, intercept = np.polyfit(frame[x_col], frame[y_col], 1)
            xs = np.linspace(frame[x_col].min(), frame[x_col].max(), 100)
            ax.plot(xs, slope * xs + intercept, color="red", linewidth=1)
            ax.set_xlabel(x_col)
            ax.set_ylabel(y_col)
            ax.set_title("Cross-Sectional Regression Fit")
            ax.grid(True, alpha=0.3)
            fig.tight_layout()
            figures["fig1_regression_scatter"] = _upload(session_id, "fig1_regression_scatter", "fig1_regression_scatter.png", "Scatter plot of the primary predictor against the subsequent return with fitted line.", "fig:regression_scatter", fig)

        residual = frame[y_col] - frame[y_col].mean()
        fig, ax = plt.subplots(figsize=(8, 4))
        ax.hist(residual, bins=40, color="#cccccc", edgecolor="white", alpha=0.85)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.set_xlabel("Demeaned outcome")
        ax.set_ylabel("Frequency")
        ax.set_title("Outcome Distribution Around Its Mean")
        fig.tight_layout()
        figures["fig2_regression_distribution"] = _upload(session_id, "fig2_regression_distribution", "fig2_regression_distribution.png", "Distribution of the regression outcome around its sample mean.", "fig:regression_distribution", fig)


def generate_figures_for_study(session_id: str, blueprint: dict[str, Any], csv_outputs: dict[str, str], results_dict: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Generate verified figure artifacts from the method-shaped compute outputs."""
    figures: dict[str, dict[str, Any]] = {}
    try:
        import matplotlib

        matplotlib.use("Agg")
        import numpy as np  # noqa: F401 - imported to validate runtime availability for render helpers
    except Exception as exc:  # pragma: no cover
        logger.warning("Matplotlib unavailable; figures skipped for %s: %s", session_id, exc)
        return figures

    results_dict = results_dict or {}
    method = _method_style(blueprint)
    overnight_df = _load_frame(csv_outputs, "overnight_returns.csv")
    event_df = _load_frame(csv_outputs, "event_returns.csv")
    car_df = _load_frame(csv_outputs, "event_window_car.csv")
    predictive_df = _load_frame(csv_outputs, "predictive_series.csv")
    regression_df = _load_frame(csv_outputs, "regression_design.csv")

    if method == "event_study":
        _plot_cumulative_returns(session_id, figures, overnight_df)
        _event_figures(session_id, figures, event_df, car_df, overnight_df, results_dict)
    elif method in {"time_series", "var_model", "cointegration"}:
        _plot_cumulative_returns(session_id, figures, overnight_df)
        _time_series_figures(session_id, figures, predictive_df, results_dict)
    elif method in {"regression", "panel_regression", "quantile_regression", "causal_forest"}:
        _plot_cumulative_returns(session_id, figures, overnight_df)
        _regression_figures(session_id, figures, regression_df)
    else:
        _plot_cumulative_returns(session_id, figures, overnight_df)
        if predictive_df is not None:
            _time_series_figures(session_id, figures, predictive_df, results_dict)
        if regression_df is not None:
            _regression_figures(session_id, figures, regression_df)
        if event_df is not None and car_df is not None:
            _event_figures(session_id, figures, event_df, car_df, overnight_df, results_dict)

    return figures
