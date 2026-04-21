Below is a methodology-only reimplementation plan derived strictly from the provided specification text.

---

# Reimplementation Plan

## 0. Overall objective

Test whether **passive GSCI investor concentration above 30% of open interest** in **GSCI energy futures** is associated with a **reduction in 12-month momentum strategy Sharpe ratio of at least 0.15**, relative to periods below 30%, while accounting for:

- GARCH(1,1) volatility clustering
- Fama-French momentum/factor exposure
- regime effects
- cross-asset correlation structure

Universe specified:

- WRDS Compustat Futures
- GSCI energy sector
- crude oil
- natural gas
- sample period 2000–2024

Primary output:

- annualized Sharpe differential between high- and low-concentration periods using rolling 252-day windows

---

# 1. Full implementation steps in order

## Step 1: Register assumptions and unresolved specification gaps

Before implementation, create a formal assumptions log containing every missing detail from the spec and the chosen resolution. This is necessary because the spec is materially underspecified in several places.

This log should include at minimum:

- exact contract identifiers used for crude oil and natural gas
- exact definition of passive concentration
- exact momentum portfolio construction
- exact factor construction
- exact handling of rolling windows and overlap
- exact simulation environment design
- exact interpretation of “qualitatively consistent”

Do not proceed without freezing these assumptions.

---

## Step 2: Enforce governance prerequisites from the spec

The spec says:

- pre-analysis plan status must be **COMMITTED**
- all runs rejected otherwise
- DataPassport SHA-256 signature required on all outputs
- audit gates exist

Methodologically, implement these as run prerequisites:

1. Verify pre-analysis status equals `COMMITTED`.
2. Refuse execution if not committed.
3. Record SHA-256 signatures for all extracted and transformed datasets and all model outputs.
4. Record audit metadata for methodology review.

These are process requirements, not statistical ones, but they are explicitly required by the spec.

---

## Step 3: Acquire and define the dataset

Extract from WRDS Compustat Futures:

- daily data for GSCI energy sector futures
- crude oil futures
- natural gas futures
- sample from 2000-01-01 through 2024-12-31, or nearest available trading dates

Required fields, inferred from the methodology:

- trade date
- contract identifier
- underlying commodity
- price series needed for returns
- open interest
- bid-ask spread or bid and ask quotes
- contract maturity / expiration
- volume if available
- any field needed to construct continuous futures under ratio-backward rolling

Also acquire:

- dates of major macro announcements:
  - FOMC
  - CPI
- factor data needed for Fama-French regressions
- any data needed to estimate passive GSCI concentration if not directly available

---

## Step 4: Define the eligible contract universe

Apply exclusion rules in this order:

1. Exclude contracts with fewer than 100 trading days of history.
2. Exclude observations on roll dates within 5 days of major macro announcements:
   - FOMC
   - CPI
3. Exclude contracts/observations where bid-ask spread exceeds 2% of contract price.

Because the spec does not define whether exclusions are at the contract level or observation level in all cases, this must be explicitly assumed and documented.

---

## Step 5: Construct continuous futures series

Use:

- roll convention: `ratio_backward`
- adjustment method: `ratio_backward`

Implementation sequence:

1. For each commodity, sort contracts by date and maturity.
2. Define roll dates according to a chosen operational rule consistent with ratio-backward construction.
3. Build a continuous adjusted price series by backward ratio adjustment across rolls.
4. Preserve raw and adjusted prices separately.
5. Compute daily returns from the adjusted continuous series.

Because the spec gives the adjustment method but not the exact roll trigger, this is an underspecified step and must be assumed.

---

## Step 6: Define passive investor concentration

Construct a daily passive concentration measure for each GSCI energy future.

Target concept from hypothesis:

- passive GSCI index investor concentration as a percentage of open interest

Operationally, for each date and commodity:

\[
\text{Passive Concentration}_{t} =
\frac{\text{Estimated passive GSCI-linked open interest}_{t}}
{\text{Total open interest}_{t}}
\]

