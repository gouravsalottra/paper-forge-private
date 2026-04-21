Below is a methodology reimplementation based only on the provided specification text.

---

# Reimplementation Plan

## 0) Overall objective

Test whether **passive GSCI investor concentration above 30% of open interest** in **GSCI energy futures** is associated with a **reduction of at least 0.15 annualized Sharpe units** in a **12-month momentum strategy**, relative to periods below 30%, while accounting for:

- volatility clustering via **GARCH(1,1)**
- momentum factor exposure via **Fama-French regression**
- regime dependence via **Markov switching**
- cross-asset dependence via **DCC-GARCH**

Universe specified:

- WRDS Compustat Futures
- GSCI energy sector
- crude oil
- natural gas
- sample period 2000–2024

---

# 1) Full implementation steps in order

## Step 1 — Formalize the study design

Define the core estimand:

- Primary quantity:  
  **Sharpe ratio differential = annualized rolling 252-day Sharpe during high passive concentration periods minus annualized rolling 252-day Sharpe during low passive concentration periods**

Define concentration regimes:

- Low concentration: 10% of open interest
- Medium concentration: 30% of open interest
- High concentration: 60% of open interest

Define hypothesis comparison:

- Main threshold comparison implied by hypothesis:
  - **above 30%** vs **below 30%**
- Therefore operationally:
  - high regime = concentration > 30%
  - low regime = concentration < 30%
- Since scenarios are explicitly 10%, 30%, 60%, the practical comparison is likely:
  - low = 10%
  - high = 60%
  - medium = 30% used as threshold/reference scenario

Define economic significance rule:

- If Sharpe differential is greater than -0.15, result is economically insignificant even if statistically significant.

---

## Step 2 — Enforce governance and audit preconditions

Before any empirical run:

1. Verify pre-analysis plan status is **COMMITTED**
   - Spec says runs must be rejected if status is not COMMITTED.
2. Require audit workflow prerequisites:
   - CODEC bidirectional audit required before paper writing
   - HAWK methodology score must be at least 7/10
   - maximum 3 HAWK revision cycles
   - DataPassport SHA-256 signature required on all MINER outputs

These are process constraints, not statistical methodology, but they are mandatory according to the spec.

---

## Step 3 — Acquire and define the dataset

Pull data from:

- WRDS Compustat Futures
- instruments restricted to GSCI energy sector:
  - crude oil futures
  - natural gas futures
- date range:
  - 2000-01-01 through 2024-12-31, or all available dates within 2000–2024

Required raw fields, inferred from the methodology:

- trade date
- contract identifier
- futures price
- open interest
- bid price and ask price, or enough information to compute bid-ask spread
- contract expiration / maturity metadata
- volume if needed for liquidity checks
- any field needed to construct continuous futures under ratio-backward rolling
- any field identifying GSCI energy membership if not hardcoded by commodity

Also obtain macro announcement calendar for:

- FOMC dates
- CPI release dates

These are needed for exclusion windows around roll dates.

---

## Step 4 — Define the futures universe and contract eligibility

Restrict to contracts satisfying all exclusion rules:

1. Exclude contracts with fewer than 100 trading days of history
2. Exclude roll dates within 5 days of major macro announcements:
   - FOMC
   - CPI
3. Exclude contracts where bid-ask spread exceeds 2% of contract price

Implementation sequence:

- For each commodity and contract:
  - count available trading days
  - remove contracts with <100 trading days
- For each daily observation:
  - compute spread percentage = (ask - bid) / contract price
  - exclude observations or contracts where spread > 2%
- For rolling schedule:
  - identify candidate roll dates
  - remove or shift roll dates that fall within ±5 calendar days or ±5 trading days of FOMC/CPI, depending on assumption chosen

---

## Step 5 — Construct continuous futures series

Use:

- Roll convention: **ratio_backward**
- Adjustment method: **ratio_backward**

Implementation:

1. For crude oil and natural gas separately, sort contracts by date and maturity.
2. Define front/next contract sequence.
3. Determine roll dates according to a chosen operational rule consistent with ratio-backward construction.
4. On each roll:
   - compute adjustment ratio between outgoing and incoming contract prices
   - backward-adjust historical prices multiplicatively
