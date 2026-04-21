Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 1) Full implementation steps in order

## Phase 0 — Governance and run eligibility
1. **Verify pre-analysis status is committed**
   - The spec states the pre-analysis plan status is initially `UNCOMMITTED` and must be committed before execution.
   - Operationally, do not run the study until a committed status exists in the experiment governance layer.
   - If not committed, halt.

2. **Define the exact six simultaneous tests**
   - Bonferroni correction is specified for 6 tests, but the six tests are not enumerated.
   - Before execution, explicitly register the six hypothesis tests that will be treated as the simultaneous family.

3. **Define audit and provenance requirements**
   - Ensure all produced outputs carry a SHA-256 signature.
   - Ensure methodology review criteria are documented so the run can later be audited.
   - These are process requirements, not analytical steps, but they are mandatory per spec.

---

## Phase 1 — Data acquisition and sample construction
4. **Acquire futures data**
   - Source: WRDS Compustat Futures.
   - Universe: GSCI energy sector.
   - Instruments explicitly named: crude oil and natural gas.
   - Sample period: 2000–2024.

5. **Acquire open interest and passive concentration inputs**
   - Obtain daily open interest for included futures.
   - Obtain or construct daily passive GSCI investor concentration as a fraction of open interest for GSCI energy futures.
   - This is essential because the hypothesis is defined on concentration above/below 30%.

6. **Acquire contract-level microstructure fields**
   - Need bid, ask, or bid-ask spread data to apply the exclusion rule:
     - exclude contracts where bid-ask spread exceeds 2% of contract price.

7. **Acquire macro announcement calendar**
   - Need dates for major macro announcements:
     - FOMC
     - CPI
   - These are required to exclude roll dates within 5 days of such announcements.

8. **Acquire factor data for momentum exposure control**
   - The spec requires controlling for “Fama-French momentum factor exposure.”
   - Also lists “Fama-French three-factor OLS regression.”
   - Therefore obtain daily factor returns needed for the chosen control specification.

9. **Acquire any additional data needed for simulation agents**
   - Macro signals for the macro allocator.
   - Inputs needed for the liquidity provider and RL environment.
   - Cross-asset data if DCC-GARCH is implemented beyond crude oil and natural gas.

---

## Phase 2 — Contract processing and continuous series construction
10. **Filter contracts with insufficient history**
   - Exclude contracts with fewer than 100 trading days of history.

11. **Define eligible roll dates**
   - Identify roll dates for each futures contract chain.
   - Exclude roll dates within 5 calendar days or trading days of FOMC/CPI announcements; this is underspecified and must be fixed in advance.

12. **Apply roll convention**
   - Construct continuous futures series using:
     - roll convention = `ratio_backward`
     - adjustment method = `ratio_backward`
   - Apply consistently to all included contracts.

13. **Apply bid-ask spread exclusion**
   - Exclude contracts where bid-ask spread exceeds 2% of contract price.
   - Decide whether this is checked daily, at roll, or over some aggregation interval; this is underspecified and must be fixed.

14. **Construct final continuous daily return series**
   - For crude oil and natural gas, produce adjusted daily prices and returns after all exclusions.

---

## Phase 3 — Define concentration regimes and scenarios
15. **Compute passive concentration measure**
   - For each day and instrument (or sector aggregate), compute passive GSCI concentration:
     \[
     \text{concentration}_t = \frac{\text{passive GSCI holdings}_t}{\text{open interest}_t}
     \]
   - The exact numerator is underspecified and must be defined.

16. **Assign concentration regimes**
   - Low concentration period: below 30%.
   - High concentration period: above 30%.
   - The treatment of exactly 30% is underspecified and must be fixed.
   - Medium and high scenarios are also listed:
     - Low = 10%
     - Medium = 30%
     - High = 60%
   - Decide whether these are empirical bins, simulation targets, or both.

17. **Create scenario labels for simulation**
   - Build three passive capital scenarios:
     - 10% open interest
     - 30% open interest
     - 60% open interest
   - These likely parameterize the passive_gsci simulation agent.

---

