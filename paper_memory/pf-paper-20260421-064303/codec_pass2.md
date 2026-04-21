Below is a methodology reimplementation based only on the provided specification text.

---

# Reimplementation Plan

## 1) Full implementation steps in order

## Phase A — Governance and run eligibility

1. **Create a locked study configuration**
   - Encode the hypothesis, sample period, instruments, thresholds, tests, exclusion rules, seeds, and significance criteria exactly as stated.
   - Include:
     - hypothesis threshold = 30% passive concentration
     - minimum economic effect = -0.15 Sharpe units
     - rolling window = 252 trading days
     - seeds = [1337, 42, 9999]
     - sample = 2000–2024
     - instruments = GSCI energy futures: crude oil and natural gas
   - Mark the pre-analysis plan status as **COMMITTED** before any estimation or simulation.

2. **Define the six simultaneous tests**
   - The spec says Bonferroni correction for 6 simultaneous tests, but does not explicitly enumerate the six hypothesis families.
   - Before execution, define and freeze the six tests to be corrected together.

3. **Set audit metadata requirements**
   - Attach a SHA-256 signature to all generated data outputs.
   - Record methodology audit checkpoints so the process can later be reviewed against the stated rubric and revision limits.

---

## Phase B — Data acquisition and raw dataset construction

4. **Acquire futures data**
   - Pull daily data from WRDS Compustat Futures for the GSCI energy sector over 2000–2024.
   - Required fields at minimum:
     - contract identifier
     - trade date
     - price series needed for returns
     - open interest
     - bid-ask spread or bid/ask quotes
     - contract lifecycle metadata
   - Because passive concentration is defined relative to open interest, obtain total open interest by contract/date.

5. **Acquire passive investor concentration inputs**
   - Construct or obtain daily passive GSCI investor concentration in crude oil and natural gas futures as a fraction of open interest.
   - Since the spec refers to “Passive GSCI index investor concentration” but does not define the exact source, methodology, or mapping, this must be explicitly assumed and frozen before implementation.

6. **Acquire macro announcement calendar**
   - Obtain dates for major macro announcements:
     - FOMC
     - CPI
   - Build a trading-day exclusion mask for dates within 5 days of those announcements.

7. **Acquire factor data for momentum exposure control**
   - Obtain Fama-French three-factor data and a momentum factor series if momentum exposure is to be controlled.
   - The spec says “Fama-French momentum factor exposure” but separately says “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth),” which is internally inconsistent.
   - Freeze the factor set before estimation.

---

## Phase C — Futures series engineering

8. **Filter contracts by minimum history**
   - Exclude contracts with fewer than 100 trading days of history.

9. **Filter contracts by spread**
   - Exclude contracts where bid-ask spread exceeds 2% of contract price.
   - Apply this at the contract-date level or contract level; this is underspecified and must be fixed in advance.

10. **Apply macro-date exclusion**
   - Exclude roll dates within 5 days of major macro announcements.
   - Because only roll dates are excluded, not all trading dates, identify all roll dates first.

11. **Construct continuous futures series**
   - Build continuous series for crude oil and natural gas using:
     - roll convention = ratio_backward
     - adjustment method = ratio_backward
   - Since both fields are given as ratio_backward, implement backward ratio adjustment at each roll.
   - Define exact roll trigger logic, because the spec gives the adjustment convention but not the contract selection rule.

12. **Generate daily returns**
   - Compute daily log or simple returns from the adjusted continuous series.
   - Freeze return definition before analysis.

13. **Define tradable universe**
   - Final universe should contain the eligible continuous crude oil and natural gas futures series after all exclusions and adjustments.

---

## Phase D — Passive concentration regime construction

14. **Compute passive concentration measure**
   - For each date and instrument, compute:
     \[
     \text{Passive Concentration}_{t} = \frac{\text{Passive GSCI holdings or equivalent exposure}_{t}}{\text{Open Interest}_{t}}
     \]
   - If concentration is instrument-specific, preserve instrument-level values.
   - If concentration is sector-level, define how it is mapped to crude oil and natural gas.

