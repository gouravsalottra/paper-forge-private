Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 1) Full implementation steps in order

## Phase 0 — Governance and run eligibility
1. **Verify pre-analysis status is committed**
   - The spec states the pre-analysis plan status is initially `UNCOMMITTED` and must be committed before execution.
   - Operationally, do not proceed unless the run is marked as committed in the experiment governance layer.

2. **Define the exact research question operationally**
   - Test whether periods with **passive GSCI investor concentration > 30% of open interest** in GSCI energy futures have **12-month momentum Sharpe ratios at least 0.15 lower** than periods with concentration below 30%.
   - Include controls for:
     - GARCH(1,1) volatility clustering
     - Fama-French momentum factor exposure
   - Use 2000–2024 data for GSCI energy sector futures: crude oil and natural gas.

3. **Register all required seeds and scenario grid**
   - Seeds: `1337`, `42`, `9999`
   - Passive capital scenarios: `10%`, `30%`, `60%` of open interest
   - Require qualitative consistency across all seeds.

---

## Phase 1 — Data acquisition and raw dataset construction
4. **Acquire futures data from WRDS Compustat Futures**
   - Pull daily data for GSCI energy sector contracts covering:
     - crude oil
     - natural gas
   - Date range: 2000-01-01 through 2024-12-31 or latest available 2024 date.
   - Required fields, as implied by the spec:
     - prices sufficient to construct continuous futures returns
     - open interest
     - bid-ask spread or bid and ask quotes
     - contract identifiers
     - trading dates
     - contract history length
   - If available, also collect volume and expiration metadata to support rolling.

5. **Acquire macro announcement calendar**
   - Obtain dates for:
     - FOMC announcements
     - CPI releases
   - Build a calendar to exclude roll dates within 5 days of these announcements.

6. **Acquire factor data for momentum exposure control**
   - Obtain Fama-French factor data plus a momentum factor series, because the hypothesis explicitly mentions momentum factor exposure while the statistical tests mention “three-factor OLS regression.”
   - Align factor frequency to daily if possible; otherwise define a conversion rule.

7. **Acquire any additional data needed for simulation agents**
   - For macro signals used by `macro_allocator`, obtain macro variables if needed.
   - For non-energy allocation decisions, obtain non-energy benchmark or futures data if required by the simulation design.
   - For DCC-GARCH cross-asset correlation, obtain the additional asset return series to correlate against if cross-asset means beyond crude oil and natural gas.

---

## Phase 2 — Data cleaning and exclusions
8. **Apply contract-history exclusion**
   - Exclude contracts with fewer than 100 trading days of history.

9. **Apply bid-ask spread exclusion**
   - Exclude contracts where bid-ask spread exceeds 2% of contract price.
   - Compute spread ratio as:
     - `(ask - bid) / mid` or another explicit denominator assumption if only spread and price are available.

10. **Identify roll dates under the specified convention**
   - Construct roll dates for each futures chain using `ratio_backward` roll convention and `ratio_backward` adjustment method.

11. **Apply macro-announcement roll exclusion**
   - Exclude roll dates within 5 calendar days or trading days of FOMC/CPI announcements; this is underspecified and must be fixed by assumption.
   - Rebuild continuous series after excluding affected roll dates or omit affected observations, depending on implementation choice.

12. **Validate cleaned sample coverage**
   - Confirm sufficient post-exclusion data remains for crude oil and natural gas over 2000–2024.

---

## Phase 3 — Continuous futures construction
13. **Construct continuous futures price series**
   - For each commodity, build a continuous adjusted series using:
     - roll convention: `ratio_backward`
     - adjustment method: `ratio_backward`
   - Ensure consistency between rolling and adjustment.

14. **Compute daily returns**
   - Compute daily log returns or simple returns; this is underspecified and must be fixed by assumption.
   - Use these returns for momentum strategy performance and econometric models.

15. **Create open-interest-based passive concentration measure**
   - For each date and commodity, compute passive GSCI investor concentration as:
     - passive GSCI holdings / total open interest
   - Because passive holdings are not directly defined in the spec, derive or proxy them according to an explicit assumption.
   - Label concentration regimes:
     - Low: 10%
     - Medium: 30%
     - High: 60%
   - For the primary hypothesis, define:
     - high-concentration periods: `> 30%`
     - low-concentration periods: `< 30%`
   - Decide treatment of exactly `30%` observations by assumption.

