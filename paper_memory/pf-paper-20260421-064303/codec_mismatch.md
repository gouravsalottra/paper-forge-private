# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T13:52:09+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 34
matched: 7
mismatched: 13
not_found_in_code: 14
match_ratio: 0.206

## mismatched_parameters
- Two-tailed t-test: paper=Two-tailed t-test, p < 0.05, Newey-West HAC correction (4 lags) | code=OLS mean test with HAC standard errors in agents/sigma_job2.py::_newey_west_ttest using statsmodels OLS(...).fit(cov_type='HAC', cov_kwds={'maxlags': 4}); p-value recorded; two-tailed not explicitly stated
- Bonferroni correction: paper=Bonferroni correction for 6 simultaneous tests — adjusted threshold p < 0.0083 | code=Bonferroni implemented in agents/sigma_job2.py::_bonferroni with n_tests = 7
- Fama-French regression: paper=Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth) | code=agents/sigma_job2.py::_fama_macbeth; linearmodels indicated as intended dependency; Fama-MacBeth regression present, but three-factor OLS / Fama-French factor construction not shown
- Data Source: paper=WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024 | code=Primary implemented source is yfinance in agents/miner/miner.py; optional source contract allows 'wrds', but concrete implementation shown uses yfinance tickers CL=F and NG=F; date range 2000-01-01 to 2024-01-01 exclusive
- Seed Policy: paper=seeds = [1337, 42, 9999]; all three seeds must produce qualitatively consistent results; finding valid only if it holds across all three seeds | code=Seeds used in simulation sweep: 1337, 42, 9999; seed consistency validity rule NOT FOUND
- Simulation Agent 1: paper=passive_gsci — rebalances to GSCI index weights mechanically | code=Agent 'passive_gsci' implemented; behavior always long / action forced to 1, not explicit GSCI weight rebalancing
- Simulation Agent 3: paper=mean_reversion — fades 3-month extremes | code=Agent 'mean_reversion' implemented, but behavior uses 2% deviation from obs[1]; 3-month extremes not shown
- Simulation Agent 4: paper=liquidity_provider — posts limit orders both sides | code=Agent 'liquidity_provider' implemented, but behavior alternates long/short actions; limit-order posting not shown
- Simulation Agent 5: paper=macro_allocator — switches energy/non-energy on macro signals | code=Agent 'macro_allocator' implemented, but behavior depends on passive concentration threshold obs[6] < passive_threshold; macro signals / energy-non-energy switching not shown
- Passive Capital Scenario: Medium: paper=30% of open interest | code=MacroAllocator default passive_threshold = 0.30; explicit scenario set NOT FOUND
- Significance Threshold: paper=p < 0.05 two-tailed (primary) | code=Newey-West t-test p-value recorded; explicit primary threshold p < 0.05 two-tailed NOT FOUND
- Significance Threshold (Bonferroni): paper=p < 0.0083 | code=Bonferroni implemented with n_tests = 7, implying different adjusted threshold than 0.0083
- Audit Requirement: DataPassport SHA-256 signature: paper=required on all MINER outputs | code=Data passport is referenced/recorded, but SHA-256 signature requirement on all MINER outputs NOT FOUND

## not_found_in_code
- Primary Metric (paper specifies: Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows)
- DCC-GARCH cross-asset correlation (paper specifies: DCC-GARCH cross-asset correlation)
- Minimum Effect Size (paper specifies: -0.15 Sharpe units)
- Exclusion Rule: minimum trading history (paper specifies: Exclude contracts with fewer than 100 trading days of history)
- Exclusion Rule: macro announcement window (paper specifies: Exclude roll dates within 5 days of major macro announcements (FOMC, CPI))
- Exclusion Rule: bid-ask spread filter (paper specifies: Exclude contracts where bid-ask spread exceeds 2% of contract price)
- Passive Capital Scenario: Low (paper specifies: 10% of open interest)
- Passive Capital Scenario: High (paper specifies: 60% of open interest)
- Fitness Function (paper specifies: meta_rl fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps)
- Training Episodes (paper specifies: 500,000 minimum across all scenarios and seeds)
- Pre-Analysis Plan Status (paper specifies: UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs; FORGE gate rejects any run where status is not COMMITTED in pap_lock)
- Audit Requirement: CODEC bidirectional audit (paper specifies: required before QUILL writes paper)
- Audit Requirement: HAWK minimum score (paper specifies: 7/10 on methodology rubric)
- Audit Requirement: Maximum HAWK revision cycles (paper specifies: 3)

## verdict: FAIL
severity: Major
issue: code_deviates: 13 specified parameters differ between code and PAPER.md
