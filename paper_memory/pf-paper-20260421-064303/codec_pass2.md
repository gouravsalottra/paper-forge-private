Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation of Methodology From Spec Alone

## Overall assessment
This spec is **partially implementable but materially underspecified**.  
A reasonable reproduction can be built, but several choices must be imposed by assumption, especially around:

- exact momentum portfolio construction,
- how passive concentration is measured,
- how the simulation agents interact with the empirical tests,
- how Fama-French factors apply to commodity futures,
- how DCC-GARCH and Markov switching are integrated into the main hypothesis test,
- what the “6 simultaneous tests” are.

---

# 1) Full implementation steps in order

## Phase 0: Governance and run eligibility
1. **Verify pre-analysis plan status**
   - Require that pre-analysis status is `COMMITTED` before running.
   - If not committed, reject the run.

2. **Set reproducibility controls**
   - Use seeds `[1337, 42, 9999]`.
   - Ensure every stochastic component is seeded.
   - Require final conclusions to be qualitatively consistent across all three seeds.

3. **Define output audit metadata**
   - Attach SHA-256 signatures to all generated outputs.
   - Record configuration, assumptions, package versions, and seed used.

---

## Phase 1: Data acquisition and universe definition
4. **Acquire futures data**
   - Pull WRDS Compustat Futures data for the GSCI energy sector from 2000–2024.
   - Restrict to the contracts explicitly named in the spec:
     - crude oil
     - natural gas

5. **Acquire supporting fields**
   For each contract/date, obtain at minimum:
   - prices needed for returns,
   - open interest,
   - bid and ask or bid-ask spread,
   - contract identifiers,
   - expiration dates,
   - roll-relevant fields,
   - any field needed to identify passive GSCI concentration if available.

6. **Acquire event calendar**
   - Build a calendar of major macro announcements:
     - FOMC dates
     - CPI release dates
   - Cover the full 2000–2024 sample.

7. **Acquire factor data**
   - Obtain Fama-French three factors and momentum factor data for the sample period.
   - Align to the same frequency as the futures return series.

---

## Phase 2: Contract cleaning and continuous series construction
8. **Apply minimum history exclusion**
   - Exclude contracts with fewer than 100 trading days of history.

9. **Apply bid-ask spread exclusion**
   - Exclude contracts where bid-ask spread exceeds 2% of contract price.
   - Perform this at the contract-date level unless a contract-level interpretation is chosen by assumption.

10. **Identify roll dates**
   - Construct roll dates for each futures chain.

11. **Exclude roll dates near macro announcements**
   - Remove roll dates within 5 days of FOMC or CPI announcements.

12. **Construct continuous futures series**
   - Use roll convention: `ratio_backward`.
   - Use adjustment method: `ratio_backward`.
   - Build continuous adjusted price series separately for crude oil and natural gas.

13. **Compute daily returns**
   - Compute daily log or simple returns from the adjusted continuous series.
   - Use one convention consistently throughout.

---

## Phase 3: Passive concentration measurement
14. **Define passive GSCI investor concentration**
   - For each date and asset, compute passive GSCI concentration as:
     \[
     \text{Passive Concentration}_{t} = \frac{\text{Passive GSCI Open Interest}_{t}}{\text{Total Open Interest}_{t}}
     \]
   - This requires identifying passive GSCI-linked open interest.

15. **Classify concentration regimes**
   - Low scenario: 10% of open interest
   - Medium scenario: 30% of open interest
   - High scenario: 60% of open interest

16. **Create binary hypothesis regime**
   - Define:
     - **Low-concentration period**: concentration < 30%
     - **High-concentration period**: concentration > 30%
   - Decide treatment of exactly 30% by assumption.

17. **Aggregate concentration across assets if needed**
   - If the hypothesis is tested at the sector level rather than per asset, aggregate crude oil and natural gas concentration into a GSCI-energy concentration measure.

---

