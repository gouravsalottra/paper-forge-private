Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 1) Full implementation steps in order

## Phase 0 — Governance and run eligibility
1. **Verify pre-analysis status is committed**
   - The spec states the pre-analysis plan status is initially `UNCOMMITTED` and must be changed to `COMMITTED` before execution.
   - Do not run the study unless that condition is satisfied.

2. **Define the study scope**
   - Universe: WRDS Compustat Futures, GSCI energy sector.
   - Instruments explicitly named: crude oil and natural gas.
   - Sample period: 2000–2024.

3. **Define all required outputs**
   - Primary output: annualized Sharpe ratio differential between high- and low-passive-concentration periods using rolling 252-day windows.
   - Supporting outputs:
     - t-tests with Newey-West HAC correction, 4 lags
     - Bonferroni-adjusted inference for 6 simultaneous tests
     - GARCH(1,1) volatility controls
     - Fama-French regression-based controls
     - Markov switching regime analysis
     - DCC-GARCH cross-asset correlation analysis
     - Seed-consistency assessment across seeds `[1337, 42, 9999]`

---

## Phase 1 — Data acquisition and raw dataset construction
4. **Pull futures data**
   - Retrieve daily futures data for crude oil and natural gas from WRDS Compustat Futures for 2000–2024.
   - Required fields, at minimum:
     - date
     - contract identifier
     - price series needed for returns
     - open interest
     - bid-ask spread or bid and ask quotes
     - contract listing and expiration metadata
   - Because passive concentration is defined as a share of open interest, obtain or construct passive GSCI investor holdings if available.

5. **Pull GSCI-related information**
   - Obtain GSCI energy-sector constituent weights over time.
   - Needed for:
     - identifying “GSCI energy futures”
     - implementing the passive GSCI mechanical rebalancing agent
     - potentially estimating passive concentration if direct passive holdings are unavailable

6. **Pull macro announcement calendar**
   - Obtain dates for:
     - FOMC announcements
     - CPI releases
   - Needed for exclusion of roll dates within 5 days of major macro announcements.

7. **Pull factor data**
   - Obtain Fama-French three factors and a momentum factor series, because the hypothesis mentions controlling for “Fama-French momentum factor exposure.”
   - Align factor frequency to daily if possible, or define a conversion/alignment rule.

---

## Phase 2 — Continuous futures construction
8. **Define eligible contracts**
   - For each instrument, exclude contracts with fewer than 100 trading days of history.

9. **Apply spread filter**
   - Exclude contracts where bid-ask spread exceeds 2% of contract price.
   - Compute spread ratio as:
     - `(ask - bid) / mid` if bid and ask exist, or
     - use provided spread / price if only spread is available.
   - Flag this as an assumption if exact formula is not specified.

10. **Determine roll schedule**
   - Construct continuous futures series using:
     - roll convention = `ratio_backward`
     - adjustment method = `ratio_backward`
   - Identify roll dates for each instrument.

11. **Apply macro roll exclusion**
   - Exclude roll dates within 5 days of FOMC or CPI announcements.
   - Decide whether “within 5 days” means calendar days or trading days; this is underspecified and must be assumed.
   - Rebuild the continuous series after excluding disallowed roll dates or shifting rolls according to a predefined rule.

12. **Construct adjusted continuous price series**
   - Build ratio-backward adjusted continuous series for crude oil and natural gas.
   - Compute daily returns from adjusted prices.

---

## Phase 3 — Passive concentration measurement
13. **Define passive investor concentration**
   - For each date and instrument, compute passive GSCI concentration as:
     - passive GSCI open interest / total open interest
   - If instrument-level passive holdings are unavailable, define an estimation procedure using GSCI weights and total open interest; this is a major assumption.

14. **Classify concentration regimes**
   - Low scenario: 10% of open interest
   - Medium scenario: 30% of open interest
   - High scenario: 60% of open interest
   - For the primary hypothesis test, define:
     - low-concentration periods: concentration < 30%
     - high-concentration periods: concentration > 30%
   - Decide treatment of exactly 30%; this is underspecified.

