Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 0. Scope of what is being reimplemented
Reimplement the research workflow to test:

> Whether passive GSCI index investor concentration above 30% of open interest in GSCI energy futures reduces 12-month momentum strategy Sharpe ratios by at least 0.15 versus periods below 30%, controlling for GARCH(1,1) volatility clustering and Fama-French momentum factor exposure.

The implementation must cover:
- data construction
- exclusions
- futures rolling/adjustment
- momentum strategy construction
- concentration regime assignment
- statistical testing
- auxiliary models listed in the spec
- simulation agents and seed policy
- reproducibility checks across seeds

---

# 1. Full implementation steps in order

## Step 1: Formalize the research question and testable estimand
Define the primary estimand as:

- Annualized Sharpe ratio of the 12-month momentum strategy during:
  - high passive concentration periods
  - low passive concentration periods

Then compute:

- **Sharpe differential = Sharpe(high concentration) − Sharpe(low concentration)**

Primary hypothesis:
- differential ≤ -0.15 and statistically significant under the specified tests.

Also define:
- medium concentration as a separate scenario because it is listed in passive capital scenarios
- simultaneous tests count = 6 for Bonferroni adjustment

---

## Step 2: Define the sample universe
Construct the commodity futures universe from:

- WRDS Compustat Futures
- GSCI energy sector
- instruments explicitly named:
  - crude oil
  - natural gas
- sample period:
  - 2000 through 2024

Implementation tasks:
1. Identify all crude oil and natural gas futures contracts in the source.
2. Restrict to contracts belonging to the GSCI energy sector.
3. Keep all observations within the 2000–2024 date range.

---

## Step 3: Ingest required raw fields
For each contract/day, obtain at minimum:

- trade date
- contract identifier
- underlying commodity
- price series needed for returns
- open interest
- bid price and ask price, or enough information to compute bid-ask spread
- contract listing date / first available date
- expiration date
- any fields needed to construct continuous futures series
- any fields needed to identify roll dates

Additional external data required by the spec:
- FOMC announcement dates
- CPI announcement dates
- Fama-French factors
- momentum factor exposure input series
- any macro signals needed for the macro allocator
- any data needed for DCC-GARCH cross-asset correlation
- any data needed for Markov switching regime detection

---

## Step 4: Apply contract-level exclusion rules
Apply the exclusions exactly as specified.

### 4.1 Exclude short-history contracts
Exclude contracts with:
- fewer than 100 trading days of history

Implementation:
- count available trading days per contract
- remove contracts with count < 100

### 4.2 Exclude observations near major macro announcements
Exclude:
- roll dates within 5 days of major macro announcements
- announcements listed:
  - FOMC
  - CPI

Implementation:
1. Build a calendar of FOMC and CPI announcement dates.
2. Identify all roll dates used in the continuous futures construction.
3. Remove roll events occurring within ±5 calendar days or ±5 trading days of those announcements.

This is underspecified; assumption required later.

### 4.3 Exclude contracts with excessive bid-ask spread
Exclude contracts where:
- bid-ask spread exceeds 2% of contract price

Implementation:
- compute spread percentage = (ask - bid) / reference price
- exclude observations or contracts depending on interpretation

This is underspecified; assumption required later.

---

## Step 5: Construct continuous futures series
Use the specified:

- Roll convention: `ratio_backward`
- Adjustment method: `ratio_backward`

Implementation:
1. For each commodity, order contracts by maturity.
2. Define roll schedule.
3. On each roll date, splice the outgoing and incoming contracts using backward ratio adjustment.
4. Produce continuous adjusted daily price series for:
   - crude oil
   - natural gas

Because both roll convention and adjustment method are given as ratio backward, use multiplicative backward adjustment.

---

## Step 6: Define daily returns
From the continuous adjusted series, compute daily returns.

Recommended implementation:
- arithmetic daily returns for Sharpe ratio and strategy PnL
- optionally log returns for some econometric models if needed, but keep primary metric based on arithmetic returns unless otherwise specified

This is partially underspecified.

---

## Step 7: Measure passive investor concentration
Construct passive GSCI investor concentration as:

- passive GSCI open interest share = passive GSCI open interest / total open interest