15. **Assign concentration regimes**
   - Low concentration: 10% of open interest
   - Medium concentration: 30% of open interest
   - High concentration: 60% of open interest
   - For the primary hypothesis, classify dates/windows into:
     - **below 30%**
     - **above 30%**
   - Decide treatment of exactly 30%; this is underspecified and must be fixed.

16. **Create rolling regime labels**
   - For each 252-day rolling window, assign a concentration regime.
   - Because the spec does not say whether regime is based on:
     - current-day concentration,
     - average concentration over the window,
     - majority of days in the window,
     - or scenario assignment from simulation,
     this must be explicitly chosen and frozen.

---

## Phase E — Strategy construction

17. **Implement the 12-month momentum strategy**
   - Build a long/short momentum strategy on the commodity futures universe.
   - Since only crude oil and natural gas are named, define cross-sectional or time-series momentum explicitly.
   - A reasonable implementation is:
     - signal horizon = 12 months (approximately 252 trading days)
     - rank or sign based on trailing return excluding or including the most recent month; this is underspecified
     - long positive-momentum asset(s), short negative-momentum asset(s)
   - Compute daily strategy returns.

18. **Annualize rolling Sharpe ratios**
   - For each 252-day rolling window:
     - compute mean daily return
     - compute daily standard deviation
     - annualize Sharpe ratio using trading-day convention
   - Primary metric:
     \[
     \Delta SR = SR_{\text{high concentration}} - SR_{\text{low concentration}}
     \]

19. **Implement additional simulation agents**
   - passive_gsci: mechanically rebalance to GSCI index weights
   - trend_follower: 12-month momentum long/short
   - mean_reversion: fade 3-month extremes
   - liquidity_provider: post limit orders on both sides
   - macro_allocator: switch energy/non-energy on macro signals
   - meta_rl: allocate across all strategies
   - These are required by the spec, though their exact role in testing the main hypothesis is not fully specified.

20. **Define passive capital scenarios**
   - Simulate or condition on:
     - Low = 10% open interest
     - Medium = 30%
     - High = 60%
   - Apply these scenarios consistently across all seeds.

---

## Phase F — Simulation framework

21. **Build market environment**
   - Create an environment where the six agents interact over the commodity futures sample.
   - Include at minimum:
     - tradable assets
     - daily returns
     - open interest constraints or concentration states
     - transaction/rebalancing mechanics
   - The spec does not define market impact, execution, reward timing, or state representation, so these must be assumed.

22. **Implement passive_gsci agent**
   - Rebalance mechanically to GSCI index weights.
   - Need to define:
     - exact target weights for crude oil and natural gas
     - rebalance frequency
     - whether weights vary through time

23. **Implement trend_follower agent**
   - Use the same 12-month momentum signal as the main strategy unless explicitly separated.
   - Define position sizing and rebalance frequency.

24. **Implement mean_reversion agent**
   - Fade 3-month extremes.
   - Need to define:
     - extreme threshold
     - signal normalization
     - holding period

25. **Implement liquidity_provider agent**
   - Post limit orders on both sides.
   - Need to define:
     - quote distance
     - inventory limits
     - fill model
     - spread capture assumptions

26. **Implement macro_allocator agent**
   - Switch energy/non-energy on macro signals.
   - Need to define:
     - non-energy asset universe
     - macro signals
     - switching rule
   - This is especially underspecified because the data source only names GSCI energy futures.

27. **Implement meta_rl agent**
   - Learn allocation across all strategies.
   - Define:
     - RL algorithm
     - state variables
     - action space
     - reward function
     - exploration policy
     - replay/training setup if applicable
   - Fitness:
     - Sharpe ratio over trailing 252 episodes
     - evaluated every 1000 training steps

