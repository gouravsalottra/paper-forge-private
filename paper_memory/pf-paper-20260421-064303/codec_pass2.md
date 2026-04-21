Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 1) Full implementation steps in order

## Phase 0: Governance and run eligibility
1. **Verify pre-analysis status is committed**
   - The spec states the pre-analysis plan status is initially `UNCOMMITTED` and must be committed before execution.
   - Operationally, do not run the study until the status is treated as committed.
   - Record this as a prerequisite gate.

2. **Define the study scope exactly**
   - Universe: WRDS Compustat Futures, GSCI energy sector.
   - Instruments explicitly named: crude oil and natural gas.
   - Sample period: 2000–2024.
   - Main hypothesis: passive GSCI concentration above 30% of open interest reduces 12-month momentum Sharpe by at least 0.15 versus below 30%, controlling for GARCH(1,1) volatility and Fama-French momentum exposure.

3. **Set reproducibility controls**
   - Use seeds: `1337`, `42`, `9999`.
   - Require qualitative consistency across all three seeds before accepting any finding.
   - Log all random operations under each seed.

---

## Phase 1: Data acquisition and raw dataset construction
4. **Acquire futures data**
   - Pull daily futures data for GSCI energy sector contracts from WRDS Compustat Futures for 2000–2024.
   - Required fields implied by the spec:
     - prices
     - open interest
     - bid-ask spread
     - contract identifiers
     - trading dates
     - enough contract history to evaluate 100-day minimum
   - Because momentum and rolling are required, obtain contract-level time series rather than only continuous series.

5. **Acquire passive concentration inputs**
   - Construct or obtain passive GSCI investor concentration as a fraction of open interest for the relevant energy futures.
   - Since the hypothesis is based on “passive GSCI index investor concentration above 30% of open interest,” create a daily concentration measure for each relevant market and/or aggregate energy sector measure.

6. **Acquire macro announcement calendar**
   - Obtain dates for major macro announcements:
     - FOMC
     - CPI
   - Build a calendar covering 2000–2024.

7. **Acquire factor data for controls**
   - Obtain Fama-French factors and a momentum factor series, because the hypothesis mentions “Fama-French momentum factor exposure.”
   - Align factor frequency to daily if possible, or define a conversion/alignment rule.

---

## Phase 2: Contract filtering and preprocessing
8. **Apply minimum history exclusion**
   - Exclude contracts with fewer than 100 trading days of history.

9. **Apply bid-ask spread exclusion**
   - Exclude contracts where bid-ask spread exceeds 2% of contract price.
   - Implement this at the contract-date level or contract level; this is underspecified and must be fixed by assumption.

10. **Apply macro-announcement roll exclusion**
   - Identify roll dates.
   - Exclude roll dates within 5 days of FOMC or CPI announcements.
   - Because “within 5 days” is ambiguous, define whether this means calendar days or trading days and whether symmetric around the announcement date.

11. **Construct continuous futures series**
   - Use roll convention: `ratio_backward`.
   - Use adjustment method: `ratio_backward`.
   - Build continuous adjusted price series for crude oil and natural gas.
   - Ensure consistency between roll convention and adjustment implementation.

12. **Validate cleaned dataset**
   - Confirm sufficient coverage remains after exclusions.
   - Confirm daily continuity for return calculations and rolling windows.

---

## Phase 3: Variable construction
13. **Compute daily returns**
   - Compute daily log or simple returns on the adjusted continuous series.
   - This is not specified; choose one and document it.

14. **Construct 12-month momentum signal**
   - Build the momentum signal for the trend-following strategy using a 12-month lookback.
   - Since “12-month momentum signal, long/short” is underspecified, define:
     - lookback length in trading days
     - whether to skip the most recent month
     - signal normalization
     - position sizing rule

15. **Construct 3-month mean-reversion signal**
   - Build a mean-reversion signal that fades 3-month extremes.
   - Define “extremes” operationally.

16. **Construct passive concentration regimes**
   - Create concentration categories:
     - Low = 10% of open interest
     - Medium = 30%
     - High = 60%
   - Also create the binary threshold variable needed for the main hypothesis:
     - below 30%
     - above 30%
   - Decide how exact equality at 30% is handled.