15. **Create concentration regime labels**
   - Label each date as low, medium, or high according to the passive capital scenarios.
   - Also create a binary indicator for above/below the 30% threshold for the main test.

---

## Phase 4 — Strategy construction
16. **Construct the 12-month momentum strategy**
   - For each instrument/date, compute a 12-month momentum signal.
   - Use approximately 252 trading days as the lookback horizon unless otherwise specified.
   - Decide whether to skip the most recent month; this is underspecified.
   - Convert signal into long/short positions.

17. **Define momentum portfolio formation**
   - Since the universe appears to contain only crude oil and natural gas, define how long/short is implemented:
     - cross-sectional ranking between the two contracts, or
     - time-series momentum per asset.
   - This is underspecified and must be explicitly assumed.

18. **Compute momentum strategy returns**
   - Generate daily strategy returns from the momentum positions and continuous futures returns.
   - Include transaction cost treatment only if specified; none is specified, so omission must be flagged.

19. **Construct other simulation agents**
   - Implement:
     1. passive_gsci — mechanically rebalances to GSCI weights
     2. trend_follower — 12-month momentum long/short
     3. mean_reversion — fades 3-month extremes
     4. liquidity_provider — posts limit orders both sides
     5. macro_allocator — switches energy/non-energy on macro signals
     6. meta_rl — allocates across all strategies
   - These are required by the spec, though the primary hypothesis centers on momentum profitability.

20. **Operationalize each non-primary agent**
   - passive_gsci:
     - rebalance to time-varying GSCI weights on a chosen schedule
   - mean_reversion:
     - define 3-month extreme signal and contrarian position rule
   - liquidity_provider:
     - define quoting logic, fill model, inventory limits, and PnL
   - macro_allocator:
     - define macro signals and switching rule between energy and non-energy
   - meta_rl:
     - define state, action, reward, training algorithm, and allocation constraints
   - Nearly all of these are underspecified and require assumptions.

---

## Phase 5 — Rolling performance measurement
21. **Compute rolling 252-day Sharpe ratios**
   - For the momentum strategy, compute rolling annualized Sharpe ratios over 252-day windows.
   - Annualization convention must be assumed, likely:
     - `Sharpe = mean(daily excess return) / std(daily return) * sqrt(252)`
   - Excess return benchmark is not specified.

22. **Partition Sharpe observations by concentration regime**
   - Associate each rolling window with a concentration regime.
   - Decide whether regime is determined by:
     - concentration on the window end date,
     - average concentration over the window,
     - majority of days in the window.
   - This is underspecified.

23. **Compute primary metric**
   - Primary metric:
     - Sharpe(high concentration) minus Sharpe(low concentration)
   - Compare estimated differential to the minimum effect size threshold of `-0.15`.

---

## Phase 6 — Main statistical testing
24. **Run two-tailed t-test**
   - Test whether the Sharpe differential differs from zero.
   - Apply Newey-West HAC correction with 4 lags.
   - Because rolling windows overlap, HAC is appropriate.

25. **Apply Bonferroni correction**
   - There are 6 simultaneous tests.
   - Use adjusted significance threshold `p < 0.0083`.
   - The exact six tests are not enumerated; this must be assumed and flagged.

26. **Assess economic significance**
   - Even if statistically significant, declare the effect economically insignificant if the differential is greater than `-0.15` Sharpe units.

---

## Phase 7 — Volatility and factor controls
27. **Estimate GARCH(1,1) models**
   - Fit GARCH(1,1) with Normal innovations to relevant return series.
   - Use this to control for volatility clustering.
   - Decide whether to fit:
     - per asset,
     - on strategy returns,
     - or both.
   - This is underspecified.

28. **Construct volatility-adjusted analysis**
   - Use GARCH conditional volatility estimates as controls in the main regression or as standardized returns.
   - The exact control framework is not specified and must be assumed.

29. **Run factor regressions**
   - Estimate OLS regressions with Fama-French factors and momentum factor exposure.
   - The spec says “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth),” which mixes two different frameworks.
   - Choose and document one interpretation:
     - standard time-series OLS with FF3 + momentum factor, or
     - Fama-MacBeth cross-sectional procedure.
   - This is materially underspecified.

