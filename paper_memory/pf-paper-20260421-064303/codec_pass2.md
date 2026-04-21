Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 0. Scope of what is being implemented
Implement an empirical study testing:

> Whether passive GSCI index investor concentration above 30% of open interest in GSCI energy futures reduces 12-month momentum strategy Sharpe ratios by at least 0.15 relative to periods below 30%, while controlling for GARCH(1,1) volatility clustering and Fama-French momentum factor exposure.

The implementation must cover:
- data construction
- exclusions
- futures rolling/adjustment
- momentum strategy construction
- concentration regime definition
- rolling Sharpe computation
- statistical testing
- GARCH / factor / regime / DCC-GARCH analyses
- simulation agents and meta-RL training
- seed consistency checks
- audit/pre-analysis gating requirements as procedural constraints

---

# 1. Full implementation steps in order

## Step 1: Formalize the study design
Define the study universe and outputs before touching data.

1. Set sample period to **2000–2024**.
2. Restrict instruments to **GSCI energy sector futures**, explicitly listed as:
   - crude oil
   - natural gas
3. Define the main comparison:
   - **low concentration**: passive GSCI concentration below 30% of open interest
   - **high concentration**: passive GSCI concentration above 30% of open interest
4. Define passive capital scenarios for simulation:
   - low = 10%
   - medium = 30%
   - high = 60%
5. Define primary metric:
   - annualized Sharpe ratio differential
   - computed over rolling **252-trading-day windows**
   - differential = high-concentration Sharpe minus low-concentration Sharpe
6. Define minimum economically meaningful effect:
   - differential must be **≤ -0.15** to count as economically significant
7. Define seeds:
   - 1337
   - 42
   - 9999
8. Define validity rule:
   - result must be qualitatively consistent across all three seeds

---

## Step 2: Enforce procedural gating requirements
These are not analytical methods but must be implemented as run prerequisites.

1. Require pre-analysis plan status to be **COMMITTED** before execution.
2. Reject execution if status is not COMMITTED.
3. Require DataPassport SHA-256 signature on all extracted/mined outputs.
4. Require audit workflow constraints:
   - CODEC bidirectional audit before paper-writing stage
   - HAWK methodology score at least 7/10
   - maximum 3 HAWK revision cycles

Because the spec references external governance systems, implementation should include validation hooks or metadata checks rather than assuming these happen manually.

---

## Step 3: Acquire raw data
Obtain all required raw inputs.

1. Pull futures data from **WRDS Compustat Futures** for crude oil and natural gas from 2000–2024.
2. Required raw fields should include, at minimum:
   - date
   - contract identifier
   - underlying commodity
   - expiration/maturity
   - price series needed for returns
   - open interest
   - bid
   - ask
   - volume if available
3. Obtain or construct **GSCI-related passive investor concentration** data as share of open interest for the relevant futures.
4. Obtain calendar data for **major macro announcements**:
   - FOMC dates
   - CPI release dates
5. Obtain Fama-French factor data needed for the factor regression.
6. Obtain any cross-asset data needed for DCC-GARCH if cross-asset correlation is to be estimated beyond the two energy contracts.
7. Obtain any macro signal inputs needed by the macro allocator agent.

---

## Step 4: Define the futures continuation series
Construct continuous futures series using the specified convention.

1. For each commodity, sort contracts by date and maturity.
2. Apply **roll convention = ratio_backward**.
3. Apply **adjustment method = ratio_backward**.
4. Produce a continuous adjusted price series for each commodity.
5. Preserve mapping from adjusted series back to underlying contract dates so exclusion rules can still be applied around roll dates and contract-level history.

---

## Step 5: Apply exclusion rules
Apply all exclusions before strategy estimation.

1. Exclude contracts with **fewer than 100 trading days of history**.
2. Exclude observations/roll events where the **roll date is within 5 days of major macro announcements**:
   - FOMC
   - CPI
3. Exclude contracts where **bid-ask spread exceeds 2% of contract price**.
   - Compute spread percentage as `(ask - bid) / contract price`
   - Define contract price consistently (assumption required; see underspecification section)
4. Rebuild the continuous series after exclusions if excluded contracts affect rolling continuity.
5. Log all exclusions with counts by commodity, year, and reason.

---

## Step 6: Construct daily returns
1. Compute daily returns from the adjusted continuous price series.
2. Decide whether returns are simple or log returns and use consistently throughout.
3. Align returns across commodities on a common trading calendar.
4. Handle missing values due to exclusions or holidays.

---