Then classify each date into scenarios:
- Low = 10%
- Medium = 30%
- High = 60%

For the primary hypothesis:
- compare periods above 30% concentration to periods below 30% concentration

Implementation:
1. For each date and commodity, estimate or assign passive GSCI share of open interest.
2. Label dates:
   - low-concentration periods: below 30%
   - high-concentration periods: above 30%
3. Preserve medium and high scenario labels for scenario analysis.

This is highly underspecified because the source of passive GSCI ownership is not defined.

---

## Step 8: Build the 12-month momentum strategy
Construct the trend_follower strategy as:

- 12-month momentum signal
- long/short

Implementation:
1. For each commodity/date, compute trailing 12-month momentum signal.
2. Assign long position to positive momentum and short position to negative momentum.
3. Aggregate across crude oil and natural gas into a portfolio.

Need to define:
- lookback length in trading days
- whether to skip the most recent month
- weighting scheme across assets
- rebalancing frequency
- treatment of zero signals

All are underspecified.

---

## Step 9: Compute rolling 252-day Sharpe ratios
Primary metric requires:

- annualized Sharpe ratio differential
- over rolling 252-day windows

Implementation:
1. Compute daily momentum strategy returns.
2. For each date t with at least 252 prior observations:
   - calculate mean daily return over trailing 252 days
   - calculate standard deviation over trailing 252 days
   - annualize Sharpe ratio
3. Partition windows by concentration regime.

Need to define whether:
- windows are assigned by end-of-window regime
- windows must be entirely within one regime
- windows can overlap regime changes

This is underspecified.

---

## Step 10: Compute the primary Sharpe differential
Compute:

- mean annualized rolling Sharpe during high-concentration periods
- mean annualized rolling Sharpe during low-concentration periods
- differential = high − low

Then evaluate:
- statistical significance
- economic significance threshold of -0.15 Sharpe units

Decision rule:
- finding is economically meaningful only if differential ≤ -0.15
- if differential is statistically significant but > -0.15, classify as economically insignificant

---

## Step 11: Run the primary t-test with Newey-West HAC correction
Specified test:
- two-tailed t-test
- p < 0.05
- Newey-West HAC correction with 4 lags

Implementation:
1. Form the series of rolling Sharpe observations or regime-specific return differences.
2. Estimate the mean difference between high and low concentration periods.
3. Compute HAC standard errors with 4 lags.
4. Conduct two-tailed t-test.

Need to define the exact tested unit:
- rolling Sharpe windows
- daily returns interacted with regime
- difference in average Sharpe across windows

This is underspecified.

---

## Step 12: Apply Bonferroni correction
Because there are 6 simultaneous tests:
- adjusted threshold = 0.0083

Implementation:
1. Enumerate the six tests being jointly considered.
2. For each, compute p-value.
3. Compare:
   - primary threshold: 0.05
   - Bonferroni threshold: 0.0083

Need to define exactly which six tests are included.

---

## Step 13: Fit GARCH(1,1) model
Specified:
- arch library
- p=1, q=1
- Normal distribution

Implementation:
1. Use momentum strategy returns or asset returns as the dependent series.
2. Fit GARCH(1,1) with normal innovations.
3. Extract conditional volatility estimates.
4. Use these estimates as controls or adjusted volatility inputs in the main analysis.

Need to define:
- whether GARCH is fit to portfolio returns or each commodity separately
- how “controlling for GARCH volatility clustering” enters the main test

This is underspecified.

---

## Step 14: Estimate Fama-French regression with momentum exposure
Specified:
- Fama-French three-factor OLS regression
- linearmodels
- Fama-MacBeth

Implementation:
1. Obtain Fama-French factors and momentum factor.
2. Regress momentum strategy returns on:
   - market
   - size
   - value
   - momentum factor exposure
3. Use Fama-MacBeth framework as specified.
4. Extract residualized returns or factor-adjusted alpha.
5. Reassess concentration effect controlling for factor exposure.

This is internally inconsistent/underspecified because “three-factor” and “momentum factor exposure” imply at least four factors.

---

## Step 15: Fit Markov switching regime model
Specified:
- statsmodels
- k_regimes = 2

