# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T14:18:23+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 27
matched: 9
mismatched: 10
not_found_in_code: 8
match_ratio: 0.333

## mismatched_parameters
- Hypothesis: paper=Passive GSCI index investor concentration above 30% of open interest in GSCI energy futures reduces 12-month momentum strategy Sharpe ratios by at least 0.15 units compared to periods below 30% concentration, controlling for GARCH(1,1) volatility clustering and Fama-French momentum factor exposure. | code=Partial: passive concentration threshold 0.30 is present; minimum effect size -0.15 is present; GARCH(1,1) is present; Fama-MacBeth regression is present; actual momentum logic compares against a capped lookback index of 4 despite metadata saying 252; no explicit code evidence of Fama-French momentum factor exposure control.
- Primary Metric: paper=Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows. | code=Partial: primary_metric is referenced in Bonferroni call; episode length/default window is 252; explicit implementation of Sharpe ratio differential as high-minus-low over rolling 252-day windows not shown.
- Bonferroni correction: paper=Bonferroni correction for 6 simultaneous tests — adjusted threshold p < 0.0083 | code=_bonferroni called with n_tests=7; threshold p < 0.0083 is specified elsewhere.
- Fama-French three-factor OLS regression: paper=Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth) | code=_fama_macbeth_regression; linearmodels version tracking present; exact three-factor OLS import/implementation not shown.
- Data Source: paper=WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024 | code=yfinance download of CL=F and NG=F, date range 2000-01-01 to 2023-12-31.
- Roll Convention: paper=ratio_backward | code=Passport field says ratio_backward, but actual implementation uses yfinance auto_adjust=True and explicitly notes deviation from exact ratio_backward.
- Adjustment Method: paper=ratio_backward | code=Passport field says ratio_backward, but actual implementation uses yfinance auto_adjust=True and explicitly notes deviation from exact ratio_backward.
- Exclusion Rule: fewer than 100 trading days of history: paper=Exclude contracts with fewer than 100 trading days of history | code=Specification constant 100 present in env.py; no implementation shown in miner code.
- Exclusion Rule: roll dates within 5 days of major macro announcements (FOMC, CPI): paper=Exclude roll dates within 5 days of major macro announcements (FOMC, CPI) | code=apply_macro_exclusion_window(df, exclusion_days=5) exists but is a no-op returning unchanged data.
- Exclusion Rule: bid-ask spread exceeds 2% of contract price: paper=Exclude contracts where bid-ask spread exceeds 2% of contract price | code=Specification constant 2% present in env.py; no implementation shown in miner code.

## not_found_in_code
- Topic (paper specifies: Passive Investor Concentration and Momentum Profitability in Commodity Futures Markets)
- Fitness Function (paper specifies: meta_rl fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps)
- Training Episodes (paper specifies: 500,000 minimum across all scenarios and seeds)
- Pre-Analysis Plan Status (paper specifies: UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs. FORGE gate will reject any run where this status is not COMMITTED in pap_lock.)
- Audit Requirement: CODEC bidirectional audit (paper specifies: CODEC bidirectional audit required before QUILL writes paper)
- Audit Requirement: HAWK minimum score (paper specifies: HAWK minimum score to pass: 7/10 on methodology rubric)
- Audit Requirement: Maximum HAWK revision cycles (paper specifies: Maximum HAWK revision cycles: 3)
- Audit Requirement: DataPassport SHA-256 signature (paper specifies: DataPassport SHA-256 signature required on all MINER outputs)

## verdict: FAIL
severity: Major
issue: code_deviates: 10 specified parameters differ between code and PAPER.md