Then classify periods into scenarios:

- Low = 10%
- Medium = 30%
- High = 60%

And for the primary hypothesis comparison:

- low-concentration periods: below 30%
- high-concentration periods: above 30%

The spec does not explain how passive GSCI-linked open interest is observed or estimated. This is one of the most important missing details and must be assumed.

---

## Step 7: Segment the sample into concentration regimes

Create daily regime labels:

- `below_30`: passive concentration < 30%
- `at_or_above_30` or `above_30`: depending on chosen threshold convention
- optionally retain exact scenario bins:
  - low around 10%
  - medium around 30%
  - high around 60%

For the primary metric, compare high-concentration versus low-concentration periods.

Because the spec mixes:
- “above 30%”
- “below 30%”
- scenario levels of 10%, 30%, 60%

you must define exactly whether:
- 30% belongs to medium only,
- or to high,
- or is excluded from the binary comparison.

---

## Step 8: Construct the 12-month momentum strategy

Build the `trend_follower` strategy using a 12-month momentum signal.

A minimal implementation consistent with the spec:

1. Use trailing 12-month return signal for each commodity.
2. Go long if signal positive, short if signal negative.
3. Rebalance daily or monthly according to an explicit assumption.
4. Compute strategy returns from adjusted futures returns.

Because only two commodities are named, likely implementation is cross-sectional or directional time-series momentum over crude oil and natural gas. The spec does not say which. This must be assumed.

Also define:

- lookback length in trading days: likely 252
- whether to skip the most recent month
- weighting scheme across assets
- leverage normalization
- transaction cost treatment
- handling of flat signals

All are underspecified.

---

## Step 9: Compute rolling Sharpe ratios

Primary metric:

- Sharpe ratio differential
- annualized
- rolling 252-day windows

Implementation:

1. Compute daily momentum strategy returns.
2. For each day \( t \ge 252 \), compute rolling mean and standard deviation over the prior 252 trading days.
3. Annualize Sharpe as:

\[
\text{Sharpe}_{t} = \frac{\bar r_{t}}{\sigma_{t}} \times \sqrt{252}
\]

4. Partition rolling Sharpe observations by concentration regime.
5. Compute differential:

\[
\Delta \text{Sharpe} = \text{Sharpe}_{\text{high concentration}} - \text{Sharpe}_{\text{low concentration}}
\]

6. Evaluate whether this differential is \(\le -0.15\).

The spec does not define risk-free rate usage, so likely excess return is omitted unless assumed otherwise.

---

## Step 10: Perform the primary statistical test

Run a two-tailed t-test on the Sharpe differential with:

- significance threshold p < 0.05
- Newey-West HAC correction with 4 lags

Implementation:

1. Form the time series of rolling Sharpe observations or regime-conditioned return outcomes.
2. Estimate the mean difference between high- and low-concentration periods.
3. Compute HAC-robust standard errors with 4 lags.
4. Conduct a two-tailed test of zero difference.
5. Separately assess economic significance:
   - effect must be at most -0.15 Sharpe units

Important: the spec says “t-test” with Newey-West correction, which is not a plain classical t-test. This should be implemented as a regression/intercept-difference test with HAC covariance or equivalent.

---

## Step 11: Apply Bonferroni correction

The spec requires:

- 6 simultaneous tests
- adjusted threshold p < 0.0083

Implementation:

1. Enumerate the six tests being jointly considered.
2. For each, compute raw p-value.
3. Compare each to:
   - primary threshold 0.05
   - Bonferroni threshold 0.0083

The six tests are not explicitly enumerated in the spec. This is underspecified and must be resolved before implementation.

---

## Step 12: Fit GARCH(1,1) volatility models

For each relevant return series, estimate:

- GARCH(1,1)
- Normal innovations
- `p=1`, `q=1`

Suggested implementation:

