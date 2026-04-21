Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 0. Scope of what can be implemented from the spec
The specification mixes:
- an empirical asset-pricing study,
- a market simulation / multi-agent training setup,
- multiple econometric tests,
- governance/audit workflow constraints.

A faithful reimplementation from the spec alone is possible only with explicit assumptions, because several critical details are underspecified.

---

# 1) Full implementation steps in order

## Step 1: Formalize the research question
Implement the primary hypothesis exactly as stated:

> Passive GSCI index investor concentration above 30% of open interest in GSCI energy futures reduces 12-month momentum strategy Sharpe ratios by at least 0.15 units relative to periods below 30%, controlling for GARCH(1,1) volatility clustering and Fama-French momentum factor exposure.

Operationalize:
- Universe: GSCI energy futures, specifically crude oil and natural gas
- Sample: 2000–2024
- Main comparison:
  - low concentration: below 30%
  - high concentration: above 30%
- Outcome:
  - annualized Sharpe ratio of a 12-month momentum strategy
  - computed on rolling 252-trading-day windows
- Primary effect:
  - Sharpe(high concentration) − Sharpe(low concentration)
- Economic significance threshold:
  - effect must be ≤ -0.15 to support the hypothesis

---

## Step 2: Define the data inputs required
Collect or construct the following datasets:

### 2.1 Commodity futures data
For crude oil and natural gas futures from WRDS Compustat Futures, 2000–2024:
- daily prices
- returns
- volume
- open interest
- bid and ask or bid-ask spread proxy
- contract identifiers
- expiration dates
- roll dates or enough metadata to derive them

### 2.2 Passive concentration data
Need daily or periodic measure of passive GSCI investor concentration as a fraction of open interest for GSCI energy futures:
- passive GSCI-linked holdings
- total open interest
- concentration ratio = passive holdings / open interest

If not directly available, construct a proxy from index-linked positions and open interest.

### 2.3 Macro announcement calendar
Need dates for:
- FOMC announcements
- CPI releases

Used to exclude roll dates within 5 days of these announcements.

### 2.4 Fama-French factors / momentum exposure data
Need factor returns for:
- Fama-French three factors
- momentum factor, because the hypothesis explicitly mentions controlling for momentum factor exposure

### 2.5 Inputs for simulation agents
Need any state variables required by:
- passive index weights
- 12-month momentum
- 3-month mean reversion
- liquidity conditions
- macro signals
- RL allocation environment

---

## Step 3: Apply governance precondition checks
Before running the methodology, enforce the stated procedural gate:

- Pre-analysis plan status must be `COMMITTED`
- If not committed, reject the run

Also record:
- DataPassport SHA-256 signature on all extracted/mined outputs
- audit placeholders for CODEC and HAWK requirements

These are workflow constraints, not statistical methodology, but they are explicitly required by the spec.

---

## Step 4: Build the futures continuation series
Construct continuous futures series for crude oil and natural gas using:

- Roll convention: `ratio_backward`
- Adjustment method: `ratio_backward`

Implementation sequence:
1. Sort contracts by expiry
2. Determine roll dates
3. Apply backward ratio adjustment across rolls
4. Produce continuous adjusted price series
5. Compute daily returns from adjusted prices

Because both roll convention and adjustment method are specified as ratio backward, use multiplicative backward adjustment.

---

## Step 5: Apply exclusion rules
Filter the data in this order:

### 5.1 Minimum history filter
Exclude contracts with fewer than 100 trading days of history.

### 5.2 Macro-adjacent roll-date exclusion
Exclude roll dates within 5 days of major macro announcements:
- FOMC
- CPI

Need to define whether “within 5 days” means calendar days or trading days.

### 5.3 Bid-ask spread filter
Exclude contracts where bid-ask spread exceeds 2% of contract price.

Need to define:
- whether this is checked daily or contract-level
- whether “contract price” means midprice, settlement, or last trade

---

## Step 6: Define passive concentration regimes
Create concentration regimes from passive GSCI concentration as percent of open interest:

- Low: 10%
- Medium: 30%
- High: 60%