---

## Phase 4 — Strategy construction
16. **Implement the 12-month momentum strategy**
   - Build a momentum signal for crude oil and natural gas futures.
   - Use a 12-month lookback window.
   - Determine whether to skip the most recent month; this is underspecified and must be fixed by assumption.
   - Determine whether the strategy is:
     - cross-sectional between crude and gas, or
     - time-series momentum per asset, then aggregated.
   - Generate long/short positions accordingly.

17. **Compute momentum strategy returns**
   - Apply positions to daily futures returns.
   - Include transaction cost treatment if any; not specified, so assumption required.
   - Aggregate across assets into a portfolio return series.

18. **Compute rolling annualized Sharpe ratios**
   - Use rolling 252-day windows.
   - Annualize Sharpe ratio.
   - Primary metric:
     - Sharpe(high concentration periods) minus Sharpe(low concentration periods)
   - Note: the hypothesis expects a negative differential of at least `-0.15`.

---

## Phase 5 — Agent-based simulation layer
19. **Define the simulation environment**
   - Create an environment spanning the energy futures market with at least crude oil and natural gas.
   - Include market state variables needed by all six agents:
     - prices/returns
     - open interest
     - volatility
     - liquidity/spread
     - macro signals if used

20. **Implement passive_gsci agent**
   - Mechanically rebalance to GSCI index weights.
   - Use passive capital scenarios:
     - 10%, 30%, 60% of open interest
   - Translate target passive capital into holdings or order flow.

21. **Implement trend_follower agent**
   - Use 12-month momentum signal.
   - Long/short according to signal.

22. **Implement mean_reversion agent**
   - Fade 3-month extremes.
   - Define “extremes” explicitly by assumption.

23. **Implement liquidity_provider agent**
   - Post limit orders on both sides.
   - Define spread placement, inventory limits, and fill logic by assumption.

24. **Implement macro_allocator agent**
   - Switch energy/non-energy exposure based on macro signals.
   - Define macro signals and switching rule by assumption.

25. **Implement meta_rl agent**
   - Learn optimal allocation across all strategies.
   - State space, action space, reward function, algorithm class, and exploration policy are all underspecified and must be fixed by assumption.
   - Fitness function:
     - trailing 252-episode Sharpe ratio
     - evaluated every 1000 training steps

26. **Train simulation across seeds and scenarios**
   - Minimum total training episodes: 500,000 across all scenarios and seeds.
   - Run all three seeds.
   - Run all passive capital scenarios.
   - Record whether findings are qualitatively consistent across seeds.

27. **Extract simulation outputs relevant to the hypothesis**
   - For each seed and scenario, compute momentum profitability metrics.
   - Compare low vs medium/high passive concentration conditions.
   - Preserve outputs with required audit signature metadata.

---

## Phase 6 — Econometric modeling
28. **Primary comparison: high vs low concentration Sharpe differential**
   - Partition observations into concentration regimes.
   - Compute rolling 252-day annualized Sharpe ratios for the momentum strategy.
   - Estimate the differential:
     - `Sharpe_high - Sharpe_low`

29. **Conduct two-tailed t-test with Newey-West HAC correction**
   - Use 4 lags.
   - Test whether the differential differs from zero.
   - Also compare against economic significance threshold of `-0.15`.

30. **Apply Bonferroni correction**
   - There are 6 simultaneous tests.
   - Use adjusted threshold:
     - `p < 0.0083`
   - Define the six tests explicitly; the spec does not enumerate them, so assumption required.

31. **Fit GARCH(1,1) model**
   - Use Normal distribution.
   - Model volatility clustering in momentum returns or underlying futures returns; this is underspecified and must be fixed by assumption.
   - Use conditional volatility estimates as controls or adjusted residual inputs.

32. **Estimate factor exposure regression**
   - Run OLS regression with Fama-French factors and momentum factor exposure control.
   - The spec says “Fama-French three-factor OLS regression” and also “linearmodels, Fama-MacBeth,” which are not the same procedure in standard usage.
   - Choose and document one operational interpretation or run both as robustness checks.
   - Estimate whether concentration effect remains after factor adjustment.

33. **Run Markov switching regime detection**
   - Use `k_regimes=2`.
   - Fit to either momentum returns, concentration series, or volatility-adjusted returns; this is underspecified and must be fixed by assumption.
   - Use regimes to assess whether concentration effects are regime-dependent.

