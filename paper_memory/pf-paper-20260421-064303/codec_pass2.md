Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 0. Scope of what can be implemented from the spec
The specification mixes:
- an **empirical asset-pricing study** on commodity futures,
- several **time-series/statistical tests**,
- and an **agent-based / RL simulation layer**.

A faithful reimplementation from the spec alone is possible only with explicit assumptions, because many operational details are underspecified.

---

# 1. Full implementation steps in order

## Step 1: Formalize the research question
Implement the primary hypothesis exactly as stated:

> Passive GSCI index investor concentration above 30% of open interest in GSCI energy futures reduces 12-month momentum strategy Sharpe ratios by at least 0.15 units relative to periods below 30%, controlling for GARCH(1,1) volatility clustering and Fama-French momentum factor exposure.

Operational target:
- Compute annualized rolling 252-trading-day Sharpe ratios for a 12-month momentum strategy in GSCI energy futures.
- Partition observations into:
  - **low concentration**: below 30%
  - **high concentration**: above 30%
- Estimate the Sharpe differential:
  - **high minus low**
- Test whether the differential is statistically significant and economically meaningful:
  - statistical significance via specified tests
  - economic significance threshold = **-0.15 Sharpe units**

---

## Step 2: Define the study universe
Use:
- WRDS Compustat Futures
- GSCI energy sector
- instruments explicitly named:
  - crude oil
  - natural gas
- sample period:
  - 2000–2024

Implementation tasks:
1. Pull all futures contracts for crude oil and natural gas over 2000–2024.
2. Identify which contracts belong to the GSCI energy sector universe.
3. Obtain:
   - daily prices
   - open interest
   - bid-ask spread or fields needed to compute it
   - contract metadata
   - roll-relevant fields
4. Obtain or construct passive GSCI investor concentration as a share of open interest.

---

## Step 3: Acquire auxiliary datasets
You need additional data not fully described in the spec:

1. **Major macro announcement calendar**
   - FOMC dates
   - CPI release dates
   - for 2000–2024

2. **Fama-French factors**
   - The spec says “Fama-French three-factor OLS regression” and also “momentum factor exposure.”
   - Therefore obtain:
     - market, SMB, HML
     - momentum factor if used as control
   - Align frequency to daily if daily strategy returns are used.

3. **Any data needed for DCC-GARCH**
   - likely daily return series for crude oil and natural gas momentum legs or underlying futures returns.

4. **Any data needed for passive concentration**
   - If not directly available in WRDS Compustat Futures, define a proxy or merge an external source.

---

## Step 4: Commit the pre-analysis plan gate
The spec says:

> Pre-Analysis Plan Status UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs. FORGE gate will reject any run where this status is not COMMITTED in pap_lock.

Methodology reimplementation implication:
1. Create a run-level metadata object recording pre-analysis status.
2. Set status to **COMMITTED** before any estimation or simulation.
3. Refuse execution if status is not committed.

Even though this is workflow governance rather than econometrics, it is explicitly required by the spec.

---

## Step 5: Clean and filter the futures data
Apply exclusion rules in order:

1. **Exclude contracts with fewer than 100 trading days of history**
   - For each contract, count valid trading days.
   - Remove contracts with <100 days.

2. **Exclude roll dates within 5 days of major macro announcements (FOMC, CPI)**
   - Identify all roll dates under the chosen roll convention.
   - Remove roll events occurring within ±5 calendar days or ±5 trading days of FOMC/CPI dates.
   - This choice is underspecified; assumption required.

3. **Exclude contracts where bid-ask spread exceeds 2% of contract price**
   - Compute spread / price.
   - Remove observations or contracts depending on interpretation.
   - This is underspecified; assumption required.

---

## Step 6: Construct continuous futures series
The spec gives:
- Roll convention: **ratio_backward**
- Adjustment method: **ratio_backward**

Implementation:
1. For each commodity, sort contracts by expiry.
2. Define roll dates according to a chosen rule.
3. Build a continuous adjusted price series using backward ratio adjustment:
   - At each roll, multiply prior history by the ratio needed to preserve continuity.
4. Produce:
   - adjusted daily close series
   - daily returns from adjusted prices