17. **Construct rolling Sharpe ratio series**
   - Compute annualized Sharpe ratios over rolling 252-day windows.
   - Primary metric: Sharpe differential = high-concentration periods minus low-concentration periods.
   - Define annualization convention explicitly.

18. **Construct volatility control variables**
   - Fit GARCH(1,1) models with Normal innovations to relevant return series.
   - Extract conditional volatility estimates for use as controls or adjusted inference inputs.

19. **Construct factor exposure controls**
   - Estimate exposure to Fama-French factors and momentum factor using OLS / Fama-MacBeth as specified.
   - Because the spec mixes “three-factor” with “momentum factor exposure,” define the exact factor set used in the regression.

20. **Prepare regime variables**
   - Fit a 2-regime Markov switching model to detect market regimes.
   - Use regime labels for robustness or stratified analysis.

21. **Prepare cross-asset correlation variables**
   - Estimate DCC-GARCH between crude oil and natural gas return series.
   - Use dynamic correlations as additional diagnostics or controls.

---

## Phase 4: Strategy implementation
22. **Implement passive_gsci agent**
   - Mechanically rebalance to GSCI index weights.
   - Since exact GSCI energy weights are not provided, define a source and frequency for weights.
   - Constrain passive holdings to the scenario concentration levels where needed.

23. **Implement trend_follower agent**
   - Use the 12-month momentum signal.
   - Long/short across the energy futures universe.
   - Define leverage, scaling, and rebalancing frequency.

24. **Implement mean_reversion agent**
   - Fade 3-month extremes.
   - Define entry/exit thresholds and sizing.

25. **Implement liquidity_provider agent**
   - Post limit orders on both sides.
   - Since no market microstructure model is specified, define a simplified execution and fill model.

26. **Implement macro_allocator agent**
   - Switch energy/non-energy on macro signals.
   - Since the dataset scope is energy futures only, define how non-energy exposure is represented or whether this agent is simulated abstractly.

27. **Implement meta_rl agent**
   - Learn optimal allocation across all strategies.
   - Fitness = Sharpe ratio over trailing 252 episodes.
   - Evaluate every 1000 training steps.
   - Minimum training = 500,000 episodes across all scenarios and seeds.
   - Define RL algorithm, state space, action space, reward, and exploration policy because none are specified.

---

## Phase 5: Scenario simulation
28. **Define passive capital scenarios**
   - Low: 10% of open interest
   - Medium: 30%
   - High: 60%

29. **Run simulations under each seed**
   - For each seed in `[1337, 42, 9999]`:
     - initialize all stochastic components
     - run all passive capital scenarios
     - train meta_rl with at least the required episode count
     - record strategy returns, allocations, and diagnostics

30. **Ensure episode allocation satisfies minimum**
   - Confirm total training episodes across all scenarios and seeds is at least 500,000.
   - Because this is ambiguous, decide whether 500,000 applies per seed, per scenario, or total pooled.

31. **Generate momentum strategy performance by concentration regime**
   - For each scenario and/or observed concentration regime, compute rolling 252-day Sharpe ratios for the 12-month momentum strategy.
   - Separate high-concentration and low-concentration periods.

32. **Compute primary effect**
   - Calculate:
     - mean annualized rolling Sharpe during high concentration
     - mean annualized rolling Sharpe during low concentration
     - differential = high minus low
   - Compare against minimum effect size threshold of `-0.15`.

---

## Phase 6: Statistical testing
33. **Primary t-test**
   - Conduct a two-tailed t-test on the Sharpe differential.
   - Apply Newey-West HAC correction with 4 lags.
   - Primary significance threshold: `p < 0.05`.

34. **Multiple-testing correction**
   - Apply Bonferroni correction for 6 simultaneous tests.
   - Adjusted threshold: `p < 0.0083`.
   - Define the six tests explicitly because the spec does not enumerate them.

35. **GARCH-adjusted analysis**
   - Estimate GARCH(1,1) on returns.
   - Reassess whether the concentration effect remains after controlling for volatility clustering.

36. **Factor regression analysis**
   - Run OLS / Fama-MacBeth regressions with factor exposures.
   - Test whether the concentration effect survives after controlling for factor exposure, including momentum exposure.

37. **Markov switching robustness**
   - Estimate a 2-regime Markov switching model.
   - Check whether the concentration effect differs by regime or remains robust across regimes.