28. **Train across seeds and scenarios**
   - Run all passive capital scenarios under seeds:
     - 1337
     - 42
     - 9999
   - Ensure at least 500,000 training episodes across all scenarios and seeds.
   - Record whether findings are qualitatively consistent across all three seeds.

29. **Define qualitative consistency rule**
   - Since validity requires consistency across all seeds, define what counts as “qualitatively consistent” before running:
     - same sign of effect?
     - same significance status?
     - same economic significance threshold crossed?
   - Freeze this rule.

---

## Phase G — Econometric analysis

30. **Compute primary Sharpe differential**
   - Compare annualized rolling 252-day Sharpe ratios between:
     - high-concentration periods (>30%)
     - low-concentration periods (<30%)
   - Estimate:
     \[
     \Delta SR = SR_{high} - SR_{low}
     \]
   - Evaluate whether \(\Delta SR \le -0.15\).

31. **Run two-tailed t-test with Newey-West HAC**
   - Test whether the Sharpe differential differs from zero.
   - Use HAC standard errors with 4 lags.
   - Primary significance threshold:
     - p < 0.05
   - Bonferroni-adjusted threshold:
     - p < 0.0083 for the six simultaneous tests

32. **Fit GARCH(1,1) model**
   - Use a GARCH(1,1) with Normal innovations.
   - Apply to momentum strategy returns, or to underlying asset returns if chosen and frozen.
   - Use the conditional volatility estimate to control for volatility clustering in the main analysis.

33. **Run factor exposure regression**
   - Estimate regression of momentum strategy returns on factor exposures.
   - Because the spec mentions both “Fama-French momentum factor exposure” and “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth),” choose one coherent specification and freeze it.
   - Likely regression form:
     \[
     r_t^{mom} = \alpha + \beta_M MKT_t + \beta_S SMB_t + \beta_H HML_t + \beta_U UMD_t + \epsilon_t
     \]
   - If using Fama-MacBeth, justify how it applies with this asset/time structure.

34. **Estimate concentration effect controlling for volatility and factors**
   - Run a regression or conditional comparison where the dependent variable is momentum return or rolling Sharpe proxy and regressors include:
     - high-concentration indicator
     - GARCH conditional volatility
     - factor exposures
   - Since the exact control model is not specified, define and freeze it.

35. **Run Markov switching regime detection**
   - Fit a 2-regime Markov switching model.
   - Use it to identify latent market regimes and test whether the concentration effect persists within or across regimes.
   - Need to define:
     - dependent series
     - switching mean/variance structure
     - whether concentration enters as exogenous input

36. **Run DCC-GARCH cross-asset correlation analysis**
   - Estimate dynamic conditional correlations between crude oil and natural gas.
   - Assess whether concentration regimes coincide with changes in cross-asset correlation and whether this mediates momentum profitability.
   - Need to define exact DCC specification and software implementation.

37. **Apply multiple-testing correction**
   - For the six predefined simultaneous tests, apply Bonferroni correction:
     - adjusted alpha = 0.0083

---

## Phase H — Decision logic and validity checks

38. **Evaluate statistical significance**
   - Primary criterion:
     - p < 0.05 two-tailed
   - Simultaneous-test criterion:
     - p < 0.0083 where applicable

39. **Evaluate economic significance**
   - Even if statistically significant, reject practical importance unless:
     \[
     \Delta SR \le -0.15
     \]

40. **Evaluate seed robustness**
   - A finding is valid only if it holds across all three seeds.
   - Apply the pre-frozen qualitative consistency rule.

41. **Summarize scenario results**
   - Report results for low, medium, and high passive capital scenarios.
   - Highlight whether the threshold effect appears specifically above 30%.

42. **Produce final study outputs**
   - Include:
     - primary metric estimates
     - p-values
     - HAC-adjusted inference
     - GARCH results
     - factor regression results
     - Markov switching results
     - DCC-GARCH results
     - seed-by-seed consistency table
     - exclusion counts
     - signed output hashes

---

# 2) Assumptions needed due to underspecification