## Phase 4: Momentum strategy construction
18. **Define 12-month momentum signal**
   - For each asset/date, compute trailing 12-month momentum using approximately 252 trading days.
   - Determine whether to skip the most recent month by assumption.

19. **Generate long/short positions**
   - Assign long exposure to positive momentum assets and short exposure to negative momentum assets.
   - Since only two assets are named, define cross-sectional or time-series momentum explicitly by assumption.

20. **Construct daily momentum strategy returns**
   - Compute strategy returns from the long/short positions.
   - Include transaction timing and rebalancing frequency by assumption.

21. **Compute rolling Sharpe ratios**
   - Over rolling 252-day windows, compute annualized Sharpe ratio:
     \[
     SR_t = \frac{\mu_t}{\sigma_t}\sqrt{252}
     \]
   - Use daily strategy returns within each rolling window.

22. **Split Sharpe observations by concentration regime**
   - Label each rolling-window Sharpe observation as high- or low-concentration based on the concentration regime over that window.
   - Define whether regime is based on window-end date, window-average concentration, or majority-of-days by assumption.

23. **Compute primary metric**
   - Compute:
     \[
     \Delta SR = SR_{\text{high concentration}} - SR_{\text{low concentration}}
     \]
   - Compare against minimum effect size threshold of -0.15 Sharpe units.

---

## Phase 5: Volatility control with GARCH
24. **Fit GARCH(1,1) models**
   - For each relevant return series, fit GARCH(1,1) with:
     - p = 1
     - q = 1
     - Normal distribution

25. **Extract conditional volatility**
   - Obtain conditional volatility estimates from the fitted GARCH models.

26. **Control for volatility clustering**
   - Incorporate GARCH conditional volatility into the momentum profitability analysis.
   - This can be done by:
     - volatility-adjusting returns, or
     - including conditional volatility as a control in regression.
   - Exact implementation must be chosen by assumption.

---

## Phase 6: Factor exposure control
27. **Prepare factor-aligned dataset**
   - Align momentum strategy returns with:
     - Fama-French three factors
     - momentum factor

28. **Estimate factor exposure**
   - Run OLS-style factor regressions using the specified framework:
     - linearmodels
     - Fama-MacBeth
   - Estimate exposure of momentum strategy returns to the factors.

29. **Obtain residual or controlled returns**
   - Use regression residuals or adjusted estimates to isolate momentum profitability net of factor exposure.
   - Exact use in the main test must be chosen by assumption.

---

## Phase 7: Main statistical hypothesis testing
30. **Run primary two-tailed t-test**
   - Test whether the Sharpe differential between high- and low-concentration periods differs from zero.
   - Apply Newey-West HAC correction with 4 lags.

31. **Evaluate economic significance**
   - Declare effects smaller than -0.15 Sharpe units as economically insignificant even if statistically significant.
   - Since the hypothesis is directional and negative, require observed differential to be at most -0.15 for support.

32. **Apply Bonferroni correction**
   - For 6 simultaneous tests, use adjusted threshold:
     \[
     p < 0.0083
     \]
   - Define the six tests explicitly by assumption.

33. **Determine hypothesis support**
   - A finding supports the hypothesis only if:
     - differential is negative,
     - magnitude is at least -0.15,
     - p-value passes the required threshold,
     - result is qualitatively consistent across all three seeds.

---

## Phase 8: Regime analysis
34. **Fit Markov switching model**
   - Fit a 2-regime Markov switching model to relevant return or Sharpe series.
   - Use it to detect latent market regimes.

35. **Compare concentration effect across regimes**
   - Evaluate whether the concentration-momentum relationship differs by inferred regime.

---

## Phase 9: Cross-asset dependence analysis
36. **Fit DCC-GARCH model**
   - Estimate dynamic conditional correlations between crude oil and natural gas returns.

37. **Assess whether correlation dynamics affect momentum profitability**
   - Examine whether high passive concentration coincides with elevated cross-asset correlation and weaker momentum performance.

---

