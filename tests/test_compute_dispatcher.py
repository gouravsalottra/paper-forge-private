from __future__ import annotations


def _base_blueprint(method: str) -> dict:
    identifiers = ["VIX", "VIX3M", "SPY"] if method == "time_series" else ["SPY", "QQQ", "IWM"]
    return {
        "topic": "Does the VIX term structure inversion predict next-month momentum crashes in US equity sector ETFs?",
        "focus_question": "Does the VIX term structure inversion predict next-month momentum crashes in US equity sector ETFs?",
        "method_style": method,
        "method_family": method,
        "evidence_route": "yfinance",
        "inferred_identifiers": identifiers,
        "inferred_window": {"start": "2020-01-01", "end": "2021-12-31"},
    }


def test_compute_dispatcher_preserves_event_study_shape(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from api.compute_dispatcher import dispatch_compute

    result = dispatch_compute("unit-event", _base_blueprint("event_study"))

    assert result["primary_numbers"]["primary_analysis_type"] == "event_study"
    assert "06_compute/method_outputs/event_returns.csv" in result["csv_outputs"]
    assert "06_compute/method_outputs/event_window_car.csv" in result["csv_outputs"]
    assert result["primary_numbers"]["event_count"] > 0


def test_compute_dispatcher_time_series_not_event_shaped(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from api.compute_dispatcher import dispatch_compute

    result = dispatch_compute("unit-ts", _base_blueprint("time_series"))

    assert result["primary_numbers"]["primary_analysis_type"] == "time_series"
    assert "06_compute/method_outputs/predictive_series.csv" in result["csv_outputs"]
    assert "06_compute/method_outputs/time_series_regression.csv" in result["csv_outputs"]
    assert "06_compute/method_outputs/event_returns.csv" not in result["csv_outputs"]
    assert result["primary_numbers"]["event_count"] == "not computed for this design"


def test_compute_dispatcher_regression_not_event_shaped(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from api.compute_dispatcher import dispatch_compute

    result = dispatch_compute("unit-reg", _base_blueprint("regression"))

    assert result["primary_numbers"]["primary_analysis_type"] == "regression"
    assert "06_compute/method_outputs/regression_design.csv" in result["csv_outputs"]
    assert "06_compute/method_outputs/regression_results.csv" in result["csv_outputs"]
    assert "06_compute/method_outputs/event_returns.csv" not in result["csv_outputs"]


def test_figure_generator_uses_method_shaped_outputs(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from api.compute_dispatcher import dispatch_compute
    from api.figure_generator import generate_figures_for_study

    ts_blueprint = _base_blueprint("time_series")
    ts_result = dispatch_compute("unit-fig-ts", ts_blueprint)
    ts_figures = generate_figures_for_study("unit-fig-ts", ts_blueprint, ts_result["csv_outputs"], ts_result["primary_numbers"])
    assert "fig1_time_series" in ts_figures
    assert "fig2_predictive_scatter" in ts_figures
    assert "fig2_event_returns" not in ts_figures

    reg_blueprint = _base_blueprint("regression")
    reg_result = dispatch_compute("unit-fig-reg", reg_blueprint)
    reg_figures = generate_figures_for_study("unit-fig-reg", reg_blueprint, reg_result["csv_outputs"], reg_result["primary_numbers"])
    assert "fig1_regression_scatter" in reg_figures
    assert "fig2_event_returns" not in reg_figures