## Phase 4 — Momentum strategy construction
18. **Define the 12-month momentum signal**
   - Construct a 12-month momentum signal for commodity futures.
   - The exact lookback implementation is underspecified:
     - likely 252 trading days
     - but whether to skip the most recent month is not stated.
   - Fix this before running.

19. **Define portfolio formation rule**
   - The trend_follower is described as “12-month momentum signal, long/short.”
   - Decide:
     - cross-sectional vs time-series momentum
     - equal-weight vs volatility-weighted
     - instrument-level or sector-level
   - This is central and underspecified.

20. **Generate daily momentum strategy returns**
   - Produce daily PnL/returns for the momentum strategy over the full sample.

21. **Compute rolling Sharpe ratios**
   - Primary metric uses annualized Sharpe ratio over rolling 252-day windows.
   - Compute rolling Sharpe for the momentum strategy.
   - Then compare Sharpe during high-concentration vs low-concentration periods.

22. **Compute primary effect**
   - Calculate:
     \[
     \Delta SR = SR_{\text{high concentration}} - SR_{\text{low concentration}}
     \]
   - Hypothesized effect: at most \(-0.15\) or lower.
   - Effects with magnitude smaller than 0.15 are economically insignificant.

---

## Phase 5 — Control modeling
23. **Fit GARCH(1,1) volatility model**
   - Use a GARCH(1,1) model with Normal innovations.
   - Apply to momentum returns, or underlying futures returns, depending on the chosen control design.
   - Extract conditional volatility estimates.

24. **Control for volatility clustering**
   - Incorporate GARCH conditional volatility into the main comparison.
   - This could be done by:
     - volatility-adjusted returns,
     - regression control,
     - or regime conditioning.
   - The exact method is underspecified and must be fixed.

25. **Estimate factor exposure control**
   - Run factor regression to control for momentum factor exposure.
   - The spec mentions:
     - “Fama-French momentum factor exposure”
     - and separately “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)”
   - Build the factor model chosen for the study and estimate residualized returns or adjusted Sharpe.

26. **Construct adjusted momentum performance series**
   - After controlling for GARCH volatility and factor exposure, compute adjusted returns or adjusted Sharpe ratios for the primary hypothesis test.

---

## Phase 6 — Statistical testing
27. **Run primary two-tailed t-test**
   - Test whether the Sharpe differential between high- and low-concentration periods differs from zero.
   - Use Newey-West HAC correction with 4 lags.

28. **Apply Bonferroni correction**
   - For the predefined family of 6 simultaneous tests, use adjusted threshold:
     \[
     p < 0.0083
     \]

29. **Evaluate economic significance**
   - Even if statistically significant, reject substantive support if the effect is greater than \(-0.15\) Sharpe units in magnitude.

30. **Document confidence intervals**
   - Not explicitly required, but necessary for interpretability and reproducibility.

---

## Phase 7 — Additional model-based analyses
31. **Run Fama-MacBeth / factor regression analysis**
   - Implement the specified regression framework using the selected factors.
   - Clarify whether this is cross-sectional over contracts, over strategies, or over time-sorted portfolios.

32. **Run Markov switching regime detection**
   - Fit a 2-regime Markov switching model.
   - Use it to identify latent market regimes and test whether concentration effects differ by regime.

33. **Run DCC-GARCH cross-asset correlation analysis**
   - Estimate dynamic conditional correlations across assets.
   - At minimum this likely includes crude oil and natural gas.
   - Potentially also non-energy assets if the macro allocator requires them.

34. **Assess whether concentration coincides with correlation regime shifts**
   - Examine whether high passive concentration is associated with stronger cross-asset correlation and weaker momentum profitability.

---

## Phase 8 — Multi-agent simulation
35. **Define simulation environment**
   - Build a market simulation or allocation environment containing six agents:
     1. passive_gsci
     2. trend_follower
     3. mean_reversion
     4. liquidity_provider
     5. macro_allocator
     6. meta_rl

36. **Implement passive_gsci agent**
   - Rebalances mechanically to GSCI index weights.
   - Need exact GSCI energy weights and rebalance frequency.

