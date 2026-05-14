from __future__ import annotations

import re
from typing import Any


def _entry(
    label: str,
    aliases: list[str],
    tests: list[str],
    reviewer_focus: list[str],
    leakage_rule: str,
    economic_rule: str,
    evidence_routes: list[str],
    concepts: list[str],
    features: list[str],
    primary_test: str,
    claim_scope: str,
) -> dict[str, Any]:
    return {
        "label": label,
        "aliases": aliases,
        "tests": tests,
        "reviewer_focus": reviewer_focus,
        "leakage_rule": leakage_rule,
        "economic_rule": economic_rule,
        "evidence_routes": evidence_routes,
        "concepts": concepts,
        "features": features,
        "primary_test": primary_test,
        "claim_scope": claim_scope,
        "compute_path": f"06_compute/method_outputs/{label}_results.json",
        "result_schema": f"{label}_v1",
    }


METHOD_FAMILY_REGISTRY: dict[str, dict[str, Any]] = {
    "descriptive": _entry(
        "descriptive",
        ["descriptive", "summary statistics", "describe", "map", "profile", "document"],
        ["coverage_profile", "summary_statistics", "correlation_map", "sample_stability"],
        ["coverage", "descriptive limits", "hypothesis-generating language", "sample representativeness"],
        "Descriptive summaries must not be reframed as predictive or causal evidence.",
        "Report magnitude, coverage, and sample limits without implying decision readiness.",
        ["upload", "yfinance", "fred_yfinance", "public_fallback"],
        ["descriptive finance", "data profiling", "stylized facts"],
        ["sample", "date", "identifier", "metric", "segment"],
        "Coverage profile, stability diagnostics, and descriptive statistics",
        "descriptive evidence",
    ),
    "regression": _entry(
        "regression",
        ["regression", "predict", "coefficient", "controls", "panel", "cross-sectional", "forecast"],
        ["newey_west", "fama_macbeth", "factor_regression", "out_of_sample_r2", "multiple_testing_control"],
        ["identification", "standard errors", "controls", "out-of-sample validity"],
        "Right-hand-side timing must be prior or explicitly contemporaneous in the Blueprint.",
        "Report annualized alpha or basis-point effect size, not just p-values.",
        ["yfinance", "upload", "fred_yfinance", "public_fallback"],
        ["predictive regression", "panel econometrics", "factor controls"],
        ["dependent_variable", "predictor", "control", "date", "entity"],
        "Panel or time-series regression with robust standard errors and multiple-testing control",
        "regression evidence",
    ),
    "panel_regression": _entry(
        "panel_regression",
        ["fixed effects", "random effects", "panel data", "two-way fixed", "entity fixed", "firm fixed"],
        ["entity_fixed_effects", "time_fixed_effects", "clustered_standard_errors", "hausman_test"],
        ["fixed-effect choice", "cluster level", "serial correlation", "within variation"],
        "Panel covariates must be timestamped before the outcome window and fixed-effect choices must be locked.",
        "Report within-entity effect size and economic magnitude per standard deviation change.",
        ["upload", "yfinance", "fred_yfinance"],
        ["panel econometrics", "fixed effects", "clustered inference"],
        ["entity_id", "time", "outcome", "predictor", "fixed_effect"],
        "Two-way fixed-effects panel regression with clustered standard errors",
        "panel regression evidence",
    ),
    "factor_model": _entry(
        "factor_model",
        ["fama french", "factor model", "factor exposure", "alpha", "beta", "carhart", "q-factor", "spanning"],
        ["factor_regression", "alpha_t_test", "spanning_test", "rolling_beta", "factor_timing_test"],
        ["factor choice", "alpha interpretation", "benchmark fairness", "look-ahead in factor construction"],
        "Factor returns and portfolio membership must be known at the test timestamp.",
        "Report alpha in annualized basis points and exposure stability, not only significance.",
        ["yfinance", "upload", "public_fallback"],
        ["asset pricing", "factor models", "alpha testing"],
        ["return", "factor_return", "portfolio", "exposure", "alpha"],
        "Fama-French or custom factor regression with spanning and rolling exposure checks",
        "asset-pricing factor evidence",
    ),
    "event_study": _entry(
        "event_study",
        ["event study", "announcement", "event window", "abnormal return", "CAR", "BHAR", "fomc"],
        ["CAR", "BHAR", "market_model_abnormal_return", "cross_sectional_CAR_regression", "bootstrap_inference"],
        ["event timing", "confounds", "expected return model", "event-window leakage"],
        "Feature windows cannot overlap the event window unless explicitly locked in the Blueprint.",
        "Report abnormal return magnitude relative to bid-ask spreads and event-window noise.",
        ["yfinance", "edgar_yfinance", "upload", "fred_yfinance"],
        ["event studies", "abnormal returns", "announcement effects"],
        ["event_date", "security", "expected_return", "abnormal_return", "window"],
        "Cumulative abnormal return event study with expected-return model robustness",
        "event-study evidence",
    ),
    "difference_in_differences": _entry(
        "difference_in_differences",
        ["difference-in-difference", "diff-in-diff", "parallel trends", "treated control"],
        ["parallel_trends_test", "event_study_leads_lags", "two_way_fixed_effects", "placebo_treatment"],
        ["parallel trends", "treatment timing", "spillovers", "control-group validity"],
        "Treatment timing and comparison groups must be locked before outcome inspection.",
        "Report treatment effect in economically interpretable units with pre-trend diagnostics.",
        ["upload", "fred_yfinance", "public_fallback"],
        ["quasi-experimental design", "policy shocks", "parallel trends"],
        ["treated", "control", "post", "outcome", "unit"],
        "Difference-in-differences with pre-trend and placebo diagnostics",
        "quasi-causal evidence",
    ),
    "instrumental_variables": _entry(
        "instrumental_variables",
        ["instrumental variable", "instrument", "iv", "2sls", "exclusion restriction", "first stage"],
        ["first_stage_f_statistic", "iv_2sls", "overidentification_test", "weak_instrument_diagnostics"],
        ["instrument validity", "exclusion restriction", "weak instruments", "local effect interpretation"],
        "Instrument choice must be declared before estimation and cannot be searched after seeing first-stage results.",
        "Report local average treatment effect and first-stage strength with economic units.",
        ["upload", "fred_yfinance", "public_fallback"],
        ["causal inference", "instrumental variables", "endogeneity"],
        ["instrument", "endogenous_variable", "outcome", "controls", "sample"],
        "Two-stage least squares with weak-instrument and exclusion diagnostics",
        "instrumental-variable evidence",
    ),
    "regression_discontinuity": _entry(
        "regression_discontinuity",
        ["regression discontinuity", "rdd", "cutoff", "threshold", "bandwidth", "running variable"],
        ["bandwidth_sensitivity", "mccrary_density_test", "local_linear_rdd", "placebo_cutoffs"],
        ["cutoff validity", "manipulation around threshold", "bandwidth choice", "local interpretation"],
        "Running variable, cutoff, and bandwidth selection rule must be locked before outcome estimation.",
        "Report local treatment effect near cutoff and sensitivity to bandwidth.",
        ["upload", "public_fallback"],
        ["quasi-experiment", "threshold design", "local identification"],
        ["running_variable", "cutoff", "outcome", "bandwidth", "treatment"],
        "Local linear regression discontinuity with density and bandwidth robustness checks",
        "local causal evidence",
    ),
    "synthetic_control": _entry(
        "synthetic_control",
        ["synthetic control", "donor pool", "treated unit", "counterfactual", "synthetic benchmark"],
        ["pre_treatment_fit", "donor_weight_stability", "placebo_units", "gap_in_gap"],
        ["donor pool validity", "pre-treatment fit", "post-treatment window", "placebo ranking"],
        "Donor pool and pre-treatment predictors must be locked before post-treatment outcomes are inspected.",
        "Report treatment gap relative to pre-treatment fit and placebo distribution.",
        ["upload", "yfinance", "fred_yfinance"],
        ["synthetic counterfactuals", "policy evaluation", "comparative case studies"],
        ["treated_unit", "donor_unit", "pre_period", "post_period", "outcome"],
        "Synthetic control with donor-pool, placebo, and pre-fit diagnostics",
        "synthetic-control evidence",
    ),
    "backtest": _entry(
        "backtest",
        ["backtest", "rebalance", "rebalancing", "rotation", "momentum strategy", "strategy allocation", "portfolio allocation", "trading strategy", "sharpe", "drawdown"],
        ["net_return", "annualized_sharpe", "max_drawdown", "turnover_cost", "deflated_sharpe", "block_bootstrap"],
        ["transaction costs", "turnover", "benchmark fairness", "look-ahead bias", "deflated Sharpe"],
        "No feature can use information released after the rebalance decision timestamp.",
        "Report net-of-cost returns, Sharpe, max drawdown, turnover, and capacity caveats.",
        ["yfinance", "upload", "public_fallback"],
        ["backtesting", "portfolio rules", "market frictions"],
        ["signal", "rebalance_date", "weight", "return", "cost"],
        "Net-of-cost backtest with turnover, drawdown, and block-bootstrap robustness",
        "backtest evidence",
    ),
    "portfolio_optimization": _entry(
        "portfolio_optimization",
        ["portfolio optimization", "mean variance", "risk parity", "black litterman", "efficient frontier", "allocation"],
        ["out_of_sample_sharpe", "turnover", "weight_stability", "constraint_sensitivity"],
        ["estimation error", "constraint realism", "turnover", "out-of-sample validation"],
        "Optimization inputs must be estimated using only information available before portfolio formation.",
        "Report risk-adjusted return, turnover, drawdown, and allocation stability.",
        ["yfinance", "upload"],
        ["portfolio construction", "optimization", "risk allocation"],
        ["asset", "expected_return", "covariance", "constraint", "weight"],
        "Out-of-sample portfolio optimization with turnover and stability diagnostics",
        "portfolio optimization evidence",
    ),
    "risk_model": _entry(
        "risk_model",
        ["var", "value at risk", "expected shortfall", "tail risk", "stress test", "risk model"],
        ["var_backtest", "expected_shortfall_backtest", "kupiec_test", "christoffersen_test", "stress_scenario_loss"],
        ["tail coverage", "backtest breaches", "stress scenario design", "distributional assumptions"],
        "Risk thresholds and stress scenarios must be declared before breach analysis.",
        "Report losses, exceedance rates, capital relevance, and tail coverage.",
        ["yfinance", "upload", "fred_yfinance"],
        ["market risk", "tail risk", "stress testing"],
        ["return", "risk_factor", "var", "expected_shortfall", "breach"],
        "VaR/expected-shortfall model with breach and stress-test diagnostics",
        "risk-model evidence",
    ),
    "volatility_model": _entry(
        "volatility_model",
        ["garch", "volatility model", "realized volatility", "stochastic volatility", "volatility forecast"],
        ["garch_1_1", "realized_volatility_loss", "qlike_loss", "volatility_forecast_encompassing"],
        ["forecast horizon", "volatility proxy", "loss function", "regime stability"],
        "Volatility target, forecast horizon, and realized-volatility proxy must be locked before scoring.",
        "Report forecast loss improvement and impact on risk or allocation decisions.",
        ["yfinance", "upload", "fred_yfinance"],
        ["volatility forecasting", "GARCH", "risk management"],
        ["return", "realized_volatility", "forecast", "horizon", "loss"],
        "Volatility forecast comparison with QLIKE and robustness by regime",
        "volatility-model evidence",
    ),
    "time_series": _entry(
        "time_series",
        ["time series", "arima", "forecasting", "autocorrelation", "stationarity", "unit root"],
        ["adf_unit_root", "arima_forecast", "rolling_oos_error", "ljung_box", "structural_break_test"],
        ["stationarity", "look-ahead in rolling windows", "forecast horizon", "structural breaks"],
        "Forecast windows must roll forward without future observations leaking into model fitting.",
        "Report forecast error reduction, directional accuracy, and decision impact.",
        ["yfinance", "fred_yfinance", "upload"],
        ["time-series econometrics", "forecasting", "stationarity"],
        ["date", "series", "lag", "forecast", "actual"],
        "Rolling time-series forecast with stationarity and structural-break diagnostics",
        "time-series evidence",
    ),
    "var_model": _entry(
        "var_model",
        ["vector autoregression", "VAR", "impulse response", "granger", "forecast error variance"],
        ["lag_selection", "granger_causality", "impulse_response", "variance_decomposition"],
        ["lag length", "stationarity", "ordering assumptions", "shock interpretation"],
        "Lag order and variable ordering must be locked before impulse response interpretation.",
        "Report impulse-response magnitudes and persistence in economically meaningful units.",
        ["fred_yfinance", "yfinance", "upload"],
        ["macroeconometrics", "dynamic systems", "shock transmission"],
        ["series", "lag", "shock", "response", "horizon"],
        "VAR with Granger tests, impulse responses, and variance decomposition",
        "dynamic time-series evidence",
    ),
    "cointegration": _entry(
        "cointegration",
        ["cointegration", "johansen", "pairs trading", "error correction", "mean reverting spread"],
        ["adf_spread_test", "johansen_cointegration", "error_correction_model", "half_life_estimate"],
        ["unit roots", "spread stability", "sample dependence", "tradeability"],
        "Pair/universe selection and spread construction must be fixed before cointegration testing.",
        "Report spread half-life, drawdown, transaction-cost adjusted profitability, and break risk.",
        ["yfinance", "upload"],
        ["cointegration", "pairs trading", "error correction"],
        ["asset_a", "asset_b", "spread", "error_correction", "half_life"],
        "Cointegration and error-correction analysis with half-life and stability tests",
        "cointegration evidence",
    ),
    "machine_learning": _entry(
        "machine_learning",
        ["machine learning", "random forest", "xgboost", "neural network", "prediction model", "classification"],
        ["walk_forward_validation", "feature_importance", "calibration", "out_of_sample_auc", "permutation_test"],
        ["train-test leakage", "hyperparameter search", "feature timing", "economic utility"],
        "Training, validation, and test splits must be chronological for market outcomes.",
        "Report out-of-sample economic utility and calibration, not just ML metrics.",
        ["upload", "yfinance", "edgar_yfinance", "text_corpus"],
        ["predictive modeling", "machine learning", "walk-forward validation"],
        ["feature", "target", "train_window", "test_window", "prediction"],
        "Walk-forward ML validation with leakage checks and economic utility reporting",
        "machine-learning prediction evidence",
    ),
    "text_analysis": _entry(
        "text_analysis",
        ["llm", "nlp", "sentiment", "text analysis", "earnings call", "transcript", "text corpus", "filing", "filings", "embedding", "risk language"],
        ["sentiment_score_distribution", "topic_model_coherence", "cross_sectional_sentiment_regression", "tone_shift_detection", "event_study_on_sentiment"],
        ["sentiment approach validity", "look-ahead in text windows", "multiple testing across dictionary choices", "economic magnitude of text signals"],
        "Text window and scoring approach must be locked before market response analysis.",
        "Report text signal effect in basis points per sentiment or embedding-distance unit.",
        ["text_corpus", "edgar_yfinance", "upload"],
        ["financial text", "sentiment", "embeddings", "event response"],
        ["document_time", "issuer", "text_score", "embedding_distance", "market_response"],
        "Text-signal panel/event model with timestamp and multiple-testing controls",
        "text-analysis evidence",
    ),
    "network_analysis": _entry(
        "network_analysis",
        ["network", "graph", "centrality", "systemic risk", "contagion", "interconnectedness", "holdings network"],
        ["centrality_measures", "contagion_simulation", "interconnectedness_index", "systemic_risk_contribution", "network_stability_test"],
        ["network construction methodology", "threshold sensitivity", "temporal stability", "contagion mechanism validity"],
        "Network construction methodology and thresholds must be defined before centrality or contagion analysis.",
        "Report systemic-risk contribution and contagion speed in interpretable units.",
        ["upload", "public_fallback", "yfinance"],
        ["networks", "systemic risk", "contagion"],
        ["node", "edge", "weight", "centrality", "shock"],
        "Network construction with centrality, contagion, and threshold sensitivity checks",
        "network-analysis evidence",
    ),
    "agent_based_model": _entry(
        "agent_based_model",
        ["agent-based", "agent based", "multi-agent", "multi agent", "agents interact", "emergent", "learned strategies"],
        ["crash_frequency_comparison", "crash_severity_distribution", "correlation_structure_analysis", "heterogeneity_index", "market_impact_measurement", "liquidity_stress_test"],
        ["agent strategy realism", "market clearing mechanism validity", "heterogeneity design", "results sensitivity to agent fraction", "learning algorithm justification"],
        "Agent strategy parameters must be fixed before simulation runs.",
        "Report market impact in basis points and liquidity deterioration in spread widening.",
        ["simulation_generated", "upload"],
        ["agent-based models", "market microstructure", "simulation"],
        ["agent_type", "strategy", "state", "order", "market_outcome"],
        "Agent-based simulation with sensitivity to population, strategy, and market mechanism",
        "simulation evidence",
    ),
    "simulation": _entry(
        "simulation",
        ["simulation", "synthetic", "monte carlo", "simulated"],
        ["frequency_distribution_comparison", "severity_distribution_comparison", "monte_carlo_bootstrap", "variance_ratio_test"],
        ["parameter lock", "simulation design", "sensitivity", "generalisability"],
        "Simulation parameters must be locked in the Blueprint before results are observed.",
        "Report effect sizes with bootstrap confidence intervals and sensitivity to parameters.",
        ["simulation_generated", "upload"],
        ["simulation", "Monte Carlo", "mechanism testing"],
        ["parameter", "scenario", "draw", "outcome", "seed"],
        "Monte Carlo simulation with parameter sensitivity and bootstrap uncertainty",
        "simulation evidence",
    ),
    "stress_testing": _entry(
        "stress_testing",
        ["stress test", "stress scenario", "scenario analysis", "crisis scenario", "shock scenario"],
        ["scenario_loss", "sensitivity_grid", "tail_outcome", "breach_count"],
        ["scenario plausibility", "parameter severity", "baseline comparison", "tail coverage"],
        "Stress scenarios and severity grids must be locked before loss or performance outcomes are inspected.",
        "Report downside loss, breach frequency, and capital or allocation relevance.",
        ["simulation_generated", "upload", "yfinance", "fred_yfinance"],
        ["stress testing", "scenario analysis", "tail events"],
        ["scenario", "shock", "baseline", "loss", "recovery"],
        "Scenario stress test with baseline comparison and sensitivity grid",
        "stress-test evidence",
    ),
    "survival_hazard": _entry(
        "survival_hazard",
        ["survival", "hazard", "duration", "time to", "default probability", "failure time"],
        ["cox_model", "hazard_ratio", "kaplan_meier", "proportional_hazards_test"],
        ["censoring", "duration definition", "time-varying covariates", "hazard proportionality"],
        "Entry time, censoring rule, and event definition must be locked before hazard estimation.",
        "Report hazard ratios and survival-time changes in practical economic units.",
        ["upload", "fred_yfinance", "public_fallback"],
        ["survival analysis", "duration models", "default risk"],
        ["start_time", "end_time", "event", "censor", "covariate"],
        "Survival/hazard model with censoring and proportional-hazard diagnostics",
        "duration-model evidence",
    ),
    "bayesian_model": _entry(
        "bayesian_model",
        ["bayesian", "posterior", "prior", "mcmc", "hierarchical model"],
        ["posterior_interval", "prior_sensitivity", "mcmc_diagnostics", "posterior_predictive_check"],
        ["prior choice", "convergence", "posterior predictive fit", "hierarchical pooling"],
        "Priors and model hierarchy must be declared before posterior inspection.",
        "Report posterior intervals, probability of economically meaningful effects, and prior sensitivity.",
        ["upload", "yfinance", "fred_yfinance"],
        ["Bayesian inference", "posterior uncertainty", "hierarchical models"],
        ["prior", "likelihood", "posterior", "draw", "parameter"],
        "Bayesian model with posterior predictive checks and prior sensitivity",
        "Bayesian evidence",
    ),
    "clustering": _entry(
        "clustering",
        ["cluster", "clustering", "segmentation", "k-means", "regime clustering"],
        ["cluster_stability", "silhouette_score", "out_of_sample_assignment", "economic_label_validation"],
        ["cluster stability", "feature scaling", "post-hoc labeling", "economic interpretation"],
        "Clustering features and number-selection rule must be locked before interpreting clusters.",
        "Report stability and economic interpretability, not just cluster fit statistics.",
        ["upload", "yfinance", "fred_yfinance"],
        ["unsupervised learning", "segmentation", "regime discovery"],
        ["feature", "cluster", "distance", "label", "stability"],
        "Cluster analysis with stability, scaling, and economic labeling checks",
        "unsupervised evidence",
    ),
    "anomaly_detection": _entry(
        "anomaly_detection",
        ["anomaly", "outlier", "fraud detection", "market abuse", "unusual activity"],
        ["precision_recall", "false_positive_rate", "time_split_validation", "alert_stability"],
        ["label quality", "false positives", "look-ahead in alerts", "base-rate fallacy"],
        "Alert thresholds must be fixed before evaluating anomaly outcomes.",
        "Report alert precision, false-positive cost, and operational burden.",
        ["upload", "yfinance", "public_fallback"],
        ["anomaly detection", "surveillance", "alerting"],
        ["timestamp", "entity", "score", "threshold", "alert"],
        "Anomaly detection with time-split validation and false-positive accounting",
        "anomaly-detection evidence",
    ),
    "meta_analysis": _entry(
        "meta_analysis",
        ["meta-analysis", "meta analysis", "pooled effect", "publication bias", "effect size synthesis", "systematic review"],
        ["effect_size_synthesis", "publication_bias_test", "heterogeneity_i_squared", "funnel_plot", "meta_regression"],
        ["publication bias", "study heterogeneity", "inclusion criteria", "effect size comparability"],
        "Paper inclusion criteria must be locked before effect-size extraction.",
        "Report pooled effect size, confidence interval, and heterogeneity.",
        ["manual_connector_request", "upload", "public_fallback"],
        ["systematic review", "effect synthesis", "publication bias"],
        ["paper", "effect_size", "standard_error", "sample", "method"],
        "Meta-analysis with inclusion lock, heterogeneity, and publication-bias diagnostics",
        "literature-synthesis evidence",
    ),
}