30. **Obtain concentration effect net of factor exposure**
   - Regress momentum strategy returns or rolling Sharpe outcomes on concentration indicators plus factor controls and volatility controls.
   - Extract the concentration coefficient and compare implied effect to `-0.15`.

---

## Phase 8 — Regime and dependence analysis
31. **Run Markov switching regime detection**
   - Fit a 2-regime Markov switching model (`k_regimes=2`) to either:
     - momentum returns,
     - concentration series,
     - or joint profitability states.
   - The target series is not specified.

32. **Compare concentration effect across regimes**
   - Evaluate whether the high-vs-low concentration Sharpe differential differs by latent regime.

33. **Run DCC-GARCH cross-asset correlation analysis**
   - Estimate dynamic conditional correlations between crude oil and natural gas returns.
   - Assess whether passive concentration is associated with higher/lower cross-asset correlation and whether this mediates momentum profitability.
   - Exact implementation details are not specified.

---

## Phase 9 — Simulation and reinforcement learning
34. **Set random seeds**
   - Run all stochastic components under seeds:
     - 1337
     - 42
     - 9999

35. **Train simulation agents**
   - Train/evaluate across passive capital scenarios:
     - low = 10%
     - medium = 30%
     - high = 60%
   - Minimum total training episodes across all scenarios and seeds: 500,000.

36. **Evaluate meta_rl fitness**
   - Fitness = Sharpe ratio over trailing 252 episodes
   - Evaluate every 1000 training steps

37. **Check qualitative consistency across seeds**
   - A finding is valid only if it holds across all three seeds.
   - Define “qualitatively consistent” before execution; this is underspecified.

38. **Integrate simulation findings with empirical findings**
   - Compare whether simulated momentum profitability declines under higher passive concentration in a way consistent with the empirical estimate.

---

## Phase 10 — Final inference and reporting
39. **Determine whether the hypothesis is supported**
   - Support requires:
     - high concentration above 30% associated with lower 12-month momentum Sharpe
     - differential at least `-0.15`
     - statistical significance under primary threshold and, where applicable, Bonferroni threshold
     - consistency across all three seeds

40. **Produce a reproducible results package**
   - Include:
     - data extraction parameters
     - exclusion counts
     - roll construction details
     - concentration regime counts
     - strategy definitions
     - all model specifications
     - seed-wise results
     - sensitivity analyses for underspecified choices

41. **Satisfy audit requirements**
   - Ensure:
     - bidirectional audit completed before paper writing
     - methodology score at least 7/10
     - no more than 3 revision cycles
     - SHA-256 signature on all outputs

---

# 2) Assumptions needed due to underspecification

These assumptions are necessary to make the methodology executable.

1. **Instrument universe assumption**
   - Assume the GSCI energy sector in this study includes only crude oil and natural gas because those are the only instruments explicitly named.

2. **Passive concentration data assumption**
   - Assume passive GSCI investor holdings are directly observable in the data or can be proxied from GSCI weights and open interest.
   - If proxied, assume passive notional is allocated proportionally to GSCI weights.

3. **Threshold classification assumption**
   - Assume:
     - low concentration = strictly less than 30%
     - high concentration = strictly greater than 30%
     - exactly 30% belongs to medium or is excluded from binary tests.

4. **Momentum definition assumption**
   - Assume 12-month momentum uses a 252-trading-day lookback.

5. **Momentum implementation assumption**
   - Assume time-series momentum rather than cross-sectional momentum, because the universe is too small for a robust cross-sectional sort.

6. **Signal timing assumption**
   - Assume no one-month skip unless explicitly tested in sensitivity analysis.

7. **Sharpe calculation assumption**
   - Assume annualized Sharpe uses daily returns and `sqrt(252)` annualization.

8. **Risk-free rate assumption**
   - Assume Sharpe is computed on raw daily returns if daily risk-free data are not integrated; otherwise use excess returns over daily risk-free rate.