5. Produce continuous adjusted daily price series for each commodity.

Outputs:

- adjusted close price series
- daily returns series

---

## Step 6 — Build the 12-month momentum strategy

The spec says:

- trend_follower — 12-month momentum signal, long/short

Implement a standard 12-month momentum signal on futures:

1. For each commodity on each date, compute trailing 12-month return.
   - Most likely 252 trading days
2. Generate signal:
   - long if trailing 12-month return > 0
   - short if trailing 12-month return < 0
3. Compute next-day or next-period strategy return:
   - signal × daily futures return

Because only two assets are named, portfolio construction must be defined:

- equal-weight across available commodity signals each day
- rebalance daily

Then compute rolling annualized Sharpe over 252-day windows:

- Sharpe_t = sqrt(252) × mean(returns over prior 252 days) / std(returns over prior 252 days)

This rolling Sharpe is the primary metric input.

---

## Step 7 — Define passive investor concentration series

The hypothesis is about:

- passive GSCI index investor concentration
- measured as percent of open interest in GSCI energy futures

Implementation requires a daily or periodic concentration variable for each commodity or aggregate energy basket.

Operationalize concentration as:

- passive concentration = passive GSCI investor holdings / total open interest

Then classify periods into scenarios/regimes:

- Low = 10%
- Medium = 30%
- High = 60%

Two possible implementations exist:

1. **Observed concentration approach**  
   Use empirical passive holdings data if available in WRDS or linked source.
2. **Simulation-imposed concentration approach**  
   Use agent-based simulation where passive_gsci agent is assigned holdings equal to 10%, 30%, or 60% of open interest.

Because the spec includes simulation agents and passive capital scenarios, the methodology likely expects scenario-based simulation layered onto historical market data.

Thus for each scenario and seed:

- impose passive_gsci capital such that its position size equals target fraction of open interest
- generate resulting market/strategy outcomes

---

## Step 8 — Implement the simulation environment

Create a market simulation over the historical futures environment with six agents:

1. passive_gsci — mechanically rebalances to GSCI index weights
2. trend_follower — 12-month momentum long/short
3. mean_reversion — fades 3-month extremes
4. liquidity_provider — posts limit orders on both sides
5. macro_allocator — switches energy/non-energy on macro signals
6. meta_rl — learns allocation across all strategies

For each trading step:

1. Update market state from historical data and engineered features
2. Compute each agent’s desired action
3. Translate actions into positions/orders
4. Apply market-clearing / execution logic
5. Update PnL and state variables
6. Record returns, positions, concentration, and diagnostics

The simulation must run under each:

- seed in [1337, 42, 9999]
- passive capital scenario in [10%, 30%, 60%]

Minimum training:

- 500,000 episodes across all scenarios and seeds

Meta-RL evaluation:

- fitness = Sharpe ratio over trailing 252 episodes
- evaluated every 1000 training steps

---

## Step 9 — Specify each agent behavior

### 9.1 passive_gsci
Mechanically rebalance to GSCI index weights.

Implementation:

- define target weights for crude oil and natural gas according to GSCI energy weights
- at each rebalance date, trade toward target weights
- scale total passive holdings to scenario concentration target:
  - 10%, 30%, or 60% of open interest

### 9.2 trend_follower
Use 12-month momentum signal.

Implementation:

- signal from trailing 252-day return
- long positive momentum, short negative momentum
- rebalance at chosen frequency, likely daily

### 9.3 mean_reversion
Fade 3-month extremes.

Implementation:

- compute trailing 63-trading-day return or z-score
- short strongest positive extremes, long strongest negative extremes

### 9.4 liquidity_provider
Posts limit orders both sides.

Implementation:

- maintain bid and ask quotes around midprice
- earn spread when filled
- inventory constraints needed

### 9.5 macro_allocator
Switches energy/non-energy on macro signals.

Implementation:

- use macro indicators/signals to allocate between energy and non-energy exposure
- because only energy futures are explicitly in data source, non-energy proxy must be defined by assumption

### 9.6 meta_rl
Learns optimal allocation across all strategies.

Implementation:

- state includes recent returns, volatility, concentration, regime indicators, correlations, macro features
- action = allocation weights across the five non-meta strategies or across asset-strategy sleeves
- reward = portfolio return or risk-adjusted return
- fitness = trailing 252-episode Sharpe, checked every 1000 steps

---

## Step 10 — Generate scenario outputs

For each combination of:

- seed ∈ {1337, 42, 9999}
- passive concentration scenario ∈ {10%, 30%, 60%}

Run the simulation/training and save:

- daily or episode-level returns for trend_follower
- rolling 252-day Sharpe for trend_follower
- passive concentration time series
- volatility estimates
- factor exposures
- regime labels
- cross-asset correlations
- agent allocations and PnL

Then derive:

- low-concentration Sharpe distribution
- medium-concentration Sharpe distribution
- high-concentration Sharpe distribution
- primary differential = high minus low

---

## Step 11 — Compute the primary metric

For each seed and scenario:

1. Compute trend_follower daily returns
2. Compute rolling 252-day annualized Sharpe
3. Aggregate Sharpe values by concentration regime
4. Compute:
   - mean Sharpe in high concentration periods
   - mean Sharpe in low concentration periods
   - differential = high - low

Primary hypothesis support requires:

- differential ≤ -0.15
- statistically significant under specified tests
- qualitatively consistent across all three seeds

---

## Step 12 — Run the primary statistical test

Perform:

- two-tailed t-test
- Newey-West HAC correction with 4 lags

Implementation:

- test whether mean difference in rolling Sharpe between high and low concentration periods differs from zero
- use HAC standard errors with lag 4 due to serial dependence in rolling-window Sharpe series

Decision thresholds:

- primary significance: p < 0.05
- if part of six simultaneous tests: Bonferroni-adjusted p < 0.0083

---

## Step 13 — Fit GARCH(1,1) volatility model

Specified model:

- arch library
- p=1, q=1
- Normal distribution

Implementation:

1. Fit GARCH(1,1) to momentum strategy returns, commodity returns, or both
2. Extract conditional volatility estimates
3. Use these in one of two ways:
   - as controls in regression
   - as volatility-adjusted diagnostics to verify concentration effect is not purely volatility-driven

At minimum, because the hypothesis says “controlling for GARCH(1,1) volatility clustering,” include conditional volatility as a control variable in the inferential model.

---

## Step 14 — Estimate Fama-French momentum exposure control

Spec says:

- Fama-French three-factor OLS regression
- linearmodels
- Fama-MacBeth

Implementation:

1. Obtain Fama-French factor data:
   - market excess return
   - SMB
   - HML
2. Regress momentum strategy returns on these factors
3. Also include a momentum-related exposure control if intended by the hypothesis wording

Because the spec explicitly says “Fama-French momentum factor exposure” but then names “three-factor OLS regression,” there is a mismatch. A practical implementation would estimate either:

- FF3 only, or
- FF3 plus momentum factor

Then use residual returns or estimated factor-adjusted alpha in concentration comparisons.

If using Fama-MacBeth:

- run cross-sectional regressions over time if there are enough assets/portfolios
- with only crude oil and natural gas, cross-sectional dimension is very thin, so this is problematic and must be flagged

---

## Step 15 — Fit Markov switching regime model

Specified model:

- statsmodels
- k_regimes = 2

Implementation:

1. Fit a 2-regime Markov switching model to:
   - momentum returns, or
   - Sharpe series, or
   - volatility/return state vector
2. Infer latent regimes, e.g.:
   - low-vol / high-momentum regime
   - high-vol / low-momentum regime
3. Test whether concentration effect differs by regime or remains after conditioning on regime

---

## Step 16 — Fit DCC-GARCH cross-asset correlation model

Implementation:

1. Use crude oil and natural gas return series
2. Estimate univariate GARCH models first
3. Estimate dynamic conditional correlation process
4. Produce time-varying correlation estimates
5. Use these as diagnostics or controls to determine whether concentration effects coincide with changing cross-asset dependence

---

## Step 17 — Conduct six simultaneous tests

The spec references Bonferroni correction for 6 simultaneous tests.

A reasonable implementation is to define six hypothesis tests, for example:

