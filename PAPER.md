# PAPER-FORGE Research Specification

## Topic
Passive Investor Concentration and Momentum Profitability in Commodity Futures Markets

## Hypothesis
Passive GSCI index investor concentration above 30% of open interest in GSCI
energy futures reduces 12-month momentum strategy Sharpe ratios by at least
0.15 units compared to periods below 30% concentration, controlling for
GARCH(1,1) volatility clustering and Fama-French momentum factor exposure.

## Primary Metric
Sharpe ratio differential: high-concentration periods minus low-concentration
periods, annualized over rolling 252-day windows.

## Statistical Tests
1. Two-tailed t-test, p < 0.05, Newey-West HAC correction (4 lags)
2. Bonferroni correction for 6 simultaneous tests — adjusted threshold p < 0.0083
3. GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution)
4. Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)
5. Markov switching regime detection (statsmodels, k_regimes=2)
6. DCC-GARCH cross-asset correlation

## Minimum Effect Size
-0.15 Sharpe units. Effects smaller than this are economically insignificant
regardless of statistical significance.

## Data Source
WRDS Compustat Futures — GSCI energy sector (crude oil, natural gas), 2000–2024

## Roll Convention
ratio_backward

## Adjustment Method
ratio_backward

## Seed Policy
seeds = [1337, 42, 9999]
All three seeds must produce qualitatively consistent results.
A finding is only valid if it holds across all three seeds.

## Exclusion Rules
- Exclude contracts with fewer than 100 trading days of history
- Exclude roll dates within 5 days of major macro announcements (FOMC, CPI)
- Exclude contracts where bid-ask spread exceeds 2% of contract price

## Simulation Agents
1. passive_gsci       — rebalances to GSCI index weights mechanically
2. trend_follower     — 12-month momentum signal, long/short
3. mean_reversion     — fades 3-month extremes
4. liquidity_provider — posts limit orders both sides
5. macro_allocator    — switches energy/non-energy on macro signals
6. meta_rl            — learns optimal allocation across all strategies

## Passive Capital Scenarios
- Low:    10% of open interest
- Medium: 30% of open interest (hypothesis threshold)
- High:   60% of open interest

## Fitness Function
meta_rl fitness = Sharpe ratio over trailing 252 episodes,
evaluated every 1000 training steps.

## Training Episodes
500,000 minimum across all scenarios and seeds.

## Significance Threshold
p < 0.05 two-tailed (primary)
p < 0.0083 Bonferroni-corrected (for simultaneous tests)

## Pre-Analysis Plan Status
UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs.
FORGE gate will reject any run where this status is not COMMITTED in pap_lock.

## Audit Requirements
- CODEC bidirectional audit required before QUILL writes paper
- HAWK minimum score to pass: 7/10 on methodology rubric
- Maximum HAWK revision cycles: 3
- DataPassport SHA-256 signature required on all MINER outputs