9. **Window regime assignment assumption**
   - Assume each rolling 252-day Sharpe window is assigned to the concentration regime of its end date.

10. **Spread filter assumption**
   - Assume bid-ask spread percentage is measured relative to mid-price.

11. **Macro exclusion timing assumption**
   - Assume “within 5 days” means within 5 trading days.

12. **Roll exclusion handling assumption**
   - Assume disallowed roll dates are shifted to the nearest eligible trading day.

13. **GARCH control assumption**
   - Assume GARCH(1,1) is fit on momentum strategy returns for the primary controlled analysis.

14. **Factor model assumption**
   - Assume the intended factor specification is FF3 plus a momentum factor in a time-series regression, despite the mention of Fama-MacBeth.

15. **Six simultaneous tests assumption**
   - Assume the six tests correspond to combinations such as:
     - two assets,
     - three concentration comparisons,
     - or multiple model variants.
   - This must be fixed in advance.

16. **Markov switching target assumption**
   - Assume the Markov switching model is fit to momentum strategy returns.

17. **DCC-GARCH scope assumption**
   - Assume DCC-GARCH is estimated on crude oil and natural gas daily returns.

18. **Simulation environment assumption**
   - Assume an agent-based market simulator is required, though no market microstructure details are provided.

19. **Liquidity provider assumption**
   - Assume a stylized fill model and inventory-constrained quoting process.

20. **Macro allocator assumption**
   - Assume macro signals are derived from the same FOMC/CPI information or other macro indicators available over the sample.

21. **Meta-RL algorithm assumption**
   - Assume any standard RL allocator is acceptable if it optimizes trailing 252-episode Sharpe and is evaluated every 1000 steps.

22. **Qualitative consistency assumption**
   - Assume “qualitatively consistent” means same sign and same directional conclusion regarding hypothesis support across all seeds.

23. **Training episode assumption**
   - Assume the 500,000 minimum episodes refers to the aggregate total over all seeds and scenarios, not per seed-scenario combination.

24. **Non-energy allocation assumption**
   - For macro_allocator, assume access to a non-energy benchmark or synthetic outside asset, though none is specified.

---

# 3) Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data and universe
1. **Exact contract list is not specified**
   - Only “crude oil, natural gas” are named; exact exchange contracts and maturities are not given.

2. **Exact WRDS fields are not specified**
   - Required columns for implementation are not enumerated.

3. **Passive GSCI investor holdings source is not specified**
   - The spec defines concentration but does not state where passive holdings come from.

4. **Whether concentration is measured per contract, per commodity, or sector aggregate is not specified.**

5. **Whether open interest is front-contract only or summed across eligible contracts is not specified.**

## Continuous futures construction
6. **Exact roll trigger is not specified**
   - “ratio_backward” is given, but not when to roll.

7. **How to handle excluded roll dates is not specified**
   - Skip, delay, advance, or drop observations?

8. **Whether “within 5 days” means calendar or trading days is not specified.**

9. **Whether exclusion applies only to roll dates or to surrounding return observations is not specified.**

10. **Spread calculation formula is not specified.**

## Strategy definition
11. **Momentum strategy type is not specified**
   - Cross-sectional vs time-series.

12. **Momentum signal formula is not specified**
   - Cumulative return, log return, risk-adjusted return, etc.

13. **Whether to skip the most recent month is not specified.**

14. **Position sizing rule is not specified**
   - Equal weight, volatility scaling, signal proportionality, etc.

15. **Rebalancing frequency is not specified.**

16. **Leverage constraints are not specified.**

17. **Transaction costs and slippage are not specified.**

18. **Whether returns are excess returns or total returns is not specified.**

## Primary metric and inference
19. **How rolling Sharpe windows are assigned to concentration regimes is not specified.**

20. **Whether the primary differential is mean of rolling Sharpe windows or Sharpe of pooled returns by regime is not specified.**

21. **The exact t-test setup is not specified**
   - Difference in means of rolling Sharpe windows? Regression coefficient test? Paired or unpaired?

22. **The six simultaneous tests for Bonferroni are not identified.**

23. **Whether Bonferroni applies to all analyses or only a subset is not specified.**

