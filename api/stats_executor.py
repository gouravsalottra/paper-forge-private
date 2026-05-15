from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from storage.blob import read_artifact

logger = logging.getLogger(__name__)


@dataclass
class ExecutionContext:
    data: Any
    events: Any | None
    returns: Any
    identifiers: list[str]
    window: dict[str, str]
    topic: str
    method_family: str


def _round(value: Any, digits: int = 6) -> float | None:
    try:
        if value != value:  # NaN
            return None
        return round(float(value), digits)
    except Exception:
        return None


def _csv_text(rows: list[dict[str, Any]], fieldnames: list[str]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return out.getvalue()


def _price_column(frame: Any, field: str, ticker: str):
    if getattr(frame, "columns", None) is None:
        raise KeyError(f"Missing columns for {ticker}.")
    if hasattr(frame.columns, "nlevels") and frame.columns.nlevels == 2:
        if (field, ticker) in frame.columns:
            return frame[(field, ticker)]
        if (ticker, field) in frame.columns:
            return frame[(ticker, field)]
    if field in frame.columns:
        return frame[field]
    raise KeyError(f"Missing {field} for {ticker}.")


def _window(blueprint: dict[str, Any]) -> dict[str, str]:
    raw = blueprint.get("inferred_window") if isinstance(blueprint.get("inferred_window"), dict) else {}
    return {"start": str(raw.get("start") or "2015-01-01"), "end": str(raw.get("end") or "2024-12-31")}


def _identifiers(blueprint: dict[str, Any]) -> list[str]:
    raw = blueprint.get("inferred_identifiers") or blueprint.get("identifiers") or []
    if isinstance(raw, str):
        raw = [item.strip() for item in raw.split(",")]
    out = []
    generic_phrases = {"sector etfs", "etf holdings", "us equities", "earnings calls", "sec filings"}
    for item in raw if isinstance(raw, list) else []:
        value = str(item).strip().upper()
        if not value or value.lower() in generic_phrases:
            continue
        if len(value) <= 8 and any(ch.isalpha() for ch in value):
            out.append(value)
    if out:
        return list(dict.fromkeys(out))[:12]
    default = os.getenv("THRIVARC_DEFAULT_TICKERS", "SPY,QQQ")
    return [item.strip().upper() for item in default.split(",") if item.strip()][:12]


def _event_file(blueprint: dict[str, Any]) -> bytes | None:
    path = str(blueprint.get("event_file") or blueprint.get("uploaded_event_file") or "").strip()
    if not path:
        return None
    if path.startswith("sessions/staged-upload/uploads/"):
        try:
            return read_artifact("staged-upload", path.split("sessions/staged-upload/", 1)[1])
        except Exception:
            if os.getenv("ENVIRONMENT") == "test" or os.getenv("THRIVARC_STORAGE_BACKEND") == "mock":
                return None
            raise
    if path.startswith("sessions/"):
        parts = path.split("/", 2)
        if len(parts) == 3:
            return read_artifact(parts[1], parts[2])
    return None


def _synthetic_prices(identifiers: list[str], window: dict[str, str]):
    import numpy as np
    import pandas as pd

    dates = pd.bdate_range(window["start"], window["end"])
    frames = []
    for idx, ticker in enumerate(identifiers):
        rng = np.random.default_rng(20260515 + idx)
        shocks = rng.normal(0.0002 + idx * 0.00003, 0.01 + idx * 0.002, len(dates))
        close = 100 * np.cumprod(1 + shocks)
        overnight = rng.normal(0.0, 0.003 + idx * 0.0005, len(dates))
        open_ = close * (1 + overnight)
        frames.append(pd.DataFrame({("Open", ticker): open_, ("Close", ticker): close}, index=dates))
    return pd.concat(frames, axis=1)


def load_yfinance_context(blueprint: dict[str, Any]) -> ExecutionContext:
    import pandas as pd

    method = str(blueprint.get("method_family") or blueprint.get("method_style") or "regression")
    topic = str(blueprint.get("focus_question") or blueprint.get("topic") or "")
    identifiers = _identifiers(blueprint)
    window = _window(blueprint)
    start = pd.to_datetime(window["start"])
    end = pd.to_datetime(window["end"])
    fetch_start = (start - timedelta(days=370)).strftime("%Y-%m-%d")
    fetch_end = (end + timedelta(days=7)).strftime("%Y-%m-%d")

    if os.getenv("ENVIRONMENT") == "test" or os.getenv("THRIVARC_STORAGE_BACKEND") == "mock":
        prices = _synthetic_prices(identifiers, {"start": fetch_start, "end": fetch_end})
    else:
        import yfinance as yf

        prices = yf.download(identifiers, start=fetch_start, end=fetch_end, progress=False, auto_adjust=False, group_by="column", threads=False)
        if prices is None or prices.empty:
            raise RuntimeError(f"yfinance returned no prices for identifiers={identifiers}.")
    prices = prices.sort_index()

    rows: list[dict[str, Any]] = []
    returns_by_ticker = {}
    for ticker in identifiers:
        try:
            opens = _price_column(prices, "Open", ticker).dropna()
            closes = _price_column(prices, "Close", ticker).dropna()
        except Exception as exc:
            logger.warning("Skipping identifier %s because OHLC columns are unavailable: %s", ticker, exc)
            continue
        days = opens.index.intersection(closes.index)
        days = days[(days >= start) & (days <= end)]
        ticker_returns = []
        for idx in range(1, len(days)):
            day = days[idx]
            prev_day = days[idx - 1]
            overnight = float(opens.loc[day] - closes.loc[prev_day])
            close_to_close = float(closes.loc[day] / closes.loc[prev_day] - 1.0)
            row = {
                "date": pd.Timestamp(day).date().isoformat(),
                "ticker": ticker,
                "open": _round(opens.loc[day]),
                "prev_close": _round(closes.loc[prev_day]),
                "close": _round(closes.loc[day]),
                "overnight_return": _round(overnight),
                "close_to_close_return": _round(close_to_close),
            }
            rows.append(row)
            ticker_returns.append(row)
        returns_by_ticker[ticker] = ticker_returns
    if not rows:
        raise RuntimeError("No usable yfinance rows remained after schema inspection.")

    events = None
    event_bytes = _event_file(blueprint)
    if event_bytes:
        events = pd.read_csv(io.BytesIO(event_bytes))
        if "date" not in events.columns:
            raise RuntimeError("Event file must include a date column.")
        events["date"] = pd.to_datetime(events["date"], errors="coerce")
        events = events.dropna(subset=["date"]).sort_values("date")
    elif method == "event_study" and (os.getenv("ENVIRONMENT") == "test" or os.getenv("THRIVARC_STORAGE_BACKEND") == "mock"):
        test_days = pd.bdate_range(start, end)
        step = max(1, len(test_days) // 10)
        events = pd.DataFrame({"date": [day.date().isoformat() for day in test_days[::step][:10]], "direction": ["positive" if idx % 2 == 0 else "negative" for idx in range(min(10, len(test_days[::step])))]})
    return ExecutionContext(data=prices, events=events, returns=pd.DataFrame(rows), identifiers=list(returns_by_ticker.keys()), window=window, topic=topic, method_family=method)


def _basic_summary_rows(ctx: ExecutionContext) -> list[dict[str, Any]]:
    rows = []
    for ticker, frame in ctx.returns.groupby("ticker"):
        series = frame["overnight_return"].astype(float)
        rows.append({
            "ticker": ticker,
            "sample": "all_trading_days",
            "n": int(series.count()),
            "mean": _round(series.mean()),
            "std": _round(series.std(ddof=1) if series.count() > 1 else 0.0),
            "min": _round(series.min()),
            "median": _round(series.median()),
            "max": _round(series.max()),
        })
    return rows


def event_study_car(data, params: dict[str, Any]) -> dict[str, Any]:
    import pandas as pd
    from scipy import stats

    ctx: ExecutionContext = params["context"]
    if ctx.events is None or ctx.events.empty:
        return {"status": "skipped", "reason": "No event file supplied."}
    windows = params.get("windows") or [[-1, 1], [-3, 3], [-5, 5]]
    returns = ctx.returns.copy()
    returns["date_dt"] = pd.to_datetime(returns["date"])
    event_rows: list[dict[str, Any]] = []
    car_rows: list[dict[str, Any]] = []
    for event in ctx.events.to_dict(orient="records"):
        event_date = pd.Timestamp(event["date"])
        trading_days = sorted(returns[returns["date_dt"] >= event_date]["date_dt"].unique())
        if not trading_days:
            continue
        event_day = pd.Timestamp(trading_days[0])
        event_day_iso = event_day.date().isoformat()
        direction = str(event.get("direction") or event.get("label") or "event").strip().lower()
        event_slice = returns[returns["date"] == event_day_iso]
        row = {"event_id": event.get("event_id") or event.get("id") or event_day_iso, "event_date": event_date.date().isoformat(), "event_trading_day": event_day_iso, "direction": direction}
        for ticker in ctx.identifiers:
            values = event_slice[event_slice["ticker"] == ticker]["overnight_return"].astype(float)
            row[f"{ticker.lower()}_overnight_return"] = _round(values.iloc[0]) if len(values) else None
        if len(ctx.identifiers) >= 2:
            first, second = ctx.identifiers[:2]
            if row.get(f"{first.lower()}_overnight_return") is not None and row.get(f"{second.lower()}_overnight_return") is not None:
                spread = float(row[f"{second.lower()}_overnight_return"]) - float(row[f"{first.lower()}_overnight_return"])
                aligned = -spread if "negative" in direction or "down" in direction or "fossil" in direction else spread
                row["second_minus_first_spread"] = _round(spread)
                row["direction_aligned_spread"] = _round(aligned)
        event_rows.append(row)
        all_days = sorted(returns["date_dt"].unique())
        pos = all_days.index(event_day.to_datetime64()) if event_day.to_datetime64() in all_days else None
        if pos is None:
            continue
        for left, right in windows:
            selected_days = {pd.Timestamp(day).date().isoformat() for day in all_days[max(0, pos + int(left)) : min(len(all_days), pos + int(right) + 1)]}
            car = {"event_id": row["event_id"], "event_date": row["event_date"], "event_trading_day": event_day_iso, "window": f"[{left},{right}]", "direction": direction}
            for ticker in ctx.identifiers:
                series = returns[(returns["ticker"] == ticker) & (returns["date"].isin(selected_days))]["overnight_return"].astype(float)
                car[f"{ticker.lower()}_CAR"] = _round(series.sum()) if len(series) else None
            if len(ctx.identifiers) >= 2:
                first, second = ctx.identifiers[:2]
                if car.get(f"{first.lower()}_CAR") is not None and car.get(f"{second.lower()}_CAR") is not None:
                    spread = float(car[f"{second.lower()}_CAR"]) - float(car[f"{first.lower()}_CAR"])
                    car["second_minus_first_CAR"] = _round(spread)
                    car["direction_aligned_CAR"] = _round(-spread if "negative" in direction or "down" in direction or "fossil" in direction else spread)
            car_rows.append(car)
    aligned = [float(row["direction_aligned_spread"]) for row in event_rows if row.get("direction_aligned_spread") is not None]
    t_stat, p_value = stats.ttest_1samp(aligned, 0.0) if len(aligned) >= 2 else (None, None)
    return {"status": "complete", "event_rows": event_rows, "car_rows": car_rows, "mean_aligned_effect": _round(sum(aligned) / len(aligned)) if aligned else None, "t_stat": _round(t_stat, 4), "p_value": _round(p_value, 6), "n_events": len(aligned)}


def newey_west_hac(data, params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np
    import statsmodels.api as sm

    frame = data.copy()
    y_col = params.get("y") or "target"
    x_col = params.get("x") or "predictor"
    if y_col not in frame.columns or x_col not in frame.columns:
        pivot = frame.pivot(index="date", columns="ticker", values="close_to_close_return").dropna()
        if pivot.shape[1] < 1:
            return {"status": "skipped", "reason": "No return series available."}
        y = pivot.iloc[:, 0].shift(-1).dropna()
        x = pivot.iloc[:, 0].shift(1).reindex(y.index).fillna(0.0)
    else:
        y = frame[y_col].astype(float)
        x = frame[x_col].astype(float)
    X = sm.add_constant(np.asarray(x, dtype=float))
    model = sm.OLS(np.asarray(y, dtype=float), X, missing="drop").fit(cov_type="HAC", cov_kwds={"maxlags": int(params.get("lags", 5)), "use_correction": True})
    return {"status": "complete", "coefficient": _round(model.params[1]), "HAC_se": _round(model.bse[1]), "t_stat": _round(model.tvalues[1], 4), "p_value": _round(model.pvalues[1], 6), "nobs": int(model.nobs)}


def patell_test(data, params: dict[str, Any]) -> dict[str, Any]:
    car_result = params.get("event_result") or {}
    values = [row.get("direction_aligned_spread") for row in car_result.get("event_rows", []) if row.get("direction_aligned_spread") is not None]
    if not values:
        return {"status": "skipped", "reason": "No event abnormal returns available."}
    import math
    from scipy import stats

    vals = [float(v) for v in values]
    std = (sum((v - sum(vals) / len(vals)) ** 2 for v in vals) / max(1, len(vals) - 1)) ** 0.5 or 1.0
    z_stat = sum(v / std for v in vals) / math.sqrt(len(vals))
    return {"status": "complete", "Z_stat": _round(z_stat, 4), "p_value": _round(2 * (1 - stats.norm.cdf(abs(z_stat))), 6), "N_events": len(vals)}


def placebo_test(data, params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    observed = float(params.get("observed_stat") or 0.0)
    values = data["overnight_return"].astype(float).to_numpy()
    draws = int(params.get("draws", 1000))
    sample_size = max(1, int(params.get("sample_size", min(10, len(values)))))
    rng = np.random.default_rng(20260515)
    stats_ = [float(rng.choice(values, size=sample_size, replace=False).mean()) for _ in range(min(draws, max(10, len(values)))) if len(values) >= sample_size]
    arr = np.asarray(stats_ or [0.0], dtype=float)
    return {"status": "complete", "observed_stat": _round(observed), "placebo_mean": _round(arr.mean()), "placebo_std": _round(arr.std(ddof=1) if len(arr) > 1 else 0.0), "empirical_p_value": _round((abs(arr) >= abs(observed)).mean(), 6), "draws": int(len(arr))}


def bootstrap_ci(data, params: dict[str, Any]) -> dict[str, Any]:
    import numpy as np

    column = params.get("column") or "overnight_return"
    values = data[column].astype(float).dropna().to_numpy()
    if len(values) == 0:
        return {"status": "skipped", "reason": f"Column {column} has no observations."}
    iterations = int(params.get("iterations", 5000))
    rng = np.random.default_rng(20260516)
    draws = rng.choice(values, size=(min(iterations, 5000), len(values)), replace=True).mean(axis=1)
    return {"status": "complete", "estimate": _round(values.mean()), "ci_lower": _round(np.quantile(draws, 0.025)), "ci_upper": _round(np.quantile(draws, 0.975)), "se": _round(draws.std(ddof=1))}


def bh_correction(data, params: dict[str, Any]) -> dict[str, Any]:
    p_values = [float(p) for p in params.get("p_values", []) if p is not None]
    m = len(p_values)
    if not p_values:
        return {"status": "skipped", "reason": "No p-values supplied."}
    order = sorted(range(m), key=lambda idx: p_values[idx])
    adjusted = [1.0] * m
    prev = 1.0
    for rank, idx in reversed(list(enumerate(order, start=1))):
        value = min(prev, p_values[idx] * m / rank)
        adjusted[idx] = value
        prev = value
    alpha = float(params.get("alpha", 0.05))
    return {"status": "complete", "p_values": [_round(p, 6) for p in p_values], "adjusted_p_values": [_round(p, 6) for p in adjusted], "rejected": [p <= alpha for p in adjusted], "alpha": alpha}


def subsample_analysis(data, params: dict[str, Any]) -> dict[str, Any]:
    import pandas as pd
    from scipy import stats

    split_date = pd.to_datetime(params.get("split_date") or data["date"].sort_values().iloc[len(data) // 2])
    frame = data.copy()
    frame["date_dt"] = pd.to_datetime(frame["date"])
    pre = frame[frame["date_dt"] < split_date]["overnight_return"].astype(float)
    post = frame[frame["date_dt"] >= split_date]["overnight_return"].astype(float)
    t_stat, p_value = stats.ttest_ind(pre, post, equal_var=False, nan_policy="omit") if len(pre) > 2 and len(post) > 2 else (None, None)
    return {"status": "complete", "split_date": split_date.date().isoformat(), "pre_mean": _round(pre.mean()), "post_mean": _round(post.mean()), "difference": _round(post.mean() - pre.mean()), "t_stat": _round(t_stat, 4), "p_value": _round(p_value, 6), "n_pre": int(pre.count()), "n_post": int(post.count())}


def fama_macbeth(data, params: dict[str, Any]) -> dict[str, Any]:
    try:
        from linearmodels import FamaMacBeth
    except Exception:
        return {"status": "skipped", "reason": "linearmodels.FamaMacBeth unavailable."}
    return {"status": "skipped", "reason": "Fama-MacBeth requires a user-provided cross-sectional factor panel."}


def panel_regression(data, params: dict[str, Any]) -> dict[str, Any]:
    try:
        from linearmodels.panel import PanelOLS
        import statsmodels.api as sm
    except Exception:
        return {"status": "skipped", "reason": "linearmodels.PanelOLS unavailable."}
    frame = data.copy()
    frame["date"] = frame["date"].astype(str)
    panel = frame.set_index(["ticker", "date"])
    y = panel["close_to_close_return"].astype(float)
    X = sm.add_constant(panel[["overnight_return"]].astype(float))
    try:
        model = PanelOLS(y, X, entity_effects=True).fit(cov_type="clustered", cluster_entity=True)
    except Exception as exc:
        return {"status": "failed", "reason": str(exc)}
    param = model.params.get("overnight_return")
    return {"status": "complete", "coefficient": _round(param), "clustered_se": _round(model.std_errors.get("overnight_return")), "t_stat": _round(model.tstats.get("overnight_return"), 4), "p_value": _round(model.pvalues.get("overnight_return"), 6), "r2": _round(model.rsquared), "nobs": int(model.nobs)}


def _results_to_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for name, payload in results.items():
        if isinstance(payload, dict):
            flat = {"test_name": name, "status": payload.get("status", "complete")}
            for key, value in payload.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    flat[key] = value
            rows.append(flat)
    return rows


def execute_test_battery(ctx: ExecutionContext, stats_spec: dict[str, Any] | None = None) -> dict[str, Any]:
    stats_spec = stats_spec or {}
    event_result = event_study_car(ctx.returns, {"context": ctx}) if ctx.method_family == "event_study" or ctx.events is not None else {"status": "skipped", "reason": "not an event-study design"}
    observed = event_result.get("mean_aligned_effect") or ctx.returns["overnight_return"].astype(float).mean()
    results = {
        "event_study_car": event_result,
        "newey_west_hac": newey_west_hac(ctx.returns, {"lags": 5}),
        "patell_test": patell_test(ctx.returns, {"event_result": event_result}),
        "placebo_test": placebo_test(ctx.returns, {"observed_stat": observed, "sample_size": event_result.get("n_events") or 10, "draws": 1000}),
        "bootstrap_ci": bootstrap_ci(ctx.returns, {"column": "overnight_return", "iterations": 5000}),
        "subsample_analysis": subsample_analysis(ctx.returns, {}),
        "panel_regression": panel_regression(ctx.returns, {}),
    }
    p_values = []
    for payload in results.values():
        if isinstance(payload, dict) and payload.get("p_value") is not None:
            p_values.append(payload.get("p_value"))
    results["bh_correction"] = bh_correction(ctx.returns, {"p_values": p_values})
    rows = _results_to_rows(results)
    return {"results": results, "rows": rows, "summary": {"executed_tests": [key for key, value in results.items() if value.get("status") == "complete"], "skipped_tests": {key: value.get("reason") for key, value in results.items() if value.get("status") != "complete"}}}


def execute_research_plan(blueprint: dict[str, Any], stats_spec: dict[str, Any] | None = None) -> dict[str, Any]:
    ctx = load_yfinance_context(blueprint)
    summary_rows = _basic_summary_rows(ctx)
    battery = execute_test_battery(ctx, stats_spec)
    event_result = battery["results"].get("event_study_car", {})
    event_rows = event_result.get("event_rows") or []
    car_rows = event_result.get("car_rows") or []
    stats_rows = battery["rows"]

    fieldnames_data = ["date", "ticker", "open", "prev_close", "close", "overnight_return", "close_to_close_return"]
    data_csv = _csv_text(ctx.returns.to_dict(orient="records"), fieldnames_data)
    event_fields = sorted({key for row in event_rows for key in row.keys()}) or ["status", "reason"]
    car_fields = sorted({key for row in car_rows for key in row.keys()}) or ["status", "reason"]
    stats_fields = sorted({key for row in stats_rows for key in row.keys()}) or ["test_name", "status"]
    csv_outputs = {
        "03_data/overnight_returns.csv": data_csv,
        "06_compute/method_outputs/event_returns.csv": _csv_text(event_rows, event_fields) if event_rows else _csv_text([event_result], ["status", "reason"]),
        "06_compute/method_outputs/event_window_car.csv": _csv_text(car_rows, car_fields) if car_rows else _csv_text([event_result], ["status", "reason"]),
        "07_statistics/results_tables/summary_statistics.csv": _csv_text(summary_rows, ["ticker", "sample", "n", "mean", "std", "min", "median", "max"]),
        "07_statistics/results_tables/executed_tests.csv": _csv_text(stats_rows, stats_fields),
        "07_statistics/results_tables/t_tests.csv": _csv_text(stats_rows, stats_fields),
        "07_statistics/results_tables/placebo_tests.csv": _csv_text(stats_rows, stats_fields),
        "08_stats/stats_summary.csv": _csv_text(stats_rows, stats_fields),
    }
    primary_numbers = {
        "row_count": int(len(ctx.returns)),
        "identifier_count": int(len(ctx.identifiers)),
        "event_count": int(event_result.get("n_events") or 0),
        "mean_aligned_effect": event_result.get("mean_aligned_effect"),
        "event_t_stat": event_result.get("t_stat"),
        "event_p_value": event_result.get("p_value"),
        "newey_west_coefficient": battery["results"].get("newey_west_hac", {}).get("coefficient"),
        "newey_west_t_stat": battery["results"].get("newey_west_hac", {}).get("t_stat"),
        "newey_west_p_value": battery["results"].get("newey_west_hac", {}).get("p_value"),
        "placebo_empirical_p_value": battery["results"].get("placebo_test", {}).get("empirical_p_value"),
        "bootstrap_ci_lower": battery["results"].get("bootstrap_ci", {}).get("ci_lower"),
        "bootstrap_ci_upper": battery["results"].get("bootstrap_ci", {}).get("ci_upper"),
        "return_definition": blueprint.get("return_definition") or "open(t) - close(t-1)",
    }
    conclusion = "hypothesis_supported" if (primary_numbers.get("event_p_value") is not None and float(primary_numbers["event_p_value"]) < 0.05) else "hypothesis_not_supported_or_exploratory"
    encoded = json.dumps({"primary_numbers": primary_numbers, "stats": battery["results"]}, sort_keys=True).encode("utf-8")
    return {
        "context": {"identifiers": ctx.identifiers, "window": ctx.window, "method_family": ctx.method_family, "topic": ctx.topic},
        "event_rows": event_rows,
        "car_rows": car_rows,
        "summary_statistics_rows": summary_rows,
        "executed_test_rows": stats_rows,
        "csv_outputs": csv_outputs,
        "primary_numbers": primary_numbers,
        "robustness_results": battery["results"],
        "stats_summary": battery["summary"],
        "evidence_conclusion": conclusion,
        "economic_interpretation": "Effect sizes and uncertainty are reported from verified artifacts; conclusions must remain scoped to the locked design.",
        "price_result_sha256": hashlib.sha256(encoded).hexdigest(),
        "price_window": ctx.window,
        "data_row_count": int(len(ctx.returns)),
    }