## Phase 10: Agent-based / simulation layer
38. **Define six agents**
   Implement:
   - passive_gsci
   - trend_follower
   - mean_reversion
   - liquidity_provider
   - macro_allocator
   - meta_rl

39. **Specify market environment**
   - Build a simulation environment for commodity futures trading in energy markets.
   - Include price evolution, open interest, order interaction, and passive capital scenarios.

40. **Implement passive capital scenarios**
   - Low: 10%
   - Medium: 30%
   - High: 60%
   of open interest.

41. **Implement agent behaviors**
   - passive_gsci: mechanically rebalance to GSCI weights
   - trend_follower: 12-month momentum long/short
   - mean_reversion: fade 3-month extremes
   - liquidity_provider: post limit orders on both sides
   - macro_allocator: switch energy/non-energy on macro signals
   - meta_rl: allocate across all strategies

42. **Train meta_rl**
   - Minimum 500,000 training episodes across all scenarios and seeds.
   - Evaluate fitness every 1000 training steps.
   - Fitness = Sharpe ratio over trailing 252 episodes.

43. **Run simulations under each seed**
   - Repeat all stochastic simulations for seeds 1337, 42, 9999.

44. **Check qualitative consistency**
   - Require the same directional conclusion across all seeds.

45. **Integrate simulation findings with empirical findings**
   - Use simulation results as robustness or mechanism evidence, unless promoted to primary evidence by assumption.

---

## Phase 11: Reporting and validation
46. **Summarize primary empirical result**
   - Report Sharpe differential high minus low concentration.
   - Report HAC-corrected t-stat and p-value.
   - Report whether effect exceeds -0.15 threshold.

47. **Report controlled analyses**
   - GARCH-controlled results
   - factor-controlled results
   - Markov regime results
   - DCC-GARCH results

48. **Report simulation results**
   - By passive capital scenario and seed.
   - Include whether trend-following Sharpe deteriorates as passive concentration rises.

49. **Apply audit gates**
   - Require bidirectional audit before paper writing.
   - Require methodology score at least 7/10.
   - Allow at most 3 revision cycles.

50. **Finalize reproducibility package**
   - Include assumptions log, parameter settings, seed-specific outputs, and signatures.

---

# 2) Assumptions needed due to underspecification

These assumptions are necessary to make the methodology executable.

## Data and universe assumptions
1. **Universe assumption**
   - “GSCI energy sector” is implemented using only the explicitly listed contracts: crude oil and natural gas.

2. **Frequency assumption**
   - All analyses are performed at daily frequency because rolling 252-day windows and GARCH imply daily data.

3. **Open interest availability assumption**
   - WRDS data contains enough information to estimate passive GSCI-linked open interest, or a proxy can be constructed.

---

## Continuous futures construction assumptions
4. **Roll schedule assumption**
   - Roll occurs on a deterministic rule such as a fixed number of business days before expiry if not directly specified.

5. **Ratio-backward implementation assumption**
   - Continuous prices are adjusted multiplicatively backward through history using roll ratios.

6. **Return convention assumption**
   - Daily log returns are used unless simple returns are required for compatibility with Sharpe calculations.

---

## Exclusion rule assumptions
7. **100 trading days rule assumption**
   - The exclusion is applied per individual listed contract before inclusion in the continuous chain.

8. **Bid-ask spread rule assumption**
   - The 2% threshold is applied at the daily observation level; excluded observations are removed rather than dropping the entire contract unless violations are persistent.

9. **Macro announcement exclusion assumption**
   - “Within 5 days” means ±5 calendar days or ±5 trading days; one must be chosen.
   - Roll dates near announcements are omitted from rolling/adjustment transitions rather than dropping the entire surrounding return window.

---

## Passive concentration assumptions
10. **Passive concentration measurement assumption**
   - Passive GSCI concentration is measured as passive GSCI-linked open interest divided by total open interest.

11. **Proxy assumption if passive holdings unavailable**
   - If direct passive GSCI holdings are unavailable, concentration is proxied using index-related positions or another documented proxy.