38. **DCC-GARCH robustness**
   - Estimate dynamic conditional correlations between crude oil and natural gas.
   - Assess whether changing cross-asset correlation explains the momentum Sharpe differential.

39. **Scenario-level comparisons**
   - Compare low, medium, and high passive capital scenarios.
   - Evaluate whether the threshold effect is monotonic or concentrated above 30%.

---

## Phase 7: Validity checks and acceptance criteria
40. **Economic significance check**
   - Reject findings smaller than `-0.15` Sharpe units as economically insignificant, even if statistically significant.

41. **Seed consistency check**
   - Accept a finding only if all three seeds produce qualitatively consistent results.
   - Define “qualitatively consistent” explicitly, since it is underspecified.

42. **Sensitivity checks**
   - Re-run with reasonable alternative assumptions where the spec is ambiguous:
     - return definition
     - concentration aggregation
     - momentum skip-month rule
     - spread exclusion granularity
   - Report whether conclusions are stable.

43. **Document all exclusions and sample attrition**
   - Number of contracts removed for:
     - insufficient history
     - spread > 2%
     - roll dates near macro announcements

44. **Prepare audit artifacts**
   - Produce signed outputs with SHA-256 signatures on all miner-like outputs as required by the spec.
   - Record methodology rubric evidence for auditability.
   - Since these are process requirements rather than scientific methodology, treat them as compliance outputs.

---

## Phase 8: Final interpretation
45. **Conclude hypothesis support**
   - Hypothesis is supported only if:
     - high concentration (>30%) has lower momentum Sharpe than low concentration (<30%)
     - differential is at most `-0.15`
     - statistically significant under required thresholds
     - robust to volatility and factor controls
     - consistent across all three seeds

46. **Report limitations due to underspecification**
   - Explicitly disclose every assumption made.
   - Distinguish direct replication from interpretive reconstruction.

---

# 2) Assumptions needed due to underspecification

These assumptions are necessary because the spec does not fully define implementation details.

1. **Universe assumption**
   - Assume the GSCI energy sector in this study consists only of crude oil and natural gas, because those are the only instruments explicitly listed.

2. **Data frequency assumption**
   - Assume daily data throughout, because rolling 252-day windows and daily futures data are implied.

3. **Return definition assumption**
   - Assume daily log returns for modeling and Sharpe calculations, unless simple returns are preferred for consistency with the chosen libraries.

4. **Momentum construction assumption**
   - Assume 12-month momentum uses 252 trading days.
   - Assume no skip-month unless explicitly added as a robustness check.

5. **Mean-reversion construction assumption**
   - Assume 3-month extremes are based on 63 trading-day cumulative return z-scores or percentile thresholds.

6. **Concentration measurement assumption**
   - Assume passive GSCI concentration is measured daily as passive GSCI open interest divided by total open interest.
   - If contract-level concentration is available, aggregate to market-level using open-interest weights.

7. **Threshold handling assumption**
   - Assume “above 30%” means strictly `> 0.30` and “below 30%” means strictly `< 0.30`.
   - Treat exactly `0.30` as medium/threshold and exclude from binary high-vs-low tests, or assign to low/medium by rule.

8. **Sharpe calculation assumption**
   - Assume annualized Sharpe = mean daily excess return divided by daily standard deviation times sqrt(252).
   - Assume risk-free rate is zero or negligible unless daily risk-free data are added.

9. **Excess return assumption**
   - Assume Sharpe uses raw returns if no risk-free series is specified.

10. **Spread exclusion assumption**
   - Assume the 2% bid-ask spread rule is applied at the contract-date level, excluding observations rather than entire contracts, unless too sparse.

11. **Roll-date exclusion assumption**
   - Assume “within 5 days” means within ±5 trading days of FOMC/CPI dates.

12. **Roll schedule assumption**
   - Assume a standard front-to-next eligible contract roll schedule if no exact GSCI roll calendar is provided.

13. **Ratio-backward implementation assumption**
   - Assume backward ratio adjustment is applied multiplicatively to preserve return continuity.

14. **Factor model assumption**
   - Assume the regression includes Fama-French three factors plus a momentum factor, despite the wording inconsistency.

15. **Fama-MacBeth usage assumption**
   - Assume Fama-MacBeth is used as a robustness panel-style estimator across assets/time, even though the asset universe is very small.