def method_families() -> set[str]:
    return set(METHOD_FAMILY_REGISTRY)


def method_definition(method: str) -> dict[str, Any]:
    return METHOD_FAMILY_REGISTRY.get(method, METHOD_FAMILY_REGISTRY["descriptive"])


def infer_method_family(text: str, confirmatory: bool = False) -> str:
    lower = text.lower()
    if any(term in lower for term in ["agent-based", "agent based", "multi-agent", "multi agent", "agents interact", "emergent", "learned strategies"]):
        return "agent_based_model"
    if any(term in lower for term in ["stress scenario", "scenario analysis", "stress test", "crisis scenario", "shock scenario"]):
        return "stress_testing"
    if any(term in lower for term in ["momentum strategy", "strategy allocation", "sector rotation", "rebalance", "rebalancing"]):
        return "backtest"
    priority = [
        "agent_based_model",
        "text_analysis",
        "network_analysis",
        "event_study",
        "difference_in_differences",
        "instrumental_variables",
        "regression_discontinuity",
        "synthetic_control",
        "risk_model",
        "volatility_model",
        "var_model",
        "cointegration",
        "stress_testing",
        "portfolio_optimization",
        "backtest",
        "factor_model",
        "machine_learning",
        "survival_hazard",
        "bayesian_model",
        "clustering",
        "anomaly_detection",
        "meta_analysis",
        "time_series",
        "panel_regression",
        "simulation",
        "regression",
        "descriptive",
    ]
    for method in priority:
        spec = METHOD_FAMILY_REGISTRY[method]
        if any(_alias_matches(lower, alias) for alias in spec["aliases"]):
            return method
    if any(term in lower for term in ["causal", "natural experiment", "quasi-experiment"]):
        return "difference_in_differences"
    return "regression" if confirmatory else "descriptive"


def _alias_matches(text: str, alias: str) -> bool:
    alias = alias.lower()
    if len(alias) <= 4 and alias.replace("-", "").isalnum():
        return re.search(rf"\b{re.escape(alias)}\b", text) is not None
    return alias in text


def infer_evidence_route(text: str, method: str | None = None) -> str:
    lower = text.lower()
    method = method or infer_method_family(text, False)
    if method in {"agent_based_model", "simulation", "stress_testing"} and any(term in lower for term in ["simulation", "synthetic", "simulated", "monte carlo", "agent-based", "agent based", "multi-agent"]):
        return "simulation_generated"
    if any(term in lower for term in ["upload", "proprietary", "my dataset", "private", "provided by researcher"]):
        return "upload"
    if any(term in lower for term in ["edgar", "sec filing", "10-k", "10-q"]):
        return "edgar_yfinance"
    if any(term in lower for term in ["earnings call", "transcript", "text corpus", "news", "sentiment"]):
        return "text_corpus"
    if any(term in lower for term in ["fred", "macro", "inflation", "credit spread", "yield curve"]):
        return "fred_yfinance"
    spec = method_definition(method)
    routes = spec.get("evidence_routes") or ["upload"]
    return routes[0]
