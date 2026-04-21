# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T14:13:32+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 36
matched: 14
mismatched: 14
not_found_in_code: 8
match_ratio: 0.389

## mismatched_parameters
- Primary Metric: paper=Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows | code=Primary metric referenced in Bonferroni call as primary_metric; exact rolling 252-day annualized Sharpe differential implementation NOT FOUND in provided code summary
- Bonferroni correction: paper=Bonferroni correction for 6 simultaneous tests — adjusted threshold p < 0.0083 | code=Adjusted threshold p < 0.0083 is specified, but SigmaJob2.run() calls _bonferroni(..., n_tests=7)
- Data Source: paper=WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024 | code=Dev run uses yfinance proxy with tickers CL=F and NG=F; full run requires WRDS access; date range 2000-01-01 to 2023-12-31
- Adjustment Method: paper=ratio_backward | code=Declared in passport as ratio_backward, but actual implemented download adjustment is yfinance auto_adjust=True used as proxy
- Exclusion Rule: minimum trading history: paper=Exclude contracts with fewer than 100 trading days of history | code=Present only as specification constant/paper text; implementation NOT FOUND
- Exclusion Rule: macro announcement window: paper=Exclude roll dates within 5 days of major macro announcements (FOMC, CPI) | code=apply_macro_exclusion_window(df, exclusion_days=5) exists, but actual dev-run behavior is no-op and macro_exclusion_applied: False
- Exclusion Rule: bid-ask spread filter: paper=Exclude contracts where bid-ask spread exceeds 2% of contract price | code=Present only as specification constant/paper text; implementation NOT FOUND
- Simulation Agent: paper=passive_gsci — rebalances to GSCI index weights mechanically | code=passive_gsci present; behavior always long/action 1
- Simulation Agent: paper=trend_follower — 12-month momentum signal, long/short | code=trend_follower present; implemented using short lookback from price history / lookback_idx up to 4, not 12-month momentum
- Simulation Agent: paper=mean_reversion — fades 3-month extremes | code=mean_reversion present; behavior details NOT FOUND in provided summary
- Simulation Agent: paper=liquidity_provider — posts limit orders both sides | code=liquidity_provider present; behavior details NOT FOUND in provided summary
- Simulation Agent: paper=macro_allocator — switches energy/non-energy on macro signals | code=macro_allocator present; behavior details NOT FOUND in provided summary
- Simulation Agent: paper=meta_rl — learns optimal allocation across all strategies | code=meta_rl present; learning/allocation implementation NOT FOUND in provided summary
- Audit Requirement: paper=DataPassport SHA-256 signature required on all MINER outputs | code=Data passport is written, but SHA-256 signature requirement NOT FOUND in provided summary

## not_found_in_code
- Seed Policy (paper specifies: seeds = [1337, 42, 9999])
- Seed consistency requirement (paper specifies: All three seeds must produce qualitatively consistent results. A finding is only valid if it holds across all three seeds.)
- Fitness Function (paper specifies: meta_rl fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps)
- Training Episodes (paper specifies: 500,000 minimum across all scenarios and seeds)
- Pre-Analysis Plan Status (paper specifies: UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs. FORGE gate will reject any run where this status is not COMMITTED in pap_lock.)
- Audit Requirement (paper specifies: CODEC bidirectional audit required before QUILL writes paper)
- Audit Requirement (paper specifies: HAWK minimum score to pass: 7/10 on methodology rubric)
- Audit Requirement (paper specifies: Maximum HAWK revision cycles: 3)

## verdict: FAIL
severity: Major
issue: code_deviates: 14 specified parameters differ between code and PAPER.md