16. **GARCH control assumption**
   - Assume GARCH conditional volatility enters either as a control variable in regressions or as a volatility-adjusted robustness analysis.

17. **Markov switching target assumption**
   - Assume the Markov switching model is fit to momentum strategy returns or underlying futures returns.

18. **DCC-GARCH scope assumption**
   - Assume DCC-GARCH is estimated only between crude oil and natural gas.

19. **Simulation necessity assumption**
   - Assume the agent-based simulation is part of the methodology and not merely ancillary, so all six agents must be implemented.

20. **Meta-RL algorithm assumption**
   - Assume a standard RL allocator such as PPO, DQN, or actor-critic can be used; exact choice is not specified.

21. **Episode definition assumption**
   - Assume one episode corresponds to one trading day or one rolling decision interval; must be fixed before implementation.

22. **Training minimum assumption**
   - Assume 500,000 episodes is the total minimum per full experiment, not per scenario-seed combination, unless stricter interpretation is chosen.

23. **Qualitative consistency assumption**
   - Assume qualitative consistency means same sign of effect, same directional conclusion on hypothesis support, and no seed reversing the main inference.

24. **Six simultaneous tests assumption**
   - Assume the six tests correspond to predefined model/specification variants or scenario comparisons, since they are not enumerated.

25. **Macro allocator assumption**
   - Assume non-energy allocation is represented by a cash benchmark or synthetic outside option if non-energy futures are not included in the dataset.

26. **Liquidity provider assumption**
   - Assume a stylized fill model based on midprice and spread because order book data are not specified.

27. **Passive GSCI weights assumption**
   - Assume GSCI index weights are externally sourced and rebalanced on a fixed schedule, likely monthly.

28. **Risk management assumption**
   - Assume position scaling is volatility-normalized or equal-risk unless otherwise specified.

---

# 3) Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data and sample
1. **Exact contract universe is unclear**
   - “GSCI energy sector” is named, but only crude oil and natural gas are explicitly listed.
   - It is unclear whether refined products or additional energy contracts are included.

2. **Exact WRDS fields are not specified**
   - Required variables are implied but not enumerated.

3. **Passive GSCI concentration source is unspecified**
   - The spec does not explain how passive investor concentration is observed or inferred.

4. **Open interest aggregation level is unspecified**
   - Contract-level, commodity-level, or sector-level concentration is not defined.

5. **Treatment of missing data is unspecified**
   - No imputation or deletion rules are given.

## Rolling and price construction
6. **Exact roll trigger is unspecified**
   - Only `ratio_backward` is given; the actual roll date rule is not.

7. **Roll exclusion interaction is unclear**
   - If a roll date falls near macro announcements, it is unclear whether the roll is shifted, omitted, or the observation window is dropped.

8. **Adjustment implementation details are unspecified**
   - Ratio-backward is named, but not the exact formula.

## Exclusions
9. **“Fewer than 100 trading days of history” is ambiguous**
   - History before what date? Listing date? Inclusion date? Entire sample?

10. **Spread exclusion granularity is unspecified**
   - Exclude entire contracts or only dates where spread > 2%?

11. **“Bid-ask spread exceeds 2% of contract price” formula is unspecified**
   - Relative spread could mean ask-bid divided by mid, close, or settlement.

12. **“Within 5 days” is ambiguous**
   - Trading days or calendar days?
   - Before only, after only, or symmetric around announcement?

13. **Major macro announcements list is incomplete**
   - Only FOMC and CPI are named; no source or release-time handling is specified.

## Strategy definitions
14. **12-month momentum signal is underspecified**
   - Lookback exact length
   - skip-month or not
   - ranking method
   - long/short construction
   - weighting scheme
   - rebalance frequency

15. **3-month extremes are underspecified**
   - No threshold or signal formula.

16. **Liquidity provider behavior is underspecified**
   - No order placement logic, inventory limits, fill model, or transaction cost model.

17. **Macro allocator is underspecified**
   - No macro signals defined.
   - No non-energy asset universe defined.

18. **Passive GSCI rebalancing is underspecified**
   - No exact weights, rebalance dates, or implementation mechanics.

19. **Meta-RL design is underspecified**
   - No algorithm, state variables, action space, reward shaping, constraints, or architecture.

20. **Episode definition is unspecified**
   - Critical for the 500,000 episode requirement.

