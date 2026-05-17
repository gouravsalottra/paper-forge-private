from __future__ import annotations

import inspect


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


def test_compute_dispatcher_executes_llm_authored_code(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from api.compute_dispatcher import dispatch_compute

    result = dispatch_compute("unit-llm-code", _base_blueprint("time_series"))

    assert "analysis_code" in result
    assert "DATA_CSV_PATH" in result["analysis_code"]
    assert result["csv_outputs"]
    assert "03_data/overnight_returns.csv" in result["csv_outputs"]
    assert any(path.startswith("07_statistics/results_tables/") for path in result["csv_outputs"])
    assert result["figure_artifacts"]
    assert result["primary_numbers"]["primary_label"]


def test_compute_dispatcher_has_no_method_specific_python_branches():
    import api.compute_dispatcher as cd

    source = inspect.getsource(cd.dispatch_compute)
    forbidden = [
        "compute_" + suffix
        for suffix in [
            "event_study",
            "time_series",
            "regression",
            "factor_model",
            "descriptive",
            "generic",
        ]
    ]
    for token in forbidden:
        assert token not in source
    assert "_llm_write_analysis_code" in source
    assert "_execute_analysis_code" in source
    assert "_llm_format_results" in source


def test_compute_dispatcher_does_not_emit_old_event_outputs_for_non_event(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from api.compute_dispatcher import dispatch_compute

    result = dispatch_compute("unit-ts", _base_blueprint("time_series"))

    assert "06_compute/method_outputs/event_returns.csv" not in result["csv_outputs"]
    assert "06_compute/method_outputs/event_window_car.csv" not in result["csv_outputs"]
    assert result["primary_numbers"].get("primary_analysis_type") == "time_series"


def test_figure_generator_is_compute_artifact_inventory_only():
    from api.figure_generator import generate_figures_for_study

    existing = {
        "fig1": {
            "filename": "analysis.png",
            "path": "figures/analysis.png",
            "label": "fig:analysis",
        }
    }
    assert generate_figures_for_study("unit", {}, {}, {"figure_artifacts": existing}) == existing
    assert generate_figures_for_study("unit", {}, {}, {}) == {}