## Step 7: Measure passive investor concentration
Construct the key explanatory regime variable.

1. For each date and commodity, compute or ingest **passive GSCI investor concentration as % of open interest**.
2. Aggregate to a study-level concentration measure for “GSCI energy futures.”
   - This likely requires combining crude oil and natural gas concentration into one energy-sector concentration metric.
3. Label each date into concentration regimes:
   - low: < 30%
   - medium: = or around 30% if needed for scenario analysis
   - high: > 30%
4. For the primary hypothesis test, compare **high (>30%)** vs **low (<30%)** periods.
5. Store concentration both as:
   - continuous variable
   - categorical regime variable

---

## Step 8: Build the 12-month momentum strategy
Construct the main tested strategy.

1. Define a **12-month momentum signal** for each commodity.
2. Use historical returns over a 12-month lookback window.
3. Convert signal into long/short positions.
4. Aggregate positions across crude oil and natural gas into a momentum portfolio.
5. Compute daily portfolio returns.
6. Compute rolling **252-day annualized Sharpe ratios** for the momentum portfolio.
7. Partition rolling Sharpe observations into high- and low-concentration periods based on the concentration regime at each evaluation date.

---

## Step 9: Compute the primary metric
1. For each rolling 252-day window, compute annualized Sharpe ratio of the momentum strategy.
2. Group windows by concentration regime:
   - high concentration
   - low concentration
3. Compute:
   - mean Sharpe in high-concentration periods
   - mean Sharpe in low-concentration periods
4. Compute primary differential:
   - **Sharpe_high − Sharpe_low**
5. Compare the estimated differential to the minimum effect threshold:
   - economically meaningful only if differential ≤ -0.15

---

## Step 10: Run the primary statistical test
1. Conduct a **two-tailed t-test** on the Sharpe differential between high- and low-concentration periods.
2. Apply **Newey-West HAC correction with 4 lags** to account for autocorrelation/heteroskedasticity in rolling-window estimates.
3. Use significance threshold:
   - primary: p < 0.05
4. Record:
   - estimated differential
   - HAC-adjusted standard error
   - t-statistic
   - p-value
   - economic significance indicator (≤ -0.15 or not)

---

## Step 11: Apply multiple-testing correction
1. Because the spec states **6 simultaneous tests**, apply **Bonferroni correction**.
2. Adjusted threshold:
   - p < 0.0083
3. For each of the six tests, report:
   - unadjusted p-value
   - Bonferroni-adjusted significance decision

---

## Step 12: Fit GARCH(1,1) volatility controls
1. Fit a **GARCH(1,1)** model with:
   - p = 1
   - q = 1
   - Normal distribution
2. Apply to the momentum strategy return series, or to underlying commodity returns if used as controls.
3. Extract conditional volatility estimates.
4. Use these volatility estimates to control for volatility clustering in the main analysis.
5. Re-estimate the concentration effect conditional on GARCH-based volatility controls.

---

## Step 13: Run factor exposure regression
1. Obtain Fama-French factor data.
2. Construct regression of momentum strategy returns on:
   - Fama-French three factors
   - momentum factor exposure as stated in the hypothesis text
3. Estimate using OLS / Fama-MacBeth framework as specified.
4. Use regression residuals or adjusted returns to assess whether the concentration effect remains after controlling for factor exposure.
5. Report coefficients, standard errors, t-stats, and residual Sharpe comparisons.

---

## Step 14: Run Markov switching regime detection
1. Fit a **2-regime Markov switching model** to relevant return or volatility series.
2. Infer latent regimes.
3. Test whether high passive concentration aligns with one regime more than the other.
4. Check whether the momentum Sharpe deterioration is concentrated in a specific latent regime.
5. Report transition probabilities and regime-specific performance.

---

## Step 15: Run DCC-GARCH cross-asset correlation analysis
1. Select the asset set for cross-asset correlation analysis.
2. Fit DCC-GARCH to the selected return series.
3. Estimate time-varying correlations.
4. Test whether high passive concentration periods coincide with elevated cross-asset correlation.
5. Assess whether correlation changes help explain momentum Sharpe deterioration.

---

## Step 16: Implement simulation agents
Implement all six agents named in the spec.

1. **passive_gsci**
   - mechanically rebalances to GSCI index weights
2. **trend_follower**
   - uses 12-month momentum signal
   - takes long/short positions
3. **mean_reversion**
   - fades 3-month extremes
4. **liquidity_provider**
   - posts limit orders on both sides
5. **macro_allocator**
   - switches energy/non-energy based on macro signals