Because roll timing is not specified, this requires assumptions.

---

## Step 7: Define passive investor concentration
Construct the key explanatory variable:
- passive GSCI concentration = passive GSCI investor holdings / total open interest

Then classify periods:
- **Low**: 10% scenario and/or below 30%
- **Medium**: 30%
- **High**: 60% scenario and/or above 30%

For the primary empirical test:
- low-concentration periods = concentration < 30%
- high-concentration periods = concentration > 30%

Implementation tasks:
1. Build daily concentration series for each commodity or aggregate energy sector.
2. Decide whether concentration is:
   - commodity-specific,
   - contract-specific,
   - or sector-aggregated.
3. Label each day/window by concentration regime.

---

## Step 8: Construct the 12-month momentum strategy
The spec says:
- “12-month momentum signal, long/short”

Implementation:
1. Use daily adjusted futures returns.
2. Compute a 12-month lookback signal.
   - Most natural interpretation: trailing 252 trading-day cumulative return.
3. Generate long/short positions:
   - long if signal positive
   - short if signal negative
4. Rebalance frequency must be chosen; likely daily or monthly.
5. Compute daily strategy returns.

Because only two commodities are named, the cross-sectional momentum design is unclear. A time-series momentum implementation is the most defensible assumption unless otherwise specified.

---

## Step 9: Compute rolling Sharpe ratios
Primary metric:
- annualized Sharpe ratio differential
- over rolling 252-day windows

Implementation:
1. For each day \( t \ge 252 \), compute momentum strategy returns over the trailing 252 trading days.
2. Compute rolling Sharpe:
   - mean daily return / std daily return
   - annualize using \( \sqrt{252} \)
3. Associate each rolling window with concentration regime.
   - Need a rule for window labeling:
     - end-of-window concentration,
     - average concentration over window,
     - or majority regime.
   - This is underspecified.

---

## Step 10: Estimate the primary effect
Compute:
- mean rolling Sharpe during high concentration periods
- mean rolling Sharpe during low concentration periods
- differential = high minus low

Decision rule:
- statistically significant under required tests
- economically significant if differential ≤ -0.15

---

## Step 11: Run the primary t-test with Newey-West HAC
Specified test:
- two-tailed t-test
- p < 0.05
- Newey-West HAC correction with 4 lags

Implementation:
1. Form the time series of rolling Sharpe observations or window-level differential observations.
2. Estimate the mean difference between high and low concentration periods.
3. Use HAC standard errors with lag 4.
4. Report:
   - estimate
   - t-statistic
   - p-value
   - confidence interval

Because rolling windows overlap, HAC correction is appropriate.

---

## Step 12: Apply Bonferroni correction
The spec says:
- 6 simultaneous tests
- adjusted threshold p < 0.0083

Implementation:
1. Identify the six tests being jointly corrected.
2. For each, compute raw p-value.
3. Compare against:
   - primary threshold 0.05
   - Bonferroni threshold 0.0083

This is underspecified because the six tests are not enumerated.

---

## Step 13: Fit GARCH(1,1) to control for volatility clustering
Specified:
- arch library
- p=1, q=1
- Normal distribution

Implementation:
1. Fit GARCH(1,1) to relevant return series:
   - likely momentum strategy returns
   - possibly underlying commodity returns as robustness
2. Extract conditional volatility estimates.
3. Use these as controls in the main regression or regime-adjusted comparison.

Because “controlling for GARCH(1,1) volatility clustering” is stated but not operationalized, you must choose a control framework:
- include conditional volatility as a regressor in Sharpe/return regressions, or
- standardize returns by conditional volatility before Sharpe computation.

This is underspecified.

---

## Step 14: Fit factor exposure model
Specified:
- “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)”
- hypothesis also mentions “momentum factor exposure”

Implementation:
1. Align strategy returns with factor returns.
2. Estimate factor exposure model.
3. Because Fama-MacBeth is usually cross-sectional and this setting is thin cross-section, define a practical implementation:
   - either pooled panel across assets/windows,
   - or time-series OLS with factor controls.
4. Include:
   - MKT
   - SMB
   - HML
   - momentum factor if controlling for momentum exposure as stated in hypothesis