1. High vs low Sharpe differential overall
2. High vs low for crude oil momentum
3. High vs low for natural gas momentum
4. High vs medium
5. Medium vs low
6. Regime-conditioned high vs low

Apply Bonferroni threshold:

- p < 0.0083

Because the six tests are not explicitly enumerated, this must be treated as an assumption.

---

## Step 18 — Check seed consistency requirement

For each seed:

- 1337
- 42
- 9999

Determine whether the sign, approximate magnitude, and significance pattern of the main finding are qualitatively consistent.

A finding is valid only if all three seeds support the same qualitative conclusion.

Operational consistency rule should be defined, for example:

- differential negative in all seeds
- each seed’s estimate at or below -0.15, or pooled estimate at/below -0.15 with all seeds negative
- significance pattern not contradictory

---

## Step 19 — Summarize results against decision criteria

Conclude support for hypothesis only if all are true:

1. High concentration periods show lower Sharpe than low concentration periods
2. Differential is at most -0.15 Sharpe units
3. p < 0.05 under HAC t-test
4. If among six simultaneous tests, p < 0.0083 where applicable
5. Effect remains after volatility control
6. Effect remains after factor exposure control
7. Result is qualitatively consistent across all three seeds

---

## Step 20 — Produce audit-ready outputs

Generate signed outputs containing:

- data extraction summary
- exclusions applied
- roll construction details
- strategy definitions
- simulation settings
- seed-wise results
- statistical test outputs
- model diagnostics
- audit signatures / hashes required by spec

---

# 2) Assumptions needed due to underspecification

These assumptions are necessary to make the methodology executable.

## A. Concentration measurement assumption
Assume passive investor concentration is implemented through the simulation agent as a target share of open interest:
- low = 10%
- medium = 30%
- high = 60%

Reason:
- the spec does not explicitly provide an observed passive holdings field or source.

## B. Comparison definition assumption
Assume the primary comparison is:
- high (60%) minus low (10%)

Reason:
- hypothesis says above 30% vs below 30%, while scenarios are 10/30/60.

## C. Momentum lookback assumption
Assume 12-month momentum = trailing 252 trading-day return.

## D. Momentum execution assumption
Assume signal formed at day t uses information through t-1 and is applied to return from t to t+1 to avoid look-ahead bias.

## E. Portfolio weighting assumption
Assume equal weighting across crude oil and natural gas momentum sleeves when both are available.

## F. Sharpe calculation assumption
Assume annualized Sharpe uses:
- mean daily return / daily std dev × sqrt(252)
- risk-free rate set to 0 unless separately available

## G. Roll timing assumption
Assume rolling occurs on a deterministic front-to-next schedule compatible with ratio-backward adjustment, such as a fixed number of business days before expiry.

## H. Macro exclusion window assumption
Assume “within 5 days” means ±5 trading days around FOMC/CPI dates.

## I. Bid-ask exclusion assumption
Assume spread filter is applied at the observation level first; if too many observations are removed for a contract, the contract is excluded entirely.

## J. GSCI weights assumption
Assume fixed or periodically updated GSCI energy weights for crude oil and natural gas are available externally and can be mapped to the passive_gsci agent.

## K. Mean reversion definition assumption
Assume “3-month extremes” means trailing 63-trading-day standardized return extremes.

## L. Liquidity provider execution assumption
Assume fills occur when historical price path crosses posted quotes, with simple inventory limits and transaction costs.

## M. Macro allocator assumption
Assume macro signals are based on observable macro variables and that a non-energy allocation proxy exists, even though only energy futures are explicitly named.

## N. Meta-RL algorithm assumption
Assume any standard RL allocator is acceptable so long as:
- it allocates across strategies
- uses trailing 252-episode Sharpe as fitness
- is evaluated every 1000 steps

## O. Episode definition assumption
Assume one episode corresponds to one trading step/day unless otherwise required by the RL framework.

## P. Fama-French factor assumption
Assume daily Fama-French factor data are used and aligned to futures strategy returns.

## Q. Momentum factor control assumption
Assume either:
- FF3 is used despite wording about momentum factor exposure, or
- FF3 plus momentum factor is used to satisfy the hypothesis wording