For the primary hypothesis, define:
- low-concentration periods: concentration < 30%
- high-concentration periods: concentration > 30%

Need to decide how to treat exactly 30%.

Also decide whether:
- the scenario labels (10/30/60) are empirical bins,
- simulated interventions,
- or both.

---

## Step 7: Construct the 12-month momentum strategy
Implement the trend_follower strategy as the empirical momentum portfolio.

### 7.1 Signal definition
Use a 12-month momentum signal on commodity futures.

Likely implementation:
- signal based on trailing 12-month return
- long positive-momentum asset(s), short negative-momentum asset(s)

Need to define:
- whether 12 months = 252 trading days
- whether to skip the most recent month
- whether signal is cross-sectional or time-series momentum
- whether positions are equal-weighted, volatility-scaled, or notional-weighted

### 7.2 Tradable universe
At minimum:
- crude oil
- natural gas

Need to define whether momentum is:
- cross-sectional between these two assets only, or
- directional time-series on each asset independently

### 7.3 Return construction
Compute daily strategy returns from positions and futures returns.

### 7.4 Rolling Sharpe
For each day after enough history exists:
- compute rolling 252-day Sharpe ratio
- annualize it

Need to define annualization convention:
- mean daily return / std daily return × sqrt(252)

---

## Step 8: Partition observations by concentration regime
Align each rolling 252-day Sharpe observation with the passive concentration regime.

Need to define whether regime assignment is based on:
- concentration on the window end date,
- average concentration over the 252-day window,
- majority regime within the window,
- or contemporaneous daily concentration with subsequent aggregation.

Then compute:
- Sharpe observations in low-concentration periods
- Sharpe observations in high-concentration periods

Primary metric:
- differential = mean Sharpe(high) − mean Sharpe(low)

---

## Step 9: Estimate baseline statistical difference
Run the primary statistical test:

### 9.1 Two-tailed t-test
Test whether the Sharpe differential differs from zero.

### 9.2 Newey-West HAC correction
Use 4 lags to correct standard errors for autocorrelation/heteroskedasticity.

### 9.3 Decision criteria
Primary significance:
- p < 0.05

Economic significance:
- differential must be ≤ -0.15

A valid supporting result requires both:
- statistical significance
- economic significance

---

## Step 10: Apply Bonferroni correction for simultaneous tests
Because the spec states 6 simultaneous tests, apply:
- adjusted threshold p < 0.0083

Need to define exactly which six tests are included.

For implementation, maintain both:
- unadjusted p-values
- Bonferroni-adjusted significance decisions

---

## Step 11: Control for volatility clustering with GARCH(1,1)
Fit a GARCH(1,1) model using:
- p=1
- q=1
- Normal distribution

Apply to momentum strategy returns, likely daily returns.

Use outputs to control for volatility clustering. Possible implementations:
1. include conditional volatility as a control in regression,
2. standardize returns by conditional volatility,
3. compare Sharpe differentials on GARCH-filtered residual returns.

Because the spec says “controlling for GARCH(1,1) volatility clustering,” the implementation must choose one explicit control method.

---

## Step 12: Control for factor exposure with factor regression
Run factor regressions to control for Fama-French and momentum exposure.

The spec says:
- “Fama-French three-factor OLS regression”
- “(linearmodels, Fama-MacBeth)”

Implementation sequence:
1. Regress momentum strategy returns on factor returns
2. Include:
   - market
   - size
   - value
   - momentum factor, because the hypothesis explicitly requires momentum factor exposure control
3. Estimate residual or adjusted alpha
4. Recompute concentration effect on adjusted returns or alpha-based Sharpe

Need to resolve the contradiction between:
- OLS regression
- Fama-MacBeth estimation

---

## Step 13: Run Markov switching regime detection
Estimate a 2-regime Markov switching model:
- k_regimes = 2

Purpose:
- detect latent market regimes
- test whether concentration effect is regime-dependent

Implementation:
1. Fit model to momentum returns, volatility, or concentration-linked return process
2. Infer smoothed regime probabilities
3. Compare concentration effect across regimes

Need to define:
- dependent variable
- switching mean only vs mean and variance
- exogenous regressors or none