These assumptions are necessary to make the methodology executable.

1. **Passive concentration measurement assumption**
   - Assume passive GSCI concentration can be measured daily as passive GSCI-linked notional or contract-equivalent holdings divided by total open interest.
   - If direct passive holdings are unavailable, assume a proxy based on index-linked positions or reconstructed index exposure.

2. **Instrument scope assumption**
   - Assume “GSCI energy sector” here means only crude oil and natural gas, because those are the only instruments explicitly listed.

3. **Continuous contract construction assumption**
   - Assume backward ratio adjustment is applied at each roll using the price ratio between outgoing and incoming contracts on the roll date.

4. **Roll trigger assumption**
   - Assume contracts are rolled using a deterministic front-to-next schedule based on a fixed number of business days before expiry, unless a more standard GSCI roll calendar is available.

5. **Spread exclusion assumption**
   - Assume the 2% bid-ask spread rule is applied at the daily observation level, excluding those contract-date observations rather than dropping the entire contract.

6. **Macro exclusion assumption**
   - Assume “within 5 days” means within ±5 trading days of FOMC or CPI announcement dates.

7. **Momentum strategy assumption**
   - Assume a time-series momentum strategy:
     - long if trailing 252-day return is positive
     - short if trailing 252-day return is negative
   - Equal-weight across crude oil and natural gas.

8. **Return definition assumption**
   - Assume daily log returns for modeling and daily simple returns for Sharpe computation, unless one convention is chosen consistently for both.

9. **Sharpe annualization assumption**
   - Assume annualized Sharpe = daily mean / daily std × sqrt(252), risk-free rate omitted or assumed negligible unless daily risk-free data are added.

10. **Regime assignment assumption**
   - Assume concentration regime for a rolling window is based on the average passive concentration over that 252-day window.

11. **Threshold boundary assumption**
   - Assume exactly 30% belongs to the medium regime and is excluded from strict low-vs-high comparisons unless otherwise specified.

12. **Factor model assumption**
   - Assume the intended factor control includes market, size, value, and momentum, despite the text mentioning “three-factor” and “momentum factor exposure.”

13. **Fama-MacBeth applicability assumption**
   - Assume Fama-MacBeth is used only if the panel structure is expanded appropriately; otherwise standard time-series OLS with HAC errors is substituted as the coherent implementation.

14. **GARCH control assumption**
   - Assume GARCH conditional volatility enters the main regression as a control variable.

15. **Markov switching assumption**
   - Assume the Markov switching model is fit to momentum strategy returns with two regimes and switching mean/variance.

16. **DCC-GARCH assumption**
   - Assume DCC-GARCH is estimated on crude oil and natural gas daily returns to capture time-varying correlation.

17. **Simulation necessity assumption**
   - Assume the agent-based simulation is part of the required methodology rather than optional context, because the spec explicitly lists agents, scenarios, fitness, and training episodes.

18. **Meta-RL algorithm assumption**
   - Assume a standard continuous-allocation RL method is acceptable, such as PPO or SAC, provided the action is portfolio weights across strategies.

19. **Episode definition assumption**
   - Assume one episode corresponds to one trading day or one rolling decision step; this must be fixed before training.

20. **Qualitative consistency assumption**
   - Assume “qualitatively consistent” means:
     - same sign of concentration effect,
     - same conclusion on economic significance,
     - and no seed reversing the main inference.

21. **Non-energy allocation assumption**
   - For macro_allocator, assume a synthetic or external non-energy benchmark is available, since the named data source is energy-only.

---

# 3) Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data and measurement

1. **Passive GSCI investor concentration source is unspecified**
   - No exact dataset or construction method is given.

2. **Definition of passive holdings is unspecified**
   - Contracts, notional, delta-adjusted exposure, or some other measure?

3. **Whether concentration is instrument-level or sector-level is unspecified**

4. **Exact GSCI energy contract universe is unspecified**
   - Only crude oil and natural gas are named; no contract codes or exchange mapping.