Implementation:
1. Fit a 2-regime Markov switching model to either:
   - momentum returns
   - volatility
   - concentration-adjusted returns
2. Infer latent regimes.
3. Compare whether concentration effects differ by regime.

Need to define:
- dependent variable
- switching mean vs switching variance vs both
- exogenous regressors

Underspecified.

---

## Step 16: Estimate DCC-GARCH cross-asset correlation
Specified:
- DCC-GARCH cross-asset correlation

Implementation:
1. Use crude oil and natural gas return series.
2. Fit univariate GARCH models first.
3. Fit DCC process to estimate time-varying correlation.
4. Use dynamic correlations as:
   - descriptive diagnostics, or
   - controls in robustness analysis

Need to define:
- exact DCC specification
- software/library
- whether this enters the primary hypothesis test

Underspecified.

---

## Step 17: Implement simulation agents
Create six agents:

1. passive_gsci — mechanically rebalances to GSCI index weights
2. trend_follower — 12-month momentum long/short
3. mean_reversion — fades 3-month extremes
4. liquidity_provider — posts limit orders both sides
5. macro_allocator — switches energy/non-energy on macro signals
6. meta_rl — learns optimal allocation across all strategies

Implementation:
1. Define state variables and action spaces for each agent.
2. Simulate or backtest each agent over the sample.
3. Ensure passive capital scenarios are represented:
   - 10%
   - 30%
   - 60% of open interest
4. Feed strategy returns into meta_rl.

This section is highly underspecified because market microstructure, execution, reward definitions, and environment dynamics are not defined.

---

## Step 18: Implement passive capital scenarios
For each scenario:
- Low passive capital = 10% of open interest
- Medium = 30%
- High = 60%

Implementation:
1. Parameterize passive_gsci holdings as a fixed share of open interest.
2. Recompute market environment / strategy outcomes under each scenario.
3. Compare momentum profitability across scenarios.

Need to define whether:
- these are empirical subsamples
- simulated counterfactuals
- both

Underspecified.

---

## Step 19: Train meta_rl
Specified:
- fitness = Sharpe ratio over trailing 252 episodes
- evaluated every 1000 training steps
- minimum 500,000 training episodes across all scenarios and seeds

Implementation:
1. Define RL environment with agent strategy returns as allocatable sleeves.
2. Define reward/fitness as trailing 252-episode Sharpe.
3. Train for at least 500,000 episodes total across:
   - all passive capital scenarios
   - all seeds [1337, 42, 9999]
4. Evaluate every 1000 steps.
5. Store results by seed and scenario.

Need to define:
- RL algorithm
- observation space
- action constraints
- transaction costs
- exploration schedule
- episode length

Highly underspecified.

---

## Step 20: Enforce seed policy
Specified:
- seeds = [1337, 42, 9999]
- all three seeds must produce qualitatively consistent results
- finding valid only if it holds across all three seeds

Implementation:
1. Run all stochastic components separately for each seed.
2. Compare:
   - sign of effect
   - significance status
   - economic significance status
3. Declare result valid only if all three seeds agree qualitatively.

Need to define “qualitatively consistent.”

---

## Step 21: Run the six simultaneous tests
Because Bonferroni is specified for six tests, define and execute six tests. A reasonable implementation from the spec would be:

1. Primary Sharpe differential t-test
2. GARCH-controlled effect test
3. Factor-adjusted effect test
4. Markov regime-conditioned effect test
5. DCC-correlation-conditioned effect test
6. Scenario-based high vs low passive capital effect test

This mapping is an assumption because the six tests are not explicitly enumerated.

---

## Step 22: Evaluate significance and economic materiality
For each seed and scenario:
1. Record effect estimate.
2. Record p-value.
3. Compare against:
   - 0.05
   - 0.0083
4. Compare effect size against:
   - -0.15 Sharpe units

Decision hierarchy:
- statistically significant and economically significant
- statistically significant but economically insignificant
- not statistically significant

---

## Step 23: Aggregate across seeds
A finding is valid only if all three seeds produce qualitatively consistent results.

Implementation:
1. Summarize results for each seed.
2. Check consistency rule.
3. If any seed fails, reject the finding as non-robust.

---

