# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T14:24:19+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 35
matched: 14
mismatched: 10
not_found_in_code: 11
match_ratio: 0.400

## mismatched_parameters
- Primary Metric: paper=Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows | code=Bonferroni called with primary_metric=primary_metric; exact rolling 252-day annualized Sharpe differential implementation NOT FOUND
- Fama-French regression: paper=Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth) | code=_fama_macbeth_regression(sim_df); linearmodels/Fama-MacBeth referenced; exact three-factor OLS setup NOT FOUND
- Data Source: paper=WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024 | code=Yahoo Finance via yfinance for CL=F and NG=F, start 2000-01-01 to end 2023-12-31 / 2024-01-01 exclusive
- Adjustment Method: paper=ratio_backward | code=auto_adjust=True via yfinance adjusted prices
- Exclusion Rule: macro announcement window: paper=Exclude roll dates within 5 days of major macro announcements (FOMC, CPI) | code=apply_macro_exclusion_window(df, exclusion_days=5) around FOMC_DATES_APPROX; CPI not visibly implemented; applied to return rows, not explicitly roll dates
- Simulation Agent: paper=passive_gsci — rebalances to GSCI index weights mechanically | code=PassiveGSCI always returns action 1 (long)
- Simulation Agent: paper=mean_reversion — fades 3-month extremes | code=MeanReversion uses ±2% threshold relative to obs[1]; no explicit 3-month extreme logic found
- Simulation Agent: paper=liquidity_provider — posts limit orders both sides | code=LiquidityProvider alternates long and short actions
- Simulation Agent: paper=macro_allocator — switches energy/non-energy on macro signals | code=MacroAllocator compares passive concentration obs[6] to threshold and returns long/hold
- Audit Requirement: paper=DataPassport SHA-256 signature required on all MINER outputs | code=Passport writes are mentioned, but SHA-256 signature requirement NOT FOUND

## not_found_in_code
- Hypothesized Sharpe reduction (paper specifies: reduces 12-month momentum strategy Sharpe ratios by at least 0.15 units)
- Minimum Effect Size (paper specifies: -0.15 Sharpe units)
- Roll Convention (paper specifies: ratio_backward)
- Passive Capital Scenario (paper specifies: Low: 10% of open interest)
- Passive Capital Scenario (paper specifies: High: 60% of open interest)
- Fitness Function (paper specifies: meta_rl fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps)
- Training Episodes (paper specifies: 500,000 minimum across all scenarios and seeds)
- Pre-Analysis Plan Status (paper specifies: UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs. FORGE gate will reject any run where this status is not COMMITTED in pap_lock.)
- Audit Requirement (paper specifies: CODEC bidirectional audit required before QUILL writes paper)
- Audit Requirement (paper specifies: HAWK minimum score to pass: 7/10 on methodology rubric)
- Audit Requirement (paper specifies: Maximum HAWK revision cycles: 3)

## verdict: FAIL
severity: Major
issue: code_deviates: 10 specified parameters differ between code and PAPER.md
