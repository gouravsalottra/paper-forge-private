# PAPER-FORGE Research Specification

## Topic
Passive Investor Concentration and Momentum Profitability in Commodity Futures Markets

## Hypothesis
We explore whether passive concentration is associated with momentum
profitability changes, with no directional pre-commitment.

## Primary Metric
Sharpe ratio differential: high-concentration periods minus low-concentration
periods, annualized over rolling 252-step windows.

## Statistical Tests
1. Two-tailed t-test, p < 0.05, Newey-West HAC correction (4 lags)
2. Bonferroni correction for simultaneous tests (development threshold p < 0.0083)
3. GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution)
4. Fama-MacBeth-style concentration regression (linearmodels where available)
5. Markov switching regime detection (statsmodels, k_regimes=2)
6. DCC-GARCH cross-asset correlation summary

## Minimum Effect Size
-0.15 Sharpe units. Effects smaller in magnitude are economically insignificant.

## Data Source
WRDS Compustat Futures, GSCI energy sector (crude oil and natural gas), 2000-2024.

## Sample Period
2000-01-01 through 2024-12-31.

## Roll Convention
ratio_backward.

## Adjustment Method
ratio_backward.

## Return Construction
Log returns: np.log(P_t / P_{t-1}).

## Seed Policy
Three seeds: 1337, 42, 9999.
Results valid only if directionally consistent across all three seeds.

## Exclusion Rules
- Exclude series with fewer than 100 trading days of history
- Apply macro exclusion window rule configuration at 5 days around major macro dates
- Exclude rows where proxy bid-ask spread exceeds 2% of price

## Simulation Agents
1. passive_gsci       — always long (mechanical passive demand proxy)
2. trend_follower     — momentum signal long/short policy
3. mean_reversion     — threshold-based mean-reversion policy
4. liquidity_provider — alternating two-sided action policy
5. macro_allocator    — concentration-threshold allocation policy
6. meta_rl            — CEM-optimized policy over discrete actions

## Passive Capital Scenarios
- Low:    10% concentration
- Medium: 30% concentration (hypothesis threshold)
- High:   60% concentration

## Fitness Function
meta_rl fitness is tracked as Sharpe-style objective over trailing episode rewards,
with periodic evaluation during training.

## Training Episodes
500 episodes (development run);
500,000 episodes (production run).
Set PAPER_FORGE_FORGE_EPISODES=500000 for production.

## Significance Threshold
p < 0.05 two-tailed (primary)
p < 0.0083 Bonferroni-adjusted (development simultaneous-test threshold)

## Pre-Analysis Plan Status
COMMITTED — committed by SIGMA_JOB1 in pap_lock before FORGE dispatch.

## Audit Requirements
- CODEC audit required before QUILL writes paper
- HAWK review required before final acceptance
- DataPassport SHA-256 signature required on MINER outputs