## R. Fama-MacBeth applicability assumption
Assume Fama-MacBeth is approximated despite limited cross-sectional breadth, or replaced by time-series factor regression if infeasible.

## S. Markov switching target assumption
Assume the 2-regime model is fit to momentum returns.

## T. DCC-GARCH scope assumption
Assume DCC-GARCH is estimated on crude oil and natural gas returns only.

## U. Six simultaneous tests assumption
Assume a specific set of six tests must be defined by the implementer because the spec does not enumerate them.

## V. Qualitative consistency assumption
Assume “qualitatively consistent” means same sign and same accept/reject conclusion across all seeds.

## W. Training allocation assumption
Assume the 500,000 minimum episodes are distributed across all scenario-seed combinations in any reasonable way, provided total minimum is met.

---

# 3) Every underspecified detail flagged

Below is a comprehensive list of underspecified items in the spec.

## Data and universe underspecification

1. **Exact contract identifiers are not specified**
   - “crude oil” and “natural gas” could map to multiple futures series/exchanges.

2. **Exact WRDS fields are not specified**
   - no schema or required columns listed.

3. **Whether passive holdings data exist in the source is unspecified**
   - concentration variable may not be directly observable.

4. **Whether sample uses daily settlement, close, or transaction prices is unspecified**

5. **Treatment of missing data is unspecified**

6. **Time zone / trading calendar conventions are unspecified**

---

## Continuous futures construction underspecification

7. **Roll trigger rule is unspecified**
   - first notice date, last trade date, volume switch, open-interest switch, fixed offset, etc.

8. **How to handle excluded roll dates near macro announcements is unspecified**
   - skip roll, delay roll, advance roll, or drop affected windows.

9. **Whether ratio_backward applies to prices only or also derived returns is unspecified**

10. **How to handle overlapping valid contracts is unspecified**

---

## Strategy construction underspecification

11. **Exact momentum formula is unspecified**
   - simple return, log return, excess return, skip-month convention, etc.

12. **Signal frequency is unspecified**
   - daily, weekly, monthly.

13. **Execution timing is unspecified**
   - same-day close, next-day open, next-day close.

14. **Position sizing is unspecified**
   - equal weight, volatility scaled, notional scaled, risk parity.

15. **Leverage constraints are unspecified**

16. **Transaction costs and slippage for momentum strategy are unspecified**

17. **Risk-free rate treatment in Sharpe ratio is unspecified**

---

## Concentration and scenario underspecification

18. **Observed vs simulated concentration is unspecified**

19. **Whether concentration is commodity-specific or aggregated across energy sector is unspecified**

20. **How concentration evolves through time is unspecified**
   - fixed scenario level every day vs dynamic around target.

21. **How passive holdings map to open interest mechanically is unspecified**

22. **How medium scenario (30%) is used analytically is unspecified**

---

## Agent-based simulation underspecification

23. **Simulation environment mechanics are unspecified**
   - order book, price impact, execution priority, clearing rules.

24. **Agent state spaces are unspecified**

25. **Agent action spaces are unspecified**

26. **Reward functions for non-meta agents are unspecified**

27. **Capital constraints are unspecified**

28. **Inventory constraints are unspecified**

29. **Rebalancing frequencies are unspecified**

30. **How historical data and simulated actions interact is unspecified**
   - replay environment vs endogenous price formation.

31. **Whether agents affect prices or only allocations is unspecified**

32. **How open interest updates under simulation is unspecified**

33. **How liquidity provider fills are determined is unspecified**

34. **How macro_allocator defines macro signals is unspecified**

35. **How non-energy allocation is represented is unspecified**

36. **Which RL algorithm meta_rl uses is unspecified**

37. **Meta-RL observation features are unspecified**

38. **Meta-RL action parameterization is unspecified**

39. **Meta-RL reward vs fitness distinction is unspecified**

40. **Episode definition is unspecified**

41. **How 500,000 episodes are split across seeds/scenarios is unspecified**

---

## Statistical methodology underspecification

42. **Exact dependent variable for the t-test is unspecified**
   - rolling Sharpe observations, scenario means, seed-level estimates, etc.

43. **Whether the t-test is paired or unpaired is unspecified**

44. **How Newey-West is applied to rolling Sharpe series is unspecified**