5. **Exact sample endpoints are unspecified**
   - Start/end dates within 2000 and 2024 are not defined.

6. **Bid-ask spread field source is unspecified**
   - Direct quotes vs inferred spread.

7. **Whether spread exclusion is per date or per contract is unspecified**

8. **Open interest aggregation method is unspecified**
   - End-of-day contract-level, summed across maturities, front contract only, etc.

## Futures construction

9. **Roll trigger rule is unspecified**
   - Days before expiry, volume switch, open-interest switch, GSCI calendar, etc.

10. **How ratio_backward is implemented is unspecified**
   - Exact formula and handling of missing prices not stated.

11. **Whether returns are log or simple is unspecified**

12. **Whether excess returns or raw returns are used is unspecified**

13. **Treatment of missing observations is unspecified**

14. **Treatment of holidays and non-trading days is unspecified**

## Regime definition

15. **How low/medium/high scenarios relate to observed concentration is unspecified**
   - Are these empirical bins, simulation settings, or both?

16. **Primary comparison grouping is underspecified**
   - “Above 30%” vs “below 30%” but medium scenario is exactly 30%.

17. **Treatment of exactly 30% concentration is unspecified**

18. **Whether regime is assigned daily or by rolling-window average is unspecified**

19. **Whether concentration threshold is applied separately by asset or jointly is unspecified**

## Momentum strategy

20. **Momentum strategy type is unspecified**
   - Cross-sectional vs time-series.

21. **Signal formation details are unspecified**
   - Include most recent month or skip-month convention?

22. **Portfolio weighting is unspecified**
   - Equal-weight, volatility-scaled, risk parity, signal-proportional.

23. **Rebalance frequency is unspecified**

24. **Leverage constraints are unspecified**

25. **Transaction costs are unspecified**

26. **Shorting assumptions are unspecified**

## Statistical testing

27. **How Sharpe ratio differential is tested is unspecified**
   - Difference in window-level Sharpe series? Difference in mean returns scaled by pooled vol? Jobson-Korkie-type test not mentioned.

28. **Unit of observation for the t-test is unspecified**
   - Rolling windows, daily returns, scenario averages?

29. **Overlap in rolling windows is not addressed**
   - This affects inference materially.

30. **How Newey-West is applied to Sharpe differences is unspecified**

31. **The six simultaneous tests are unspecified**
   - Bonferroni is impossible to apply correctly without defining them.

32. **Main regression specification for “controlling for” GARCH and factors is unspecified**

33. **Whether controls are contemporaneous or lagged is unspecified**

34. **Whether p-values should be seed-specific or pooled is unspecified**

## Factor model

35. **Internal inconsistency: “Fama-French momentum factor exposure” vs “three-factor”**
   - Momentum is not part of the classic three-factor model.

36. **Internal inconsistency: “OLS regression” vs “Fama-MacBeth”**
   - These are distinct estimation frameworks.

37. **Factor data frequency alignment is unspecified**

38. **Applicability of equity factors to commodity futures is not justified**
   - This may be intended but is not explained.

## GARCH / regime / correlation models

39. **Series to which GARCH is fit is unspecified**
   - Strategy returns or asset returns.

40. **How GARCH output enters the main hypothesis test is unspecified**

41. **Markov switching dependent variable is unspecified**

42. **Markov switching model structure is unspecified**
   - Switching intercept, variance, autoregression, exogenous regressors?

43. **DCC-GARCH exact specification is unspecified**
   - Univariate margins, innovation distribution, estimation method.

44. **How DCC-GARCH results connect to the hypothesis is unspecified**

## Simulation agents

45. **Why simulation is needed for an empirical hypothesis is unspecified**

46. **Market environment mechanics are unspecified**

47. **Execution model is unspecified**

48. **Slippage and market impact are unspecified**

49. **Reward definitions for non-RL agents are unspecified**

50. **Passive_gsci exact weights are unspecified**