## Step 24: Produce final outputs
Produce:
- rolling Sharpe series
- regime labels
- primary differential estimate
- HAC t-test results
- Bonferroni-adjusted significance results
- GARCH outputs
- factor regression outputs
- Markov switching outputs
- DCC-GARCH outputs
- simulation agent performance summaries
- seed consistency summary
- final conclusion on hypothesis support

---

# 2. Assumptions needed due to underspecification

Below are assumptions required to make the methodology executable.

## A1. Definition of passive GSCI concentration
Assume passive GSCI concentration is either:
- directly observable from position/open-interest data if available, or
- proxied by scenario assignment (10%, 30%, 60%) in simulation

Reason: the spec does not define how passive GSCI ownership is measured empirically.

---

## A2. Regime classification rule
Assume:
- low concentration = strictly < 30%
- high concentration = strictly > 30%
- exactly 30% belongs to medium and is excluded from the primary high-vs-low comparison

Reason: threshold wording says “above 30%” and “below 30%.”

---

## A3. Roll exclusion window interpretation
Assume “within 5 days” means:
- ±5 calendar days around FOMC/CPI announcement dates

Alternative could be trading days; not specified.

---

## A4. Bid-ask spread exclusion interpretation
Assume exclusion is applied at the observation level:
- remove daily observations where spread > 2% of contract price

Alternative is contract-level exclusion; not specified.

---

## A5. Contract price used in spread denominator
Assume contract price means:
- mid price = (bid + ask)/2

Alternative could be settlement or last trade.

---

## A6. Momentum lookback definition
Assume 12-month momentum uses:
- trailing 252 trading days cumulative return
- no skip month

Reason: 252-day windows are repeatedly referenced; skip-month convention is not specified.

---

## A7. Momentum portfolio weighting
Assume equal weighting across available energy assets:
- 50% crude oil
- 50% natural gas when both available

Alternative weighting by volatility, open interest, or GSCI weights is not specified.

---

## A8. Rebalancing frequency
Assume daily signal evaluation and daily portfolio return computation.

Alternative monthly rebalancing is common for momentum but not specified.

---

## A9. Sharpe annualization
Assume annualized Sharpe:
- mean daily return / std daily return × sqrt(252)

Risk-free rate assumed zero unless provided.

---

## A10. Rolling-window regime assignment
Assume each 252-day Sharpe window is labeled by:
- concentration regime on the window end date

Alternative is majority regime within window or pure-regime windows only.

---

## A11. Primary t-test unit
Assume the t-test is run on:
- rolling 252-day Sharpe observations grouped by regime

Alternative is daily returns with regime interaction.

---

## A12. GARCH control implementation
Assume “controlling for GARCH(1,1) volatility clustering” means:
- estimate conditional volatility from GARCH on momentum returns
- include conditional volatility as a control in regression of rolling Sharpe or returns on concentration regime

Alternative residualization methods are possible.

---

## A13. Factor model specification
Assume the factor model includes:
- market
- SMB
- HML
- momentum factor

Despite the text saying “three-factor OLS regression,” momentum exposure is explicitly required.

---

## A14. Fama-MacBeth usage
Assume Fama-MacBeth is applied across the two assets and/or rolling cross-sections over time, even though the cross-section is very small.

This is methodologically awkward but follows the spec wording.

---

## A15. Markov switching target series
Assume the Markov switching model is fit to:
- momentum strategy returns

Alternative targets are not specified.

---

## A16. DCC-GARCH asset set
Assume DCC-GARCH is estimated using:
- crude oil returns
- natural gas returns

Because these are the named GSCI energy assets.

---

## A17. Passive capital scenarios interpretation
Assume scenarios are simulated counterfactuals rather than purely empirical bins.

Reason: the spec includes simulation agents and RL training.

---

## A18. Meta-RL action space
Assume meta_rl allocates portfolio weights across the five non-meta strategies.

Reason: “learns optimal allocation across all strategies” implies allocation among strategy sleeves.

---

## A19. Episode definition
Assume one episode corresponds to one trading day.

Alternative could be one rolling window or one month.

---

