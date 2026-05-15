from __future__ import annotations

from api.guide import _architecture_defaults, _statistical_battery
from api.method_registry import method_definition
from api.sessions import _execution_profile
from api.econometric_inventory import (
    all_modeling_frameworks,
    all_statistical_tests,
    method_research_design,
)


def test_master_inventory_contains_top_tier_finance_econometric_tests() -> None:
    tests = set(all_statistical_tests())
    required = {
        "Augmented Dickey-Fuller (ADF) Test",
        "Phillips-Perron (PP) Test",
        "KPSS Test",
        "Zivot-Andrews Test",
        "Lo's Modified Rescaled Range (R/S) Test",
        "Variance Ratio Test (Lo-MacKinlay)",
        "Ljung-Box Q-Test",
        "Durbin-Watson Test",
        "BDS Test",
        "Engle's ARCH LM Test",
        "Diebold-Mariano Test",
        "Granger Causality Test",
        "Toda-Yamamoto Causality Test",
        "Johansen Cointegration Test",
        "Engle-Granger Two-Step Test",
        "Chow Test",
        "Quandt-Andrews Unknown Breakpoint Test",
        "Bai-Perron Test",
        "Hausman Specification Test",
        "Sargan-Hansen J-Test",
        "Cragg-Donald Wald Test",
        "Stock-Yogo Weak ID Test",
        "Arellano-Bond AR(1)/AR(2) Tests",
        "Pesaran CD Test",
        "Breusch-Pagan LM Panel Test",
        "Breusch-Pagan Test",
        "White's General Heteroscedasticity Test",
        "Ramsey RESET Test",
        "Variance Inflation Factor (VIF)",
        "Jarque-Bera Test",
        "Shapiro-Wilk Test",
        "DeLong's Test",
        "McNemar's Test",
        "Pesaran-Timmermann Test",
        "White's Reality Check",
        "Hansen's Superior Predictive Ability (SPA) Test",
        "Log-Likelihood Ratio (LLR) Test",
        "Patell's t-Test",
        "Boehmer-Musumeci-Poulsen (BMP) Test",
        "Corrado Rank Test",
        "Cowan Sign Test",
        "Mann-Whitney U Test",
        "Kruskal-Wallis Test",
        "Gibbons-Ross-Shanken (GRS) Test",
        "Kupiec POF Test",
        "Christoffersen Interval Forecast Test",
    }
    assert required <= tests


def test_master_inventory_keeps_models_separate_from_tests() -> None:
    models = set(all_modeling_frameworks())
    tests = set(all_statistical_tests())

    assert "Capital Asset Pricing Model (CAPM)" in models
    assert "Fama-French Factor Models" in models
    assert "Carhart Four-Factor Model" in models
    assert "GARCH Family Models" in models
    assert "Black-Scholes-Merton Option Pricing Model" in models
    assert "Markowitz Mean-Variance Optimization" in models
    assert "Logistic Regression Classification" in models
    assert "Random Forest Classification" in models
    assert "Gradient Boosting Models (XGBoost/LightGBM)" in models
    assert "Cox Proportional Hazards Model" in models
    assert "Fixed Effects Panel Model" in models
    assert "Difference-in-Differences Model" in models
    assert "Instrumental Variables / 2SLS Model" in models
    assert "Vector Autoregression (VAR)" in models
    assert "Vector Error Correction Model (VECM)" in models
    assert "Arellano-Bond Dynamic Panel GMM" in models

    assert "Gibbons-Ross-Shanken (GRS) Test" in tests
    assert "Hausman Specification Test" in tests
    assert "DeLong's Test" in tests
    assert "Patell's t-Test" in tests
    assert "Capital Asset Pricing Model (CAPM)" not in tests
    assert "Augmented Dickey-Fuller (ADF) Test" not in models