5. Use residualized returns or factor-adjusted alpha in the concentration comparison.

This section is internally inconsistent and underspecified.

---

## Step 15: Estimate Markov switching regimes
Specified:
- statsmodels
- k_regimes = 2

Implementation:
1. Fit a 2-regime Markov switching model to:
   - momentum strategy returns,
   - or Sharpe series,
   - or concentration-return relationship.
2. Infer latent regimes.
3. Check whether the concentration effect differs by regime.
4. Report transition probabilities and regime-specific means/variances.

The target variable for regime switching is not specified.

---

## Step 16: Estimate DCC-GARCH cross-asset correlation
Specified:
- DCC-GARCH cross-asset correlation

Implementation:
1. Use daily returns for crude oil and natural gas.
2. Fit univariate GARCH models first.
3. Fit DCC process to estimate time-varying correlation.
4. Use estimated dynamic correlations as:
   - descriptive diagnostics,
   - or controls/robustness checks for momentum profitability under concentration regimes.

The exact role of DCC-GARCH in the hypothesis test is not specified.

---

## Step 17: Implement passive capital scenarios
Specified scenarios:
- Low: 10% of open interest
- Medium: 30%
- High: 60%

Implementation:
1. Create scenario labels or simulated overlays for passive participation.
2. For empirical analysis:
   - map observed concentration into these bins if possible.
3. For simulation:
   - force passive_gsci agent inventory to target these shares of open interest.

Need to distinguish:
- observed historical concentration
- simulated concentration scenarios

This relationship is underspecified.

---

## Step 18: Implement simulation agents
Create six agents:

1. **passive_gsci**
   - mechanically rebalances to GSCI index weights

2. **trend_follower**
   - 12-month momentum long/short

3. **mean_reversion**
   - fades 3-month extremes

4. **liquidity_provider**
   - posts limit orders on both sides

5. **macro_allocator**
   - switches energy/non-energy on macro signals

6. **meta_rl**
   - learns allocation across all strategies

Implementation tasks:
1. Define state variables.
2. Define action spaces.
3. Define reward functions.
4. Define market interaction rules.
5. Define inventory and execution constraints.
6. Define how open interest and concentration evolve under agent actions.

Almost all of this is underspecified.

---

## Step 19: Train the meta-RL allocator
Specified:
- fitness = Sharpe ratio over trailing 252 episodes
- evaluated every 1000 training steps
- minimum 500,000 episodes across all scenarios and seeds

Implementation:
1. Choose RL algorithm.
2. Train across:
   - low, medium, high passive capital scenarios
   - seeds [1337, 42, 9999]
3. Every 1000 steps:
   - compute trailing 252-episode Sharpe
4. Continue until total episodes across all scenarios and seeds ≥ 500,000
5. Save evaluation summaries for each seed.

The RL algorithm, environment, and episode definition are not specified.

---

## Step 20: Enforce seed policy
Specified:
- seeds = [1337, 42, 9999]
- all three seeds must produce qualitatively consistent results
- finding valid only if it holds across all three seeds

Implementation:
1. Set all random number generators to each seed in turn.
2. Repeat all stochastic components:
   - simulation
   - RL training
   - any randomized estimation if applicable
3. Define “qualitatively consistent” before running:
   - same sign of effect
   - same significance classification
   - same economic significance classification
4. Accept finding only if all seeds agree.

“Qualitatively consistent” is underspecified and must be assumed.

---

## Step 21: Integrate empirical and simulation outputs
Because the spec includes both historical data analysis and simulation:
1. Run empirical tests on historical futures data.
2. Run agent-based/RL simulations under passive capital scenarios.
3. Compare whether simulated momentum degradation under high passive concentration aligns with empirical findings.

The exact integration rule is not specified.

---

## Step 22: Produce final inference
A finding should be declared valid only if all of the following hold:

1. Pre-analysis plan status committed.
2. Primary differential is negative.
3. Differential magnitude is at least -0.15 Sharpe units.
4. Statistical significance passes:
   - p < 0.05 primary
   - and, where applicable, p < 0.0083 Bonferroni-adjusted
5. Result is robust to:
   - GARCH control
   - factor control
   - regime analysis
   - cross-asset correlation diagnostics