6. **meta_rl**
   - learns optimal allocation across all strategies

For each agent:
- define state inputs
- define action space
- define reward function
- define portfolio accounting
- define transaction/roll handling
- define constraints

---

## Step 17: Simulate passive capital scenarios
1. Run simulations under passive concentration scenarios:
   - 10%
   - 30%
   - 60%
2. For each scenario, simulate market interaction among the six agents.
3. Ensure passive_gsci agent size corresponds to the scenario’s share of open interest.
4. Measure resulting momentum strategy performance under each scenario.
5. Compare scenario-level Sharpe ratios and concentration effects.

---

## Step 18: Train the meta-RL allocator
1. Train the **meta_rl** agent across all scenarios and seeds.
2. Minimum training budget:
   - **500,000 episodes across all scenarios and seeds**
3. Evaluate fitness as:
   - Sharpe ratio over trailing **252 episodes**
   - evaluated every **1000 training steps**
4. Save evaluation history for each seed and scenario.
5. Determine whether learned allocations qualitatively support the main hypothesis.

---

## Step 19: Run all seeds
Repeat the full stochastic components for each seed:
- 1337
- 42
- 9999

For each seed:
1. initialize all random processes
2. rerun simulation/training
3. recompute outputs
4. compare sign, magnitude direction, and significance consistency

A finding is valid only if all three seeds are qualitatively consistent.

---

## Step 20: Define the six simultaneous tests explicitly
Because Bonferroni is specified for six tests, implementation must enumerate six tests. A practical ordering is:

1. Primary Sharpe differential test: high vs low concentration
2. GARCH-controlled concentration effect test
3. Factor-controlled concentration effect test
4. Markov-regime-conditioned concentration effect test
5. DCC-GARCH correlation-mediated effect test
6. Simulation scenario contrast test (e.g., 60% vs 10%)

This enumeration is necessary because the spec says six simultaneous tests but does not list exactly which six are included for Bonferroni.

---

## Step 21: Summarize results against decision rules
For each seed and pooled analysis, report:

1. Sharpe_high
2. Sharpe_low
3. differential = high − low
4. p-value (HAC-adjusted)
5. Bonferroni significance
6. economic significance (≤ -0.15)
7. consistency across seeds
8. whether hypothesis is supported

Decision rule:
- supported only if:
  - differential ≤ -0.15
  - statistically significant at required threshold
  - qualitatively consistent across all three seeds

---

## Step 22: Produce audit-ready outputs
1. Attach SHA-256 signatures to all mined outputs.
2. Produce methodology summary suitable for audit.
3. Record all assumptions and underspecified choices.
4. Record exclusion counts and data attrition.
5. Record seed-by-seed reproducibility summary.

---

# 2. Assumptions needed due to underspecification

These assumptions are necessary to make the spec executable.

## Data and instrument assumptions
1. **Instrument mapping assumption**  
   “GSCI energy sector” is assumed to mean only the two explicitly named commodities:
   - crude oil
   - natural gas

2. **Contract selection assumption**  
   Use the front-month tradable contract sequence unless a different maturity ladder is required.

3. **Open interest concentration assumption**  
   Passive GSCI concentration is assumed measurable daily as:
   `passive GSCI open interest / total open interest`.

4. **Energy-sector aggregation assumption**  
   Aggregate crude oil and natural gas concentration using open-interest-weighted averaging unless commodity-specific analyses are run separately.

---

## Return and Sharpe assumptions
5. **Return definition assumption**  
   Use daily log returns or simple returns consistently; if not specified, simple excess returns are a common default.

6. **Sharpe annualization assumption**  
   Annualized Sharpe = mean daily return / std daily return × sqrt(252).

7. **Risk-free rate assumption**  
   If not provided, assume zero daily risk-free rate or use a standard daily risk-free proxy.

8. **Rolling-window labeling assumption**  
   A rolling Sharpe window is assigned to the concentration regime of its end date.

---

## Momentum strategy assumptions
9. **12-month momentum construction assumption**  
   Use a 252-trading-day lookback.

10. **Skip-month assumption**  
    No skip-month is specified; assume none unless explicitly added.

11. **Portfolio weighting assumption**  
    Equal-weight crude oil and natural gas signals unless GSCI weights are intended.

12. **Signal threshold assumption**  
    Positive trailing return = long, negative trailing return = short.

---

## Exclusion-rule assumptions
13. **Major macro announcement window assumption**  
    “Within 5 days” means ±5 calendar days or ±5 trading days; one must be chosen. Trading days is more operationally consistent.