1. Use daily momentum strategy returns, and possibly underlying commodity returns.
2. Fit:

\[
r_t = \mu + \epsilon_t,\quad \epsilon_t \sim N(0, h_t)
\]
\[
h_t = \omega + \alpha \epsilon_{t-1}^2 + \beta h_{t-1}
\]

3. Extract conditional volatility estimates.
4. Use these either:
   - as controls in the main regression, or
   - to volatility-standardize returns before Sharpe comparison.

The spec says “controlling for GARCH(1,1) volatility clustering” but does not specify exactly how the control enters the hypothesis test. This is underspecified.

---

## Step 13: Estimate factor exposure via Fama-French regression

The spec says:

- Fama-French three-factor OLS regression
- linearmodels
- Fama-MacBeth
- hypothesis mentions momentum factor exposure

Implementation requires choosing a coherent interpretation despite internal inconsistency.

A practical sequence:

1. Obtain factor returns.
2. Regress momentum strategy returns on factor returns.
3. Estimate factor-adjusted abnormal return or residualized return.
4. Use factor-adjusted returns in robustness analysis.

However, there is a conflict:
- “three-factor” usually means market, SMB, HML
- hypothesis mentions momentum factor exposure, which implies Carhart 4-factor or another momentum factor
- “OLS regression” and “Fama-MacBeth” are not the same estimation framework in the usual sense

This entire component is materially underspecified and internally inconsistent.

---

## Step 14: Estimate Markov switching regimes

Fit a 2-regime Markov switching model using statsmodels with:

- `k_regimes=2`

Possible implementation:

1. Use momentum strategy returns, volatility, or Sharpe series as the observed variable.
2. Fit a 2-state regime-switching model.
3. Infer smoothed probabilities of low/high regime.
4. Test whether passive concentration effects differ by latent regime.

The spec does not define:
- dependent variable
- switching mean vs variance vs both
- exogenous regressors
- whether this is confirmatory or robustness only

So this must be assumed.

---

## Step 15: Estimate DCC-GARCH cross-asset correlation

Use crude oil and natural gas returns to estimate dynamic conditional correlation.

Implementation:

1. Fit univariate GARCH models to each asset return series.
2. Standardize residuals.
3. Estimate DCC parameters.
4. Produce time-varying correlation series.
5. Use DCC outputs as:
   - descriptive diagnostics, or
   - controls / robustness checks for momentum profitability under concentration regimes.

The spec requires DCC-GARCH but does not specify:
- exact package
- exact parameterization
- whether this enters the main test
- whether strategy returns or asset returns are used

Underspecified.

---

## Step 16: Build the six simulation agents

Implement the following agents:

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

This implies an agent-based or market simulation layer in addition to the empirical analysis.

Implementation sequence:

1. Define state variables:
   - prices
   - returns
   - open interest
   - spreads
   - concentration regime
   - macro state
   - volatility state
2. Define action spaces for each agent.
3. Define reward functions.
4. Simulate interactions under passive capital scenarios.
5. Record resulting returns and Sharpe outcomes.

However, the spec gives almost no operational detail for the simulation environment. This is one of the largest reproducibility gaps.

---

## Step 17: Define passive capital scenarios in simulation

Run simulation under:

- Low passive capital = 10% of open interest
- Medium = 30%
- High = 60%

For each scenario:

1. Set passive_gsci participation to the target share of open interest.
2. Simulate market interactions.
3. Evaluate momentum profitability and other strategy outcomes.

Need to define whether these are:
- exogenous fixed scenario parameters,
- empirical subsamples,
- or both.

The spec suggests both empirical concentration analysis and simulation scenarios, but does not explain how they connect.

---

## Step 18: Implement the mean reversion agent

Construct a 3-month extreme-fading strategy.

Minimal implementation:

1. Compute trailing 3-month return signal.
2. Define “extreme” threshold.
3. Short positive extremes, long negative extremes.
4. Rebalance on a chosen schedule.