---

## Step 14: Run DCC-GARCH cross-asset correlation analysis
Estimate dynamic conditional correlations between crude oil and natural gas.

Purpose:
- assess whether passive concentration changes cross-asset correlation structure
- potentially explain momentum profitability changes

Implementation:
1. Fit univariate GARCH models to each asset
2. Fit DCC process to standardized residuals
3. Extract time-varying correlations
4. Compare average DCC correlations across concentration regimes

Need to define:
- exact DCC specification
- innovation distribution
- whether concentration enters as exogenous variable or only used for grouping

---

## Step 15: Implement simulation agents
Build six agents exactly as listed:

1. passive_gsci — mechanically rebalances to GSCI index weights
2. trend_follower — 12-month momentum long/short
3. mean_reversion — fades 3-month extremes
4. liquidity_provider — posts limit orders both sides
5. macro_allocator — switches energy/non-energy on macro signals
6. meta_rl — learns optimal allocation across all strategies

Implementation sequence:
1. Define state space
2. Define action space for each agent
3. Define reward functions
4. Define market interaction mechanism
5. Define execution and inventory updates
6. Define episode termination and reset logic

Need to define all of these because the spec does not.

---

## Step 16: Implement passive capital scenarios in simulation
Run simulation under:
- Low passive capital: 10% of open interest
- Medium: 30%
- High: 60%

For each scenario:
1. initialize passive_gsci participation level
2. simulate interactions among all agents
3. record trend_follower returns and Sharpe
4. compare profitability across scenarios

Need to define whether open interest is:
- fixed exogenously,
- endogenous in simulation,
- or calibrated from historical data.

---

## Step 17: Train the meta_rl allocator
Train the meta_rl agent with:

- minimum 500,000 episodes across all scenarios and seeds
- evaluation every 1000 training steps
- fitness = Sharpe ratio over trailing 252 episodes

Implementation sequence:
1. choose RL algorithm
2. initialize seed
3. train across scenarios
4. evaluate every 1000 steps
5. store trailing-252-episode Sharpe
6. repeat for all seeds

Need to define:
- RL algorithm
- observation features
- action granularity
- exploration schedule
- optimizer
- replay buffer if any
- episode length

---

## Step 18: Enforce seed consistency policy
Run the full simulation and any stochastic estimation under:
- 1337
- 42
- 9999

A finding is valid only if all three seeds produce qualitatively consistent results.

Need to define “qualitatively consistent.” A practical implementation would require:
- same sign of effect,
- same directional conclusion on significance/economic significance,
- no seed reversing the main conclusion.

---

## Step 19: Aggregate empirical and simulation evidence
Produce:
- empirical Sharpe differential estimates
- GARCH-controlled estimates
- factor-controlled estimates
- regime-conditioned estimates
- DCC correlation diagnostics
- simulation scenario comparisons
- seed robustness summary

Then determine whether the hypothesis is supported:
1. high concentration lowers momentum Sharpe
2. effect size is at least -0.15
3. significance survives required thresholds
4. result is robust across seeds

---

## Step 20: Audit and acceptance checks
Before finalizing:
- verify DataPassport SHA-256 signatures exist
- verify CODEC bidirectional audit completed
- verify HAWK methodology score ≥ 7/10
- allow at most 3 HAWK revision cycles

These are process requirements, not inferential methodology, but they are part of the spec.

---

# 2) Assumptions needed due to underspecification

Below are assumptions required to make the methodology executable.

## A. Data assumptions
1. **Passive concentration is available or can be proxied daily**
   - Assume a daily passive GSCI holdings / open interest series can be constructed.

2. **WRDS Compustat Futures contains all needed fields**
   - Assume it includes prices, open interest, bid-ask spread or enough to estimate it, contract metadata, and roll-relevant fields.

3. **Fama-French factors are usable for commodity strategy control**
   - Assume equity-style factors are intended despite commodity futures focus.

4. **Momentum factor data is available**
   - Assume a momentum factor series exists and is aligned to the sample frequency.

---

## B. Futures construction assumptions
5. **Roll dates can be derived from contract metadata**
   - Assume a deterministic roll schedule can be built.