51. **Passive_gsci rebalance frequency is unspecified**

52. **Mean_reversion “3-month extremes” threshold is unspecified**

53. **Liquidity_provider quoting logic is unspecified**

54. **Liquidity_provider fill model is unspecified**

55. **Macro_allocator macro signals are unspecified**

56. **Macro_allocator non-energy universe is unspecified**

57. **Meta_rl algorithm is unspecified**

58. **Meta_rl state space is unspecified**

59. **Meta_rl action space is unspecified**

60. **Meta_rl reward timing is unspecified**

61. **Episode definition is unspecified**

62. **How 500,000 episodes are distributed across seeds/scenarios is unspecified**

63. **How simulation outputs map to the empirical Sharpe differential is unspecified**

## Seed policy and robustness

64. **What randomness enters the empirical pipeline is unspecified**
   - Seeds matter mainly for simulation/RL unless bootstrapping or stochastic estimation is used.

65. **“Qualitatively consistent” is unspecified**

66. **Whether all tests must pass under all seeds or only the main finding is unspecified**

## Exclusions and calendars

67. **“Major macro announcements” limited to FOMC and CPI or illustrative only is unspecified**
   - The bullet lists only those two, but wording could imply more.

68. **Whether exclusion applies to roll execution only or also return observations around roll dates is unspecified**

69. **How to handle a roll date excluded by macro proximity is unspecified**
   - Delay roll? Advance roll? Drop observation?

## Governance / audit

70. **How COMMITTED status is operationalized is unspecified**

71. **What constitutes a CODEC bidirectional audit is unspecified**

72. **HAWK methodology rubric contents are unspecified**

73. **How revision cycles affect methodology changes is unspecified**

74. **DataPassport signature scope is unspecified**
   - Raw outputs only or all intermediate artifacts?

---

# 4) Reproducibility rating: 2 / 5

## Rating: 2 out of 5

## Rationale

### Why not higher
The spec contains many important components, but several core implementation details are missing or internally inconsistent:

- **Passive concentration measurement is not operationalized**
  - This is central to the hypothesis.
- **Momentum strategy construction is incomplete**
  - Cross-sectional vs time-series, weighting, rebalance, and skip-month are unspecified.
- **Roll logic is incomplete**
  - Adjustment convention is given, but not the actual roll trigger.
- **Main control regression is not defined**
  - “Controlling for GARCH(1,1) volatility clustering and Fama-French momentum factor exposure” is conceptually stated but not translated into an estimable equation.
- **Factor model specification is inconsistent**
  - Three-factor vs momentum factor; OLS vs Fama-MacBeth.
- **Bonferroni correction cannot be reproduced exactly**
  - The six simultaneous tests are not enumerated.
- **Simulation framework is highly underspecified**
  - Agent behavior, environment, rewards, and RL setup are mostly absent.
- **Seed consistency criterion is vague**
  - “Qualitatively consistent” is not defined.

### Why not lower
It is still possible to produce a defensible implementation because the spec does provide:

- clear hypothesis direction and threshold
- sample period
- named instruments
- primary metric
- significance thresholds
- exclusion rules
- rolling window length
- GARCH order
- Markov regime count
- DCC-GARCH requirement
- passive capital scenarios
- seed list
- minimum training episodes

So the study is **partially reproducible**, but not fully reproducible without substantial assumptions.

---

# 5) Concise implementation recommendation

To make this executable from the spec alone, I would freeze the following before running anything:

1. exact passive concentration formula and source
2. exact contract roll trigger
3. exact momentum strategy definition
4. exact low/high regime assignment rule
5. exact main regression equation with controls
6. exact six Bonferroni-tested hypotheses
7. exact RL algorithm and episode definition
8. exact meaning of “qualitatively consistent”

Without those decisions, multiple materially different implementations could all claim compliance.

If you want, I can next turn this into a **formal reproducible protocol** with:
- a frozen assumptions table,
- explicit equations,
- and a step-by-step pseudocode workflow.