def test_method_families_map_to_models_and_defensive_tests() -> None:
    cases = {
        "factor_model": {
            "models": {"Capital Asset Pricing Model (CAPM)", "Fama-French Factor Models", "Carhart Four-Factor Model"},
            "tests": {"Gibbons-Ross-Shanken (GRS) Test", "Engle's ARCH LM Test", "Variance Ratio Test (Lo-MacKinlay)"},
        },
        "risk_model": {
            "models": {"Value-at-Risk (VaR) Models", "Expected Shortfall (ES) Models"},
            "tests": {"Kupiec POF Test", "Christoffersen Interval Forecast Test"},
        },
        "machine_learning": {
            "models": {"Logistic Regression Classification", "Gradient Boosting Models (XGBoost/LightGBM)", "Deep Neural Networks"},
            "tests": {"DeLong's Test", "McNemar's Test", "Pesaran-Timmermann Test", "White's Reality Check", "Hansen's Superior Predictive Ability (SPA) Test"},
        },
        "event_study": {
            "models": {"Market Model Event Study", "Buy-and-Hold Abnormal Return Model"},
            "tests": {"Patell's t-Test", "Boehmer-Musumeci-Poulsen (BMP) Test", "Corrado Rank Test", "Cowan Sign Test"},
        },
        "time_series": {
            "models": {"ARIMA / ARIMAX Forecasting Model"},
            "tests": {"Augmented Dickey-Fuller (ADF) Test", "Phillips-Perron (PP) Test", "KPSS Test", "Zivot-Andrews Test", "Ljung-Box Q-Test", "Diebold-Mariano Test"},
        },
        "cointegration": {
            "models": {"Vector Error Correction Model (VECM)"},
            "tests": {"Johansen Cointegration Test", "Engle-Granger Two-Step Test"},
        },
        "panel_regression": {
            "models": {"Fixed Effects Panel Model", "Random Effects Panel Model"},
            "tests": {"Hausman Specification Test", "Pesaran CD Test", "Breusch-Pagan LM Panel Test"},
        },
        "instrumental_variables": {
            "models": {"Instrumental Variables / 2SLS Model"},
            "tests": {"Sargan-Hansen J-Test", "Cragg-Donald Wald Test", "Stock-Yogo Weak ID Test"},
        },
    }

    for method, expected in cases.items():
        design = method_research_design(method)
        assert expected["models"] <= set(design["modeling_frameworks"]), method
        assert expected["tests"] <= set(design["statistical_tests"]), method
        assert design["models_vs_tests_rule"].startswith("Models estimate")


def test_research_architect_exposes_models_and_tests_as_separate_contracts() -> None:
    battery = _statistical_battery("factor_model")
    assert "modeling_frameworks" in battery
    assert "diagnostic_tests" in battery
    assert "inference_tests" in battery
    assert "Gibbons-Ross-Shanken (GRS) Test" in battery["statistical_tests"]
    assert "Capital Asset Pricing Model (CAPM)" in battery["modeling_frameworks"]
    assert "Capital Asset Pricing Model (CAPM)" not in battery["statistical_tests"]

    spec = method_definition("machine_learning")
    assert "modeling_frameworks" in spec
    assert "diagnostic_tests" in spec
    assert "evaluation_tests" in spec
    assert "DeLong's Test" in spec["statistical_tests"]
    assert "Gradient Boosting Models (XGBoost/LightGBM)" in spec["modeling_frameworks"]


def test_architecture_defaults_replaces_stale_llm_methodology_contract() -> None:
    stale_llm_result = {
        "validated": True,
        "research_state": "confirmatory_pap",
        "clarifications": [],
        "blueprint_summary": {
            "method_style": "regression",
            "statistical_battery": {"method": "regression", "tests": ["newey_west"]},
        },
    }

    normalized = _architecture_defaults(
        stale_llm_result,
        {
            "topic": "Do Fama-French factor exposures explain sector ETF alpha after controlling for momentum and quality factors?",
        },
    )
    summary = normalized["blueprint_summary"]
    battery = summary["statistical_battery"]

    assert summary["method_style"] == "factor_model"
    assert battery["analytical_domain"] == "Quantitative Finance & Asset Pricing"
    assert "Capital Asset Pricing Model (CAPM)" in battery["modeling_frameworks"]
    assert "Gibbons-Ross-Shanken (GRS) Test" in battery["statistical_tests"]
    assert "Capital Asset Pricing Model (CAPM)" not in battery["statistical_tests"]


def test_execution_profile_gives_compute_and_statistics_agents_distinct_roles() -> None:
    profile = _execution_profile({
        "topic": "Do Fama-French factor exposures explain sector ETF alpha after controlling for momentum and quality factors?",
        "method_family": "factor_model",
        "method_style": "factor_model",
        "evidence_source": "yfinance",
        "hypothesis": "Factor exposures explain sector ETF alpha.",
    })

    execution = profile["execution_profile"]
    assert "Capital Asset Pricing Model (CAPM)" in execution["modeling_frameworks"]
    assert "Gibbons-Ross-Shanken (GRS) Test" in execution["statistical_tests"]
    assert "Capital Asset Pricing Model (CAPM)" not in execution["statistical_tests"]

    compute_skills = profile["agent_context"]["agents"]["Method / Compute Agent"]["skills"]
    stats_skills = profile["agent_context"]["agents"]["Statistics Agent"]["skills"]
    assert "Fama-French Factor Models" in compute_skills
    assert "Gibbons-Ross-Shanken (GRS) Test" in stats_skills
    assert "Fama-French Factor Models" not in stats_skills
