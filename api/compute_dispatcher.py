from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

from api.stats_executor import (  # noqa: E402
    ExecutionContext,
    _basic_summary_rows,
    _csv_text,
    _round,
    bh_correction,
    bootstrap_ci,
    event_study_car,
    load_yfinance_context,
    panel_regression,
    placebo_test,
    subsample_analysis,
)


EVENT_METHODS = {"event_study"}
TIME_SERIES_METHODS = {"time_series", "var_model", "cointegration"}
REGRESSION_METHODS = {"regression", "panel_regression", "quantile_regression", "causal_forest"}
FACTOR_METHODS = {"factor_model", "backtest", "portfolio_optimization", "risk_model", "volatility_model"}
DESCRIPTIVE_METHODS = {"descriptive", "exploratory", "clustering", "anomaly_detection"}


def _method_style(blueprint: dict[str, Any]) -> str:
    return str(blueprint.get("method_style") or blueprint.get("method_family") or "descriptive").strip().lower()


def dispatch_compute(session_id: str | None, blueprint: dict[str, Any], artifacts: dict[str, Any] | None = None, conn: Any | None = None) -> dict[str, Any]:
    """Dispatch the compute phase from the locked Blueprint method style."""
    method = _method_style(blueprint)
    ctx = load_yfinance_context({**blueprint, "method_family": method, "method_style": method})
    if method in EVENT_METHODS:
        return compute_event_study(session_id, blueprint, ctx)
    if method in TIME_SERIES_METHODS:
        return compute_time_series(session_id, blueprint, ctx)
    if method in REGRESSION_METHODS:
        return compute_regression(session_id, blueprint, ctx)
    if method in FACTOR_METHODS:
        return compute_factor_model(session_id, blueprint, ctx)
    if method in DESCRIPTIVE_METHODS:
        return compute_descriptive(session_id, blueprint, ctx)
    return compute_generic(session_id, blueprint, ctx)


def _data_csv(ctx: ExecutionContext) -> str:
    fields = ["date", "ticker", "open", "prev_close", "close", "overnight_return", "close_to_close_return"]
    return _csv_text(ctx.returns.to_dict(orient="records"), fields)


def _summary_csv(ctx: ExecutionContext) -> tuple[list[dict[str, Any]], str]:
    rows = _basic_summary_rows(ctx)
    return rows, _csv_text(rows, ["ticker", "sample", "n", "mean", "std", "min", "median", "max"])


