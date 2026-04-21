Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 0) Overall objective

Test whether **passive GSCI investor concentration above 30% of open interest** in **GSCI energy futures** is associated with a **reduction of at least 0.15 annualized Sharpe units** in a **12-month momentum strategy**, relative to periods below 30%, while incorporating:

- GARCH(1,1) volatility modeling
- Fama-French momentum-related factor control as specified
- Markov switching regime detection
- DCC-GARCH cross-asset correlation
- multiple-testing correction
- simulation scenarios with specified agents and seeds

The covered market is:

- WRDS Compustat Futures
- GSCI energy sector
- crude oil and natural gas
- 2000–2024

---

# 1) Full implementation steps in order

## Step 1: Define the study design and lock assumptions

1. Define the study universe as:
   - commodity futures in the GSCI energy sector
   - explicitly including crude oil and natural gas
   - sample period 2000-01-01 through 2024-12-31 unless data availability truncates endpoints

2. Define the primary comparison:
   - **high concentration periods**: passive GSCI concentration strictly above 30% of open interest
   - **low concentration periods**: passive GSCI concentration below 30% of open interest
   - note that the spec also defines “medium = 30%” and “high = 60%”; these should be used in simulation scenarios, while the hypothesis threshold is 30%

3. Define the primary outcome:
   - annualized Sharpe ratio differential
   - computed over rolling 252-trading-day windows
   - differential = Sharpe during high-concentration windows minus Sharpe during low-concentration windows

4. Define the decision rule:
   - statistical significance: two-tailed p < 0.05
   - simultaneous-test significance: Bonferroni-adjusted p < 0.0083 for 6 tests
   - economic significance: effect must be ≤ -0.15 Sharpe units
   - valid finding must hold qualitatively across seeds [1337, 42, 9999]

5. Record all assumptions required by underspecification before implementation begins.

---

## Step 2: Acquire and validate raw data

1. Pull futures data from WRDS Compustat Futures for 2000–2024 for:
   - crude oil futures
   - natural gas futures

2. Retrieve at minimum the following fields if available:
   - trade date
   - contract identifier
   - expiration/maturity date
   - open, high, low, close or settlement price
   - volume
   - open interest
   - bid price
   - ask price
   - any available contract metadata needed for rolling and continuous series construction

3. Retrieve or construct passive GSCI investor concentration data:
   - concentration defined as passive GSCI index investor holdings as a percentage of open interest
   - if not directly available in WRDS Compustat Futures, derive from linked holdings/exposure data only if a defensible mapping is possible

4. Retrieve macro announcement calendar data for:
   - FOMC dates
   - CPI release dates

5. Retrieve factor data needed for the specified regression control:
   - Fama-French three factors
   - momentum factor exposure as referenced in the hypothesis
   - align factor frequency to daily if possible, otherwise define a conversion rule

6. Validate data completeness:
   - confirm date coverage
   - confirm both assets exist over sufficient history
   - confirm open interest availability
   - confirm bid-ask spread availability or identify fallback

---

## Step 3: Apply exclusion rules

For each contract and date:

1. Exclude contracts with fewer than 100 trading days of history.

2. Exclude observations on roll dates that fall within 5 calendar days or trading days of major macro announcements:
   - FOMC
   - CPI
   - because the spec does not define calendar vs trading days, choose one and document it

3. Exclude contracts where bid-ask spread exceeds 2% of contract price:
   - spread measure likely `(ask - bid) / mid` or `(ask - bid) / price`
   - choose one and document it

4. Keep an audit table of all exclusions:
   - contract
   - date
   - exclusion reason
   - counts by asset and year

---

## Step 4: Construct continuous futures series

1. For each asset, sort contracts by date and maturity.

2. Implement the specified roll convention:
   - `ratio_backward`

3. Implement the specified adjustment method:
   - `ratio_backward`

4. Build a continuous adjusted price series for each asset:
   - identify roll dates
   - backward-adjust historical prices by multiplicative ratios at each roll
   - ensure return continuity across rolls

5. Preserve both:
   - adjusted continuous series for signal generation and return computation
   - raw contract-level data for exclusion logic and microstructure checks

6. Verify:
   - no artificial jumps at roll boundaries after adjustment
   - return distributions are plausible

---

## Step 5: Define passive concentration regimes

1. Compute daily passive concentration for each asset:
   - passive GSCI holdings / total open interest

2. Define regime labels:
   - low: 10% scenario for simulation
   - medium: 30% scenario for simulation and threshold reference
   - high: 60% scenario for simulation
   - empirical threshold comparison:
     - low-concentration period: concentration < 30%
     - high-concentration period: concentration > 30%