12. **Threshold handling assumption**
   - Exactly 30% concentration is assigned either to high, low, or excluded; must be fixed in advance.

13. **Window labeling assumption**
   - A rolling Sharpe window is labeled high or low concentration based on the average concentration over the window.

---

## Momentum strategy assumptions
14. **Momentum type assumption**
   - Use time-series momentum because only two assets are named and cross-sectional ranking is weak with two instruments.

15. **Lookback assumption**
   - 12-month momentum uses the prior 252 trading days.

16. **Skip-month assumption**
   - No 1-month skip is applied unless explicitly added as a robustness check.

17. **Position sizing assumption**
   - Equal-weight positions across available assets.

18. **Rebalancing assumption**
   - Rebalance daily or monthly; one must be chosen. Monthly is conventional, daily is easier to align with rolling windows.

19. **Transaction cost assumption**
   - No explicit transaction cost model is specified; either omit costs or use bid-ask spread as an implicit liquidity filter only.

---

## Sharpe ratio assumptions
20. **Annualization assumption**
   - Sharpe is annualized using \(\sqrt{252}\).

21. **Risk-free rate assumption**
   - Excess returns are approximated by raw futures returns if no daily risk-free series is specified.

22. **Window sufficiency assumption**
   - Require full 252 observations to compute each rolling Sharpe.

---

## Statistical testing assumptions
23. **Unit of inference assumption**
   - The t-test is performed on rolling-window Sharpe observations or on return differences; one must be chosen.

24. **Newey-West implementation assumption**
   - HAC correction with exactly 4 lags is applied to the primary regression/test residuals.

25. **Six simultaneous tests assumption**
   - The six tests are defined as a prespecified family, e.g.:
     - crude oil primary
     - natural gas primary
     - pooled energy primary
     - GARCH-controlled
     - factor-controlled
     - regime-conditioned
   - This is not stated and must be imposed.

---

## GARCH and factor model assumptions
26. **GARCH target series assumption**
   - GARCH is fit to daily momentum strategy returns and/or underlying asset returns.

27. **Control implementation assumption**
   - “Controlling for GARCH volatility clustering” means including conditional volatility as a control variable in regression.

28. **Factor applicability assumption**
   - Fama-French factors and momentum factor are treated as valid controls for commodity futures strategy returns despite being equity-origin factors.

29. **Fama-MacBeth applicability assumption**
   - Fama-MacBeth is adapted to this setting even though the panel dimension is very small if only two assets are used.

---

## Markov switching and DCC-GARCH assumptions
30. **Markov switching target assumption**
   - The 2-regime model is fit to pooled energy momentum returns or Sharpe series.

31. **DCC-GARCH target assumption**
   - DCC-GARCH is estimated on crude oil and natural gas daily returns.

32. **Role assumption**
   - These models are robustness/mechanism analyses rather than part of the primary test statistic.

---

## Simulation assumptions
33. **Simulation necessity assumption**
   - The agent-based simulation is part of the methodology and must be implemented, even though the hypothesis is empirical.

34. **Environment assumption**
   - Historical data can be used as the environment backbone, with agents interacting over replayed or synthetic market states.

35. **Meta-RL algorithm assumption**
   - Any standard RL allocator may be used if not specified.

36. **Episode definition assumption**
   - An episode corresponds to one trading day, one rolling window, or one simulation path; must be chosen.

37. **Qualitative consistency assumption**
   - “Qualitatively consistent” means same sign and same accept/reject conclusion across seeds.

38. **Scenario integration assumption**
   - Passive capital scenarios are imposed exogenously in simulation rather than inferred from historical data.

---

## Audit/process assumptions
39. **Audit implementation assumption**
   - Audit requirements are procedural gates and do not alter statistical methodology.

40. **DataPassport assumption**
   - SHA-256 signatures satisfy the stated signature requirement if no additional schema is specified.

---

