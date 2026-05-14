from __future__ import annotations

from typing import Any


def _test(name: str, domain: str, objective: str, aliases: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "statistical_test",
        "domain": domain,
        "objective": objective,
        "aliases": aliases or [],
    }


def _model(name: str, domain: str, objective: str, aliases: list[str] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "kind": "modeling_framework",
        "domain": domain,
        "objective": objective,
        "aliases": aliases or [],
    }


STATISTICAL_TEST_INVENTORY: dict[str, dict[str, Any]] = {
    "Augmented Dickey-Fuller (ADF) Test": _test("Augmented Dickey-Fuller (ADF) Test", "Time-Series & Asset Pricing", "Unit-root test for non-stationarity."),
    "Phillips-Perron (PP) Test": _test("Phillips-Perron (PP) Test", "Time-Series & Asset Pricing", "Unit-root test robust to serial correlation and heteroscedasticity."),
    "KPSS Test": _test("KPSS Test", "Time-Series & Asset Pricing", "Stationarity test with stationary null against unit-root alternative."),
    "Zivot-Andrews Test": _test("Zivot-Andrews Test", "Time-Series & Asset Pricing", "Unit-root test allowing one endogenous structural break."),
    "Lo's Modified Rescaled Range (R/S) Test": _test("Lo's Modified Rescaled Range (R/S) Test", "Time-Series & Asset Pricing", "Long-memory and long-range dependence test."),
    "Variance Ratio Test (Lo-MacKinlay)": _test("Variance Ratio Test (Lo-MacKinlay)", "Time-Series & Asset Pricing", "Weak-form random-walk and market-efficiency test."),
    "Ljung-Box Q-Test": _test("Ljung-Box Q-Test", "Time-Series & Asset Pricing", "Joint autocorrelation and residual white-noise test."),
    "Durbin-Watson Test": _test("Durbin-Watson Test", "Time-Series & Asset Pricing", "First-order serial-correlation diagnostic for regression residuals."),
    "BDS Test": _test("BDS Test", "Time-Series & Asset Pricing", "Non-linear dependence diagnostic."),
    "Engle's ARCH LM Test": _test("Engle's ARCH LM Test", "Time-Series & Asset Pricing", "Volatility clustering diagnostic for residuals."),
    "Diebold-Mariano Test": _test("Diebold-Mariano Test", "Time-Series & Asset Pricing", "Forecast accuracy comparison test."),
    "Granger Causality Test": _test("Granger Causality Test", "Causality & Structural Breaks", "Predictive-causality test using lagged information."),
    "Toda-Yamamoto Causality Test": _test("Toda-Yamamoto Causality Test", "Causality & Structural Breaks", "Causality test robust to mixed integration orders."),
    "Johansen Cointegration Test": _test("Johansen Cointegration Test", "Causality & Structural Breaks", "System cointegration rank test for long-run equilibria."),
    "Engle-Granger Two-Step Test": _test("Engle-Granger Two-Step Test", "Causality & Structural Breaks", "Residual-based pairwise cointegration test."),
    "Chow Test": _test("Chow Test", "Causality & Structural Breaks", "Known-date structural-break test."),
    "Quandt-Andrews Unknown Breakpoint Test": _test("Quandt-Andrews Unknown Breakpoint Test", "Causality & Structural Breaks", "Unknown-date single-break search test."),
    "Bai-Perron Test": _test("Bai-Perron Test", "Causality & Structural Breaks", "Multiple unknown structural-break test."),
    "Hausman Specification Test": _test("Hausman Specification Test", "Endogeneity & Microeconometric Specification", "Fixed-vs-random effects and endogeneity specification test."),
    "Sargan-Hansen J-Test": _test("Sargan-Hansen J-Test", "Endogeneity & Microeconometric Specification", "Overidentifying-restrictions test for instrument validity."),
    "Cragg-Donald Wald Test": _test("Cragg-Donald Wald Test", "Endogeneity & Microeconometric Specification", "Weak-instrument strength diagnostic."),
    "Stock-Yogo Weak ID Test": _test("Stock-Yogo Weak ID Test", "Endogeneity & Microeconometric Specification", "Weak-instrument critical-value benchmark."),
    "Arellano-Bond AR(1)/AR(2) Tests": _test("Arellano-Bond AR(1)/AR(2) Tests", "Endogeneity & Microeconometric Specification", "Serial-correlation diagnostics in dynamic panel GMM."),
    "Pesaran CD Test": _test("Pesaran CD Test", "Endogeneity & Microeconometric Specification", "Cross-sectional dependence diagnostic in panel errors."),
    "Breusch-Pagan LM Panel Test": _test("Breusch-Pagan LM Panel Test", "Endogeneity & Microeconometric Specification", "Pooled OLS versus random-effects panel diagnostic."),
    "Breusch-Pagan Test": _test("Breusch-Pagan Test", "Regression Diagnostics & Functional Form", "Linear heteroscedasticity diagnostic."),
    "White's General Heteroscedasticity Test": _test("White's General Heteroscedasticity Test", "Regression Diagnostics & Functional Form", "General heteroscedasticity diagnostic allowing non-linear terms."),
    "Ramsey RESET Test": _test("Ramsey RESET Test", "Regression Diagnostics & Functional Form", "Functional-form and omitted-variable diagnostic."),
    "Variance Inflation Factor (VIF)": _test("Variance Inflation Factor (VIF)", "Regression Diagnostics & Functional Form", "Multicollinearity diagnostic."),
    "Jarque-Bera Test": _test("Jarque-Bera Test", "Regression Diagnostics & Functional Form", "Residual normality test using skewness and kurtosis."),
    "Shapiro-Wilk Test": _test("Shapiro-Wilk Test", "Regression Diagnostics & Functional Form", "Small-sample normality test."),
    "DeLong's Test": _test("DeLong's Test", "Fintech, ML & Cryptoeconomics", "AUROC comparison test for competing classifiers."),
    "McNemar's Test": _test("McNemar's Test", "Fintech, ML & Cryptoeconomics", "Paired classification-error comparison test."),
    "Pesaran-Timmermann Test": _test("Pesaran-Timmermann Test", "Fintech, ML & Cryptoeconomics", "Directional-accuracy test for market forecasts."),
    "White's Reality Check": _test("White's Reality Check", "Fintech, ML & Cryptoeconomics", "Data-snooping robust strategy-performance test."),
    "Hansen's Superior Predictive Ability (SPA) Test": _test("Hansen's Superior Predictive Ability (SPA) Test", "Fintech, ML & Cryptoeconomics", "Improved data-snooping robust predictive-superiority test."),
    "Log-Likelihood Ratio (LLR) Test": _test("Log-Likelihood Ratio (LLR) Test", "Fintech, ML & Cryptoeconomics", "Nested model fit comparison test."),
    "Patell's t-Test": _test("Patell's t-Test", "Event Study & Non-Parametric Market Tests", "Standardized residual event-study abnormal-return test."),
    "Boehmer-Musumeci-Poulsen (BMP) Test": _test("Boehmer-Musumeci-Poulsen (BMP) Test", "Event Study & Non-Parametric Market Tests", "Event-induced variance adjusted abnormal-return test."),
    "Corrado Rank Test": _test("Corrado Rank Test", "Event Study & Non-Parametric Market Tests", "Non-parametric rank event-study test."),
    "Cowan Sign Test": _test("Cowan Sign Test", "Event Study & Non-Parametric Market Tests", "Event-day sign frequency test."),
    "Mann-Whitney U Test": _test("Mann-Whitney U Test", "Event Study & Non-Parametric Market Tests", "Two-sample distribution comparison test."),
    "Kruskal-Wallis Test": _test("Kruskal-Wallis Test", "Event Study & Non-Parametric Market Tests", "Multi-group median/distribution comparison test."),
    "Gibbons-Ross-Shanken (GRS) Test": _test("Gibbons-Ross-Shanken (GRS) Test", "Quantitative Finance & Asset Pricing", "Joint test that all factor-model alphas equal zero."),
    "Kupiec POF Test": _test("Kupiec POF Test", "Quantitative Finance & Asset Pricing", "VaR unconditional coverage breach-frequency test."),
    "Christoffersen Interval Forecast Test": _test("Christoffersen Interval Forecast Test", "Quantitative Finance & Asset Pricing", "VaR conditional coverage and breach-independence test."),
    "Log-Rank Test": _test("Log-Rank Test", "Survival & Duration Models", "Non-parametric survival-curve comparison test."),
    "Schoenfeld Residual Proportional Hazards Test": _test("Schoenfeld Residual Proportional Hazards Test", "Survival & Duration Models", "Cox proportional-hazards assumption diagnostic."),
    "Gelman-Rubin R-hat Diagnostic": _test("Gelman-Rubin R-hat Diagnostic", "Bayesian Models", "MCMC convergence diagnostic."),
    "Posterior Predictive Check": _test("Posterior Predictive Check", "Bayesian Models", "Bayesian model fit diagnostic."),
    "Silhouette Stability Test": _test("Silhouette Stability Test", "Unsupervised Learning", "Cluster separation and stability diagnostic."),
    "Egger Publication Bias Test": _test("Egger Publication Bias Test", "Meta-Analysis", "Funnel-plot asymmetry and publication-bias test."),
    "I-squared Heterogeneity Test": _test("I-squared Heterogeneity Test", "Meta-Analysis", "Cross-study heterogeneity diagnostic."),
}


