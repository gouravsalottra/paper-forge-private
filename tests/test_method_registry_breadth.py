from __future__ import annotations

from api.guide import _fallback_blueprint, _leakage_policy, _reviewer_gate, _statistical_battery, _economic_significance
from api.method_registry import METHOD_FAMILY_REGISTRY, method_definition
from api.sessions import _execution_profile


BROAD_METHOD_TOPICS = {
    "factor_model": "Do Fama-French factor exposures explain sector ETF alpha after controlling for momentum and quality factors?",
    "event_study": "Do FOMC announcement surprises produce significant cumulative abnormal returns in bank ETFs during a three-day event window?",
    "difference_in_differences": "Does a short-sale ban reduce liquidity relative to untreated peer stocks using a difference-in-difference design with parallel trends?",
    "instrumental_variables": "Does index inclusion affect corporate bond liquidity using an instrumental variable with a strong first stage and exclusion restriction?",
    "regression_discontinuity": "Does crossing a credit-rating cutoff change funding costs in a regression discontinuity design around the threshold?",
    "synthetic_control": "Did a macroprudential policy shock reduce bank equity volatility relative to a synthetic control donor pool?",
    "portfolio_optimization": "Can Black Litterman portfolio optimization improve out-of-sample Sharpe versus risk parity under turnover constraints?",
    "risk_model": "Can expected shortfall and value at risk models forecast tail risk breaches during high volatility regimes?",
    "volatility_model": "Does a GARCH volatility forecast outperform realized volatility benchmarks for sector ETF risk prediction?",
    "time_series": "Can an ARIMA time series forecast predict weekly credit spread changes after structural break tests?",
    "var_model": "Do inflation shocks propagate to sector ETF returns through a vector autoregression with impulse response functions?",
    "cointegration": "Are two commodity ETFs cointegrated enough for a mean reverting spread pairs trading strategy with half-life estimates?",
    "machine_learning": "Can an XGBoost machine learning model predict downside ETF returns using walk-forward validation and feature importance?",
    "network_analysis": "Do ETF holdings network centrality measures predict systemic risk contagion during stress periods?",
    "stress_testing": "How do sector rotation strategies perform under stress scenario analysis with oil shock and credit-spread widening scenarios?",
    "survival_hazard": "Does firm leverage predict time to default using a survival hazard model with censoring rules?",
    "bayesian_model": "Does a Bayesian hierarchical model estimate posterior sector risk premia with prior sensitivity checks?",
    "clustering": "Can regime clustering segment market states using volatility, correlation, and credit spread features?",
    "anomaly_detection": "Can anomaly detection identify unusual intraday ETF trading activity while controlling false positive alerts?",
    "meta_analysis": "What is the pooled effect size in a meta-analysis of published momentum crash studies with publication bias tests?",
}


def test_method_registry_is_broad_enough_for_research_lab_coverage() -> None:
    assert len(METHOD_FAMILY_REGISTRY) >= 24
    required = {
        "descriptive", "regression", "panel_regression", "factor_model", "event_study",
        "difference_in_differences", "instrumental_variables", "regression_discontinuity",
        "synthetic_control", "backtest", "portfolio_optimization", "risk_model",
        "volatility_model", "time_series", "var_model", "cointegration", "machine_learning",
        "text_analysis", "network_analysis", "agent_based_model", "simulation", "stress_testing",
        "survival_hazard", "bayesian_model", "clustering", "anomaly_detection", "meta_analysis",
    }
    assert required <= set(METHOD_FAMILY_REGISTRY)



def test_research_architect_routes_broad_finance_topics_to_method_families() -> None:
    for expected_method, topic in BROAD_METHOD_TOPICS.items():
        summary = _fallback_blueprint({"topic": topic})["blueprint_summary"]
        assert summary["method_style"] == expected_method, expected_method
        assert summary["evidence_source"] in method_definition(expected_method)["evidence_routes"], expected_method



def test_every_registered_method_has_pipeline_contracts() -> None:
    for method, spec in METHOD_FAMILY_REGISTRY.items():
        assert len(_statistical_battery(method)["tests"]) >= 3, method
        assert _leakage_policy(method)["primary_rule"] == spec["leakage_rule"], method
        assert _economic_significance(method)["rule"] == spec["economic_rule"], method
        assert len(_reviewer_gate(True, method)["method_focus"]) >= 3, method

        profile = _execution_profile({
            "topic": f"Generic {method} research question in empirical finance",
            "focus_question": f"Can a {method} design answer this finance research question?",
            "method_family": method,
            "method_style": method,
            "evidence_source": spec["evidence_routes"][0],
            "hypothesis": "The selected method produces reviewer-checkable evidence.",
        })
        assert profile["method_family"] == method, method
        assert profile["compute_path"] == spec["compute_path"], method
        assert profile["compute"]["result_schema"] == spec["result_schema"], method
        assert method in profile["agent_context"]["agents"]["Method / Compute Agent"]["skills"], method
        assert profile["verification"]["numbers_verified"] is True, method