6. **ratio_backward means multiplicative backward adjustment**
   - Assume standard ratio-adjusted continuous futures construction.

7. **Returns are computed from adjusted continuous prices**
   - Assume this is the intended return series for strategy testing.

---

## C. Strategy assumptions
8. **12-month momentum means 252 trading days**
   - Assume 12 months = 252 trading days.

9. **Momentum is time-series momentum**
   - Because only two assets are listed, assume long/short is directional by asset rather than cross-sectional ranking only.

10. **No skip-month unless specified**
   - Assume momentum uses the full trailing 252-day return including the most recent month, since no skip rule is given.

11. **Equal weighting across assets**
   - Assume crude oil and natural gas positions are equally weighted unless volatility scaling is explicitly chosen.

12. **Sharpe annualization uses sqrt(252)**
   - Assume standard daily-to-annual conversion.

---

## D. Regime assumptions
13. **Primary grouping uses concentration on the window end date**
   - Assume each rolling Sharpe observation is assigned to the concentration regime observed on the final day of the 252-day window.

14. **Exactly 30% belongs to medium, not high or low**
   - Assume:
   - low < 30%
   - medium = 30% or around 30%
   - high > 30%
   For the primary binary test, use strict inequalities.

---

## E. Statistical assumptions
15. **Primary t-test is on rolling Sharpe observations**
   - Assume the t-test compares distributions of rolling annualized Sharpe values across regimes.

16. **Newey-West is applied to the differential regression or mean comparison**
   - Assume HAC standard errors are computed on a regression of Sharpe on high-concentration indicator.

17. **Bonferroni applies to six predeclared hypothesis families**
   - Assume six simultaneous tests correspond to the six listed statistical procedures or six outcome comparisons.

18. **GARCH control uses volatility-adjusted returns**
   - Assume the cleanest implementation is to estimate GARCH conditional volatility and standardize returns before recomputing Sharpe/regressions.

19. **Factor control uses time-series OLS**
   - Assume OLS on strategy returns versus factors is the intended baseline, despite mention of Fama-MacBeth.

20. **Markov switching is fit to momentum returns**
   - Assume returns are the dependent variable for regime detection.

21. **DCC-GARCH is estimated on crude oil and natural gas daily returns**
   - Assume pairwise dynamic correlation is sufficient.

---

## F. Simulation assumptions
22. **Simulation is supplementary, not primary**
   - Assume the empirical test is primary and simulation is robustness/mechanism analysis.

23. **Open interest in simulation is exogenous and scenario-controlled**
   - Assume passive capital shares are imposed externally.

24. **meta_rl allocates across strategy sleeves**
   - Assume actions are portfolio weights over the five non-meta strategies.

25. **Episode length is one trading day or one fixed horizon**
   - Need one choice; assume one episode corresponds to one trading day for trailing-252-episode Sharpe consistency.

26. **Qualitative consistency across seeds means same directional conclusion**
   - Assume all seeds must show negative concentration effect and no seed may contradict the main inference.

---

## G. Workflow assumptions
27. **Audit requirements are pass/fail metadata checks**
   - Assume they do not alter estimation itself.

28. **DataPassport SHA-256 means hashing exported outputs**
   - Assume every generated dataset/result artifact is hashed.

---

# 3) Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data and sample construction
1. **Exact contract universe is underspecified**
   - “GSCI energy sector (crude oil, natural gas)” does not specify exact contract symbols, exchanges, or whether multiple maturities are included.

2. **Passive concentration measurement is underspecified**
   - No source or formula is given for passive GSCI investor concentration.

3. **Frequency of concentration data is underspecified**
   - Daily, weekly, or monthly is not stated.

4. **Open interest definition is underspecified**
   - Contract-level, aggregated across maturities, or front-month only is not stated.

5. **Bid-ask spread source is underspecified**
   - Actual quotes vs estimated spread is not stated.

6. **Macro announcement calendar source is underspecified**
   - No source or timezone convention is given.

7. **Sample start/end handling is underspecified**
   - Whether 2000 and 2024 are full calendar years or partial is not stated.

---