## A20. Qualitative consistency across seeds
Assume “qualitatively consistent” means:
- same sign of effect
- same conclusion on economic significance
- same conclusion on statistical significance at the primary threshold

---

## A21. Six simultaneous tests
Assume the six tests correspond to six model variants/robustness checks rather than six assets or six horizons.

---

## A22. Non-energy data for macro allocator
Assume additional non-energy benchmark assets are required for the macro allocator, even though the main hypothesis concerns energy futures only.

---

## A23. Audit and governance items
Assume audit requirements and pre-analysis commitment are procedural gates, not part of the statistical methodology itself.

---

# 3. Every underspecified detail flagged

Below is a comprehensive list of underspecified or ambiguous details in the spec.

## Data and sample construction
1. **Exact contract identifiers** for crude oil and natural gas are not specified.
2. **How to identify “GSCI energy sector” membership** in the data is not specified.
3. **Whether both nearby and deferred contracts are included before rolling** is not specified.
4. **Which price field** to use for returns (settlement, close, last trade, mid) is not specified.
5. **How missing data are handled** is not specified.
6. **Whether holidays/non-trading days are aligned across assets** is not specified.

## Passive concentration measurement
7. **How passive GSCI investor concentration is observed or estimated** is not specified.
8. **Whether concentration is measured daily, weekly, or monthly** is not specified.
9. **Whether concentration is commodity-specific or portfolio-level** is not specified.
10. **How to treat exactly 30% concentration** is not specified.
11. **Whether low/medium/high scenarios are empirical bins or simulated interventions** is not specified.

## Roll and adjustment
12. **Exact roll trigger** is not specified.
13. **How many days before expiry to roll** is not specified.
14. **Whether roll dates are fixed or liquidity-based** is not specified.
15. **How ratio_backward is operationalized** is not fully specified.
16. **How excluded roll dates are replaced** is not specified.

## Exclusion rules
17. **Whether “within 5 days” means calendar days or trading days** is not specified.
18. **Whether macro-announcement exclusion removes the roll event only or surrounding observations too** is not specified.
19. **Whether bid-ask spread exclusion is observation-level or contract-level** is not specified.
20. **What “contract price” means in the spread ratio** is not specified.
21. **Whether the 100-day history rule applies before or after exclusions** is not specified.

## Momentum strategy
22. **Exact 12-month momentum formula** is not specified.
23. **Whether to skip the most recent month** is not specified.
24. **Signal frequency** is not specified.
25. **Rebalancing frequency** is not specified.
26. **Portfolio weighting across assets** is not specified.
27. **Whether positions are scaled by volatility** is not specified.
28. **How to handle ties/near-zero signals** is not specified.
29. **Whether transaction costs are included** is not specified.

## Sharpe ratio construction
30. **Whether excess returns or raw returns are used** is not specified.
31. **Risk-free rate source** is not specified.
32. **Annualization formula** is not explicitly specified.
33. **How rolling windows are assigned to concentration regimes** is not specified.
34. **Whether windows crossing regimes are allowed** is not specified.

## Statistical testing
35. **Exact tested variable for the t-test** is not specified.
36. **Whether the t-test compares means of rolling Sharpe windows or another statistic** is not specified.
37. **How Newey-West is applied to overlapping rolling windows** is not specified.
38. **What the six simultaneous tests are** is not specified.
39. **Whether Bonferroni applies to all reported tests or only a subset** is not specified.

## GARCH
40. **Which return series the GARCH model is fit to** is not specified.
41. **Whether GARCH is fit separately by asset or on portfolio returns** is not specified.
42. **How GARCH outputs enter the main hypothesis test** is not specified.
43. **Whether mean equation includes exogenous regressors** is not specified.

## Factor regression
44. **The factor set is inconsistent**: “three-factor” but also “momentum factor exposure.”
45. **Frequency of factor data** is not specified.
46. **How daily futures returns are matched to factor data** is not specified.
47. **Why Fama-MacBeth is used with such a small cross-section** is not specified.
48. **Whether the output of this regression is alpha, residuals, or adjusted returns** is not specified.

## Markov switching
49. **Dependent variable for regime detection** is not specified.
50. **Whether switching occurs in mean, variance, or both** is not specified.
51. **Whether exogenous regressors are included** is not specified.
52. **How regime outputs affect the main inference** is not specified.