6. All three seeds produce qualitatively consistent results.

---

## Step 23: Audit and provenance requirements
The spec requires:
- CODEC bidirectional audit before paper writing
- HAWK minimum score 7/10 on methodology rubric
- max 3 HAWK revision cycles
- DataPassport SHA-256 signature on all MINER outputs

Methodology implementation:
1. Hash all generated outputs with SHA-256.
2. Attach signatures to all extracted/transformed datasets and model outputs.
3. Run methodology audit scoring.
4. Limit revision loop to 3 cycles.
5. Require audit completion before final reporting.

These are process requirements, not scientific methodology, but they are explicitly required.

---

# 2. Assumptions needed due to underspecification

Below are the assumptions I would need to make to implement the methodology.

## A. Momentum strategy definition
**Assumption:** Use **time-series momentum** on each commodity based on trailing 252-trading-day cumulative return, with daily rebalancing and sign-based long/short positions.

Reason:
- Only two commodities are listed, making cross-sectional momentum weakly defined.
- “12-month momentum signal, long/short” most naturally maps to time-series momentum.

---

## B. Return frequency
**Assumption:** Use **daily returns** throughout.

Reason:
- Rolling 252-day Sharpe windows imply daily data.
- GARCH and DCC-GARCH are commonly estimated on daily returns.

---

## C. Roll date rule
**Assumption:** Roll from front-month to next eligible contract on a fixed pre-expiry schedule, such as 5 trading days before first notice date or expiry, subject to exclusion rules.

Reason:
- “ratio_backward” specifies adjustment style, not roll timing.

---

## D. Macro-announcement exclusion window
**Assumption:** “Within 5 days” means **±5 trading days** around FOMC and CPI release dates.

Reason:
- Trading-day alignment is more natural for futures return analysis.

---

## E. Bid-ask spread exclusion interpretation
**Assumption:** Exclude **daily observations** where spread > 2% of contract price, and exclude a contract entirely only if too few valid observations remain.

Reason:
- Excluding entire contracts for occasional spread spikes would be extreme.

---

## F. Passive concentration measurement
**Assumption:** Passive GSCI concentration is measured **daily at the commodity level** as estimated passive GSCI-linked open interest divided by total open interest.

Reason:
- The hypothesis is framed in terms of open interest concentration in GSCI energy futures.

---

## G. Concentration regime labeling for rolling windows
**Assumption:** Label each 252-day Sharpe window by the **average concentration over the same window**.

Reason:
- This aligns the explanatory regime with the performance measurement horizon.

---

## H. Low/high concentration definitions
**Assumption:** For the primary test:
- low = concentration < 30%
- high = concentration > 30%
- observations exactly at 30% are assigned to medium and excluded from binary comparison

Reason:
- The hypothesis uses “above 30%” and “below 30%.”

---

## I. GARCH control implementation
**Assumption:** Fit GARCH(1,1) to daily momentum strategy returns and include estimated conditional volatility as a control in regressions explaining rolling Sharpe or daily returns.

Reason:
- The spec says to control for volatility clustering but does not specify how.

---

## J. Factor model implementation
**Assumption:** Use daily factor returns and estimate a **time-series OLS** factor model with MKT, SMB, HML, and momentum factor, despite the mention of Fama-MacBeth.

Reason:
- Fama-MacBeth is not naturally suited to a two-asset daily strategy setting.

---

## K. Six simultaneous tests
**Assumption:** The six tests are:
1. primary t-test
2. GARCH-controlled test
3. factor-controlled test
4. Markov regime subsample test
5. DCC-informed robustness test
6. simulation scenario comparison

Reason:
- The spec states six simultaneous tests but does not enumerate them.

---

## L. Markov switching target
**Assumption:** Fit the 2-regime Markov switching model to daily momentum strategy returns.

Reason:
- This is the most standard target.

---

## M. DCC-GARCH target series
**Assumption:** Fit DCC-GARCH to daily crude oil and natural gas returns.

Reason:
- “cross-asset correlation” most naturally refers to the two energy assets.

---

## N. Simulation environment
**Assumption:** Use an abstract market simulator where agents trade the two energy futures and passive concentration affects liquidity, impact, and return dynamics.