37. **Implement trend_follower agent**
   - Uses the same 12-month momentum signal as the empirical strategy.

38. **Implement mean_reversion agent**
   - Fades 3-month extremes.
   - Need exact threshold and position sizing rule.

39. **Implement liquidity_provider agent**
   - Posts limit orders on both sides.
   - Need spread placement, inventory limits, fill model, and adverse selection assumptions.

40. **Implement macro_allocator agent**
   - Switches energy/non-energy on macro signals.
   - Need exact macro signals and switching rule.

41. **Implement meta_rl agent**
   - Learns optimal allocation across all strategies.
   - Fitness = Sharpe ratio over trailing 252 episodes.
   - Evaluation every 1000 training steps.

42. **Set passive capital scenarios**
   - Run the simulation under:
     - low passive capital = 10% OI
     - medium = 30% OI
     - high = 60% OI

43. **Set seeds**
   - Run all stochastic components under seeds:
     - 1337
     - 42
     - 9999

44. **Train for minimum episodes**
   - Total training episodes must be at least 500,000 across all scenarios and seeds.
   - Clarify allocation of episodes across scenarios and seeds.

45. **Evaluate qualitative consistency across seeds**
   - A finding is valid only if all three seeds produce qualitatively consistent results.
   - Define “qualitatively consistent” before execution.

46. **Compare momentum profitability across passive capital scenarios**
   - Assess whether higher passive concentration/capital reduces momentum Sharpe by at least 0.15.

---

## Phase 9 — Synthesis and decision rule
47. **Integrate empirical and simulation evidence**
   - Compare empirical high-vs-low concentration results with simulation scenario results.

48. **Apply final validity criteria**
   - Support for the hypothesis requires:
     - negative Sharpe differential in the expected direction,
     - magnitude at least 0.15,
     - statistical significance under stated thresholds,
     - consistency across all three seeds for simulation-based findings.

49. **Produce auditable outputs**
   - Include signed outputs, test definitions, assumptions, and all exclusion counts.

---

# 2) Assumptions needed due to underspecification

These assumptions are necessary to make the methodology executable.

1. **Instrument universe assumption**
   - Assume the GSCI energy sector sample consists only of crude oil and natural gas because those are the only instruments explicitly named.

2. **Frequency assumption**
   - Assume all analysis is conducted at daily frequency because rolling windows are 252-day and futures/open interest data are typically daily.

3. **Momentum definition assumption**
   - Assume 12-month momentum uses trailing 252 trading-day cumulative return.
   - Because no skip-month is specified, assume no skip unless pre-registered otherwise.

4. **Momentum portfolio assumption**
   - Assume time-series momentum rather than cross-sectional momentum, since only two named instruments are provided and “long/short” is stated.

5. **Sharpe annualization assumption**
   - Assume annualized Sharpe = mean daily return / std daily return × sqrt(252).

6. **Concentration measurement assumption**
   - Assume passive concentration is measured daily as passive GSCI notional or positions divided by total open interest.

7. **Threshold boundary assumption**
   - Assume exactly 30% belongs to the medium scenario and is excluded from strict low/high binary comparisons unless otherwise pre-registered.

8. **High/low period construction assumption**
   - Assume low periods are concentration < 30% and high periods are concentration > 30%, pooled across the sample.

9. **Open interest aggregation assumption**
   - Assume concentration is computed at the contract or instrument level and then aggregated to sector level using open-interest weights.

10. **Bid-ask spread filter assumption**
   - Assume the 2% spread rule is applied on each trading day at the contract level using:
     \[
     \frac{\text{ask} - \text{bid}}{\text{midprice}}
     \]
   - Exclude observations or contracts violating this threshold.

11. **Macro announcement exclusion assumption**
   - Assume “within 5 days” means 5 trading days around the roll date, symmetric window.

12. **Roll-date handling assumption**
   - Assume if a roll date falls in the exclusion window, that roll event is omitted or shifted to the nearest eligible date according to a pre-specified rule.

