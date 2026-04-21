Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 0. Scope of what is being reimplemented
Reimplement the research workflow to test:

> Whether passive GSCI index investor concentration above 30% of open interest in GSCI energy futures reduces 12-month momentum strategy Sharpe ratios by at least 0.15 relative to periods below 30%, controlling for GARCH(1,1) volatility clustering and Fama-French momentum factor exposure.

The implementation must cover:
- data construction
- exclusions
- rolling momentum strategy
- concentration regime assignment
- Sharpe differential estimation
- required statistical tests
- simulation agents and meta-RL training
- seed consistency checks
- reporting and validity criteria

---

# 1. Full implementation steps in order

## Step 1: Define the study universe
1. Select commodity futures from **WRDS Compustat Futures**.
2. Restrict to **GSCI energy sector** contracts.
3. Based on the spec, include at minimum:
   - crude oil
   - natural gas
4. Restrict sample period to **2000–2024**.

### Output
A raw panel of daily futures data for GSCI energy contracts over 2000–2024.

---

## Step 2: Gather required raw fields
For each contract/day, obtain at minimum:
1. date
2. contract identifier
3. underlying commodity
4. price fields needed to construct returns
5. open interest
6. bid-ask spread or bid and ask quotes
7. contract listing and expiration information
8. any fields needed to implement rolling under **ratio_backward**
9. any indicator needed to identify GSCI-related passive concentration, if directly available

### Output
A daily contract-level dataset sufficient for rolling, filtering, and return construction.

---

## Step 3: Build the macro-announcement calendar
1. Construct a calendar of **major macro announcements** containing:
   - FOMC dates
   - CPI release dates
2. For each date in the futures sample, mark whether it falls within **5 days of a major macro announcement**.

### Output
A daily event-calendar flag for exclusion processing.

---

## Step 4: Construct continuous futures series
1. For each eligible energy futures market, create a continuous contract series.
2. Use:
   - **Roll convention = ratio_backward**
   - **Adjustment method = ratio_backward**
3. Apply the roll procedure consistently across the full sample.

### Output
Continuous adjusted daily price series for crude oil and natural gas.

---

## Step 5: Apply exclusion rules
Apply all exclusions before strategy estimation.

### 5A. Minimum history exclusion
Exclude contracts with **fewer than 100 trading days of history**.

### 5B. Macro-announcement roll exclusion
Exclude **roll dates** that occur within **5 days of FOMC or CPI announcements**.

### 5C. Bid-ask spread exclusion
Exclude contracts where **bid-ask spread exceeds 2% of contract price**.

### Output
A filtered continuous futures dataset and a record of all excluded observations/contracts.

---

## Step 6: Measure passive GSCI investor concentration
1. Construct a daily measure of **passive GSCI index investor concentration as a percentage of open interest**.
2. Define concentration regimes using the spec’s scenarios:
   - Low = 10%
   - Medium = 30%
   - High = 60%
3. For the primary hypothesis test, classify periods as:
   - **Low-concentration periods**: below 30%
   - **High-concentration periods**: above 30%
4. Preserve the 30% threshold as the hypothesis cutoff.

### Output
A daily concentration series and regime labels.

---

## Step 7: Construct the 12-month momentum strategy
1. Define a **12-month momentum signal** for the energy futures universe.
2. Use the continuous adjusted futures returns.
3. Form a **long/short momentum strategy** based on the 12-month signal.
4. Compute daily strategy returns.

### Output
A daily return series for the 12-month momentum strategy.

---

## Step 8: Compute rolling annualized Sharpe ratios
1. Use **rolling 252-day windows**.
2. For each window, compute the annualized Sharpe ratio of the momentum strategy.
3. Align each rolling Sharpe estimate with the corresponding concentration regime.

### Output
A time series of rolling annualized Sharpe ratios with regime labels.

---

## Step 9: Compute the primary metric
1. Split rolling Sharpe observations into:
   - high-concentration periods (>30%)
   - low-concentration periods (<30%)
2. Compute:

\[
\Delta Sharpe = Sharpe_{high} - Sharpe_{low}
\]

3. Compare the estimated differential to the minimum effect size:
   - economically meaningful only if **ΔSharpe ≤ -0.15**

