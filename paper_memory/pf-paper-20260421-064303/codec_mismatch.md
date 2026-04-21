# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T13:27:54+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 35
matched: 5
mismatched: 5
not_found_in_code: 25
match_ratio: 0.143

## mismatched_parameters
- Hypothesis threshold (passive GSCI concentration): paper=above 30% of open interest in GSCI energy futures | code=Passive concentration scenarios implemented at 0.10, 0.30, 0.60; environment only allows {0.10, 0.30, 0.60}
- GARCH model: paper=GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution) | code=Implemented in analyst DCC stage: univariate GARCH with mean='Zero', vol='GARCH', p=1, q=1, dist='normal'
- Data Source: paper=WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024 | code=yfinance futures data for 5 tickers (CL=F, GC=F, ZC=F, NG=F, HG=F), date range 2010-01-01 to 2024-01-01 exclusive
- Adjustment Method: paper=ratio_backward | code=yfinance download with auto_adjust=True
- Seed Policy: paper=seeds = [1337, 42, 9999]; all three seeds must produce qualitatively consistent results; finding valid only if it holds across all three seeds | code=Seeds implemented exactly: [1337, 42, 9999]

## not_found_in_code
- Primary Metric (paper specifies: Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows)
- Two-tailed t-test (paper specifies: p < 0.05)
- Newey-West HAC correction (paper specifies: 4 lags)
- Bonferroni correction (paper specifies: 6 simultaneous tests; adjusted threshold p < 0.0083)
- Fama-French regression (paper specifies: Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth))
- Markov switching regime detection (paper specifies: statsmodels, k_regimes=2)
- Minimum Effect Size (paper specifies: -0.15 Sharpe units)
- Roll Convention (paper specifies: ratio_backward)
- Exclusion Rule: minimum trading history (paper specifies: Exclude contracts with fewer than 100 trading days of history)
- Exclusion Rule: macro announcement window (paper specifies: Exclude roll dates within 5 days of major macro announcements (FOMC, CPI))
- Exclusion Rule: bid-ask spread filter (paper specifies: Exclude contracts where bid-ask spread exceeds 2% of contract price)
- Simulation Agent 1 (paper specifies: passive_gsci — rebalances to GSCI index weights mechanically)
- Simulation Agent 2 (paper specifies: trend_follower — 12-month momentum signal, long/short)
- Simulation Agent 3 (paper specifies: mean_reversion — fades 3-month extremes)
- Simulation Agent 4 (paper specifies: liquidity_provider — posts limit orders both sides)
- Simulation Agent 5 (paper specifies: macro_allocator — switches energy/non-energy on macro signals)
- Simulation Agent 6 (paper specifies: meta_rl — learns optimal allocation across all strategies)
- Fitness Function (paper specifies: meta_rl fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps)
- Significance Threshold (paper specifies: p < 0.05 two-tailed (primary))
- Significance Threshold (Bonferroni) (paper specifies: p < 0.0083)
- Pre-Analysis Plan Status (paper specifies: UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs; FORGE gate rejects if not COMMITTED in pap_lock)
- Audit Requirement: CODEC bidirectional audit (paper specifies: required before QUILL writes paper)
- Audit Requirement: HAWK minimum score (paper specifies: 7/10 on methodology rubric)
- Audit Requirement: Maximum HAWK revision cycles (paper specifies: 3)
- Audit Requirement: DataPassport SHA-256 signature (paper specifies: required on all MINER outputs)

## verdict: FAIL
severity: Major
issue: code_deviates: 5 specified parameters differ between code and PAPER.md