13. **GARCH control assumption**
   - Assume GARCH(1,1) is fit to daily momentum strategy returns and conditional volatility is included as a control in regression or used to volatility-standardize returns.

14. **Factor model assumption**
   - Assume factor controls include the standard three factors plus a momentum factor because the text references both three-factor regression and momentum exposure.

15. **Fama-MacBeth applicability assumption**
   - Assume Fama-MacBeth is used despite the small asset universe by forming repeated cross-sections over available contracts/portfolios.

16. **DCC-GARCH universe assumption**
   - Assume DCC-GARCH is estimated at minimum on crude oil and natural gas returns.

17. **Simulation environment assumption**
   - Assume the simulation is an abstract market/allocation environment calibrated to empirical return and liquidity characteristics rather than a full exchange microstructure simulator.

18. **Meta-RL algorithm assumption**
   - Assume any standard RL allocator may be used, provided it optimizes trailing-252-episode Sharpe and is evaluated every 1000 steps.

19. **Episode definition assumption**
   - Assume one episode corresponds to one trading day or one fixed trading horizon; must be fixed before execution.

20. **Qualitative consistency assumption**
   - Assume “qualitatively consistent” means same sign of effect and same substantive conclusion relative to the -0.15 threshold across all seeds.

21. **Six-test family assumption**
   - Assume the six simultaneous tests correspond to six pre-registered hypothesis variants, such as by asset, regime, or scenario.

---

# 3) Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data and universe
1. **Exact contract list is not specified**
   - Only “crude oil, natural gas” are named.
   - No exchange symbols, contract variants, or nearby/deferred selection rules are given.

2. **Definition of “GSCI energy sector” is incomplete**
   - It may include more than the two named contracts.

3. **How passive GSCI investor concentration is observed or constructed is not specified**
   - No source for passive holdings is given.

4. **Whether concentration is measured by contracts, notional, delta-adjusted notional, or another basis is not specified.**

5. **Whether concentration is contract-level, instrument-level, or sector-level is not specified.**

6. **No exact source for bid-ask spread data is specified.**

7. **No exact source for FOMC/CPI calendar is specified.**

8. **No exact source/version/frequency for factor data is specified.**

## Sample construction
9. **Whether “2000–2024” means full calendar years, available sample dates, or inclusive endpoints is not specified.**

10. **Whether fewer than 100 trading days of history refers to contract history, continuous series history, or post-filter history is not specified.**

11. **How to handle excluded roll dates is not specified**
   - drop observation, shift roll, or skip contract.

12. **Whether “within 5 days” means calendar days or trading days is not specified.**

13. **Whether the 5-day exclusion window is before only, after only, or symmetric around announcements is not specified.**

14. **Whether bid-ask spread >2% excludes the entire contract, the day, or the roll event is not specified.**

15. **“Contract price” denominator for spread calculation is not specified**
   - last trade, settlement, mid, close.

## Continuous futures construction
16. **The exact implementation of `ratio_backward` is not specified**
   - especially around missing data and excluded roll dates.

17. **Roll trigger rule is not specified**
   - e.g., fixed days before expiry, volume switch, open-interest switch.

18. **Whether roll convention and adjustment method being both `ratio_backward` are redundant or distinct is not clarified.**

## Momentum strategy
19. **Momentum methodology is not specified**
   - time-series vs cross-sectional.

20. **Lookback exactness is not specified**
   - 12 calendar months vs 252 trading days.

21. **Whether to skip the most recent month is not specified.**

22. **Signal normalization is not specified.**

23. **Position sizing is not specified**
   - equal weight, inverse vol, risk parity, etc.

24. **Rebalance frequency is not specified.**

25. **Transaction costs/slippage are not specified.**

26. **Whether returns are excess returns, total returns, or spot-equivalent futures returns is not specified.**

27. **How to compute Sharpe in overlapping rolling windows for inference is not specified.**

## Hypothesis testing
28. **How the Sharpe differential is statistically tested is not specified**
   - difference in average rolling Sharpe, difference in returns, or another estimator.

29. **What exactly receives Newey-West correction is not specified.**

30. **The six simultaneous tests are not enumerated.**