## Continuous futures construction
8. **Exact roll trigger is underspecified**
   - Days before expiry, volume switch, open-interest switch, or fixed calendar rule is not stated.

9. **Interaction between roll convention and exclusion rule is underspecified**
   - If a roll date is excluded due to macro announcements, replacement roll logic is not specified.

10. **ratio_backward implementation details are underspecified**
   - Exact formula and treatment of missing prices are not stated.

---

## Exclusion rules
11. **“Fewer than 100 trading days of history” is underspecified**
   - History of the individual contract or history remaining after filters?

12. **“Within 5 days” is underspecified**
   - Trading days or calendar days?

13. **“Major macro announcements” is underspecified beyond FOMC and CPI**
   - The bullet lists only FOMC and CPI, but wording suggests possible broader set.

14. **Bid-ask spread threshold application is underspecified**
   - Daily exclusion, contract exclusion, or observation exclusion is not stated.

15. **“Contract price” is underspecified**
   - Settlement, close, midquote, or adjusted price is not stated.

---

## Momentum strategy
16. **Momentum definition is underspecified**
   - Time-series vs cross-sectional.

17. **Lookback exact length is underspecified**
   - 12 calendar months vs 252 trading days.

18. **Skip-month convention is underspecified**
   - Common in momentum literature but not stated.

19. **Portfolio weighting is underspecified**
   - Equal weight, risk parity, inverse vol, or notional weighting.

20. **Rebalancing frequency is underspecified**
   - Daily, weekly, or monthly.

21. **Execution timing is underspecified**
   - Signal at close, trade next open, same-day close, etc.

22. **Transaction costs are underspecified**
   - Not mentioned at all.

23. **Leverage and margin treatment are underspecified**
   - Not stated.

---

## Sharpe ratio and primary metric
24. **Risk-free rate treatment is underspecified**
   - Sharpe ratio usually requires excess returns, but no risk-free series is specified.

25. **Rolling window alignment is underspecified**
   - End-of-window assignment vs average regime over window.

26. **Annualization formula is underspecified**
   - Standard convention implied but not stated.

27. **Primary differential aggregation is underspecified**
   - Mean of rolling Sharpe differences vs difference in mean Sharpe by regime.

---

## Statistical testing
28. **Exact t-test formulation is underspecified**
   - Difference in means, regression coefficient test, or paired test is not stated.

29. **How Newey-West is applied is underspecified**
   - On rolling Sharpe series, return regression, or differential series is not stated.

30. **The six simultaneous tests are underspecified**
   - Bonferroni denominator is given, but the six tests are not enumerated.

31. **Use of Fama-French three-factor model in commodity futures is underspecified**
   - Economic rationale and exact factor mapping are not stated.

32. **Momentum factor inclusion conflicts with “three-factor” wording**
   - Hypothesis requires momentum exposure control, but listed model is three-factor.

33. **“OLS regression (linearmodels, Fama-MacBeth)” is internally inconsistent**
   - Fama-MacBeth is not plain OLS in the usual sense.

34. **Dependent variable for factor regression is underspecified**
   - Raw returns, excess returns, alpha, or Sharpe is not stated.

35. **How factor controls feed into the main hypothesis test is underspecified**
   - Residualization, multivariate regression, or alpha comparison is not stated.

36. **Markov switching model specification is underspecified**
   - Variable, switching parameters, and exogenous inputs are not stated.

37. **DCC-GARCH specification is underspecified**
   - Distribution, estimation method, and dimensionality are not stated.

---

## Simulation framework
38. **Purpose of simulation relative to empirical test is underspecified**
   - Core methodology or supplementary robustness is not stated.

39. **Market microstructure model is underspecified**
   - Matching engine, price impact, and order book dynamics are not stated.

40. **Agent state spaces are underspecified**
   - Inputs available to each agent are not defined.

41. **Agent action spaces are underspecified**
   - Position sizes, order types, and constraints are not defined.

42. **Reward functions are underspecified**
   - Especially for liquidity_provider, macro_allocator, and meta_rl.

43. **GSCI index weights are underspecified**
   - Static or time-varying weights are not provided.