MODELING_FRAMEWORK_INVENTORY: dict[str, dict[str, Any]] = {
    "Capital Asset Pricing Model (CAPM)": _model("Capital Asset Pricing Model (CAPM)", "Quantitative Finance & Asset Pricing", "Single-factor expected-return model."),
    "Fama-French Factor Models": _model("Fama-French Factor Models", "Quantitative Finance & Asset Pricing", "Multi-factor asset-pricing models."),
    "Carhart Four-Factor Model": _model("Carhart Four-Factor Model", "Quantitative Finance & Asset Pricing", "Momentum-augmented factor model."),
    "ARCH Family Models": _model("ARCH Family Models", "Quantitative Finance & Asset Pricing", "Conditional heteroscedasticity volatility models."),
    "GARCH Family Models": _model("GARCH Family Models", "Quantitative Finance & Asset Pricing", "Time-varying volatility models including GARCH, EGARCH, and GJR-GARCH."),
    "Black-Scholes-Merton Option Pricing Model": _model("Black-Scholes-Merton Option Pricing Model", "Quantitative Finance & Asset Pricing", "Continuous-time option pricing model."),
    "Cox-Ingersoll-Ross (CIR) Interest Rate Model": _model("Cox-Ingersoll-Ross (CIR) Interest Rate Model", "Quantitative Finance & Asset Pricing", "Stochastic interest-rate model."),
    "Markowitz Mean-Variance Optimization": _model("Markowitz Mean-Variance Optimization", "Quantitative Finance & Asset Pricing", "Portfolio optimization by expected return and covariance."),
    "Black-Litterman Model": _model("Black-Litterman Model", "Quantitative Finance & Asset Pricing", "Bayesian portfolio allocation model blending priors and views."),
    "Hierarchical Risk Parity (HRP)": _model("Hierarchical Risk Parity (HRP)", "Quantitative Finance & Asset Pricing", "Cluster-aware risk allocation model."),
    "Value-at-Risk (VaR) Models": _model("Value-at-Risk (VaR) Models", "Quantitative Finance & Asset Pricing", "Tail-loss threshold models."),
    "Expected Shortfall (ES) Models": _model("Expected Shortfall (ES) Models", "Quantitative Finance & Asset Pricing", "Average tail-loss severity models."),
    "Logistic Regression Classification": _model("Logistic Regression Classification", "Fintech & Cryptoeconomics", "Probability model for binary outcomes."),
    "Random Forest Classification": _model("Random Forest Classification", "Fintech & Cryptoeconomics", "Tree ensemble classifier."),
    "Gradient Boosting Models (XGBoost/LightGBM)": _model("Gradient Boosting Models (XGBoost/LightGBM)", "Fintech & Cryptoeconomics", "Boosted tree classifiers or regressors."),
    "Deep Neural Networks": _model("Deep Neural Networks", "Fintech & Cryptoeconomics", "Non-linear predictive model family."),
    "Cox Proportional Hazards Model": _model("Cox Proportional Hazards Model", "Fintech & Cryptoeconomics", "Survival and time-to-event model."),
    "Constant Product Market Maker (CPMM)": _model("Constant Product Market Maker (CPMM)", "Fintech & Cryptoeconomics", "Automated market-maker liquidity model."),
    "Isolation Forest": _model("Isolation Forest", "Fintech & Cryptoeconomics", "Tree-based anomaly detection model."),
    "Autoencoder Anomaly Model": _model("Autoencoder Anomaly Model", "Fintech & Cryptoeconomics", "Neural reconstruction anomaly detector."),
    "OLS Regression Model": _model("OLS Regression Model", "Empirical Economics & Econometrics", "Linear conditional-mean model."),
    "Fixed Effects Panel Model": _model("Fixed Effects Panel Model", "Empirical Economics & Econometrics", "Panel model controlling for unobserved entity/time traits."),
    "Random Effects Panel Model": _model("Random Effects Panel Model", "Empirical Economics & Econometrics", "Panel model with random unobserved effects."),
    "Difference-in-Differences Model": _model("Difference-in-Differences Model", "Empirical Economics & Econometrics", "Quasi-experimental treatment-effect model."),
    "Regression Discontinuity Design": _model("Regression Discontinuity Design", "Empirical Economics & Econometrics", "Local threshold-based causal identification model."),
    "Instrumental Variables / 2SLS Model": _model("Instrumental Variables / 2SLS Model", "Empirical Economics & Econometrics", "Endogeneity-robust causal model using instruments."),
    "Vector Autoregression (VAR)": _model("Vector Autoregression (VAR)", "Empirical Economics & Econometrics", "Dynamic multi-series system model."),
    "Vector Error Correction Model (VECM)": _model("Vector Error Correction Model (VECM)", "Empirical Economics & Econometrics", "Cointegrated dynamic-equilibrium model."),
    "Arellano-Bond Dynamic Panel GMM": _model("Arellano-Bond Dynamic Panel GMM", "Empirical Economics & Econometrics", "Dynamic panel estimator using lagged instruments."),
    "ARIMA / ARIMAX Forecasting Model": _model("ARIMA / ARIMAX Forecasting Model", "Empirical Economics & Econometrics", "Univariate or exogenous time-series forecasting model."),
    "Market Model Event Study": _model("Market Model Event Study", "Quantitative Finance & Asset Pricing", "Expected-return model for event studies."),
    "Buy-and-Hold Abnormal Return Model": _model("Buy-and-Hold Abnormal Return Model", "Quantitative Finance & Asset Pricing", "Long-horizon abnormal-return model."),
    "Rule-Based Portfolio Backtest": _model("Rule-Based Portfolio Backtest", "Quantitative Finance & Asset Pricing", "Trading rule simulation through time."),
    "Agent-Based Market Microstructure Simulation": _model("Agent-Based Market Microstructure Simulation", "Quantitative Finance & Asset Pricing", "Heterogeneous or correlated trading-agent simulation."),
    "Network Contagion Model": _model("Network Contagion Model", "Quantitative Finance & Asset Pricing", "Graph-based transmission and centrality model."),
    "Embedding-Space Text Signal Model": _model("Embedding-Space Text Signal Model", "Fintech & Cryptoeconomics", "LLM or embedding model for document-derived features."),
}