The threshold for “extreme” is not specified.

---

## Step 19: Implement the liquidity provider agent

Construct a market-making style agent.

Minimal implementation:

1. Post bid and ask limit orders around midprice.
2. Earn spread capture when filled.
3. Manage inventory with limits.
4. Include adverse selection and inventory penalties.

None of these mechanics are specified, so all must be assumed.

---

## Step 20: Implement the macro allocator agent

Construct an agent that switches energy/non-energy exposure based on macro signals.

Implementation requires:

1. Define macro signals.
2. Define non-energy asset universe.
3. Define switching rule.
4. Define rebalance frequency.

All are underspecified.

---

## Step 21: Implement the meta-RL allocator

The spec requires:

- learns optimal allocation across all strategies
- fitness = Sharpe ratio over trailing 252 episodes
- evaluated every 1000 training steps
- minimum 500,000 training episodes across all scenarios and seeds

Implementation:

1. Define observation/state space:
   - recent returns of all agents
   - volatility
   - concentration regime
   - macro state
   - correlation state
2. Define action space:
   - portfolio weights across the six strategies or five base strategies
3. Define reward:
   - likely episodic return, while fitness metric is trailing 252-episode Sharpe
4. Train under each scenario and seed.
5. Evaluate every 1000 steps.
6. Continue until total episodes across all scenarios and seeds reach at least 500,000.

Need to define:
- RL algorithm
- episode length
- exploration schedule
- transaction costs
- constraints on weights
- whether meta_rl allocates to itself or only to the other agents

All are underspecified.

---

## Step 22: Run all seeds

Use seeds:

- 1337
- 42
- 9999

For every stochastic component:

- simulation initialization
- RL training
- any randomized sampling or optimization

Run the full pipeline separately for each seed.

---

## Step 23: Define and test qualitative consistency across seeds

The spec says:

- all three seeds must produce qualitatively consistent results
- finding valid only if it holds across all three seeds

Operationalize this before running:

A reasonable rule would be:

1. Sign of effect must match across all seeds.
2. Economic significance threshold (-0.15 Sharpe units) must be met across all seeds.
3. Statistical significance should hold across all seeds for confirmatory validity.

But this is not specified and must be assumed.

---

## Step 24: Aggregate empirical and simulation results

For each seed and scenario, report:

- mean rolling Sharpe in low concentration periods
- mean rolling Sharpe in high concentration periods
- Sharpe differential
- HAC-corrected t-statistic and p-value
- Bonferroni-adjusted significance decision
- GARCH diagnostics
- factor-adjusted results
- Markov regime results
- DCC-GARCH correlation diagnostics
- simulation-agent outcomes
- meta-RL fitness trajectory

---

## Step 25: Make the final validity decision

A finding supports the hypothesis only if all of the following hold:

1. High concentration periods show lower momentum Sharpe than low concentration periods.
2. Differential is at most -0.15 Sharpe units.
3. Primary p-value < 0.05.
4. If part of the simultaneous family, p-value < 0.0083 after Bonferroni where applicable.
5. Result is qualitatively consistent across all three seeds.
6. Governance/audit prerequisites are satisfied.

---

# 2. Assumptions needed due to underspecification

Below are the assumptions required to make the methodology executable.

## Data assumptions

1. **Contract mapping assumption**  
   “GSCI energy sector (crude oil, natural gas)” means using front-month or continuous futures for those two commodities only.

2. **Date coverage assumption**  
   Use all available trading days from 2000 through 2024 inclusive.

3. **Bid-ask spread assumption**  
   If bid and ask are available, spread = ask - bid; if only quoted spread exists, use that directly.  
   “Exceeds 2% of contract price” means spread / midprice > 0.02.

4. **Macro announcement exclusion assumption**  
   “Within 5 days” means ±5 calendar days or ±5 trading days; one must choose one. A more defensible choice is ±5 trading days.

---

## Continuous futures assumptions