Reason:
- No environment mechanics are specified.

---

## O. Meta-RL algorithm
**Assumption:** Use a standard continuous-control or policy-gradient RL method to allocate weights across the five non-meta strategies.

Reason:
- The algorithm is unspecified.

---

## P. Episode definition
**Assumption:** One episode corresponds to one trading day or one fixed-length trading block; trailing 252 episodes are treated as approximately one trading year.

Reason:
- “252 episodes” is specified but episode length is not.

---

## Q. Qualitative consistency across seeds
**Assumption:** Results are qualitatively consistent if all seeds produce:
- the same sign of Sharpe differential,
- the same economic significance classification relative to -0.15,
- and the same significance/pass-fail conclusion at the primary threshold.

Reason:
- The phrase is otherwise undefined.

---

## R. Risk-free rate in Sharpe ratio
**Assumption:** Use zero risk-free rate or omit risk-free adjustment for daily futures excess returns.

Reason:
- No risk-free series is specified.

---

# 3. Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data and universe
1. **Exact contract identifiers** for crude oil and natural gas are not specified.
2. **How to identify “GSCI energy sector” membership** in the dataset is not specified.
3. **Whether passive concentration is directly observed or must be proxied** is not specified.
4. **Whether concentration is measured at contract, commodity, or sector level** is not specified.
5. **Whether open interest should be raw, adjusted, or aggregated across maturities** is not specified.

## Continuous futures construction
6. **Roll timing rule** is not specified.
7. **Eligible next contract selection rule** is not specified.
8. **How exclusion of roll dates near macro announcements interacts with continuity construction** is not specified.
9. **Whether ratio_backward applies to settlement, close, or another price field** is not specified.

## Exclusion rules
10. **Whether “fewer than 100 trading days of history” refers to contract-level history or continuous-series history** is not specified.
11. **Whether spread >2% excludes observations or entire contracts** is not specified.
12. **How bid-ask spread is computed if only quotes or settlement data are available** is not specified.
13. **Whether “within 5 days” means calendar days or trading days** is not specified.
14. **Whether the macro exclusion is symmetric before/after announcement dates** is not specified.

## Momentum strategy
15. **Whether momentum is time-series or cross-sectional** is not specified.
16. **Exact 12-month signal formula** is not specified.
17. **Whether to skip the most recent month** is not specified.
18. **Rebalancing frequency** is not specified.
19. **Position sizing rule** is not specified.
20. **Whether returns are equal-weighted or volatility-scaled across assets** is not specified.
21. **How to handle only two assets in a long/short framework** is not specified.
22. **Transaction costs and slippage treatment** are not specified.

## Sharpe ratio metric
23. **Whether Sharpe uses excess returns over risk-free rate** is not specified.
24. **How windows are assigned to concentration regimes** is not specified.
25. **Whether overlapping windows are the intended unit of inference** is not explicitly stated.
26. **Whether annualization uses sqrt(252)** is implied but not explicitly stated.

## Hypothesis testing
27. **What exact sample enters the t-test** is not specified.
28. **Whether the t-test compares means of rolling Sharpe windows or another statistic** is not specified.
29. **The six simultaneous tests for Bonferroni correction are not enumerated.**
30. **Whether Bonferroni applies to all analyses or only a predefined family** is not specified.

## GARCH control
31. **Which series receives the GARCH(1,1) model** is not specified.
32. **How GARCH output is used as a control** is not specified.
33. **Whether GARCH is fit separately by asset, by strategy, or pooled** is not specified.

## Factor model
34. **The spec says Fama-French three-factor but hypothesis mentions momentum factor exposure; this is internally inconsistent.**
35. **Whether momentum factor is included in addition to the three factors** is not specified.
36. **Frequency of factor data** is not specified.
37. **How Fama-MacBeth is applied in a two-asset futures setting** is not specified.
38. **Whether the target is raw returns, alpha, or residualized Sharpe** is not specified.

## Markov switching
39. **Target variable for the Markov switching model** is not specified.
40. **Whether switching affects mean only or mean and variance** is not specified.
41. **How regime results feed into the main hypothesis test** is not specified.