# 3) Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data specification gaps
1. **Exact contract list is unclear**
   - “GSCI energy sector” is broader than the two listed contracts, but only crude oil and natural gas are named.

2. **Exact WRDS fields are not specified**
   - No field names or required variables are listed.

3. **Passive GSCI investor holdings source is unspecified**
   - The spec requires passive concentration but does not specify where passive GSCI-linked open interest comes from.

4. **Whether concentration is asset-level or sector-level is unspecified**

5. **Whether analysis is daily, weekly, or monthly is not explicitly stated**
   - 252-day windows imply daily, but not explicitly.

---

## Continuous futures construction gaps
6. **Exact roll trigger is unspecified**
   - Only `ratio_backward` is given, not when to roll.

7. **How to handle excluded roll dates is unspecified**
   - Skip roll? delay roll? interpolate? drop observations?

8. **Whether returns are log or arithmetic is unspecified**

---

## Exclusion rule gaps
9. **“Contracts with fewer than 100 trading days of history” is ambiguous**
   - Listed contract history or continuous-series history?

10. **“Exclude contracts where bid-ask spread exceeds 2%” is ambiguous**
   - Entire contract or only violating dates?

11. **“Within 5 days” of macro announcements is ambiguous**
   - Trading days or calendar days?

12. **Macro announcement source/calendar is unspecified**

---

## Momentum strategy gaps
13. **Momentum definition is unspecified**
   - Time-series vs cross-sectional.

14. **Signal formula is unspecified**
   - Cumulative return, average return, risk-adjusted return, etc.

15. **Whether to skip the most recent month is unspecified**

16. **Rebalancing frequency is unspecified**

17. **Position sizing is unspecified**
   - Equal weight, volatility scaled, notional scaled, risk parity, etc.

18. **Leverage constraints are unspecified**

19. **Shorting assumptions are unspecified**

20. **Transaction costs/slippage are unspecified**

---

## Sharpe ratio and primary metric gaps
21. **How rolling windows are assigned to concentration regimes is unspecified**

22. **Whether Sharpe is computed on raw or excess returns is unspecified**

23. **Whether high-minus-low is computed from average Sharpe windows or from strategy returns conditioned on regime is unspecified**

24. **Whether overlapping rolling windows are acceptable for inference is unspecified**

---

## Statistical testing gaps
25. **Exact test object is unspecified**
   - Difference in mean rolling Sharpe? regression coefficient? difference in returns?

26. **How Newey-West is applied to Sharpe ratios is unspecified**

27. **The six simultaneous tests are not identified**

28. **Whether Bonferroni applies to all analyses or only a subset is unspecified**

29. **Whether the hypothesis is tested one-sided or two-sided in practice is ambiguous**
   - Spec says two-tailed, but hypothesis is directional.

---

## GARCH/factor model gaps
30. **What series receives GARCH modeling is unspecified**

31. **How GARCH enters the control framework is unspecified**

32. **Why Fama-French three factors are appropriate for commodity futures is not justified**

33. **How the momentum factor is included relative to “three-factor” wording is ambiguous**
   - Three-factor plus momentum becomes four factors.

34. **How Fama-MacBeth is structured with such a small asset set is unspecified**

35. **Whether factor regressions use daily or monthly data is unspecified**

---

## Markov switching and DCC-GARCH gaps
36. **Target variable for Markov switching is unspecified**

37. **How regime detection affects the main conclusion is unspecified**

38. **DCC-GARCH estimation details are unspecified**
   - univariate margins, innovation distribution, estimation window, etc.

39. **Whether DCC-GARCH is descriptive or inferential is unspecified**

---

## Simulation/agent gaps
40. **Relationship between empirical analysis and simulation is unspecified**

41. **Market simulator design is unspecified**

42. **State space, action space, and reward for meta_rl are unspecified**

43. **RL algorithm is unspecified**

44. **Episode definition is unspecified**

45. **How passive capital scenarios alter market mechanics is unspecified**