5. **Roll trigger assumption**  
   Because only `ratio_backward` is specified, assume rolling occurs on a fixed rule such as a set number of business days before expiration or when next contract volume/open interest exceeds front contract.

6. **Return computation assumption**  
   Daily returns are log returns or simple returns from adjusted continuous prices; one must choose one. Sharpe is usually computed on simple returns, but either can be used if consistent.

---

## Passive concentration assumptions

7. **Passive concentration observability assumption**  
   Passive GSCI-linked open interest is not directly specified as available in WRDS Compustat Futures, so assume it must be estimated from index weights and open interest participation.

8. **Threshold classification assumption**  
   “Above 30%” means strictly > 0.30 and “below 30%” means strictly < 0.30; observations exactly at 30% are either excluded or assigned to medium. Must choose one.

9. **Scenario mapping assumption**  
   Low/medium/high scenarios correspond to target concentration bins centered on 10%, 30%, and 60%, or exact fixed scenario settings in simulation. Must define bin widths if using empirical data.

---

## Strategy assumptions

10. **Momentum definition assumption**  
    “12-month momentum” means trailing 252-trading-day return.

11. **Momentum implementation assumption**  
    Use time-series momentum: long if own trailing 12-month return > 0, short otherwise.

12. **Rebalancing assumption**  
    Rebalance daily unless monthly is chosen; the spec does not say.

13. **Portfolio weighting assumption**  
    Equal-weight crude oil and natural gas unless GSCI weights are intended.

14. **Transaction cost assumption**  
    The spec does not mention transaction costs for strategy returns; assume either zero costs or costs based on bid-ask spread. Must choose.

15. **Risk-free rate assumption**  
    Sharpe ratio uses zero risk-free rate unless an external daily risk-free series is added.

---

## Statistical assumptions

16. **Primary test implementation assumption**  
    The “t-test with Newey-West HAC correction” is implemented as a regression-based mean-difference test with HAC standard errors.

17. **Bonferroni family assumption**  
    The six simultaneous tests must be explicitly defined by the implementer.

18. **GARCH control assumption**  
    “Controlling for GARCH(1,1)” means including conditional volatility estimates as controls or using volatility-adjusted residual returns.

19. **Factor model assumption**  
    Because the spec mixes three-factor and momentum exposure, assume either:
    - FF3 plus a separate momentum factor robustness test, or
    - a four-factor model despite the text saying three-factor.

20. **Fama-MacBeth assumption**  
    Since Fama-MacBeth is not standard for a two-asset daily time-series setup, assume this is intended as a robustness framework rather than the primary estimator.

21. **Markov switching assumption**  
    Fit the model to momentum strategy returns with switching mean and/or variance.

22. **DCC-GARCH assumption**  
    Estimate DCC on crude oil and natural gas daily returns.

---

## Simulation assumptions

23. **Simulation necessity assumption**  
    The simulation-agent section is part of the required methodology, not optional.

24. **Market environment assumption**  
    Use a stylized multi-agent market environment calibrated to empirical return, volatility, spread, and open-interest characteristics.

25. **Passive agent assumption**  
    `passive_gsci` trades mechanically to maintain target GSCI weights and target passive capital share.

26. **Mean reversion assumption**  
    “3-month extremes” means trailing 63-trading-day returns beyond a chosen percentile threshold.

27. **Liquidity provider assumption**  
    Agent quotes symmetrically around midprice with inventory constraints.

28. **Macro allocator assumption**  
    Macro signals are derived from FOMC/CPI or other macro indicators; non-energy assets must be externally defined.

29. **Meta-RL action assumption**  
    `meta_rl` allocates across the other strategies, not including itself.

30. **Episode assumption**  
    One episode corresponds to one trading day or one rolling decision interval; must choose.

31. **Training count assumption**  
    “500,000 minimum across all scenarios and seeds” means total episodes summed over all runs, not per run.

---

## Seed consistency assumptions