### Output
Primary effect estimate: high-minus-low Sharpe differential.

---

## Step 10: Estimate volatility control using GARCH(1,1)
1. Fit a **GARCH(1,1)** model to the momentum strategy return series.
2. Use:
   - p = 1
   - q = 1
   - Normal distribution
3. Extract conditional volatility estimates.
4. Use these estimates to control for volatility clustering in the analysis of Sharpe differences.

### Output
Conditional volatility series and volatility-adjusted analysis inputs.

---

## Step 11: Estimate factor exposure control
1. Obtain the required **Fama-French factors** and momentum factor exposure inputs.
2. Run **OLS regression** with the specified framework:
   - linearmodels
   - Fama-MacBeth
3. Include at minimum:
   - Fama-French three factors
   - momentum factor exposure, because the hypothesis explicitly says to control for it
4. Use regression residuals or adjusted returns as the factor-controlled series for robustness/controlled inference.

### Output
Factor exposure estimates and factor-adjusted return or residual series.

---

## Step 12: Perform the primary statistical test
1. Conduct a **two-tailed t-test** comparing high- vs low-concentration Sharpe outcomes.
2. Apply **Newey-West HAC correction with 4 lags**.
3. Use:
   - primary significance threshold: **p < 0.05**
   - simultaneous-test threshold: **p < 0.0083** after Bonferroni correction for 6 tests

### Output
Primary p-value, HAC-adjusted test statistic, and significance decision.

---

## Step 13: Run the remaining required simultaneous tests
The spec lists 6 simultaneous tests. Implement all listed methods as part of the simultaneous inference set:

1. Two-tailed t-test with Newey-West HAC (4 lags)
2. Bonferroni-adjusted significance evaluation
3. GARCH(1,1) volatility model
4. Fama-French three-factor OLS / Fama-MacBeth
5. Markov switching regime detection with:
   - k_regimes = 2
6. DCC-GARCH cross-asset correlation

For each test, evaluate whether the high-concentration regime is associated with weaker momentum profitability.

### Output
A six-test results table with raw and Bonferroni-adjusted significance interpretation.

---

## Step 14: Run Markov switching regime detection
1. Fit a **2-regime Markov switching model** to the relevant return or Sharpe process.
2. Infer latent regimes.
3. Compare inferred regimes with concentration regimes.
4. Assess whether high passive concentration aligns with the lower-momentum-profitability regime.

### Output
Regime probabilities, inferred states, and regime alignment analysis.

---

## Step 15: Run DCC-GARCH cross-asset correlation analysis
1. Use the energy assets in the sample (at minimum crude oil and natural gas).
2. Estimate time-varying cross-asset correlations using **DCC-GARCH**.
3. Examine whether high passive concentration periods coincide with elevated cross-asset correlation and reduced momentum diversification/profitability.

### Output
Dynamic correlation estimates and concentration-regime comparison.

---

## Step 16: Implement simulation agents
Implement the six agents exactly as listed:

1. **passive_gsci**
   - mechanically rebalances to GSCI index weights

2. **trend_follower**
   - uses 12-month momentum signal
   - long/short

3. **mean_reversion**
   - fades 3-month extremes

4. **liquidity_provider**
   - posts limit orders on both sides

5. **macro_allocator**
   - switches energy/non-energy on macro signals

6. **meta_rl**
   - learns optimal allocation across all strategies

### Output
A simulation environment with six agent classes/behaviors.

---

## Step 17: Define passive capital scenarios in simulation
Run all simulations under:
- Low passive capital = 10% of open interest
- Medium passive capital = 30% of open interest
- High passive capital = 60% of open interest

### Output
Scenario-specific simulation configurations.

---

## Step 18: Train the meta-RL allocator
1. Train the **meta_rl** agent across all strategies.
2. Use the fitness function:
   - Sharpe ratio over trailing 252 episodes
   - evaluated every 1000 training steps
3. Ensure at least **500,000 training episodes across all scenarios and seeds**.

### Output
Trained meta-RL policies and evaluation logs.

---

## Step 19: Apply seed policy
Repeat all stochastic components using:
- 1337
- 42
- 9999

A finding is valid only if results are **qualitatively consistent across all three seeds**.

### Output
Per-seed result sets and consistency assessment.

---

