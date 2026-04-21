# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T14:00:16+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 36
matched: 11
mismatched: 16
not_found_in_code: 9
match_ratio: 0.306

## mismatched_parameters
- Hypothesized Sharpe ratio reduction: paper=reduces 12-month momentum strategy Sharpe ratios by at least 0.15 units | code=Minimum effect threshold not enforced; no explicit -0.15 hypothesis check visible
- Primary Metric: paper=Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows | code=sim_results consumed with columns including concentration and sharpe; no explicit high-minus-low rolling 252-day Sharpe differential computation visible
- Two-tailed t-test: paper=Two-tailed t-test, p < 0.05, Newey-West HAC correction (4 lags) | code=OLS intercept test with HAC/Newey-West covariance, maxlags=4; no explicit p < 0.05 threshold enforcement visible
- Bonferroni correction: paper=Bonferroni correction for 6 simultaneous tests — adjusted threshold p < 0.0083 | code=Bonferroni correction applied with n_tests=7
- GARCH model: paper=GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution) | code=arch_model used; mean='Constant', volatility='GARCH'; p=1, q=1, distribution not confirmed from visible code
- Fama-French regression: paper=Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth) | code=Fama-MacBeth invoked, but exact implementation library and three-factor OLS setup not visible
- Markov switching regime detection: paper=statsmodels, k_regimes=2 | code=MarkovAutoregression used; exact fitted parameters including k_regimes not visible
- Minimum Effect Size: paper=-0.15 Sharpe units | code=No minimum effect threshold enforced in visible implementation
- Data Source: paper=WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024 | code=Primary implemented dev source is yfinance for CL=F and NG=F; alternate source='wrds' path exists but visible config fetches kind='ff_factors' and dataset contents are not visible
- Roll Convention: paper=ratio_backward | code=Passport records roll_convention='ratio_backward'; note says yfinance auto_adjust=True used as proxy
- Adjustment Method: paper=ratio_backward | code=Passport records adjustment_method='ratio_backward'; note says yfinance auto_adjust=True used as proxy
- Training Episodes: paper=500,000 minimum across all scenarios and seeds | code=Data consumed by SigmaJob2 includes n_episodes, but no visible enforcement of 500,000 minimum across all scenarios and seeds
- Significance Threshold (primary): paper=p < 0.05 two-tailed | code=No explicit primary alpha threshold enforced in visible implementation excerpt
- Significance Threshold (Bonferroni): paper=p < 0.0083 | code=Bonferroni applied with n_tests=7; adjusted threshold p < 0.0083 not visible
- Pre-Analysis Plan Status: paper=UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs. FORGE gate will reject any run where this status is not COMMITTED in pap_lock. | code=Bootstrap seed derived from pap_lock via _seed_from_pap_lock(); no visible FORGE gate rejecting runs unless pap_lock status is COMMITTED
- Audit Requirement: DataPassport SHA-256 signature: paper=required on all MINER outputs | code=DataPassport SHA-256 mentioned in paper requirement, but no explicit enforcement on all MINER outputs visible in provided code extract

## not_found_in_code
- DCC-GARCH cross-asset correlation (paper specifies: DCC-GARCH cross-asset correlation)
- Seed consistency requirement (paper specifies: All three seeds must produce qualitatively consistent results. A finding is only valid if it holds across all three seeds.)
- Exclusion Rule: minimum trading history (paper specifies: Exclude contracts with fewer than 100 trading days of history)
- Exclusion Rule: macro announcement window (paper specifies: Exclude roll dates within 5 days of major macro announcements (FOMC, CPI))
- Exclusion Rule: bid-ask spread filter (paper specifies: Exclude contracts where bid-ask spread exceeds 2% of contract price)
- Fitness Function (paper specifies: meta_rl fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps)
- Audit Requirement: CODEC bidirectional audit (paper specifies: required before QUILL writes paper)
- Audit Requirement: HAWK minimum score (paper specifies: 7/10 on methodology rubric)
- Audit Requirement: Maximum HAWK revision cycles (paper specifies: 3)

## verdict: FAIL
severity: Major
issue: code_deviates: 16 specified parameters differ between code and PAPER.md