3. Decide treatment of exactly 30% observations:
   - must be specified because the hypothesis says “above 30%” and “below 30%”

4. Create rolling 252-day windows and assign each window to a concentration regime:
   - either by current-day regime
   - or by average concentration over the window
   - this is underspecified and must be fixed explicitly

---

## Step 6: Build the 12-month momentum strategy

1. Define the momentum lookback horizon:
   - 12 months
   - likely 252 trading days

2. For each asset on each eligible date:
   - compute trailing 12-month return from the adjusted continuous series

3. Convert signal into position:
   - long if trailing return > 0
   - short if trailing return < 0
   - treatment of zero return must be specified

4. Determine portfolio construction:
   - equal-weight across crude oil and natural gas, unless another weighting is justified
   - rebalance frequency must be specified

5. Compute daily strategy returns:
   - position at t-1 times return from t-1 to t
   - include transaction costs only if specified; otherwise note omission as an assumption

6. Compute rolling 252-day annualized Sharpe ratio:
   - annualized mean / annualized volatility
   - define risk-free rate treatment; likely zero unless daily risk-free is included

---

## Step 7: Estimate the primary metric

1. Partition rolling windows into:
   - high-concentration windows
   - low-concentration windows

2. Compute:
   - average annualized Sharpe in high-concentration windows
   - average annualized Sharpe in low-concentration windows

3. Compute primary effect:
   - `Sharpe_diff = Sharpe_high - Sharpe_low`

4. Compare against minimum effect size:
   - economically meaningful only if `Sharpe_diff <= -0.15`

---

## Step 8: Conduct the primary statistical test

1. Form the sample of rolling-window Sharpe observations by regime.

2. Perform a two-tailed t-test comparing high vs low concentration Sharpe outcomes.

3. Apply Newey-West HAC correction with 4 lags to account for serial dependence in rolling-window estimates.

4. Record:
   - test statistic
   - HAC-adjusted standard error
   - p-value
   - confidence interval if implemented

5. Evaluate:
   - primary significance at p < 0.05
   - economic significance at ≤ -0.15 Sharpe units

---

## Step 9: Fit GARCH(1,1) volatility models

1. For each asset and/or strategy return series, fit a GARCH(1,1) model:
   - p=1
   - q=1
   - Normal distribution

2. Use the fitted conditional volatility estimates to control for volatility clustering.

3. Incorporate GARCH outputs into the analysis in one of the following ways:
   - volatility-adjusted returns before Sharpe computation
   - conditional-volatility covariate in regression
   - regime-conditioned robustness analysis

4. Because the spec says “controlling for GARCH(1,1) volatility clustering,” explicitly define the chosen control mechanism.

5. Re-estimate the concentration effect after volatility control.

---

## Step 10: Run factor regression control

1. Prepare factor data for the specified regression:
   - Fama-French three factors
   - momentum factor exposure as referenced in the hypothesis

2. Align factor data with strategy returns.

3. Estimate factor exposure using OLS / panel framework as specified:
   - the spec says “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)”
   - because OLS and Fama-MacBeth are not identical procedures, choose and document an implementation interpretation

4. Regress momentum strategy returns on factors and concentration indicator or concentration level.

5. Extract:
   - alpha
   - factor loadings
   - concentration coefficient if included
   - robust standard errors

6. Assess whether the concentration effect remains after factor control.

---

## Step 11: Detect regimes with Markov switching

1. Fit a 2-regime Markov switching model:
   - `k_regimes = 2`

2. Choose the modeled series:
   - strategy returns
   - or concentration-adjusted returns
   - or volatility
   - this must be specified because the target series is not given

3. Infer latent regimes and regime probabilities.

4. Test whether the concentration effect differs by latent regime.

5. Use this as a robustness or heterogeneity analysis among the six simultaneous tests.

---

## Step 12: Estimate DCC-GARCH cross-asset correlation

1. Use crude oil and natural gas return series.

2. Fit univariate GARCH models as needed for each asset.

3. Estimate dynamic conditional correlation between the two assets.

4. Examine whether high passive concentration periods coincide with elevated or altered cross-asset correlation.

5. Use this as another robustness or mechanism-oriented test.

---

## Step 13: Implement simulation agents

For each passive capital scenario and seed, simulate the following agents:

1. `passive_gsci`
   - mechanically rebalances to GSCI index weights

2. `trend_follower`
   - 12-month momentum long/short

3. `mean_reversion`
   - fades 3-month extremes

4. `liquidity_provider`
   - posts limit orders on both sides

5. `macro_allocator`
   - switches energy/non-energy on macro signals