## Step 20: Define validity decision rule
A finding is valid only if all of the following hold:
1. High-concentration periods are associated with lower momentum Sharpe than low-concentration periods.
2. The differential is at least **-0.15 Sharpe units** in magnitude.
3. Statistical significance passes:
   - p < 0.05 primary
   - and, where applicable, p < 0.0083 under Bonferroni correction
4. Results are qualitatively consistent across all three seeds.

### Output
Final accept/reject conclusion for the hypothesis.

---

## Step 21: Produce audit and governance artifacts
The spec requires:
1. Pre-analysis plan status must be **COMMITTED** before execution.
2. CODEC bidirectional audit before paper writing.
3. HAWK methodology score at least **7/10**.
4. Maximum HAWK revision cycles = 3.
5. DataPassport SHA-256 signature on all MINER outputs.

### Output
A compliance checklist and signed outputs.

---

# 2. Assumptions needed due to underspecification

These assumptions are necessary because the spec does not fully define implementation details.

## A. Asset universe assumption
Assume the GSCI energy sector sample contains only:
- crude oil
- natural gas

Reason: these are the only assets explicitly named.

## B. Return frequency assumption
Assume all analysis is conducted on **daily returns**.

Reason: rolling 252-day Sharpe windows imply daily frequency.

## C. Momentum signal construction assumption
Assume 12-month momentum is computed as trailing **252-trading-day cumulative return**, possibly excluding no skip month.

Reason: “12-month momentum signal” is specified, but exact formula is not.

## D. Cross-sectional portfolio assumption
Assume the long/short momentum strategy ranks the available energy contracts and goes long winners, short losers, with equal weights.

Reason: “long/short” is specified, but portfolio formation is not.

## E. Concentration measurement assumption
Assume passive GSCI concentration is measured daily as:

\[
\text{Passive GSCI holdings} / \text{total open interest}
\]

Reason: “concentration above 30% of open interest” is specified, but exact numerator source is not.

## F. Regime classification assumption
Assume:
- low-concentration = strictly below 30%
- high-concentration = strictly above 30%
- exactly 30% is either excluded or assigned to medium

Reason: threshold handling is not specified.

## G. Sharpe annualization assumption
Assume annualized Sharpe is:

\[
\sqrt{252} \times \frac{\text{mean daily return}}{\text{std daily return}}
\]

Reason: annualization formula is not explicitly stated.

## H. GARCH control assumption
Assume GARCH is fit to daily momentum strategy returns and conditional volatility is included as a control variable or used for volatility-standardized returns.

Reason: “controlling for GARCH(1,1)” is specified, but operationalization is not.

## I. Factor model assumption
Assume factor control uses daily factor returns aligned to the futures return frequency.

Reason: factor frequency and exact mapping are not specified.

## J. Fama-French applicability assumption
Assume the requested Fama-French framework is used as a generic factor-control device despite commodity futures not being standard equity assets.

Reason: the spec explicitly requires it, even though asset-class fit is unclear.

## K. Newey-West implementation assumption
Assume HAC correction is applied to the mean-difference regression or equivalent t-test framework with lag length 4.

Reason: a plain t-test does not itself define HAC mechanics.

## L. Markov switching target assumption
Assume the Markov switching model is fit to momentum returns or rolling Sharpe series.

Reason: target variable is not specified.

## M. DCC-GARCH input assumption
Assume DCC-GARCH is estimated on daily returns of crude oil and natural gas continuous series.

Reason: exact assets and return inputs are not specified.

## N. Mean reversion signal assumption
Assume “fades 3-month extremes” means taking the opposite side of trailing 63-trading-day extreme performers.

Reason: exact signal definition is absent.

## O. Liquidity provider assumption
Assume the liquidity provider earns spread capture subject to inventory risk and posts symmetric limit orders around midprice.

Reason: no market microstructure rules are given.

## P. Macro allocator assumption
Assume macro signals are derived from the same FOMC/CPI calendar or related macro indicators and determine energy vs non-energy allocation.

Reason: “macro signals” are not defined.

## Q. Meta-RL algorithm assumption
Assume any standard RL allocator may be used, provided it learns allocations across the listed strategies and is evaluated by trailing 252-episode Sharpe every 1000 steps.