46. **How GSCI weights are obtained for passive_gsci is unspecified**

47. **How macro signals are defined for macro_allocator is unspecified**

48. **How 3-month extremes are defined for mean_reversion is unspecified**

49. **How liquidity_provider order placement is modeled is unspecified**

50. **How simulation outputs map to the paper hypothesis is unspecified**

---

## Seed/reproducibility gaps
51. **Many empirical components are deterministic**
   - It is unclear which parts are expected to vary by seed besides simulation and possibly regime model initialization.

52. **“Qualitatively consistent” is not formally defined**

53. **How to aggregate results across seeds is unspecified**

---

## Process/audit gaps
54. **How pre-analysis commitment is represented is unspecified**

55. **Audit rubric details are unspecified**

56. **DataPassport format beyond SHA-256 is unspecified**

---

# 4) Reproducibility rating: 2/5

## Rating: 2 out of 5

## Rationale
This spec contains enough information to build a **plausible approximation**, but not enough to guarantee a faithful reproduction.

### What helps reproducibility
- Clear hypothesis direction and threshold.
- Defined sample period: 2000–2024.
- Named data source.
- Named assets: crude oil and natural gas.
- Roll convention and adjustment method specified.
- Key statistical tools are listed:
  - Newey-West with 4 lags
  - GARCH(1,1)
  - Fama-MacBeth
  - Markov switching with 2 regimes
  - DCC-GARCH
- Seed list is explicit.
- Exclusion rules are partially specified.
- Minimum effect size is explicit.

### What hurts reproducibility
- Core variable **passive GSCI concentration** is not operationalized.
- Momentum strategy construction is not fully defined.
- The primary test object is ambiguous.
- The six simultaneous tests are not identified.
- The role of simulation versus empirical analysis is unclear.
- Several listed methods are named but not integrated into a coherent estimation pipeline.
- Fama-French factor usage for commodity futures is underspecified and conceptually awkward.
- Many implementation-critical details are omitted:
  - roll timing,
  - return convention,
  - regime labeling,
  - transaction costs,
  - RL setup,
  - exact inference unit.

### Why not 1/5
It is not completely unreproducible because the broad empirical design is visible and a reasonable implementation can be assembled.

### Why not 3/5 or higher
Too many central methodological choices must be invented by the implementer, especially around:
- concentration measurement,
- momentum portfolio definition,
- statistical test construction,
- simulation architecture.

---

# 5) Recommended minimal faithful implementation choice set

If forced to implement from this spec alone, the most defensible minimal version would be:

1. Use **daily data** for crude oil and natural gas from 2000–2024.
2. Build **ratio-backward continuous futures** with a fixed roll rule.
3. Exclude:
   - listed contracts with <100 trading days,
   - daily observations with spread >2%,
   - roll transitions within ±5 trading days of FOMC/CPI.
4. Define **passive concentration** as passive GSCI-linked open interest / total open interest, using the best available proxy if direct holdings are unavailable.
5. Use **time-series 12-month momentum** on each asset with 252-day lookback, no skip month, equal weights.
6. Compute **daily strategy returns** and **rolling 252-day annualized Sharpe**.
7. Label windows by **average concentration over the window**, with:
   - low < 30%
   - high > 30%
   - exactly 30% excluded.
8. Primary test:
   - compare mean rolling Sharpe in high vs low periods,
   - use HAC/Newey-West 4-lag inference.
9. Control analyses:
   - include GARCH(1,1) conditional volatility as a regression control,
   - regress strategy returns on FF3 + momentum factor and use residualized returns.
10. Treat Markov switching and DCC-GARCH as **robustness/mechanism analyses**.
11. Implement simulation separately as a **supporting mechanism study**, not the primary hypothesis test.
12. Require same directional conclusion across seeds.

---

If you want, I can next convert this into a **formal implementation protocol** with:
- exact equations,
- a decision table for every ambiguity,
- and a “spec-faithful default parameterization” ready to execute.