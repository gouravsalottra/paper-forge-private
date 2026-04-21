# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T14:37:20+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 43
matched: 15
mismatched: 20
not_found_in_code: 8
match_ratio: 0.349

## mismatched_parameters
- Hypothesis threshold (passive GSCI concentration): paper=above 30% of open interest in GSCI energy futures | code=Passive capital scenarios include Medium = 30% of open interest; no explicit hypothesis comparison implementation shown beyond scenario levels
- Hypothesis effect size: paper=reduces 12-month momentum strategy Sharpe ratios by at least 0.15 units | code=Minimum effect size = -0.15 Sharpe units referenced in spec/context; no explicit code enforcement shown
- Primary Metric: paper=Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows | code=Returns tested are sim_df["mean_reward"]; no explicit rolling 252-day annualized Sharpe differential implementation shown
- Newey-West HAC lags: paper=4 lags | code=Helper body not shown; context states paper-level parameter is 4 lags
- Bonferroni adjusted threshold: paper=p < 0.0083 | code=Threshold stated in context for Bonferroni; explicit helper-body threshold not shown
- Fama-MacBeth: paper=linearmodels, Fama-MacBeth | code=_fama_macbeth_regression(sim_df); linearmodels not imported in shown code, only recorded in library_versions.json
- Markov switching regime detection: paper=statsmodels, k_regimes=2 | code=_markov_regime(returns); statsmodels MarkovAutoregression; k_regimes=2 stated only in context/spec, helper body not shown
- Minimum Effect Size: paper=-0.15 Sharpe units | code=No explicit code enforcement shown
- Data Source: paper=WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024 | code=yfinance using CL=F and NG=F, 2000-01-01 to 2023-12-31/2024-01-01 exclusive
- Adjustment Method: paper=ratio_backward | code=yfinance auto_adjust=True
- Seed Policy: paper=seeds = [1337, 42, 9999] | code=Bootstrap call uses seed=1337; no evidence all three seeds are run/enforced
- Exclusion Rule: macro announcement window: paper=Exclude roll dates within 5 days of major macro announcements (FOMC, CPI) | code=apply_macro_exclusion_window(df, exclusion_days=5) around approximate FOMC dates only
- Exclusion Rule: bid-ask spread threshold: paper=Exclude contracts where bid-ask spread exceeds 2% of contract price | code=apply_bid_ask_spread_filter(..., threshold=0.02) using spread proxy abs(high-low)/close
- Simulation Agent: paper=passive_gsci — rebalances to GSCI index weights mechanically | code=passive_gsci implemented; always returns action 1 (long)
- Simulation Agent: paper=mean_reversion — fades 3-month extremes | code=mean_reversion implemented using ±2% relative to obs[1]; no explicit 3-month extreme logic shown
- Simulation Agent: paper=liquidity_provider — posts limit orders both sides | code=liquidity_provider listed as environment possible agent; behavior not shown in provided context
- Simulation Agent: paper=macro_allocator — switches energy/non-energy on macro signals | code=macro_allocator listed as environment possible agent; behavior not shown in provided context
- Simulation Agent: paper=meta_rl — learns optimal allocation across all strategies | code=meta_rl listed as environment possible agent; learning/allocation behavior not shown in provided context
- Significance Threshold: paper=p < 0.0083 Bonferroni-corrected | code=Bonferroni with n_tests=6; explicit threshold not shown in helper body
- Audit Requirement: paper=DataPassport SHA-256 signature required on all MINER outputs | code=Passport writes are mentioned, but SHA-256 signature requirement not evidenced

## not_found_in_code
- Roll Convention (paper specifies: ratio_backward)
- Seed consistency requirement (paper specifies: All three seeds must produce qualitatively consistent results; finding valid only if it holds across all three seeds)
- Fitness Function (paper specifies: meta_rl fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps)
- Training Episodes (paper specifies: 500,000 minimum across all scenarios and seeds)
- Pre-Analysis Plan Status (paper specifies: UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs; FORGE gate rejects if not COMMITTED in pap_lock)
- Audit Requirement (paper specifies: CODEC bidirectional audit required before QUILL writes paper)
- Audit Requirement (paper specifies: HAWK minimum score to pass: 7/10 on methodology rubric)
- Audit Requirement (paper specifies: Maximum HAWK revision cycles: 3)

## verdict: FAIL
severity: Major
issue: code_deviates: 20 specified parameters differ between code and PAPER.md