Reason: no RL algorithm, state space, action space, or reward details are given.

## R. Episode definition assumption
Assume one episode corresponds to one trading day or one fixed simulation interval.

Reason: “episode” is not defined.

## S. Qualitative consistency assumption
Assume “qualitatively consistent” means same directional conclusion and same significance/economic-significance classification across all seeds.

Reason: consistency criterion is not formally defined.

## T. Simultaneous tests assumption
Assume the six listed statistical procedures correspond to the “6 simultaneous tests” referenced by Bonferroni correction.

Reason: the mapping is implied but not explicitly stated.

---

# 3. Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data and universe
1. **Exact contract list** within “GSCI energy sector” is not fully specified.
2. **Whether only crude oil and natural gas** are included, or additional energy contracts too, is unclear.
3. **Exact WRDS fields** required are not specified.
4. **How passive GSCI investor holdings are observed or inferred** is not specified.

## Continuous futures construction
5. **Exact roll trigger** for ratio_backward is not specified.
6. **Whether rolling occurs on volume switch, open-interest switch, fixed calendar, or last-trade rule** is not specified.
7. **How excluded roll dates are handled** if they fall near macro announcements is not specified.
8. **Whether the roll is postponed, advanced, or omitted** is not specified.

## Exclusions
9. **“Fewer than 100 trading days of history”** is ambiguous:
   - per contract
   - per continuous series
   - before first eligibility date
10. **Bid-ask spread exceeds 2% of contract price** is ambiguous:
   - using close price?
   - midprice?
   - settlement?
11. **Whether spread exclusion is daily, contract-wide, or permanent** is not specified.
12. **“Within 5 days”** of macro announcements is ambiguous:
   - calendar days or trading days
   - inclusive or exclusive bounds

## Momentum strategy
13. **Exact 12-month momentum formula** is not specified.
14. **Whether to skip the most recent month** is not specified.
15. **Portfolio formation method** is not specified.
16. **Weighting scheme** is not specified.
17. **Rebalancing frequency** is not specified.
18. **Whether momentum is cross-sectional or time-series** is not specified.
19. **How many contracts are long and short** is not specified.
20. **How to handle only two assets** for long/short ranking is not specified.

## Sharpe ratio
21. **Exact annualization formula** is not specified.
22. **Risk-free rate treatment** is not specified.
23. **Whether Sharpe is computed from raw or excess returns** is not specified.
24. **How rolling windows are aligned to regimes** is not specified.
25. **Whether windows spanning both low and high concentration periods are allowed** is not specified.

## Concentration regimes
26. **How concentration is measured daily** is not specified.
27. **Whether concentration is asset-specific or aggregate across energy futures** is not specified.
28. **How to classify exactly 30% concentration** is not specified.
29. **How low scenario 10% and high scenario 60% relate to empirical regime classification** is not fully specified.

## Statistical testing
30. **What exactly is being t-tested** is not specified:
   - rolling Sharpe values
   - mean returns
   - regression coefficients
31. **How Newey-West is applied to Sharpe differences** is not specified.
32. **What the 6 simultaneous tests are exactly** is implied but not formally enumerated as hypothesis families.
33. **Whether Bonferroni applies to all listed methods or only selected outcome tests** is not specified.
34. **How economic significance and statistical significance are jointly adjudicated** is only partially specified.

## GARCH
35. **Which series receives GARCH(1,1)** is not specified.
36. **How GARCH output enters the main hypothesis test** is not specified.
37. **Whether GARCH is estimated separately by regime** is not specified.

## Factor model
38. **Which Fama-French dataset/version** is not specified.
39. **How equity factors are mapped to commodity futures returns** is not specified.
40. **How momentum factor exposure is included** is not specified.
41. **Why “three-factor” is named while momentum exposure is also required** is internally ambiguous.
42. **How Fama-MacBeth is applied with this asset universe** is not specified.

## Markov switching
43. **Target variable for regime detection** is not specified.
44. **Whether switching variance, mean, or both are modeled** is not specified.
45. **How Markov regimes are compared to concentration regimes** is not specified.

## DCC-GARCH
46. **Exact asset set** for cross-asset correlation is not specified.
47. **Whether DCC-GARCH is estimated on returns, residuals, or standardized residuals** is not specified.
48. **How DCC-GARCH results feed into the main inference** is not specified.

