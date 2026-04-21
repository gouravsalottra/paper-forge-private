# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T14:28:27+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 36
matched: 18
mismatched: 8
not_found_in_code: 10
match_ratio: 0.500

## mismatched_parameters
- Primary Metric: paper=Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows | code=Bonferroni primary_metric passed in SigmaJob2.run(); exact Sharpe differential high-minus-low annualized over rolling 252-day windows NOT FOUND
- Fama-French regression: paper=Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth) | code=_fama_french_three_factor_ols(sim_df) and _fama_macbeth_regression(sim_df); linearmodels usage not explicitly visible
- Data Source: paper=WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024 | code=yfinance; tickers CL=F and NG=F; date range 2000-01-01 to 2023-12-31
- Adjustment Method: paper=ratio_backward | code=auto_adjust=True in yfinance download
- Seed Policy: paper=seeds = [1337, 42, 9999] | code=seed derived from _seed_from_pap_lock(); explicit [1337, 42, 9999] NOT FOUND
- Exclusion Rule: macro announcement window: paper=Exclude roll dates within 5 days of major macro announcements (FOMC, CPI) | code=apply_macro_exclusion_window(df, exclusion_days=5); approximate FOMC dates sample, CPI not clearly implemented, applied to rows not explicitly roll dates
- Exclusion Rule: bid-ask spread threshold: paper=Exclude contracts where bid-ask spread exceeds 2% of contract price | code=apply_bid_ask_spread_filter(..., threshold=0.02) using spread proxy abs(high-low)/close
- Audit Requirement: paper=DataPassport SHA-256 signature required on all MINER outputs | code=DataPassport mentioned; SHA-256 signature requirement on all MINER outputs NOT FOUND

## not_found_in_code
- Hypothesis Sharpe ratio reduction threshold (paper specifies: reduces 12-month momentum strategy Sharpe ratios by at least 0.15 units)
- Minimum Effect Size (paper specifies: -0.15 Sharpe units)
- Roll Convention (paper specifies: ratio_backward)
- Seed consistency requirement (paper specifies: All three seeds must produce qualitatively consistent results. A finding is only valid if it holds across all three seeds.)
- Fitness Function (paper specifies: meta_rl fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps)
- Training Episodes (paper specifies: 500,000 minimum across all scenarios and seeds)
- Pre-Analysis Plan Status (paper specifies: UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs. FORGE gate will reject any run where this status is not COMMITTED in pap_lock.)
- Audit Requirement (paper specifies: CODEC bidirectional audit required before QUILL writes paper)
- Audit Requirement (paper specifies: HAWK minimum score to pass: 7/10 on methodology rubric)
- Audit Requirement (paper specifies: Maximum HAWK revision cycles: 3)

## verdict: FAIL
severity: Major
issue: code_deviates: 8 specified parameters differ between code and PAPER.md