6. `meta_rl`
   - learns optimal allocation across all strategies

Implementation sequence:

1. Define the market environment:
   - assets
   - state variables
   - action spaces
   - reward definitions
   - episode boundaries

2. Define passive capital scenarios:
   - low = 10% of open interest
   - medium = 30%
   - high = 60%

3. For each scenario and each seed:
   - initialize environment and agents
   - run training/evaluation

4. Ensure total training episodes are at least 500,000 across all scenarios and seeds.

5. For `meta_rl`:
   - fitness = Sharpe ratio over trailing 252 episodes
   - evaluate every 1000 training steps

6. Record whether the qualitative finding holds across all three seeds.

---

## Step 14: Define the six simultaneous tests for Bonferroni correction

Because the spec states Bonferroni correction for 6 simultaneous tests but does not enumerate all six explicitly, define six tests before execution. A defensible set would be:

1. Primary high-vs-low Sharpe differential test
2. GARCH-controlled concentration effect test
3. Factor-controlled concentration effect test
4. Markov regime interaction test
5. DCC-GARCH correlation shift test
6. Simulation-based scenario effect test

Then apply:
- adjusted threshold p < 0.0083

This enumeration must be fixed in advance because it is underspecified.

---

## Step 15: Evaluate seed consistency

1. Repeat all stochastic components for seeds:
   - 1337
   - 42
   - 9999

2. Define “qualitatively consistent results” before running:
   - same sign of effect
   - same conclusion on economic significance
   - preferably same significance classification

3. A finding is valid only if it holds across all three seeds.

---

## Step 16: Summarize results against hypothesis

For the hypothesis to be supported, all of the following should hold:

1. High concentration (>30%) is associated with lower momentum Sharpe than low concentration (<30%).

2. The differential is at most -0.15 Sharpe units.

3. The result is statistically significant:
   - p < 0.05 primary
   - and if treated among simultaneous tests, p < 0.0083 where applicable

4. The result remains qualitatively consistent after:
   - GARCH control
   - factor control
   - regime analysis
   - cross-asset correlation analysis
   - simulation scenarios
   - all three seeds

---

## Step 17: Produce reproducible outputs and audit artifacts

1. Save:
   - cleaned datasets
   - exclusion logs
   - continuous series construction metadata
   - rolling Sharpe outputs
   - model estimates
   - simulation summaries
   - seed-by-seed results

2. Generate DataPassport SHA-256 signatures on all outputs designated as MINER outputs.

3. Ensure methodology quality is sufficient for HAWK rubric target of at least 7/10.

4. Ensure bidirectional audit readiness for CODEC.

5. Note that the pre-analysis plan status must be COMMITTED before execution; otherwise the run should be rejected.

---

# 2) Assumptions needed due to underspecification

These assumptions are necessary to make the methodology executable.

## Data and universe assumptions

1. **Asset universe assumption**
   - GSCI energy sector is operationalized as only crude oil and natural gas because those are the only instruments explicitly named.

2. **Date boundary assumption**
   - Use all available trading days from 2000-01-01 to 2024-12-31.

3. **Passive concentration data assumption**
   - Passive GSCI investor concentration can be observed directly or credibly proxied from available holdings/open-interest data.

4. **Open interest denominator assumption**
   - Concentration is measured as passive GSCI position size divided by total contract open interest on the same date.

## Continuous futures construction assumptions

5. **Roll trigger assumption**
   - Roll occurs using a standard rule such as rolling from front to next contract a fixed number of days before expiry, since the exact trigger is not specified.

6. **Ratio backward implementation assumption**
   - Backward multiplicative adjustment is applied at each roll using the price ratio between outgoing and incoming contracts on the roll date.

## Exclusion assumptions

7. **Trading-day history assumption**
   - “Fewer than 100 trading days of history” refers to each contract’s own observed history in the dataset.

8. **Macro exclusion window assumption**
   - “Within 5 days” is interpreted as 5 trading days unless calendar days are chosen and documented.

9. **Bid-ask spread assumption**
   - Spread percentage is computed as `(ask - bid) / midprice`.

## Momentum strategy assumptions

10. **12-month horizon assumption**
    - 12 months = 252 trading days.

11. **Signal mapping assumption**
    - Positive trailing return implies long; negative implies short; zero implies flat.

12. **Portfolio weighting assumption**
    - Equal-weight the two assets.

13. **Rebalancing assumption**
    - Rebalance daily after signal update.

14. **Risk-free rate assumption**
    - Use zero daily risk-free rate in Sharpe computation unless daily risk-free data are added.