def _dedupe(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


METHOD_RESEARCH_DESIGN: dict[str, dict[str, Any]] = {
    "descriptive": {
        "analytical_domain": "Research Scoping & Descriptive Evidence",
        "modeling_frameworks": [],
        "diagnostic_tests": ["Jarque-Bera Test", "Shapiro-Wilk Test"],
        "inference_tests": [],
        "evaluation_tests": ["Mann-Whitney U Test", "Kruskal-Wallis Test"],
    },
    "regression": {
        "analytical_domain": "Empirical Economics & Econometrics",
        "modeling_frameworks": ["OLS Regression Model"],
        "diagnostic_tests": ["Breusch-Pagan Test", "White's General Heteroscedasticity Test", "Ramsey RESET Test", "Variance Inflation Factor (VIF)", "Durbin-Watson Test", "Jarque-Bera Test"],
        "inference_tests": ["Ljung-Box Q-Test"],
        "evaluation_tests": [],
    },
    "panel_regression": {
        "analytical_domain": "Empirical Economics & Econometrics",
        "modeling_frameworks": ["Fixed Effects Panel Model", "Random Effects Panel Model"],
        "diagnostic_tests": ["Hausman Specification Test", "Pesaran CD Test", "Breusch-Pagan LM Panel Test", "Arellano-Bond AR(1)/AR(2) Tests"],
        "inference_tests": ["Breusch-Pagan Test", "White's General Heteroscedasticity Test"],
        "evaluation_tests": [],
    },
    "factor_model": {
        "analytical_domain": "Quantitative Finance & Asset Pricing",
        "modeling_frameworks": ["Capital Asset Pricing Model (CAPM)", "Fama-French Factor Models", "Carhart Four-Factor Model"],
        "diagnostic_tests": ["Engle's ARCH LM Test", "Ljung-Box Q-Test", "Durbin-Watson Test"],
        "inference_tests": ["Gibbons-Ross-Shanken (GRS) Test", "Variance Ratio Test (Lo-MacKinlay)"],
        "evaluation_tests": [],
    },
    "event_study": {
        "analytical_domain": "Event Study & Non-Parametric Market Tests",
        "modeling_frameworks": ["Market Model Event Study", "Buy-and-Hold Abnormal Return Model"],
        "diagnostic_tests": ["Jarque-Bera Test", "Shapiro-Wilk Test"],
        "inference_tests": ["Patell's t-Test", "Boehmer-Musumeci-Poulsen (BMP) Test", "Corrado Rank Test", "Cowan Sign Test"],
        "evaluation_tests": ["Mann-Whitney U Test", "Kruskal-Wallis Test"],
    },
    "difference_in_differences": {
        "analytical_domain": "Empirical Economics & Econometrics",
        "modeling_frameworks": ["Difference-in-Differences Model", "Fixed Effects Panel Model"],
        "diagnostic_tests": ["Chow Test", "Bai-Perron Test", "Pesaran CD Test"],
        "inference_tests": ["Hausman Specification Test"],
        "evaluation_tests": [],
    },
    "instrumental_variables": {
        "analytical_domain": "Endogeneity & Microeconometric Specification",
        "modeling_frameworks": ["Instrumental Variables / 2SLS Model"],
        "diagnostic_tests": ["Cragg-Donald Wald Test", "Stock-Yogo Weak ID Test", "Hausman Specification Test"],
        "inference_tests": ["Sargan-Hansen J-Test"],
        "evaluation_tests": [],
    },
    "regression_discontinuity": {
        "analytical_domain": "Empirical Economics & Econometrics",
        "modeling_frameworks": ["Regression Discontinuity Design"],
        "diagnostic_tests": ["Ramsey RESET Test", "Breusch-Pagan Test"],
        "inference_tests": ["Mann-Whitney U Test"],
        "evaluation_tests": [],
    },
    "synthetic_control": {
        "analytical_domain": "Empirical Economics & Econometrics",
        "modeling_frameworks": ["Difference-in-Differences Model"],
        "diagnostic_tests": ["Chow Test", "Bai-Perron Test"],
        "inference_tests": ["Mann-Whitney U Test"],
        "evaluation_tests": [],
    },
    "backtest": {
        "analytical_domain": "Quantitative Finance & Asset Pricing",
        "modeling_frameworks": ["Rule-Based Portfolio Backtest", "Markowitz Mean-Variance Optimization", "Black-Litterman Model", "Hierarchical Risk Parity (HRP)"],
        "diagnostic_tests": ["Variance Ratio Test (Lo-MacKinlay)", "Ljung-Box Q-Test", "Engle's ARCH LM Test"],
        "inference_tests": ["White's Reality Check", "Hansen's Superior Predictive Ability (SPA) Test", "Pesaran-Timmermann Test"],
        "evaluation_tests": ["Diebold-Mariano Test"],
    },
    "portfolio_optimization": {
        "analytical_domain": "Quantitative Finance & Asset Pricing",
        "modeling_frameworks": ["Markowitz Mean-Variance Optimization", "Black-Litterman Model", "Hierarchical Risk Parity (HRP)"],
        "diagnostic_tests": ["Variance Ratio Test (Lo-MacKinlay)", "Engle's ARCH LM Test"],
        "inference_tests": ["White's Reality Check", "Hansen's Superior Predictive Ability (SPA) Test"],
        "evaluation_tests": ["Pesaran-Timmermann Test"],
    },
    "risk_model": {
        "analytical_domain": "Quantitative Finance & Asset Pricing",
        "modeling_frameworks": ["Value-at-Risk (VaR) Models", "Expected Shortfall (ES) Models"],
        "diagnostic_tests": ["Engle's ARCH LM Test", "BDS Test"],
        "inference_tests": ["Kupiec POF Test", "Christoffersen Interval Forecast Test"],
        "evaluation_tests": [],
    },
    "volatility_model": {
        "analytical_domain": "Quantitative Finance & Asset Pricing",
        "modeling_frameworks": ["ARCH Family Models", "GARCH Family Models"],
        "diagnostic_tests": ["Engle's ARCH LM Test", "Ljung-Box Q-Test", "BDS Test"],
        "inference_tests": ["Diebold-Mariano Test"],
        "evaluation_tests": [],
    },
    "time_series": {
        "analytical_domain": "Time-Series & Asset Pricing",
        "modeling_frameworks": ["ARIMA / ARIMAX Forecasting Model"],
        "diagnostic_tests": ["Augmented Dickey-Fuller (ADF) Test", "Phillips-Perron (PP) Test", "KPSS Test", "Zivot-Andrews Test", "Ljung-Box Q-Test", "Durbin-Watson Test", "BDS Test"],
        "inference_tests": ["Lo's Modified Rescaled Range (R/S) Test", "Variance Ratio Test (Lo-MacKinlay)"],
        "evaluation_tests": ["Diebold-Mariano Test"],
    },
    "var_model": {
        "analytical_domain": "Empirical Economics & Econometrics",
        "modeling_frameworks": ["Vector Autoregression (VAR)"],
        "diagnostic_tests": ["Augmented Dickey-Fuller (ADF) Test", "KPSS Test", "Ljung-Box Q-Test"],
        "inference_tests": ["Granger Causality Test", "Toda-Yamamoto Causality Test"],
        "evaluation_tests": ["Diebold-Mariano Test"],
    },
    "cointegration": {
        "analytical_domain": "Causality & Structural Breaks",
        "modeling_frameworks": ["Vector Error Correction Model (VECM)"],
        "diagnostic_tests": ["Augmented Dickey-Fuller (ADF) Test", "Phillips-Perron (PP) Test", "KPSS Test", "Zivot-Andrews Test"],
        "inference_tests": ["Johansen Cointegration Test", "Engle-Granger Two-Step Test"],
        "evaluation_tests": ["Bai-Perron Test"],
    },
    "machine_learning": {
        "analytical_domain": "Fintech, ML & Cryptoeconomics",
        "modeling_frameworks": ["Logistic Regression Classification", "Random Forest Classification", "Gradient Boosting Models (XGBoost/LightGBM)", "Deep Neural Networks"],
        "diagnostic_tests": ["Log-Likelihood Ratio (LLR) Test"],
        "inference_tests": ["DeLong's Test", "McNemar's Test", "Pesaran-Timmermann Test"],
        "evaluation_tests": ["White's Reality Check", "Hansen's Superior Predictive Ability (SPA) Test", "Diebold-Mariano Test"],
    },
    "text_analysis": {
        "analytical_domain": "Fintech, ML & Cryptoeconomics",
        "modeling_frameworks": ["Embedding-Space Text Signal Model", "OLS Regression Model", "Market Model Event Study"],
        "diagnostic_tests": ["White's General Heteroscedasticity Test", "Variance Inflation Factor (VIF)", "Ljung-Box Q-Test"],
        "inference_tests": ["Patell's t-Test", "Boehmer-Musumeci-Poulsen (BMP) Test", "Log-Likelihood Ratio (LLR) Test"],
        "evaluation_tests": ["Diebold-Mariano Test", "Pesaran-Timmermann Test"],
    },
    "network_analysis": {
        "analytical_domain": "Network Finance & Systemic Risk",
        "modeling_frameworks": ["Network Contagion Model"],
        "diagnostic_tests": ["Bai-Perron Test", "Mann-Whitney U Test"],
        "inference_tests": ["Kruskal-Wallis Test"],
        "evaluation_tests": [],
    },
    "agent_based_model": {
        "analytical_domain": "Market Microstructure Simulation",
        "modeling_frameworks": ["Agent-Based Market Microstructure Simulation"],
        "diagnostic_tests": ["Mann-Whitney U Test", "Kruskal-Wallis Test"],
        "inference_tests": ["White's Reality Check", "Hansen's Superior Predictive Ability (SPA) Test"],
        "evaluation_tests": ["Pesaran-Timmermann Test"],
    },
    "simulation": {
        "analytical_domain": "Simulation & Mechanism Design",
        "modeling_frameworks": ["Agent-Based Market Microstructure Simulation"],
        "diagnostic_tests": ["Mann-Whitney U Test", "Kruskal-Wallis Test"],
        "inference_tests": ["White's Reality Check"],
        "evaluation_tests": [],
    },
    "stress_testing": {
        "analytical_domain": "Quantitative Finance & Asset Pricing",
        "modeling_frameworks": ["Value-at-Risk (VaR) Models", "Expected Shortfall (ES) Models"],
        "diagnostic_tests": ["Engle's ARCH LM Test", "BDS Test"],
        "inference_tests": ["Kupiec POF Test", "Christoffersen Interval Forecast Test"],
        "evaluation_tests": ["Mann-Whitney U Test"],
    },
    "survival_hazard": {
        "analytical_domain": "Fintech & Cryptoeconomics",
        "modeling_frameworks": ["Cox Proportional Hazards Model"],
        "diagnostic_tests": ["Log-Likelihood Ratio (LLR) Test", "Schoenfeld Residual Proportional Hazards Test"],
        "inference_tests": ["Log-Rank Test", "Mann-Whitney U Test"],
        "evaluation_tests": [],
    },
    "bayesian_model": {
        "analytical_domain": "Empirical Economics & Econometrics",
        "modeling_frameworks": ["Black-Litterman Model"],
        "diagnostic_tests": ["Gelman-Rubin R-hat Diagnostic", "Posterior Predictive Check", "Jarque-Bera Test"],
        "inference_tests": ["Log-Likelihood Ratio (LLR) Test"],
        "evaluation_tests": [],
    },
    "clustering": {
        "analytical_domain": "Fintech & Cryptoeconomics",
        "modeling_frameworks": ["Gradient Boosting Models (XGBoost/LightGBM)"],
        "diagnostic_tests": ["Silhouette Stability Test", "Mann-Whitney U Test", "Kruskal-Wallis Test"],
        "inference_tests": [],
        "evaluation_tests": [],
    },
    "anomaly_detection": {
        "analytical_domain": "Fintech & Cryptoeconomics",
        "modeling_frameworks": ["Isolation Forest", "Autoencoder Anomaly Model"],
        "diagnostic_tests": ["McNemar's Test"],
        "inference_tests": ["DeLong's Test"],
        "evaluation_tests": ["Pesaran-Timmermann Test"],
    },
    "meta_analysis": {
        "analytical_domain": "Evidence Synthesis",
        "modeling_frameworks": [],
        "diagnostic_tests": ["Egger Publication Bias Test", "I-squared Heterogeneity Test", "Kruskal-Wallis Test"],
        "inference_tests": ["Mann-Whitney U Test"],
        "evaluation_tests": [],
    },
}


def all_statistical_tests() -> list[str]:
    return sorted(STATISTICAL_TEST_INVENTORY)


def all_modeling_frameworks() -> list[str]:
    return sorted(MODELING_FRAMEWORK_INVENTORY)


def method_research_design(method: str) -> dict[str, Any]:
    base = METHOD_RESEARCH_DESIGN.get(method, METHOD_RESEARCH_DESIGN["descriptive"])
    diagnostic_tests = _dedupe(list(base.get("diagnostic_tests", [])))
    inference_tests = _dedupe(list(base.get("inference_tests", [])))
    evaluation_tests = _dedupe(list(base.get("evaluation_tests", [])))
    return {
        "analytical_domain": base["analytical_domain"],
        "modeling_frameworks": _dedupe(list(base.get("modeling_frameworks", []))),
        "diagnostic_tests": diagnostic_tests,
        "inference_tests": inference_tests,
        "evaluation_tests": evaluation_tests,
        "statistical_tests": _dedupe(diagnostic_tests + inference_tests + evaluation_tests),
        "models_vs_tests_rule": "Models estimate relationships, forecasts, or mechanisms; tests diagnose assumptions, identification, inference validity, and predictive superiority.",
    }