32. **Qualitative consistency assumption**  
    Results are qualitatively consistent if sign, economic significance, and broad statistical conclusion match across all seeds.

---

# 3. Every underspecified detail flagged

Below is a comprehensive list of underspecified or internally inconsistent details in the spec.

## Data and universe

1. **Exact contract identifiers are not specified.**
2. **Whether only crude oil and natural gas are included, or all GSCI energy contracts, is ambiguous.**
3. **Whether data are daily settlement, close, or another price field is not specified.**
4. **Whether open interest is end-of-day or another convention is not specified.**
5. **Whether bid-ask spread data are directly available in the stated source is not specified.**

## Continuous futures construction

6. **Roll convention says `ratio_backward`, but exact roll trigger is not specified.**
7. **Adjustment method duplicates roll convention but does not define implementation details.**
8. **Whether returns are simple or log returns is not specified.**

## Exclusion rules

9. **“Exclude contracts with fewer than 100 trading days of history” does not specify whether exclusion is contract-level or observation-level.**
10. **“Exclude roll dates within 5 days of major macro announcements” does not specify 5 calendar days or 5 trading days.**
11. **It does not specify whether exclusion applies only to the roll date or the entire surrounding window.**
12. **“Major macro announcements” lists FOMC and CPI only, but does not specify source/calendar standardization.**
13. **“Exclude contracts where bid-ask spread exceeds 2% of contract price” does not specify whether this is checked daily or averaged over a period.**

## Passive concentration

14. **The source or construction of passive GSCI investor concentration is not specified.**
15. **It is not specified whether passive concentration is directly observed or estimated.**
16. **It is not specified whether concentration is commodity-specific or sector-wide then mapped to contracts.**
17. **Threshold handling at exactly 30% is not specified.**
18. **The relationship between empirical concentration periods and the 10/30/60 scenario levels is not specified.**

## Momentum strategy

19. **“12-month momentum signal” does not specify time-series vs cross-sectional momentum.**
20. **Lookback length in exact trading days is not specified.**
21. **Whether there is a one-month skip is not specified.**
22. **Rebalancing frequency is not specified.**
23. **Weighting across assets is not specified.**
24. **Leverage or volatility scaling is not specified.**
25. **Transaction cost treatment is not specified.**
26. **Whether signals are based on adjusted or raw prices is not specified.**

## Primary metric and testing

27. **The exact unit of analysis for the Sharpe differential test is not specified.**
28. **Whether Sharpe is computed from excess returns or raw returns is not specified.**
29. **Whether overlapping rolling windows are used in inference is not explicitly addressed.**
30. **How Newey-West is applied to Sharpe differences is not specified.**
31. **The six simultaneous tests for Bonferroni correction are not enumerated.**

## GARCH and factor controls

32. **“Controlling for GARCH(1,1) volatility clustering” does not specify the exact regression structure.**
33. **Whether GARCH is fit to asset returns or strategy returns is not specified.**
34. **“Fama-French three-factor OLS regression” conflicts with “momentum factor exposure.”**
35. **“linearmodels, Fama-MacBeth” conflicts with “OLS regression.”**
36. **The factor dataset source is not specified.**
37. **How factor adjustment enters the main hypothesis test is not specified.**

## Markov switching and DCC-GARCH

38. **The dependent variable for Markov switching is not specified.**
39. **Whether switching occurs in mean, variance, or both is not specified.**
40. **How Markov regimes are used in the final inference is not specified.**
41. **DCC-GARCH package and exact formulation are not specified.**
42. **Whether DCC is estimated on underlying assets or strategy returns is not specified.**
43. **How DCC outputs affect the main conclusion is not specified.**

## Simulation agents