45. **The six simultaneous tests are not enumerated**

46. **How Bonferroni interacts with primary vs secondary tests is unspecified**

47. **How GARCH controls enter the main hypothesis test is unspecified**
   - regression covariate, residualization, stratification.

48. **What series receives GARCH(1,1) fitting is unspecified**
   - asset returns, strategy returns, residuals.

49. **Fama-French “three-factor” vs “momentum factor exposure” is internally inconsistent**
   - momentum factor is not part of FF3.

50. **How Fama-MacBeth is feasible with only two commodities is unspecified**

51. **Whether factor regression is time-series or cross-sectional is unclear**

52. **What exactly Markov switching is fit to is unspecified**

53. **How regime outputs are used in inference is unspecified**

54. **DCC-GARCH implementation details are unspecified**
   - package, estimation method, use in final test.

55. **Whether multiple-testing correction applies to all six tests or only a subset is unspecified**

---

## Decision rule underspecification

56. **“Qualitatively consistent” across seeds is not defined**

57. **Whether all three seeds must each individually meet significance is unspecified**

58. **Whether economic significance must hold per seed or only pooled is unspecified**

59. **How to aggregate across seeds is unspecified**

60. **How to aggregate across commodities is unspecified**

---

## Audit/process underspecification

61. **How COMMITTED status is checked is unspecified**

62. **How CODEC audit is operationalized is unspecified**

63. **How HAWK scoring is performed is unspecified**

64. **What constitutes a MINER output is unspecified**

65. **How DataPassport SHA-256 signatures are generated/verified is unspecified**

---

# 4) Reproducibility rating: 2 / 5

## Rating: 2 out of 5

### Rationale

The spec is strong on:
- high-level hypothesis
- sample period
- broad data source
- some exclusion rules
- some named statistical tools
- seed policy
- scenario levels

But reproducibility is limited because many critical implementation details are missing or internally inconsistent.

### Why not higher

Major blockers to exact reproduction:

1. **Concentration variable is not operationally defined**
   - central to the hypothesis.

2. **Simulation design is highly underspecified**
   - six agents are named, but mechanics are absent.

3. **Continuous futures construction lacks roll trigger details**
   - ratio-backward alone is insufficient for exact replication.

4. **Momentum strategy details are incomplete**
   - signal timing, weighting, execution, costs.

5. **Statistical framework is partly inconsistent**
   - FF3 vs momentum factor exposure
   - Fama-MacBeth with only two commodities
   - six simultaneous tests not listed

6. **Observed-data study vs simulation study is ambiguous**
   - the spec mixes empirical finance and agent-based RL methodology.

### Why not lower

It is still possible to produce a reasonable implementation because the spec does provide:

- universe
- date range
- primary metric
- threshold effect size
- key tests
- concentration scenarios
- seeds
- training minimum
- exclusion rules

So the study is not unrecoverable; it is just not precisely reproducible without substantial assumptions.

---

# 5) Practical reimplementation summary

If I were implementing this from the spec alone, I would proceed as follows:

1. Pull crude oil and natural gas futures data from WRDS for 2000–2024.
2. Build continuous ratio-backward adjusted series.
3. Apply exclusions:
   - <100 trading days
   - spread >2%
   - roll dates within ±5 trading days of FOMC/CPI
4. Construct daily 12-month momentum returns.
5. Build an agent-based overlay with passive concentration scenarios at 10/30/60% of open interest.
6. Run all scenarios under seeds 1337, 42, 9999.
7. Train/evaluate meta_rl for at least 500,000 total episodes, evaluating trailing 252-episode Sharpe every 1000 steps.
8. Compute rolling 252-day annualized Sharpe for the trend_follower.
9. Compare high vs low concentration Sharpe.
10. Test significance with HAC t-tests.
11. Fit GARCH(1,1), factor regression, Markov switching, and DCC-GARCH as controls/diagnostics.
12. Apply Bonferroni correction across six defined tests.
13. Accept the finding only if:
   - effect ≤ -0.15
   - statistically significant
   - robust across all three seeds.

If you want, I can next turn this into a **pseudo-code implementation blueprint** or a **methods section written as a reproducible protocol**.