## Volatility and factor controls
24. **How GARCH(1,1) enters the main hypothesis test is not specified.**

25. **Which series receives the GARCH model is not specified.**

26. **The factor model is internally ambiguous**
   - “Fama-French three-factor OLS regression” and “Fama-MacBeth” are different procedures.

27. **The momentum factor source/frequency is not specified.**

28. **How factor exposure is used as a control in the Sharpe differential analysis is not specified.**

## Regime/dependence models
29. **Markov switching target variable is not specified.**

30. **Markov switching model form is not specified**
   - switching mean, variance, both?

31. **DCC-GARCH implementation details are not specified**
   - univariate margins, innovation distribution, estimation window, etc.

32. **How DCC-GARCH results feed into the main conclusion is not specified.**

## Simulation agents
33. **Simulation environment is not specified.**

34. **Market clearing mechanism is not specified.**

35. **Order book or execution model is not specified.**

36. **Agent observation spaces are not specified.**

37. **Agent action spaces are not specified.**

38. **Reward functions for all agents except meta_rl are not specified.**

39. **Mean reversion “3-month extremes” is not operationally defined.**

40. **Liquidity provider behavior is not operationally defined.**

41. **Macro signals for macro_allocator are not specified.**

42. **What “switches energy/non-energy” means in terms of tradable assets is not specified.**

43. **Meta-RL algorithm is not specified.**

44. **Meta-RL state representation is not specified.**

45. **Meta-RL action constraints are not specified.**

46. **Whether simulation is calibrated to empirical data is not specified.**

47. **How passive capital scenarios map into simulated order flow is not specified.**

48. **How simulation outputs relate to the empirical hypothesis test is not specified.**

## Seeds and validity
49. **What counts as “qualitatively consistent” is not specified.**

50. **Whether all three seeds must individually meet significance thresholds is not specified.**

51. **Whether 500,000 episodes is total or per seed/scenario is not specified.**

## Audit/process requirements
52. **How to operationalize the audit requirements in a methodology implementation is not specified.**

53. **What constitutes a valid DataPassport signature artifact is not specified.**

---

# 4) Reproducibility rating: 2 / 5

## Rating: 2 out of 5

## Rationale
The specification provides a strong high-level research intent but is not sufficiently operational for high-confidence exact reproduction.

### Why it is not a 1
- It clearly states:
  - hypothesis
  - sample period
  - data source family
  - key instruments
  - primary metric
  - significance thresholds
  - several required statistical models
  - exclusion rules
  - passive concentration scenarios
  - seeds
  - minimum episode count

This is enough to build a plausible implementation.

### Why it is not a 3 or higher
Several core methodological components are materially underspecified:

- passive concentration measurement source and construction
- exact futures roll trigger despite naming ratio-backward adjustment
- exact momentum strategy definition
- exact mapping from concentration regimes to rolling Sharpe windows
- exact regression/control specification
- ambiguity between OLS and Fama-MacBeth
- undefined six simultaneous tests
- largely unspecified simulation environment and agent mechanics
- undefined criterion for seed consistency

These choices can materially change results, especially the primary Sharpe differential.

### Practical implication
A competent researcher can implement a study inspired by this spec, but two independent teams working only from this text would likely produce meaningfully different results unless they harmonize assumptions first.

---

# 5) Recommended implementation stance

To faithfully reimplement from this spec alone:

1. **Freeze all assumptions in a written protocol before running anything.**
2. **Treat every flagged underspecified item as a sensitivity dimension.**
3. **Prioritize the empirical core first**
   - continuous futures construction
   - passive concentration measurement
   - 12-month momentum returns
   - rolling Sharpe differential
   - HAC inference
4. **Then add controls**
   - GARCH
   - factor regressions
   - Markov switching
   - DCC-GARCH
5. **Then implement simulation**
   - only after defining a complete market environment and agent rules
6. **Require seed-wise directional consistency**
   - because the spec explicitly makes this validity-critical

If you want, I can next turn this into a **formal pseudocode protocol** or a **step-by-step experimental design document with equations**.