14. **Bid-ask spread denominator assumption**  
    “2% of contract price” means midpoint price unless last trade/settlement is specified.

15. **Contract history assumption**  
    “Fewer than 100 trading days of history” refers to each individual listed contract before inclusion in the continuation chain.

---

## Statistical assumptions
16. **t-test unit assumption**  
    The t-test is applied to rolling-window Sharpe observations or to regime-specific mean returns transformed into Sharpe estimates; the former is assumed.

17. **Newey-West implementation assumption**  
    HAC correction is applied to the regression/intercept difference series with lag 4.

18. **Bonferroni family assumption**  
    The six simultaneous tests are assumed to be the six major analyses listed in Step 20.

19. **Factor model assumption**  
    Because the hypothesis mentions “Fama-French momentum factor exposure” but the tests mention “three-factor,” assume regression includes FF3 plus a momentum factor.

20. **Fama-MacBeth assumption**  
    Since Fama-MacBeth is usually cross-sectional and the study is time-series-heavy, assume it is used only if cross-sectional panels across contracts are constructed; otherwise standard time-series OLS may be needed.

---

## Regime and DCC assumptions
21. **Markov switching target assumption**  
    Fit the Markov switching model to momentum returns or volatility, not to concentration directly.

22. **DCC asset universe assumption**  
    DCC-GARCH is estimated at minimum on crude oil and natural gas returns; broader asset inclusion is optional if available.

---

## Simulation assumptions
23. **Market simulator assumption**  
    A stylized multi-agent market simulator must be built because no simulator mechanics are specified.

24. **Execution-cost assumption**  
    Transaction costs, slippage, and fill logic must be assumed; otherwise agent results are not meaningful.

25. **Meta-RL algorithm assumption**  
    Any standard RL allocator algorithm may be used because none is specified.

26. **Episode definition assumption**  
    One episode likely corresponds to one trading period or one portfolio decision interval; must be fixed explicitly.

27. **Qualitative consistency assumption**  
    “Qualitatively consistent” means same directional conclusion and similar significance/economic-significance outcome across seeds.

---

## Governance assumptions
28. **Pre-analysis lock assumption**  
    “pap_lock” is treated as a metadata status store, not a statistical object.

29. **Audit-system assumption**  
    CODEC, HAWK, SIGMA_JOB1, QUILL, FORGE are workflow systems external to the analysis and must be represented as validation checkpoints.

---

# 3. Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data specification underspecified
1. **Exact contract symbols/identifiers** for crude oil and natural gas are not specified.
2. **Which exchanges/contracts** within WRDS Compustat Futures are included is not specified.
3. **Exact fields** required from WRDS are not listed.
4. **How passive GSCI investor concentration is observed or constructed** is not specified.
5. **Whether concentration is daily, weekly, or monthly** is not specified.
6. **How to aggregate concentration across crude oil and natural gas** is not specified.
7. **Whether non-energy assets are needed** for macro allocator or DCC-GARCH is not specified.
8. **Source of Fama-French factors** is not specified.
9. **Which momentum factor series** is intended is not specified.
10. **Source of FOMC and CPI calendars** is not specified.

---

## Futures construction underspecified
11. **Exact roll trigger** for ratio_backward is not specified.
12. **Which contract is rolled into which** is not specified.
13. **Whether roll occurs on fixed days, volume switch, or open-interest switch** is not specified.
14. **How ratio_backward is implemented mathematically** is not specified.
15. **Whether settlement, close, or adjusted close prices** are used is not specified.

---

## Exclusion rules underspecified
16. **Whether “within 5 days” means calendar or trading days** is not specified.
17. **Whether exclusion removes only the roll date or the entire contract/window** is not specified.
18. **Definition of “major macro announcements” beyond FOMC and CPI** is not specified.
19. **How bid-ask spread is measured when bid/ask are missing** is not specified.
20. **What “contract price” means** for the 2% spread rule is not specified.
21. **Whether exclusions are applied before or after continuation construction** is not specified.

---

## Strategy construction underspecified
22. **Exact 12-month momentum formula** is not specified.
23. **Whether there is a one-month skip** is not specified.
24. **Whether momentum is cross-sectional or time-series** is not specified.
25. **How long/short weights are assigned** is not specified.
26. **Whether leverage is allowed** is not specified.
27. **How portfolio weights across crude oil and natural gas are combined** is not specified.
28. **How missing signals are handled** is not specified.

---