def _result_hash(primary_numbers: dict[str, Any], results: dict[str, Any]) -> str:
    encoded = json.dumps({"primary_numbers": primary_numbers, "stats": results}, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _result_package(
    ctx: ExecutionContext,
    *,
    method: str,
    primary_numbers: dict[str, Any],
    results: dict[str, Any],
    stats_rows: list[dict[str, Any]],
    csv_outputs: dict[str, str],
    summary_rows: list[dict[str, Any]],
    event_rows: list[dict[str, Any]] | None = None,
    car_rows: list[dict[str, Any]] | None = None,
    conclusion: str = "hypothesis_not_supported_or_exploratory",
    interpretation: str | None = None,
) -> dict[str, Any]:
    return {
        "context": {"identifiers": ctx.identifiers, "window": ctx.window, "method_family": method, "topic": ctx.topic},
        "event_rows": event_rows or [],
        "car_rows": car_rows or [],
        "summary_statistics_rows": summary_rows,
        "executed_test_rows": stats_rows,
        "csv_outputs": csv_outputs,
        "primary_numbers": primary_numbers,
        "robustness_results": results,
        "stats_summary": {
            "executed_tests": [row.get("test_name") for row in stats_rows if row.get("status") == "complete"],
            "skipped_tests": {row.get("test_name"): row.get("reason") for row in stats_rows if row.get("status") != "complete" and row.get("test_name")},
        },
        "evidence_conclusion": conclusion,
        "economic_interpretation": interpretation or "Effect sizes and uncertainty are reported from verified artifacts; conclusions remain scoped to the locked design.",
        "price_result_sha256": _result_hash(primary_numbers, results),
        "price_window": ctx.window,
        "data_row_count": int(len(ctx.returns)),
    }


def _flatten_results(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, payload in results.items():
        if not isinstance(payload, dict):
            continue
        row = {"test_name": name, "status": payload.get("status", "complete")}
        for key, value in payload.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                row[key] = value
        rows.append(row)
    return rows


def _stats_csv(rows: list[dict[str, Any]]) -> str:
    fields = sorted({key for row in rows for key in row.keys()}) or ["test_name", "status"]
    return _csv_text(rows, fields)


def compute_event_study(session_id: str | None, blueprint: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    from api.stats_executor import execute_test_battery

    summary_rows, summary_csv = _summary_csv(ctx)
    battery = execute_test_battery(ctx)
    event_result = battery["results"].get("event_study_car", {})
    event_rows = event_result.get("event_rows") or []
    car_rows = event_result.get("car_rows") or []
    stats_rows = battery["rows"]
    event_fields = sorted({key for row in event_rows for key in row.keys()}) or ["status", "reason"]
    car_fields = sorted({key for row in car_rows for key in row.keys()}) or ["status", "reason"]
    stats_csv = _stats_csv(stats_rows)
    csv_outputs = {
        "03_data/overnight_returns.csv": _data_csv(ctx),
        "06_compute/method_outputs/event_returns.csv": _csv_text(event_rows, event_fields) if event_rows else _csv_text([event_result], ["status", "reason"]),
        "06_compute/method_outputs/event_window_car.csv": _csv_text(car_rows, car_fields) if car_rows else _csv_text([event_result], ["status", "reason"]),
        "07_statistics/results_tables/summary_statistics.csv": summary_csv,
        "07_statistics/results_tables/executed_tests.csv": stats_csv,
        "07_statistics/results_tables/t_tests.csv": stats_csv,
        "07_statistics/results_tables/placebo_tests.csv": stats_csv,
        "08_stats/stats_summary.csv": stats_csv,
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
        "primary_analysis_type": "event_study",
    }
    conclusion = "hypothesis_supported" if primary_numbers.get("event_p_value") is not None and float(primary_numbers["event_p_value"]) < 0.05 else "hypothesis_not_supported_or_exploratory"
    return _result_package(ctx, method="event_study", primary_numbers=primary_numbers, results=battery["results"], stats_rows=stats_rows, csv_outputs=csv_outputs, summary_rows=summary_rows, event_rows=event_rows, car_rows=car_rows, conclusion=conclusion)


def _forward_compound_return(series, periods: int = 21):
    shifted = (1.0 + series.astype(float)).shift(-1)
    return shifted.rolling(periods).apply(lambda values: float(values.prod()), raw=True).shift(-(periods - 1)) - 1.0


def _time_series_design(ctx: ExecutionContext, blueprint: dict[str, Any]):
    import pandas as pd

    pivot = ctx.returns.pivot(index="date", columns="ticker", values="close_to_close_return").sort_index()
    pivot.index = pd.to_datetime(pivot.index)
    cols = [str(col) for col in pivot.columns]
    topic = str(blueprint.get("focus_question") or blueprint.get("topic") or "")
    volatility_cols = [col for col in cols if "VIX" in col.upper()]
    if len(volatility_cols) >= 2:
        predictor = pivot[volatility_cols[0]].astype(float) - pivot[volatility_cols[1]].astype(float)
        predictor_name = f"{volatility_cols[0]} minus {volatility_cols[1]}"
    else:
        predictor_col = volatility_cols[0] if volatility_cols else cols[0]
        predictor = pivot[predictor_col].astype(float)
        predictor_name = f"lagged {predictor_col} return"
    non_vol = [col for col in cols if col not in volatility_cols]
    target_col = non_vol[0] if non_vol else cols[-1]
    if re_search := __import__("re").search(r"next[-\s]?month|monthly|month", topic, flags=__import__("re").I):
        outcome = _forward_compound_return(pivot[target_col].astype(float), 21)
        horizon = "next_month_return"
    else:
        outcome = pivot[target_col].astype(float).shift(-1)
        horizon = "next_period_return"
    design = pd.DataFrame({"date": pivot.index, "predictor": predictor.values, "predictor_lag1": predictor.shift(1).values, horizon: outcome.values})
    design["outcome"] = design[horizon]
    design = design.dropna().reset_index(drop=True)
    return design, predictor_name, target_col, horizon


def _hac_regression(design, y_col: str, x_col: str, lags: int = 5) -> dict[str, Any]:
    import numpy as np
    import statsmodels.api as sm

    if design is None or len(design) < 8 or y_col not in design.columns or x_col not in design.columns:
        return {"status": "skipped", "reason": "Insufficient observations for HAC regression."}
    y = design[y_col].astype(float)
    x = design[x_col].astype(float)
    X = sm.add_constant(np.asarray(x, dtype=float))
    model = sm.OLS(np.asarray(y, dtype=float), X, missing="drop").fit(cov_type="HAC", cov_kwds={"maxlags": int(lags), "use_correction": True})
    return {
        "status": "complete",
        "coefficient": _round(model.params[1]),
        "HAC_se": _round(model.bse[1]),
        "t_stat": _round(model.tvalues[1], 4),
        "p_value": _round(model.pvalues[1], 6),
        "r2": _round(model.rsquared),
        "nobs": int(model.nobs),
    }


def _oos_r2(design, y_col: str, x_col: str) -> dict[str, Any]:
    import numpy as np
    import statsmodels.api as sm

    if design is None or len(design) < 40:
        return {"status": "skipped", "reason": "Insufficient observations for out-of-sample validation."}
    split = max(10, int(len(design) * 0.7))
    train = design.iloc[:split]
    test = design.iloc[split:]
    if len(test) < 5:
        return {"status": "skipped", "reason": "Insufficient holdout observations."}
    model = sm.OLS(train[y_col].astype(float), sm.add_constant(train[[x_col]].astype(float)), missing="drop").fit()
    pred = model.predict(sm.add_constant(test[[x_col]].astype(float), has_constant="add"))
    y = test[y_col].astype(float)
    mse_model = float(((y - pred) ** 2).mean())
    mse_bench = float(((y - train[y_col].astype(float).mean()) ** 2).mean())
    r2_oos = 1.0 - mse_model / mse_bench if mse_bench else None
    return {"status": "complete", "oos_r2": _round(r2_oos), "train_n": int(len(train)), "test_n": int(len(test)), "benchmark": "training-sample mean"}


def _rolling_correlation_summary(design, y_col: str, x_col: str, window: int = 63) -> dict[str, Any]:
    if len(design) < window + 5:
        return {"status": "skipped", "reason": "Insufficient observations for rolling correlation."}
    corr = design[x_col].astype(float).rolling(window).corr(design[y_col].astype(float)).dropna()
    return {"status": "complete", "window": int(window), "mean_rolling_corr": _round(corr.mean()), "min_rolling_corr": _round(corr.min()), "max_rolling_corr": _round(corr.max()), "nobs": int(corr.count())}


def compute_time_series(session_id: str | None, blueprint: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    summary_rows, summary_csv = _summary_csv(ctx)
    design, predictor_name, target_name, horizon = _time_series_design(ctx, blueprint)
    hac = _hac_regression(design, "outcome", "predictor_lag1", lags=5)
    oos = _oos_r2(design, "outcome", "predictor_lag1")
    rolling = _rolling_correlation_summary(design, "outcome", "predictor_lag1")
    placebo = placebo_test(ctx.returns, {"observed_stat": hac.get("coefficient") or 0.0, "sample_size": 21, "draws": 1000})
    boot = bootstrap_ci(design.rename(columns={"outcome": "estimate_series"}), {"column": "estimate_series", "iterations": 2000}) if len(design) else {"status": "skipped", "reason": "No design rows."}
    results = {"predictive_regression_hac": hac, "out_of_sample_r2": oos, "rolling_correlation": rolling, "placebo_test": placebo, "bootstrap_ci": boot}
    p_values = [payload.get("p_value") for payload in results.values() if isinstance(payload, dict) and payload.get("p_value") is not None]
    results["bh_correction"] = bh_correction(ctx.returns, {"p_values": p_values})
    stats_rows = _flatten_results(results)
    stats_csv = _stats_csv(stats_rows)
    design_rows = design.copy()
    if "date" in design_rows.columns:
        design_rows["date"] = design_rows["date"].astype(str)
    design_csv = _csv_text(design_rows.to_dict(orient="records"), list(design_rows.columns)) if len(design_rows) else _csv_text([{"status": "skipped", "reason": "No usable time-series design rows."}], ["status", "reason"])
    regression_csv = _csv_text([{"model": "predictive_regression_hac", "predictor": predictor_name, "outcome": horizon, **hac}], sorted({"model", "predictor", "outcome", *hac.keys()}))
    csv_outputs = {
        "03_data/overnight_returns.csv": _data_csv(ctx),
        "06_compute/method_outputs/predictive_series.csv": design_csv,
        "06_compute/method_outputs/time_series_regression.csv": regression_csv,
        "07_statistics/results_tables/summary_statistics.csv": summary_csv,
        "07_statistics/results_tables/executed_tests.csv": stats_csv,
        "07_statistics/results_tables/time_series_tests.csv": stats_csv,
        "08_stats/stats_summary.csv": stats_csv,
    }
    primary_numbers = {
        "row_count": int(len(ctx.returns)),
        "identifier_count": int(len(ctx.identifiers)),
        "event_count": "not computed for this design",
        "predictor": predictor_name,
        "outcome": horizon,
        "target_series": target_name,
        "newey_west_coefficient": hac.get("coefficient"),
        "newey_west_t_stat": hac.get("t_stat"),
        "newey_west_p_value": hac.get("p_value"),
        "oos_r2": oos.get("oos_r2"),
        "mean_rolling_corr": rolling.get("mean_rolling_corr"),
        "placebo_empirical_p_value": placebo.get("empirical_p_value"),
        "bootstrap_ci_lower": boot.get("ci_lower"),
        "bootstrap_ci_upper": boot.get("ci_upper"),
        "return_definition": blueprint.get("return_definition") or "close-to-close returns for predictive time-series design",
        "primary_analysis_type": "time_series",
    }
    conclusion = "hypothesis_supported" if hac.get("p_value") is not None and float(hac["p_value"]) < 0.05 else "hypothesis_not_supported_or_exploratory"
    return _result_package(ctx, method=str(ctx.method_family), primary_numbers=primary_numbers, results=results, stats_rows=stats_rows, csv_outputs=csv_outputs, summary_rows=summary_rows, conclusion=conclusion, interpretation="The time-series design estimates whether lagged predictors forecast subsequent returns while reporting dependence-robust precision and holdout fit.")


def _panel_design(ctx: ExecutionContext):
    import pandas as pd

    frame = ctx.returns.copy()
    frame["date_dt"] = pd.to_datetime(frame["date"])
    frame = frame.sort_values(["ticker", "date_dt"])
    groups = []
    for ticker, group in frame.groupby("ticker"):
        g = group.copy()
        ret = g["close_to_close_return"].astype(float)
        g["lagged_return"] = ret.shift(1)
        g["momentum_21d"] = ret.shift(1).rolling(21).sum()
        g["rolling_volatility_21d"] = ret.shift(1).rolling(21).std()
        g["next_quarter_return"] = ret.shift(-1).rolling(63).sum().shift(-62)
        groups.append(g)
    return pd.concat(groups, ignore_index=True).dropna(subset=["next_quarter_return", "momentum_21d", "rolling_volatility_21d"])


def _pooled_regression(design) -> dict[str, Any]:
    import statsmodels.api as sm

    if design is None or len(design) < 20:
        return {"status": "skipped", "reason": "Insufficient panel observations for pooled regression."}
    y = design["next_quarter_return"].astype(float)
    X = sm.add_constant(design[["momentum_21d", "rolling_volatility_21d"]].astype(float))
    model = sm.OLS(y, X, missing="drop").fit(cov_type="HC3")
    return {"status": "complete", "coefficient": _round(model.params.get("momentum_21d")), "HC3_se": _round(model.bse.get("momentum_21d")), "t_stat": _round(model.tvalues.get("momentum_21d"), 4), "p_value": _round(model.pvalues.get("momentum_21d"), 6), "r2": _round(model.rsquared), "nobs": int(model.nobs)}


def compute_regression(session_id: str | None, blueprint: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    summary_rows, summary_csv = _summary_csv(ctx)
    design = _panel_design(ctx)
    pooled = _pooled_regression(design)
    panel = panel_regression(ctx.returns, {}) if len(ctx.identifiers) > 1 else {"status": "skipped", "reason": "Panel regression requires multiple identifiers."}
    subsample = subsample_analysis(ctx.returns, {})
    boot = bootstrap_ci(design.rename(columns={"next_quarter_return": "target"}), {"column": "target", "iterations": 2000}) if len(design) else {"status": "skipped", "reason": "No regression design rows."}
    results = {"pooled_regression_hc3": pooled, "panel_regression": panel, "subsample_analysis": subsample, "bootstrap_ci": boot}
    p_values = [payload.get("p_value") for payload in results.values() if isinstance(payload, dict) and payload.get("p_value") is not None]
    results["bh_correction"] = bh_correction(ctx.returns, {"p_values": p_values})
    stats_rows = _flatten_results(results)
    stats_csv = _stats_csv(stats_rows)
    design_rows = design.drop(columns=["date_dt"], errors="ignore").copy()
    csv_outputs = {
        "03_data/overnight_returns.csv": _data_csv(ctx),
        "06_compute/method_outputs/regression_design.csv": _csv_text(design_rows.to_dict(orient="records"), list(design_rows.columns)) if len(design_rows) else _csv_text([{"status": "skipped", "reason": "No usable regression design rows."}], ["status", "reason"]),
        "06_compute/method_outputs/regression_results.csv": _csv_text([{"model": "pooled_regression_hc3", **pooled}], sorted({"model", *pooled.keys()})),
        "07_statistics/results_tables/summary_statistics.csv": summary_csv,
        "07_statistics/results_tables/executed_tests.csv": stats_csv,
        "07_statistics/results_tables/regression_tests.csv": stats_csv,
        "08_stats/stats_summary.csv": stats_csv,
    }
    primary_numbers = {
        "row_count": int(len(ctx.returns)),
        "identifier_count": int(len(ctx.identifiers)),
        "event_count": "not computed for this design",
        "primary_predictor": "momentum_21d",
        "outcome": "next_quarter_return",
        "newey_west_coefficient": pooled.get("coefficient"),
        "newey_west_t_stat": pooled.get("t_stat"),
        "newey_west_p_value": pooled.get("p_value"),
        "regression_r2": pooled.get("r2"),
        "bootstrap_ci_lower": boot.get("ci_lower"),
        "bootstrap_ci_upper": boot.get("ci_upper"),
        "return_definition": blueprint.get("return_definition") or "forward return from verified price data",
        "primary_analysis_type": "regression",
    }
    conclusion = "hypothesis_supported" if pooled.get("p_value") is not None and float(pooled["p_value"]) < 0.05 else "hypothesis_not_supported_or_exploratory"
    return _result_package(ctx, method=str(ctx.method_family), primary_numbers=primary_numbers, results=results, stats_rows=stats_rows, csv_outputs=csv_outputs, summary_rows=summary_rows, conclusion=conclusion, interpretation="The regression design estimates whether pre-measured predictors explain subsequent returns with heteroskedasticity-robust precision.")


def compute_factor_model(session_id: str | None, blueprint: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    # A factor/backtest design still receives a returns-based execution rather
    # than event-shaped outputs; fuller factor libraries can replace this adapter.
    return compute_regression(session_id, {**blueprint, "method_family": "regression"}, ctx)


def compute_descriptive(session_id: str | None, blueprint: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    summary_rows, summary_csv = _summary_csv(ctx)
    boot = bootstrap_ci(ctx.returns, {"column": "overnight_return", "iterations": 2000})
    subsample = subsample_analysis(ctx.returns, {})
    results = {"bootstrap_ci": boot, "subsample_analysis": subsample}
    stats_rows = _flatten_results(results)
    stats_csv = _stats_csv(stats_rows)
    csv_outputs = {
        "03_data/overnight_returns.csv": _data_csv(ctx),
        "07_statistics/results_tables/summary_statistics.csv": summary_csv,
        "07_statistics/results_tables/executed_tests.csv": stats_csv,
        "08_stats/stats_summary.csv": stats_csv,
    }
    primary_numbers = {"row_count": int(len(ctx.returns)), "identifier_count": int(len(ctx.identifiers)), "event_count": "not computed for this design", "bootstrap_ci_lower": boot.get("ci_lower"), "bootstrap_ci_upper": boot.get("ci_upper"), "primary_analysis_type": "descriptive"}
    return _result_package(ctx, method=str(ctx.method_family), primary_numbers=primary_numbers, results=results, stats_rows=stats_rows, csv_outputs=csv_outputs, summary_rows=summary_rows, interpretation="The descriptive design reports distributional evidence without forcing an event-study or regression estimand.")


def compute_generic(session_id: str | None, blueprint: dict[str, Any], ctx: ExecutionContext) -> dict[str, Any]:
    return compute_descriptive(session_id, blueprint, ctx)


def execute_research_plan(blueprint: dict[str, Any], stats_spec: dict[str, Any] | None = None) -> dict[str, Any]:
    """Compatibility entrypoint used by session orchestration and tests."""
    return dispatch_compute(None, blueprint)