15. **Transaction cost assumption**
    - Ignore transaction costs unless bid-ask and slippage are explicitly incorporated into strategy returns.

## Statistical modeling assumptions

16. **Sharpe comparison sample assumption**
    - Rolling-window Sharpe observations are treated as the units for the t-test.

17. **Newey-West application assumption**
    - HAC correction is applied to the regression or mean-difference framework used for rolling Sharpe differentials.

18. **GARCH control assumption**
    - Volatility control is implemented by including conditional volatility estimates as controls or by standardizing returns.

19. **Factor model assumption**
    - Because the hypothesis mentions momentum factor exposure but the test list mentions only Fama-French three factors, include momentum factor as an additional control if available.

20. **Fama-MacBeth assumption**
    - If only two assets exist, Fama-MacBeth may be weakly identified; use time-series factor regression or pooled panel interpretation and document the limitation.

21. **Markov switching target assumption**
    - Fit the Markov switching model to strategy returns.

22. **DCC-GARCH assumption**
    - DCC-GARCH is estimated on crude oil and natural gas daily returns.

## Simulation assumptions

23. **Environment assumption**
    - The simulation environment is based on historical market data with agent interactions layered on top.

24. **Mean reversion definition assumption**
    - “3-month extremes” means deviations based on trailing 63-trading-day returns.

25. **Macro allocator assumption**
    - Macro signals are derived from the same FOMC/CPI or other macro indicators available to the study.

26. **Meta-RL algorithm assumption**
    - Any standard RL allocator may be used, provided fitness is trailing-252-episode Sharpe and evaluation occurs every 1000 steps.

27. **Episode definition assumption**
    - One episode corresponds to one trading day or one fixed trading window; this must be chosen and documented.

28. **Qualitative consistency assumption**
    - “Qualitatively consistent” means same sign and same support/non-support conclusion for the hypothesis across all seeds.

## Governance assumptions

29. **Pre-analysis lock assumption**
    - No execution should proceed unless pre-analysis status is COMMITTED.

30. **Audit artifact assumption**
    - DataPassport signatures are generated for all relevant outputs, even though exact output scope is not defined.

---

# 3) Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## A. Data definition underspecification

1. **Exact contract identifiers are not specified.**
2. **Whether only front-month contracts or all listed maturities are included is not specified.**
3. **Whether additional GSCI energy contracts beyond crude oil and natural gas are excluded is not explicitly stated.**
4. **How passive GSCI investor concentration is measured or sourced is not specified.**
5. **Whether concentration is asset-specific, market-wide, or aggregated across energy futures is not specified.**
6. **Whether open interest is contract-level or aggregated across maturities is not specified.**
7. **Whether factor data are daily, monthly, or another frequency is not specified.**
8. **How to obtain a commodity-relevant momentum factor while referencing Fama-French factors is not specified.**

## B. Continuous futures construction underspecification

9. **Roll trigger date is not specified.**
10. **Whether rolling is volume-based, open-interest-based, or calendar-based is not specified.**
11. **How ratio_backward is operationalized exactly is not specified.**
12. **Whether returns are computed from settlement or close prices is not specified.**

## C. Exclusion rule underspecification

13. **“100 trading days of history” could refer to contract history, asset history, or continuous-series history.**
14. **“Within 5 days” of macro announcements does not specify calendar days vs trading days.**
15. **The exact macro announcement source/calendar is not specified.**
16. **Bid-ask spread formula is not specified.**
17. **Contract price denominator for the 2% spread rule is not specified.**
18. **Whether exclusions remove only the affected date or the entire contract is not specified.**

## D. Momentum strategy underspecification

19. **Exact momentum signal formula is not specified.**
20. **Whether there is a skip month between formation and holding is not specified.**
21. **Whether the strategy is cross-sectional or time-series momentum is not specified.**
22. **How long/short is implemented with only two assets is not specified.**
23. **Portfolio weighting scheme is not specified.**
24. **Rebalancing frequency is not specified.**
25. **Treatment of zero signals is not specified.**
26. **Transaction costs are not specified.**
27. **Risk-free rate treatment in Sharpe ratio is not specified.**

## E. Primary metric underspecification

28. **How rolling windows are assigned to concentration regimes is not specified.**
29. **Whether Sharpe is computed from daily returns within each window or from another frequency is not specified.**
30. **Whether annualization uses 252 or another convention is implied but not explicitly stated.**
31. **How exactly 30% concentration observations are handled is not specified.**
32. **Whether the primary metric is asset-level, portfolio-level, or scenario-level is not specified.**

## F. Statistical test underspecification