## Primary metric underspecified
29. **Whether Sharpe uses excess returns over risk-free** is not specified.
30. **How annualization is done** is not explicitly specified.
31. **Whether rolling windows overlap** is not specified, though implied.
32. **How windows spanning both low and high concentration periods are classified** is not specified.
33. **Whether the differential is difference in mean rolling Sharpes or Sharpe of pooled returns by regime** is not specified.

---

## Statistical testing underspecified
34. **Exact t-test formulation** is not specified.
35. **Whether HAC is applied to a regression, mean difference, or Sharpe series** is not specified.
36. **The exact six simultaneous tests** for Bonferroni are not specified.
37. **How GARCH controls enter the main hypothesis test** is not specified.
38. **Whether GARCH is fit to strategy returns or underlying returns** is not specified.
39. **How factor exposure is controlled while testing Sharpe differences** is not specified.
40. **“Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)” is internally ambiguous**, because OLS and Fama-MacBeth are distinct estimation setups.
41. **How Markov switching output is used in inference** is not specified.
42. **Which assets enter DCC-GARCH** is not specified.
43. **How DCC-GARCH results connect to the primary hypothesis** is not specified.

---

## Simulation-agent framework underspecified
44. **Why simulation agents are needed for the primary empirical hypothesis** is not specified.
45. **State variables for each agent** are not specified.
46. **Action spaces for each agent** are not specified.
47. **Reward functions for non-meta agents** are not specified.
48. **Execution model / matching engine** is not specified.
49. **Transaction costs and slippage** are not specified.
50. **Inventory/risk constraints** are not specified.
51. **How passive_gsci maps to actual GSCI weights** is not specified.
52. **What macro signals drive macro_allocator** is not specified.
53. **What algorithm powers meta_rl** is not specified.
54. **What observation frequency the simulator uses** is not specified.
55. **What an episode means** is not specified.
56. **How 500,000 episodes are distributed across scenarios and seeds** is not specified.
57. **How simulation outputs integrate with empirical tests** is not specified.

---

## Seed policy underspecified
58. **Which components are stochastic and therefore seeded** is not specified.
59. **What “qualitatively consistent” means operationally** is not specified.
60. **Whether all empirical analyses or only simulations must be rerun per seed** is not specified.

---

## Governance/audit underspecified
61. **How COMMITTED status is checked** is not specified.
62. **What DataPassport SHA-256 signature format is required** is not specified.
63. **How CODEC bidirectional audit is operationalized** is not specified.
64. **What HAWK methodology rubric contains** is not specified.
65. **How revision cycles are counted** is not specified.

---

# 4. Reproducibility rating: 2/5

## Rating: 2 out of 5

## Rationale
The specification is strong on:
- hypothesis statement
- sample period
- broad data source
- some statistical tools
- threshold values
- exclusion criteria
- seed list
- effect-size criterion

However, reproducibility is substantially limited because many implementation-critical details are missing or ambiguous:

1. **Core variable construction is underspecified**
   - passive GSCI concentration is central but not operationally defined
   - aggregation across commodities is unspecified

2. **Momentum strategy is not fully defined**
   - no exact signal formula
   - no weighting scheme
   - no skip-month rule
   - no leverage/exposure convention

3. **Futures continuation methodology is incomplete**
   - ratio_backward is named, but roll trigger mechanics are absent

4. **Statistical design has internal ambiguity**
   - FF3 vs momentum factor inconsistency
   - OLS vs Fama-MacBeth ambiguity
   - six Bonferroni tests not enumerated

5. **Simulation section is highly underspecified**
   - agents are named but not formally defined
   - RL algorithm, environment, and episode structure are absent

6. **Governance requirements depend on external systems**
   - these cannot be reproduced from the spec alone without assumptions

Why not 1/5?
- Because the spec still provides enough structure to build a plausible approximation of the intended study.

Why not 3/5 or higher?
- Because too many choices that materially affect results must be invented by the implementer.

---

# 5. Recommended implementation interpretation to maximize fidelity

If forced to implement from this spec alone, the most defensible approach is:

1. Treat the study as primarily an **empirical futures-return analysis**.
2. Treat the **simulation/meta-RL section as secondary robustness analysis**, not the main identification strategy.
3. Use:
   - daily adjusted futures returns
   - 252-day time-series momentum
   - open-interest-weighted concentration
   - rolling annualized Sharpe
   - HAC-adjusted difference-in-means/regression framework
4. Explicitly document every assumption listed above.
5. Pre-register the missing choices before running the analysis to avoid researcher degrees of freedom.

---

If you want, I can next turn this into a **pseudo-code implementation blueprint** or a **methods section written as a reproducible protocol**.