34. **Run DCC-GARCH cross-asset correlation analysis**
   - Estimate dynamic conditional correlations across assets.
   - At minimum use crude oil and natural gas.
   - Optionally include non-energy assets if required by the simulation design.
   - Assess whether passive concentration coincides with elevated cross-asset correlation and reduced momentum profitability.

---

## Phase 7 — Hypothesis decision logic
35. **Evaluate statistical significance**
   - Primary threshold: `p < 0.05`
   - Simultaneous-test threshold: `p < 0.0083`

36. **Evaluate economic significance**
   - Effect must be `<= -0.15` Sharpe units.
   - Smaller effects are economically insignificant even if statistically significant.

37. **Evaluate seed consistency**
   - The finding is valid only if all three seeds produce qualitatively consistent results.
   - Define “qualitatively consistent” explicitly by assumption, e.g. same sign and same significance/economic-significance direction.

38. **Determine final support for hypothesis**
   - Conclude support only if:
     - high concentration periods show lower momentum Sharpe than low concentration periods,
     - differential is at least `-0.15`,
     - significance criteria are met,
     - result survives specified controls,
     - result is consistent across all seeds.

---

## Phase 8 — Audit and reporting
39. **Attach DataPassport SHA-256 signatures to all outputs**
   - Ensure all generated outputs are signed as required.

40. **Prepare methodology audit package**
   - Include enough detail for bidirectional audit.
   - Ensure methodology quality would satisfy HAWK score threshold of 7/10.

41. **Limit revision cycles**
   - If methodology review fails, revise up to 3 cycles maximum.

42. **Report results**
   - Report:
     - sample construction
     - exclusions
     - concentration regime definitions
     - momentum strategy definition
     - Sharpe differential
     - t-test with HAC
     - Bonferroni-adjusted results
     - GARCH control results
     - factor-adjusted results
     - Markov-switching results
     - DCC-GARCH results
     - seed-by-seed consistency
     - scenario-by-scenario outcomes

---

# 2) Assumptions needed due to underspecification

These assumptions are necessary to make the spec executable.

1. **Passive concentration measurement**
   - Assume passive GSCI investor concentration can be observed or proxied daily as passive GSCI-linked notional holdings divided by total open interest.
   - If direct passive holdings are unavailable, assume concentration is imposed by simulation scenarios rather than inferred from historical holdings.

2. **Treatment of the 30% threshold**
   - Assume:
     - high concentration = `> 30%`
     - low concentration = `< 30%`
     - exactly `30%` is excluded from the primary binary comparison or assigned to medium only.

3. **Return definition**
   - Assume daily log returns for futures and strategy returns unless simple returns are preferred for Sharpe consistency.

4. **Momentum strategy design**
   - Assume time-series momentum for each asset using trailing 252 trading days.
   - Assume no one-month skip unless explicitly added as a robustness check.
   - Assume equal-weight aggregation across crude oil and natural gas.

5. **Sharpe annualization**
   - Assume annualized Sharpe = mean daily return / std daily return × sqrt(252).

6. **Rolling-window assignment**
   - Assume each 252-day Sharpe window is classified by the average concentration over that same window.

7. **Transaction costs**
   - Assume no explicit transaction costs unless bid-ask spread is used as a trading-cost proxy.
   - Alternatively, assume spread-based costs deducted on position changes.

8. **Roll exclusion timing**
   - Assume “within 5 days” means 5 trading days centered around the macro announcement date or preceding/following only; must choose one.
   - Most practical assumption: exclude roll dates occurring within ±5 calendar days of announcement dates.

9. **Bid-ask spread denominator**
   - Assume spread threshold is `(ask - bid) / midprice > 2%`.

10. **Factor model interpretation**
   - Assume factor control includes market, size, value, and momentum if available, despite the text saying “three-factor” while also requiring momentum exposure control.
   - If only three factors are used, add momentum separately.

11. **Fama-MacBeth interpretation**
   - Assume this means use the `linearmodels` package for panel-style factor estimation or cross-sectional robustness, even though the main regression is described as OLS.

12. **GARCH target series**
   - Assume GARCH(1,1) is fit to momentum strategy returns, not raw futures returns, because the hypothesis concerns momentum profitability.

13. **Markov switching target series**
   - Assume the 2-regime model is fit to momentum strategy returns or Sharpe differential series.