33. **The exact implementation of the t-test with Newey-West HAC on rolling Sharpe windows is not specified.**
34. **The six simultaneous tests for Bonferroni correction are not enumerated.**
35. **How GARCH(1,1) “control” enters the hypothesis test is not specified.**
36. **The factor model is inconsistent: hypothesis mentions momentum factor exposure, while tests specify Fama-French three-factor OLS.**
37. **“OLS regression (linearmodels, Fama-MacBeth)” mixes two different approaches and is not fully coherent.**
38. **The dependent variable in the factor regression is not specified.**
39. **The role of concentration in the regression equation is not specified.**
40. **The target series for Markov switching is not specified.**
41. **The purpose and test statistic for DCC-GARCH are not specified.**
42. **Whether p-values from all robustness tests must pass Bonferroni or only selected tests is not specified.**

## G. Simulation underspecification

43. **The simulation environment is not defined.**
44. **Agent state spaces are not defined.**
45. **Agent action spaces are not defined.**
46. **Reward functions for all agents except meta_rl are not defined.**
47. **How passive_gsci maps to actual GSCI weights is not specified.**
48. **How trend_follower interacts with the empirical momentum strategy is not specified.**
49. **How mean_reversion defines “3-month extremes” is not specified.**
50. **How liquidity_provider order placement and fill mechanics work is not specified.**
51. **How macro_allocator defines macro signals is not specified.**
52. **What RL algorithm meta_rl uses is not specified.**
53. **What an episode is is not specified.**
54. **How 500,000 minimum training episodes are distributed across scenarios and seeds is not specified.**
55. **How simulation outputs connect to the empirical hypothesis test is not specified.**

## H. Seed policy underspecification

56. **Which components are stochastic and therefore seed-sensitive is not specified.**
57. **“Qualitatively consistent results” is not defined.**
58. **Whether all six tests must be consistent across seeds or only the primary finding is not specified.**

## I. Governance/audit underspecification

59. **How pre-analysis commitment is verified operationally is not specified.**
60. **What constitutes a MINER output for DataPassport signing is not specified.**
61. **How CODEC bidirectional audit is performed is not specified.**
62. **How HAWK methodology scoring is operationalized is not specified.**
63. **What happens after 3 HAWK revision cycles is not specified.**

---

# 4) Reproducibility rating: 2 / 5

## Rating: 2 out of 5

## Rationale

The specification is strong on:
- hypothesis statement
- primary metric concept
- sample period
- broad data source
- some model families
- thresholds
- seeds
- exclusion categories

However, reproducibility is limited because many implementation-critical details are missing or internally inconsistent.

### Why not higher?

1. **Core variable construction is underspecified**
   - passive GSCI concentration is central but not operationally defined

2. **Strategy definition is incomplete**
   - 12-month momentum is not fully specified as time-series vs cross-sectional, weighting, rebalancing, skip rules, or cost treatment

3. **Continuous futures construction is incomplete**
   - ratio backward is named, but roll trigger logic is absent

4. **Statistical framework has inconsistencies**
   - “Fama-French three-factor OLS regression” and “Fama-MacBeth” are not the same thing
   - hypothesis mentions momentum factor exposure but test list omits it

5. **Bonferroni correction references 6 tests without defining them**
   - this materially affects inference

6. **Simulation section is highly underspecified**
   - agents are named but not operationalized
   - environment, rewards, episodes, and RL algorithm are missing

7. **Seed consistency criterion is vague**
   - “qualitatively consistent” is not defined

### Why not lower?

1. The hypothesis direction and effect size threshold are explicit.
2. The sample universe and period are reasonably clear.
3. Several model classes and significance thresholds are named.
4. Exclusion categories are at least partially specified.
5. The roll and adjustment method names are given, even if not fully operationalized.

So the study is **partially reproducible**, but not enough for a faithful independent reimplementation without substantial assumptions.

---

# 5) Recommended minimal clarification set before implementation

If you want this to become reproducible at a high level, the minimum clarifications needed are:

1. Exact formula/source for passive GSCI concentration
2. Exact contract universe and maturity handling
3. Exact roll trigger rule
4. Exact momentum strategy definition
5. Exact Sharpe computation convention
6. Exact regression specification including factors and concentration term
7. Enumeration of the 6 Bonferroni-tested hypotheses
8. Exact Markov switching target variable
9. Exact DCC-GARCH objective/statistic
10. Exact simulation environment, episode definition, and meta_rl algorithm
11. Definition of “qualitatively consistent across seeds”

---

If you want, I can next convert this into a **formal implementation protocol** with:
- equations,
- pseudocode,
- data schema,
- and a decision table for every assumption.