## Simulation agents
49. **Simulation environment mechanics** are not specified.
50. **Market clearing mechanism** is not specified.
51. **Price impact model** is not specified.
52. **Transaction costs/slippage** are not specified.
53. **Inventory constraints** are not specified.
54. **Leverage constraints** are not specified.
55. **Position limits** are not specified.
56. **Observation/state spaces** are not specified.
57. **Action spaces** are not specified.
58. **Reward functions** for non-meta agents are not specified.
59. **How passive_gsci rebalances to GSCI weights** is not specified.
60. **What “mechanically” means operationally** is not specified.
61. **How mean_reversion defines “extremes”** is not specified.
62. **How liquidity_provider posts quotes** is not specified.
63. **What macro signals drive macro_allocator** is not specified.
64. **What non-energy assets are available to macro_allocator** is not specified.
65. **How meta_rl allocates across strategies** is not specified.

## RL training
66. **RL algorithm** is not specified.
67. **Episode definition** is not specified.
68. **Training/evaluation split** is not specified.
69. **How 500,000 episodes are distributed across scenarios and seeds** is not specified.
70. **Whether each seed gets 500,000 episodes or total across all seeds/scenarios** is ambiguous.
71. **How trailing 252-episode Sharpe is computed during training** is not specified.
72. **Whether evaluation every 1000 steps affects learning** is not specified.

## Seed policy
73. **Which components are stochastic and must be reseeded** is not specified.
74. **Definition of “qualitatively consistent”** is not specified.
75. **Tolerance for numerical variation across seeds** is not specified.

## Governance/audit
76. **How COMMITTED status is verified** is not specified.
77. **What constitutes CODEC bidirectional audit** is not specified.
78. **How HAWK methodology score is computed** is not specified.
79. **What MINER outputs are** is not specified.
80. **How DataPassport SHA-256 signatures are generated and attached** is not specified.

---

# 4. Reproducibility rating: 2 / 5

## Rating: 2 out of 5

### Rationale
The spec is strong on:
- hypothesis statement
- primary metric
- significance thresholds
- sample period
- some model families
- exclusion categories
- seed policy
- scenario levels

However, reproducibility is limited because many implementation-critical details are missing:

1. **Core variable construction is underspecified**
   - passive GSCI concentration measurement is not operationally defined
   - momentum signal construction is incomplete
   - Sharpe computation details are incomplete

2. **Continuous futures methodology is incomplete**
   - ratio_backward is named, but roll trigger logic is absent

3. **Statistical control implementation is unclear**
   - how GARCH and factor controls enter the main test is not specified

4. **Simulation design is highly underspecified**
   - agent mechanics, environment, rewards, and RL algorithm are mostly absent

5. **Several requirements are internally ambiguous**
   - “Fama-French three-factor” plus “momentum factor exposure”
   - “linearmodels, Fama-MacBeth” paired with OLS
   - six simultaneous tests are implied but not formally structured

### Why not 1/5?
Because the spec still provides enough structure to build a plausible implementation:
- clear hypothesis
- clear threshold values
- named methods
- sample source and period
- explicit exclusion categories
- explicit seeds and validity rule

### Why not 3/5 or higher?
Because independent teams could make materially different choices on:
- concentration measurement
- momentum portfolio formation
- roll timing
- factor controls
- simulation architecture

Those choices could substantially change results.

---

# 5. Practical implementation recommendation

To reimplement from this spec alone, I would proceed in two layers:

## Layer 1: Deterministic empirical study
Implement first:
1. data extraction
2. continuous futures construction
3. exclusions
4. concentration regime labeling
5. 12-month momentum returns
6. rolling Sharpe
7. HAC t-test
8. GARCH control
9. factor-control regression
10. Markov switching
11. DCC-GARCH

This is the most directly inferable part of the spec.

## Layer 2: Simulation and meta-RL extension
Implement second:
1. simplified market simulator
2. six agents
3. passive capital scenarios
4. meta-RL allocator
5. seed consistency checks

This part requires the most assumptions and should be explicitly documented as assumption-heavy.

---

If you want, I can next convert this into a **formal pseudocode protocol** or a **step-by-step implementation blueprint with equations for each module**.