14. **DCC-GARCH asset set**
   - Assume DCC-GARCH is estimated on crude oil and natural gas returns at minimum.

15. **Simulation necessity**
   - Assume the simulation-agent framework is part of the required methodology, not optional context.

16. **Meta-RL algorithm**
   - Assume a standard reinforcement learning allocator, such as PPO, DQN, or actor-critic, because no algorithm is specified.

17. **Episode definition**
   - Assume one episode corresponds to one trading day or one rolling decision interval; must be fixed explicitly.

18. **Qualitative consistency across seeds**
   - Assume this means same sign of effect and same conclusion regarding economic significance.

19. **Six simultaneous tests**
   - Assume the six tests correspond to six predefined model/specification comparisons, such as:
     - crude only
     - gas only
     - equal-weight portfolio
     - low vs medium
     - low vs high
     - pooled high vs low
   - Or another explicit six-test family.

20. **Macro allocator signals**
   - Assume macro signals are derived from the FOMC/CPI calendar and/or inflation/rate surprises.

21. **Non-energy benchmark for macro allocator**
   - Assume a broad non-energy commodity basket or cash proxy if non-energy futures are unavailable.

22. **Sample endpoint**
   - Assume use of all available 2024 data through the final trading day in the dataset.

---

# 3) Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data and measurement
1. **How passive GSCI investor concentration is measured historically**
2. **Whether passive concentration is observed data, estimated, or simulation-imposed**
3. **Exact contract universe within “GSCI energy sector”**
4. **Whether only front-month contracts are used before rolling**
5. **Exact fields available from the stated data source**
6. **Whether open interest is contract-level or aggregated across maturities**
7. **How to aggregate open interest across contracts**
8. **How to map passive holdings to open interest**
9. **Whether concentration is commodity-specific or pooled across energy futures**
10. **Whether dates are trading dates or calendar dates for all filters**

## Rolling and price construction
11. **Exact roll trigger under `ratio_backward`**
12. **Which contract is rolled into which and when**
13. **Whether roll occurs on fixed days before expiry, volume switch, or open-interest switch**
14. **How excluded roll dates are handled if a scheduled roll is blocked by macro-announcement proximity**
15. **Whether returns are log or simple**
16. **Whether prices are settlement, close, or another field**

## Exclusions
17. **Whether “fewer than 100 trading days of history” refers to individual contracts or continuous series eligibility**
18. **How bid-ask spread is computed if only one spread field exists**
19. **Whether the 2% spread rule excludes entire contracts, dates, or observations**
20. **Whether “within 5 days” means calendar days or trading days**
21. **Whether “within 5 days” means before, after, or symmetric around announcements**
22. **How overlapping FOMC and CPI windows are handled**

## Momentum strategy
23. **Whether momentum is time-series or cross-sectional**
24. **Whether the lookback is exactly 252 trading days or 12 calendar months**
25. **Whether there is a one-month skip**
26. **How signals are transformed into positions**
27. **Whether positions are binary, scaled, or volatility-targeted**
28. **How crude and natural gas are weighted**
29. **Whether leverage is allowed**
30. **Whether transaction costs are included**
31. **Whether rebalancing is daily, monthly, or another frequency**

## Primary metric
32. **How rolling Sharpe windows are assigned to concentration regimes**
33. **Whether Sharpe is computed from daily returns within each window**
34. **Whether windows can overlap**
35. **How annualization is done**
36. **How missing observations are handled**
37. **Whether the differential is averaged over windows or estimated in a regression framework**

## Statistical testing
38. **What exact sample enters the t-test**
39. **Whether the t-test is on window-level Sharpe differences or return-level differences**
40. **How Newey-West is applied to rolling-window statistics**
41. **What the six simultaneous tests are**
42. **Whether Bonferroni applies to all analyses or only a predefined family**
43. **Whether the minimum effect size is tested formally or used as a decision threshold only**

## GARCH / factor / regime models
44. **Whether GARCH is fit to strategy returns or asset returns**
45. **How GARCH enters as a control in the main hypothesis test**
46. **Whether conditional volatility is included as a regressor or used to standardize returns**
47. **The contradiction between “Fama-French momentum factor exposure” and “three-factor OLS regression”**
48. **The contradiction between “OLS regression” and “Fama-MacBeth”**
49. **Whether factor data are daily or monthly**
50. **How factor frequencies are aligned to futures returns**
51. **Whether Markov switching is fit to returns, Sharpe, volatility, or concentration**
52. **How regime outputs are used in inference**
53. **Which assets are included in DCC-GARCH cross-asset correlation**
54. **How DCC-GARCH results connect to the primary hypothesis**