44. **Macro signals for macro_allocator are underspecified**
   - Which signals and how they are computed are not stated.

45. **Mean reversion “3-month extremes” is underspecified**
   - Threshold and signal formula are not stated.

46. **Liquidity provider behavior is underspecified**
   - Spread width, inventory limits, and fill model are not stated.

47. **meta_rl algorithm is underspecified**
   - No RL method is named.

48. **Episode definition is underspecified**
   - Length and reset conditions are not stated.

49. **Training step definition is underspecified**
   - Environment steps, gradient steps, or episodes are not stated.

50. **Trailing 252 episodes Sharpe is underspecified**
   - Episode return frequency and annualization are not stated.

51. **500,000 minimum across all scenarios and seeds is underspecified**
   - Could mean total combined or per scenario-seed combination.

52. **Qualitative consistency across seeds is underspecified**
   - No formal criterion is given.

---

## Governance and audit
53. **SIGMA_JOB1 and pap_lock are underspecified operationally**
   - No implementation details are given.

54. **CODEC bidirectional audit is underspecified**
   - No criteria or procedure provided.

55. **HAWK methodology rubric is underspecified**
   - No rubric dimensions are given.

56. **MINER outputs are underspecified**
   - No definition of output artifacts.

57. **DataPassport signature generation procedure is underspecified**
   - Only hash type is given.

---

# 4) Reproducibility rating: 2 / 5

## Rating: 2 out of 5

### Rationale
The spec provides:
- a clear hypothesis,
- sample period,
- broad asset universe,
- some statistical procedures,
- some thresholds,
- some simulation components.

However, reproducibility is weak because many implementation-critical details are missing or internally inconsistent.

### Why not 1/5?
It is better than minimal because the spec does specify:
- data source family,
- assets,
- period,
- roll/adjustment convention label,
- exclusion thresholds,
- concentration thresholds,
- seeds,
- minimum episode count,
- named statistical methods.

This is enough to build a plausible implementation.

### Why not 3/5 or higher?
Too many core details are missing:
- passive concentration measurement,
- exact momentum construction,
- exact roll trigger,
- exact statistical model formulations,
- exact six simultaneous tests,
- factor model inconsistency,
- simulation environment design,
- RL algorithm,
- seed consistency criterion.

These omissions mean two competent implementers could produce materially different results while both claiming compliance.

### Summary judgment
- **Empirical portion reproducibility:** about 3/5 if reasonable conventions are imposed
- **Simulation/RL portion reproducibility:** about 1/5 due to severe underspecification
- **Overall combined reproducibility:** **2/5**

---

# 5) Recommended implementation choices to make the spec executable

If you want a concrete reimplementation from this spec alone, the least-arbitrary executable version would be:

1. Use daily crude oil and natural gas continuous futures returns, ratio-backward adjusted.
2. Define momentum as time-series momentum:
   - signal = sign of trailing 252-day return
   - equal-weight across assets
   - daily rebalancing
3. Compute rolling 252-day annualized Sharpe using zero risk-free rate.
4. Define concentration as daily passive GSCI holdings divided by aggregate open interest across relevant contracts.
5. Assign each Sharpe observation to the concentration regime on the window end date.
6. Test mean Sharpe difference with HAC(4) regression:
   - rolling_sharpe_t = a + b * high_concentration_t + e_t
7. Require:
   - b < 0
   - p < 0.05
   - b ≤ -0.15
8. Re-estimate after GARCH(1,1) volatility standardization.
9. Run factor regression on daily strategy returns using market, SMB, HML, and momentum factor; test concentration effect on residual returns.
10. Fit 2-state Markov switching model on strategy returns.
11. Fit bivariate DCC-GARCH on crude oil and natural gas returns.
12. Treat simulation as supplementary robustness:
   - passive capital scenarios at 10/30/60%
   - meta-RL allocates among five base strategies
   - require same directional result across seeds 1337, 42, 9999.

---

If you want, I can next turn this into a **fully specified pseudo-protocol** with:
- exact formulas,
- exact regression equations,
- exact data schema,
- and a “decision table” for hypothesis acceptance/rejection.