## Metrics and inference
21. **Sharpe ratio formula is unspecified**
   - Excess vs raw returns
   - arithmetic vs geometric mean
   - annualization convention

22. **Primary metric aggregation is unclear**
   - Is the differential computed from average rolling Sharpe windows, from scenario-level Sharpe, or from time-partitioned samples?

23. **High vs low concentration periods are not fully defined**
   - What happens to medium or exactly 30% periods?

24. **The six simultaneous tests are not enumerated**
   - Bonferroni correction cannot be applied unambiguously without this.

25. **Use of GARCH as a control is underspecified**
   - In regression? Standardization? Residual modeling?

26. **Factor model wording is inconsistent**
   - “Fama-French three-factor OLS regression” conflicts with “controlling for ... momentum factor exposure.”

27. **Fama-MacBeth applicability is unclear**
   - With only a tiny asset universe, the intended panel structure is uncertain.

28. **Markov switching target variable is unspecified**
   - Underlying returns, strategy returns, or concentration series?

29. **DCC-GARCH purpose is unspecified**
   - Diagnostic only, control variable, or hypothesis test component?

30. **Newey-West application target is unspecified**
   - Applied to Sharpe differential series, regression residuals, or rolling-window estimates?

## Simulation and seeds
31. **Why seeds matter is underspecified for deterministic components**
   - Seeds imply stochastic simulation, but the empirical analysis itself may be deterministic.

32. **“Qualitatively consistent” is undefined**
   - No formal criterion.

33. **500,000 minimum episodes scope is ambiguous**
   - Total, per seed, per scenario, or per agent?

34. **Scenario integration with observed data is unclear**
   - Are passive concentration scenarios simulated counterfactuals, or are they empirical partitions?

35. **How simulation outputs connect to the primary empirical hypothesis is unclear**
   - The spec mixes empirical asset pricing and multi-agent simulation without defining the bridge.

## Compliance and audit
36. **Commit mechanism is external and unspecified**
   - The methodology cannot independently enforce it.

37. **Audit procedures are process requirements, not methodological details**
   - No operational definitions are given for implementation.

38. **DataPassport signature generation process is unspecified**
   - Only the requirement is stated.

---

# 4) Reproducibility rating: 2/5

## Rating: 2 out of 5

## Rationale
The specification provides a strong high-level research objective and several concrete parameters, but it is not sufficiently complete for high-confidence exact replication.

### What is well specified
- Hypothesis direction and threshold
- Primary metric concept
- Sample period
- Data source family
- Roll convention and adjustment label
- Exclusion categories
- Statistical tools to use
- Passive capital scenarios
- Seed list
- Minimum effect size
- Training episode minimum

### What prevents strong reproducibility
- Core variables are not operationalized precisely, especially passive concentration.
- Strategy definitions are incomplete.
- The six simultaneous tests are not identified.
- The factor model is internally inconsistent.
- The simulation framework is highly underspecified.
- The bridge between empirical analysis and agent simulation is unclear.
- Several exclusion rules lack implementation granularity.
- Sharpe computation details are omitted.
- Roll timing mechanics are omitted despite being crucial in futures studies.

### Why not 1/5
It is still possible to produce a defensible implementation because the spec gives:
- a clear hypothesis,
- a defined sample,
- named methods,
- threshold values,
- and scenario structure.

So this is not wholly non-reproducible; it is partially reproducible with explicit assumptions.

---

# 5) Concise implementation recommendation

If forced to implement from this spec alone, the most defensible path is:

1. Build daily continuous crude oil and natural gas futures series using backward ratio adjustment.
2. Construct daily passive concentration measures relative to open interest.
3. Partition periods into below-30% and above-30% concentration.
4. Implement a simple 12-month momentum strategy on the energy futures universe.
5. Compute rolling 252-day annualized Sharpe ratios.
6. Test the high-minus-low Sharpe differential with HAC-adjusted inference.
7. Add GARCH volatility controls and factor regressions.
8. Run robustness with Markov switching and DCC-GARCH.
9. Separately implement the six-agent simulation with explicit assumptions and use seeds consistently.
10. Accept findings only if effect size ≤ -0.15 and direction is stable across all seeds.

If you want, I can next turn this into a **formal pseudocode protocol** or a **methods section written like a replication appendix**.