## Simulation agents
55. **Whether simulation is required for the primary empirical test or only supplementary**
56. **Exact market microstructure of the simulation**
57. **How passive_gsci rebalances mechanically**
58. **What GSCI weights are used and whether they vary over time**
59. **How trend_follower interacts with the empirical momentum strategy**
60. **How mean_reversion defines “3-month extremes”**
61. **How liquidity_provider quotes and gets filled**
62. **What macro signals drive macro_allocator**
63. **What non-energy assets are available to macro_allocator**
64. **What RL algorithm powers meta_rl**
65. **State space for meta_rl**
66. **Action space for meta_rl**
67. **Reward function beyond stated fitness evaluation**
68. **Training schedule across scenarios and seeds**
69. **What an episode is**
70. **How 500,000 episodes are allocated across seeds/scenarios**
71. **How simulation outputs map to the empirical hypothesis**
72. **What “qualitatively consistent” means across seeds**

## Decision rules and reporting
73. **Whether exact 30% observations are included in low, high, or excluded**
74. **Whether medium scenario is part of the primary hypothesis test**
75. **Whether high concentration means only 60% scenario in simulation or all observed >30% periods empirically**
76. **How to combine empirical and simulation evidence**
77. **What constitutes final acceptance if some tests pass and others fail**
78. **How audit requirements affect methodology execution**
79. **What exactly must be signed in “all MINER outputs” when no system architecture is defined**
80. **How HAWK methodology scoring is operationalized**

---

# 4) Reproducibility rating: 2 / 5

## Rating: 2 out of 5

## Rationale
The specification provides a strong **high-level research objective** and several important constraints:
- hypothesis
- sample period
- asset class
- primary metric
- several statistical tests
- exclusion rules
- seeds
- scenario levels

However, reproducibility is limited because many implementation-critical details are missing or internally inconsistent:

### Strengths
- Clear hypothesis and effect-size threshold
- Clear date range and broad data source
- Clear concentration thresholds/scenarios
- Clear requirement for rolling 252-day Sharpe
- Clear mention of HAC, GARCH, Markov switching, DCC-GARCH
- Clear seed policy and consistency requirement

### Weaknesses
- No operational definition of **passive GSCI investor concentration**
- No exact **momentum strategy construction**
- No exact **continuous futures roll trigger**
- No exact **test family of six simultaneous tests**
- Contradiction between:
  - “Fama-French momentum factor exposure”
  - “three-factor OLS regression”
  - “Fama-MacBeth”
- Simulation framework is highly underspecified:
  - no environment
  - no RL algorithm
  - no episode definition
  - no mapping from simulation to empirical inference
- Several exclusion rules lack precise implementation details
- Audit/governance requirements are procedural but not methodologically operationalized

### Why not 1/5
It is not completely irreproducible because the core empirical structure is identifiable and a reasonable implementation can be built.

### Why not 3/5 or higher
Too many central components require discretionary choices that could materially change results, especially:
- concentration measurement
- momentum definition
- factor model specification
- simulation design

---

# 5) Concise implementation recommendation

If forced to implement from this spec alone, the most defensible approach is:

1. Build continuous crude oil and natural gas futures with backward-ratio adjustment.
2. Apply all exclusions explicitly.
3. Define passive concentration as a daily commodity-level ratio of passive GSCI holdings to open interest, or use scenario-imposed concentration if historical holdings are unavailable.
4. Implement a daily time-series 12-month momentum strategy, equal-weighted across crude and gas.
5. Compute rolling 252-day annualized Sharpe ratios.
6. Compare windows with concentration above 30% versus below 30%.
7. Test the differential with Newey-West HAC t-tests.
8. Require effect size ≤ -0.15.
9. Add GARCH(1,1), factor-adjusted regression, Markov switching, and DCC-GARCH as robustness/control layers.
10. Run all passive-capital scenarios and all three seeds in the simulation layer.
11. Accept the finding only if sign and economic significance are consistent across all seeds.

If you want, I can next turn this into a **formal pseudocode protocol** or a **methods section written like a paper**.