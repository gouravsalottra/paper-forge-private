# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T14:47:29+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 38
matched: 19
mismatched: 12
not_found_in_code: 7
match_ratio: 0.500

## mismatched_parameters
- Primary Metric: paper=Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows | code=rolling 252-day / 12-month window used for momentum and meta_rl trailing 252 episodes; explicit primary metric formula NOT FOUND
- Data Source: paper=WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024 | code=yfinance; tickers CL=F and NG=F; date range 2000-01-01 to 2023-12-31
- Adjustment Method: paper=ratio_backward | code=yfinance auto_adjust=True
- Seed Policy: paper=seeds = [1337, 42, 9999] | code=bootstrap seed=1337 found; full seed list [1337, 42, 9999] NOT FOUND
- Exclusion Rule: macro announcement window: paper=Exclude roll dates within 5 days of major macro announcements (FOMC, CPI) | code=remove rows within ±5 days of approximate FOMC dates; CPI not evidenced; applied to rows not explicitly roll dates
- Simulation Agent: paper=passive_gsci — rebalances to GSCI index weights mechanically | code=passive_gsci agent present; behavior always long, no evidence of rebalancing to GSCI index weights
- Simulation Agent: paper=mean_reversion — fades 3-month extremes | code=mean_reversion fades ±2% deviations relative to obs[1]; 3-month horizon NOT FOUND
- Simulation Agent: paper=liquidity_provider — posts limit orders both sides | code=liquidity_provider alternates long/short actions; limit-order posting both sides NOT FOUND
- Simulation Agent: paper=macro_allocator — switches energy/non-energy on macro signals | code=macro_allocator returns long/hold based on passive concentration threshold; energy/non-energy switching on macro signals NOT FOUND
- Simulation Agent: paper=meta_rl — learns optimal allocation across all strategies | code=meta_rl agent referenced; learns allocation across strategies implied but not explicitly evidenced in provided extract
- Fitness Function: paper=meta_rl fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps | code=trailing 252 episodes evidenced; evaluated every 1000 training steps NOT FOUND
- Audit Requirement: paper=DataPassport SHA-256 signature required on all MINER outputs | code=Passport writes start/end dates; SHA-256 signature requirement NOT FOUND

## not_found_in_code
- Roll Convention (paper specifies: ratio_backward)
- Seed consistency requirement (paper specifies: All three seeds must produce qualitatively consistent results; finding valid only if it holds across all three seeds)
- Training Episodes (paper specifies: 500,000 minimum across all scenarios and seeds)
- Pre-Analysis Plan Status (paper specifies: must be COMMITTED by SIGMA_JOB1 before FORGE runs; FORGE rejects if not COMMITTED in pap_lock)
- Audit Requirement (paper specifies: CODEC bidirectional audit required before QUILL writes paper)
- Audit Requirement (paper specifies: HAWK minimum score to pass: 7/10 on methodology rubric)
- Audit Requirement (paper specifies: Maximum HAWK revision cycles: 3)

## verdict: FAIL
severity: Major
issue: code_deviates: 12 specified parameters differ between code and PAPER.md