31. **Whether Bonferroni applies to all analyses or only a subset is not specified.**

32. **No confidence interval procedure is specified.**

33. **No multiple-testing family registration procedure is specified.**

## Controls and models
34. **How GARCH(1,1) is used as a control is not specified.**

35. **Whether GARCH is fit separately by asset, by strategy, or pooled is not specified.**

36. **The factor model is internally inconsistent/ambiguous**
   - hypothesis mentions momentum factor exposure,
   - tests mention Fama-French three-factor OLS,
   - and “linearmodels, Fama-MacBeth” mixes two distinct regression ideas.

37. **Which factors are included is not specified.**

38. **Frequency alignment between futures returns and factor returns is not specified.**

39. **How factor-adjusted Sharpe is computed is not specified.**

40. **Markov switching model target series is not specified**
   - returns, volatility, Sharpe, concentration, or residuals.

41. **DCC-GARCH asset set is not specified.**

42. **DCC-GARCH purpose in the decision rule is not specified.**

## Simulation
43. **Simulation objective is not clearly linked to the primary empirical hypothesis.**

44. **Market simulator mechanics are not specified.**

45. **Execution model is not specified.**

46. **Order book/fill model for liquidity provider is not specified.**

47. **Mean reversion “3-month extremes” threshold is not specified.**

48. **Macro signals for macro allocator are not specified.**

49. **Energy/non-energy universe for macro allocator is not specified.**

50. **Meta-RL state space, action space, reward timing, and algorithm are not specified.**

51. **What an “episode” is not specified.**

52. **How 500,000 minimum episodes are distributed across scenarios and seeds is not specified.**

53. **How simulation outputs map to the empirical Sharpe differential is not specified.**

54. **What “qualitatively consistent” means is not specified.**

## Governance/audit
55. **How commitment is operationally verified is not specified.**

56. **Audit scoring rubric details are not specified.**

57. **What constitutes a revision cycle is not specified.**

58. **How SHA-256 signatures are attached/verified is not specified.**

---

# 4) Reproducibility rating: 2/5

## Rating: 2 out of 5

## Rationale
This specification is **partially reproducible**, but not strongly reproducible.

### Why it is not a 1/5
- It clearly states:
  - hypothesis direction and threshold
  - primary metric
  - sample period
  - data source family
  - roll/adjustment convention label
  - exclusion rules
  - statistical tools to use
  - passive capital scenarios
  - seeds
  - minimum training episodes
  - significance thresholds

These provide a meaningful scaffold.

### Why it is not higher than 2/5
Several core methodological components are too ambiguous to guarantee independent replication:

1. **Primary variable construction is underspecified**
   - passive concentration is central but not operationally defined.

2. **Momentum strategy is underspecified**
   - no exact signal, weighting, rebalance, or cost treatment.

3. **Main statistical design is underspecified**
   - unclear how Sharpe differential is estimated and tested.

4. **Factor control specification is inconsistent**
   - “Fama-French momentum factor exposure” conflicts with “three-factor OLS” and “Fama-MacBeth.”

5. **Simulation framework is highly underspecified**
   - agents are named, but mechanics are absent.

6. **Bonferroni family is undefined**
   - six simultaneous tests are referenced but not listed.

7. **Several exclusion rules lack operational detail**
   - especially roll-date handling and spread filtering.

### Practical implication
Two competent researchers could implement this spec and produce materially different results while both claiming compliance. That lowers reproducibility substantially.

---

# 5) Concise implementation recommendation

To make this executable with minimal ambiguity, pre-register the following before running:
1. exact contract universe
2. exact passive concentration formula and source
3. exact momentum signal and portfolio construction
4. exact roll trigger rule
5. exact handling of excluded roll dates
6. exact factor model
7. exact primary regression/test equation
8. exact six Bonferroni tests
9. exact simulation environment and episode definition
10. exact definition of “qualitatively consistent”

If you want, I can next turn this into a **formal reproducible protocol** with:
- a pre-registered decision table,
- exact equations,
- and a “must choose one option” list for every underspecified item.