44. **The simulation environment is not described.**
45. **Price formation mechanism is not specified.**
46. **Order matching mechanism is not specified.**
47. **Inventory and execution constraints are not specified.**
48. **Agent observation spaces are not specified.**
49. **Agent action spaces are not specified.**
50. **Reward functions are not specified except for meta_rl fitness.**
51. **How empirical data and simulation interact is not specified.**
52. **Whether simulation is confirmatory or exploratory is not specified.**

## Specific agents

53. **`passive_gsci` exact GSCI weights are not specified.**
54. **`mean_reversion` does not define “extremes.”**
55. **`liquidity_provider` does not define quote placement or fill model.**
56. **`macro_allocator` does not define macro signals.**
57. **`macro_allocator` references non-energy assets, but the non-energy universe is not specified.**
58. **`meta_rl` does not specify algorithm.**
59. **`meta_rl` does not specify whether it allocates across five or six strategies.**
60. **`meta_rl` does not specify episode length.**
61. **`meta_rl` does not specify portfolio constraints.**

## Seeds and validity

62. **What counts as “qualitatively consistent results” is not specified.**
63. **Whether all statistical thresholds must hold for each seed individually is not specified.**
64. **Whether results are pooled across seeds or treated separately is not specified.**

## Governance and audit

65. **How pre-analysis commitment is operationally verified is not specified.**
66. **Audit requirements are process requirements but not integrated into the statistical workflow.**
67. **HAWK methodology rubric criteria are not specified.**
68. **MINER outputs are referenced but not defined in the methodology.**

---

# 4. Reproducibility rating: 2 / 5

## Rating: 2 out of 5

### Rationale

This spec is **partially reproducible**, but not fully.

### Why not 1/5
It does provide several concrete anchors:

- hypothesis direction and threshold
- sample period
- data source family
- asset class focus
- rolling window length
- significance thresholds
- HAC lag count
- GARCH order and distribution
- Markov regime count
- passive capital scenarios
- seeds
- minimum training episodes
- exclusion rules

These are enough to build a rough implementation.

### Why not 3/5 or higher
Several core components are too underspecified or internally inconsistent:

1. **Passive concentration measurement is not operationalized.**  
   This is central to the hypothesis.

2. **Momentum strategy construction is incomplete.**  
   Time-series vs cross-sectional, rebalance frequency, weighting, and costs are all missing.

3. **Factor model specification is inconsistent.**  
   “Three-factor,” “momentum exposure,” “OLS,” and “Fama-MacBeth” do not align cleanly.

4. **Simulation framework is largely unspecified.**  
   The six-agent system cannot be faithfully reproduced from the text alone.

5. **Bonferroni family is undefined.**  
   The six simultaneous tests are not listed.

6. **Seed consistency criterion is undefined.**

7. **Continuous futures roll trigger is missing.**

Because these gaps affect the main result, independent teams could produce materially different outcomes while all claiming compliance.

### Bottom line
A competent researcher could implement a plausible approximation, but not a uniquely determined reproduction. Hence **2/5**.

---

# 5. Concise recommended implementation interpretation

If forced to implement from this spec alone, the most defensible path is:

1. Use crude oil and natural gas daily futures data from 2000–2024.
2. Build ratio-backward continuous series with an explicitly chosen roll rule.
3. Estimate daily passive concentration as passive GSCI-linked open interest divided by total open interest.
4. Define momentum as daily-rebalanced time-series momentum using trailing 252-day returns.
5. Compute rolling 252-day annualized Sharpe ratios.
6. Compare Sharpe during concentration >30% vs <30%.
7. Test the difference using HAC-robust mean-difference regression with 4 lags.
8. Require effect size ≤ -0.15.
9. Run robustness checks with GARCH(1,1), factor adjustment, Markov switching, and DCC-GARCH.
10. Separately implement a stylized multi-agent simulation under 10/30/60% passive-capital scenarios.
11. Run all stochastic components under seeds 1337, 42, and 9999.
12. Accept findings only if sign and economic significance are consistent across all seeds.

If you want, I can next turn this into a **formal pseudocode protocol** or a **methods section written as executable research steps**.