## DCC-GARCH
42. **Which return series are used in DCC-GARCH** is not specified.
43. **Whether DCC-GARCH is descriptive or inferential** is not specified.
44. **How DCC outputs affect the primary conclusion** is not specified.

## Passive capital scenarios
45. **Whether 10/30/60% are empirical bins, simulation settings, or both** is not specified.
46. **How observed historical concentration maps to these scenarios** is not specified.
47. **Whether medium scenario is included in the primary test** is not specified.

## Simulation agents
48. **Agent state spaces** are not specified.
49. **Agent action spaces** are not specified.
50. **Reward functions** are not specified.
51. **Execution model** is not specified.
52. **Market-clearing mechanism** is not specified.
53. **Price impact model** is not specified.
54. **Inventory constraints** are not specified.
55. **How passive_gsci obtains GSCI weights** is not specified.
56. **How macro_allocator defines macro signals** is not specified.
57. **How mean_reversion defines “3-month extremes”** is not specified.
58. **How liquidity_provider quotes are priced and filled** is not specified.
59. **How agent behavior links to open interest concentration** is not specified.

## Meta-RL
60. **RL algorithm** is not specified.
61. **Observation/state representation** is not specified.
62. **Action representation** is not specified.
63. **Reward timing** is not specified.
64. **Episode length** is not specified.
65. **How 252 episodes correspond to the Sharpe fitness horizon** is not specified.
66. **How training is split across scenarios and seeds** is not specified.
67. **What “500,000 minimum across all scenarios and seeds” means exactly** is not specified:
   - total combined,
   - per scenario,
   - or per seed.

## Seed policy
68. **What counts as “qualitatively consistent”** is not specified.
69. **Whether deterministic empirical analyses must also be rerun under seeds** is not specified.

## Governance/audit
70. **How SIGMA_JOB1, FORGE, pap_lock, CODEC, HAWK, QUILL, MINER, DataPassport are operationalized** is not specified.
71. **What constitutes a HAWK methodology score of 7/10** is not specified.
72. **What exactly must be signed in MINER outputs** is not specified.

---

# 4. Reproducibility rating: 2/5

## Rating: 2 out of 5

### Rationale
The specification is strong on:
- high-level hypothesis,
- sample period,
- named assets,
- some statistical tools,
- some thresholds,
- and some governance requirements.

However, reproducibility is substantially limited because many implementation-critical details are missing or inconsistent.

### Why not 4 or 5?
A high reproducibility score would require clear definitions for:
- momentum construction,
- passive concentration measurement,
- roll timing,
- factor model specification,
- exact test family for Bonferroni,
- simulation environment,
- RL algorithm,
- and seed-consistency criteria.

These are all central to the result and are not fully specified.

### Why not 1?
It is still possible to build a plausible implementation because the spec does provide:
- universe,
- date range,
- primary metric,
- significance thresholds,
- GARCH order/distribution,
- Markov regime count,
- DCC-GARCH requirement,
- passive concentration thresholds,
- and seed values.

So the study is not completely non-reproducible; it is partially reproducible with assumptions.

### Main reproducibility blockers
1. **Passive concentration variable is not operationally defined.**
2. **Momentum strategy is not fully specified.**
3. **Roll timing is missing despite roll adjustment being specified.**
4. **Factor model instructions are internally inconsistent.**
5. **Simulation and RL layers are largely schematic rather than implementable.**
6. **Bonferroni family of six tests is not enumerated.**

---

# 5. Recommended implementation stance

If forced to implement from this spec alone, I would do the following:

1. Treat the **historical empirical analysis** as the primary study.
2. Implement the **simulation/RL layer as a secondary exploratory module**, clearly labeled assumption-heavy.
3. Pre-register all assumptions listed above before running anything.
4. Report every result with:
   - raw estimate,
   - p-value,
   - Bonferroni-adjusted interpretation,
   - economic significance relative to -0.15,
   - and sensitivity to alternative reasonable assumptions.

---

# Bottom line

This spec is sufficient to build a **reasonable approximation** of the methodology, but not a uniquely determined implementation. The empirical core is moderately implementable; the simulation/RL portion is heavily underspecified. The overall reproducibility is therefore **2/5**.