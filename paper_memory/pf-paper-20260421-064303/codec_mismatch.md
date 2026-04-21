# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T14:33:19+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 34
matched: 11
mismatched: 13
not_found_in_code: 10
match_ratio: 0.324

## mismatched_parameters
- Primary metric: paper=Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows | code=_bonferroni(..., primary_metric=primary_metric) mentioned, but exact primary metric implementation/value not visible
- Two-tailed t-test: paper=Two-tailed t-test, p < 0.05, Newey-West HAC correction (4 lags) | code=_newey_west_ttest(returns) invoked; exact two-tailed and 4-lag implementation not visible
- Data source: paper=WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024 | code=yfinance via yf.download(...); tickers CL=F and NG=F; START_DATE=2000-01-01; END_DATE_EXCLUSIVE=2024-01-01
- Adjustment Method: paper=ratio_backward | code=yf.download(..., auto_adjust=True, ...)
- Seed Policy: paper=seeds = [1337, 42, 9999] | code=bootstrap uses seed=1337; full seed list [1337, 42, 9999] not visible
- Exclusion Rule: macro announcement window: paper=Exclude roll dates within 5 days of major macro announcements (FOMC, CPI) | code=apply_macro_exclusion_window(df, exclusion_days=5); visible dates are approximate FOMC only, comment says FOMC/CPI
- Simulation agent: paper=passive_gsci — rebalances to GSCI index weights mechanically | code=PassiveGSCI always returns action 1 (always long)
- Simulation agent: paper=mean_reversion — fades 3-month extremes | code=acts on ~2% deviations using obs[0] vs obs[1]; no visible 3-month extreme logic
- Simulation agent: paper=liquidity_provider — posts limit orders both sides | code=alternates long/short each action, resetting each episode
- Simulation agent: paper=macro_allocator — switches energy/non-energy on macro signals | code=MacroAllocator exists with passive_threshold=0.30; switching energy/non-energy on macro signals not visible in provided excerpt
- Simulation agent: paper=meta_rl — learns optimal allocation across all strategies | code=agent exists by name in env.py; learning optimal allocation across all strategies not visible
- Passive Capital Scenario: paper=Medium: 30% of open interest | code=MacroAllocator passive_threshold=0.30; scenario value itself not otherwise visible
- Significance Threshold: paper=p < 0.05 two-tailed (primary) | code=PAPER/env spec strings mention p < 0.05, but exact enforcement in code not visible

## not_found_in_code
- Minimum effect size (paper specifies: -0.15 Sharpe units)
- Roll Convention (paper specifies: ratio_backward)
- Passive Capital Scenario (paper specifies: Low: 10% of open interest)
- Passive Capital Scenario (paper specifies: High: 60% of open interest)
- Fitness Function (paper specifies: meta_rl fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps)
- Training Episodes (paper specifies: 500,000 minimum across all scenarios and seeds)
- Pre-Analysis Plan Status (paper specifies: UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs; FORGE gate rejects if not COMMITTED in pap_lock)
- Audit Requirement (paper specifies: CODEC bidirectional audit required before QUILL writes paper)
- Audit Requirement (paper specifies: HAWK minimum score to pass: 7/10 on methodology rubric)
- Audit Requirement (paper specifies: Maximum HAWK revision cycles: 3)

## verdict: FAIL
severity: Major
issue: code_deviates: 13 specified parameters differ between code and PAPER.md