## DCC-GARCH
53. **Exact DCC specification** is not specified.
54. **Software/library for DCC-GARCH** is not specified.
55. **Whether DCC is estimated on raw returns or residuals** is not specified.
56. **How DCC outputs are used in the main analysis** is not specified.

## Simulation agents
57. **Execution model** for all agents is not specified.
58. **Market impact model** is not specified.
59. **Order book assumptions** for liquidity_provider are not specified.
60. **Macro signals** for macro_allocator are not specified.
61. **Definition of “3-month extremes”** for mean_reversion is not specified.
62. **GSCI index weights source and rebalance schedule** are not specified.
63. **Whether agents interact in a simulated market or are independently backtested** is not specified.

## Meta-RL
64. **RL algorithm** is not specified.
65. **State representation** is not specified.
66. **Action space** is not specified.
67. **Reward function beyond fitness evaluation** is not specified.
68. **Episode length** is not specified.
69. **Exploration policy** is not specified.
70. **Transaction costs and constraints** are not specified.
71. **How 500,000 episodes are distributed across seeds/scenarios** is not specified.

## Seed policy
72. **Which components are stochastic and seed-dependent** is not specified.
73. **Definition of “qualitatively consistent”** is not specified.
74. **Tolerance for numerical variation across seeds** is not specified.

## Governance/audit
75. **How pre-analysis commitment is operationally checked** is not specified.
76. **How audit scores affect methodology changes** is not specified.
77. **How DataPassport signatures are generated** is not specified.

---

# 4. Reproducibility rating: 2/5

## Rating: 2 out of 5

## Rationale
The spec provides:
- a clear hypothesis
- sample period
- named assets
- some model classes
- significance thresholds
- exclusion rules
- seed policy
- passive capital scenarios

However, reproducibility is weak because many critical implementation details are missing or ambiguous, especially:

1. **Passive concentration measurement is not operationalized**
   - This is central to the hypothesis.
   - Without a precise construction, different implementations could produce very different results.

2. **Momentum strategy definition is incomplete**
   - No exact signal formula, skip-month rule, weighting, or rebalance frequency.

3. **Primary statistical test is not fully specified**
   - It is unclear what exact series is subjected to the HAC t-test.

4. **Factor model specification is internally inconsistent**
   - “Three-factor” plus momentum exposure conflicts with standard nomenclature.

5. **Simulation/RL section is highly underspecified**
   - Agent mechanics, environment, and RL algorithm are absent.

6. **The six simultaneous tests are not enumerated**
   - Bonferroni correction cannot be applied unambiguously.

7. **Roll implementation details are incomplete**
   - Ratio backward is named, but roll trigger timing is not.

Because the broad intent is reproducible but the exact implementation is not, the spec is **partially reproducible but not fully executable without substantial assumptions**, hence **2/5** rather than 1/5.

---

# 5. Recommended minimal executable interpretation

If forced to implement from this spec alone, the most defensible minimal version would be:

1. Build continuous crude oil and natural gas futures series from 2000–2024 using backward ratio adjustment.
2. Exclude contracts with <100 trading days.
3. Remove observations with spread >2% using mid-price denominator.
4. Exclude roll events within ±5 calendar days of FOMC/CPI announcements.
5. Define momentum as trailing 252-trading-day return, daily rebalanced, equal-weight long/short across the two assets.
6. Define concentration regimes using scenario labels:
   - low = 10%
   - medium = 30%
   - high = 60%
7. Compute rolling 252-day annualized Sharpe ratios.
8. Compare high vs low Sharpe windows using HAC(4) t-test.
9. Fit GARCH(1,1) on momentum returns and include conditional volatility as a control.
10. Fit factor regression with market, SMB, HML, and momentum factor.
11. Fit 2-state Markov switching on momentum returns.
12. Fit DCC-GARCH on crude oil and natural gas returns.
13. Run all stochastic components under seeds 1337, 42, and 9999.
14. Accept findings only if sign/significance/economic significance are consistent across all seeds.

---

If you want, I can next turn this into a **pseudo-code implementation blueprint** or a **methods section written as a reproducible protocol**.