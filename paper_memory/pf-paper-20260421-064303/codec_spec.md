# PASS1

## 1. Statistical tests implemented

From `agents/sigma_job2.py` and related spec constants in `agents/forge/env.py` / `PAPER.md`, the implemented econometric battery includes:

1. **Newey-West t-test**
   - Method call: `_newey_west_ttest(returns)`
   - Input: `returns = sim_df["mean_reward"].to_numpy(dtype=float)`
   - Library:
     - `statsmodels.api as sm` imported in `agents/sigma_job2.py`
   - Spec parameters:
     - Two-tailed t-test
     - Newey-West HAC correction
     - `4` lags
   - Thresholds:
     - Primary significance threshold `p < 0.05` two-tailed
     - Included in Bonferroni family of 6 tests

2. **GARCH(1,1) volatility model**
   - Method call: `_garch_11(returns)`
   - Library:
     - `arch.arch_model`
   - Spec parameters:
     - `p=1`, `q=1`
     - Normal distribution
   - Reported p-value used in multiplicity correction:
     - `garch_result["alpha_pvalue"]`

3. **Bootstrap confidence interval / bootstrap test**
   - Method call: `_bootstrap_ci(returns, seed=seed, n_resamples=1000)`
   - Library:
     - not explicitly shown in truncated body; uses NumPy/Python code in project context
   - Exact implemented parameters visible:
     - `seed=seed`
     - `n_resamples=1000`
   - Reported p-value used in multiplicity correction:
     - `bootstrap_result["mean_lt_zero_p_value"]`

4. **Deflated Sharpe test**
   - Method call: `_deflated_sharpe(returns, n_trials=6)`
   - Library:
     - internal implementation in `sigma_job2.py`; `scipy.stats.norm` imported
   - Exact implemented parameters visible:
     - `n_trials=6`
   - Reported p-value used in multiplicity correction:
     - `deflated_result["p_value"]`

5. **Markov regime-switching model**
   - Method call: `_markov_regime(returns)`
   - Library:
     - `statsmodels.tsa.regime_switching.markov_autoregression.MarkovAutoregression`
   - Spec parameters:
     - `k_regimes=2`
   - Reported p-value used in multiplicity correction:
     - `regime_result["regime_mean_diff_p_value"]`

6. **Fama-MacBeth regression**
   - Method call: `_fama_macbeth_regression(sim_df)`
   - Library:
     - output version tracking includes `"linearmodels"`
     - `PAPER.md` says `linearmodels, Fama-MacBeth`
   - Spec parameters:
     - described in `PAPER.md` as “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)”
   - Reported p-value used in multiplicity correction:
     - `fama_result.get("concentration_pvalue", 1.0)`

7. **DCC-GARCH cross-asset correlation summary**
   - Method call: `_dcc_garch_summary()`
   - Output fields written:
     - `method`
     - `n_pairs`
     - `mean_dcc_correlation`
     - `error`
   - Spec name:
     - DCC-GARCH cross-asset correlation
   - Library:
     - not shown in provided code excerpt
   - Note:
     - not included in the Bonferroni p-value list in the visible code

8. **Bonferroni correction**
   - Method call:
     - `_bonferroni([...], n_tests=6, primary_metric=primary_metric)`
   - Exact implemented parameters:
     - `n_tests=6`
   - Inputs corrected:
     - Newey-West t-test p-value
     - GARCH alpha p-value
     - Deflated Sharpe p-value
     - Markov regime mean-difference p-value
     - Bootstrap mean<0 p-value
     - Fama-MacBeth concentration p-value

## 2. Data

### Source
Implemented data source in `agents/miner/miner.py`:
- **Yahoo Finance via `yfinance`**
- Function calls:
  - `yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)`

Spec text in `PAPER.md` says:
- **WRDS Compustat Futures — GSCI energy sector**

But the actual code in `miner.py` downloads from **Yahoo Finance**, not WRDS.

### Tickers
Exact implemented tickers in `agents/miner/miner.py`:
- `CL=F` → `crude_oil_wti`
- `NG=F` → `natural_gas`

### Date range
Exact implemented constants:
- `START_DATE = "2000-01-01"`
- `END_DATE_EXCLUSIVE = "2024-01-01"`
- Effective intended inclusive coverage:
  - through `2023-12-31`
- Passport writes:
  - `"start": "2000-01-01"`
  - `"end": "2023-12-31"`

### Adjustment method
Actual download setting:
- `auto_adjust=True`

Spec text also states:
- Roll convention: `ratio_backward`
- Adjustment method: `ratio_backward`

But in the provided implementation of `miner.py`, the actual market data retrieval uses:
- **Yahoo Finance adjusted prices via `auto_adjust=True`**
not an explicit futures roll construction routine.

### Return construction
Implemented in `build_returns_frame()`:
- inner join across ticker close series
- sorted by date
- log returns:
  - `np.log(close_df / close_df.shift(1)).dropna()`

### Exclusion / filtering rules actually implemented
1. **Minimum trading history**
   - retain only columns with at least `100` non-null trading days

2. **Macro announcement exclusion**
   - function: `apply_macro_exclusion_window(df, exclusion_days=5)`
   - exclusion window:
     - `±5` calendar days around dates in `FOMC_DATES_APPROX`
   - comment says FOMC and CPI, but visible list is `FOMC_DATES_APPROX`
   - applied to return rows

3. **Bid-ask spread filter**
   - function: `apply_bid_ask_spread_filter(..., threshold=0.02)`
   - spread proxy:
     - `(High - Low).abs() / Close`
   - row removed if:
     - `aligned_spread.max(axis=1) > 0.02`

## 3. Simulation agents and behaviors

From `agents/forge/agents.py` and `agents/forge/env.py`, the six agents are:

1. **passive_gsci / `PassiveGSCI`**
   - Behavior:
     - ignores observation
     - always returns action `1`
   - In env action semantics:
     - `0=hold, 1=long, 2=short`

2. **trend_follower / `TrendFollower`**
   - Base class behavior in `agents.py`:
     - returns `1` if `obs[0] > obs[4]`, else `2`
   - Runner override in training episode (`_run_single_episode`):
     - computes 12-month momentum using environment price history
     - `lookback_window = 252`
     - `momentum_signal = current_price - lookback_price`
     - action `1` if momentum positive, else `2`

3. **mean_reversion / `MeanReversion`**
   - Behavior:
     - if `obs[0] > obs[1] * 1.02`: action `2`
     - if `obs[0] < obs[1] * 0.98`: action `1`
     - else action `0`

4. **liquidity_provider / `LiquidityProvider`**
   - Behavior:
     - alternates between action `1` and action `2`
     - starts with counter `0`, so first action is `1`
     - increments counter each act call

5. **macro_allocator / `MacroAllocator`**
   - Parameter:
     - `passive_threshold: float = 0.30`
   - In runner instantiated as:
     - `MacroAllocator(passive_threshold=self.passive_concentration)`
   - Behavior:
     - returns `1` if `obs[6] < self.passive_threshold`
     - else `0`
   - Since `obs[6]` is passive concentration in env observation, this compares concentration to threshold

6. **meta_rl / `MetaRL`**
   - Placeholder class behavior in `agents.py`:
     - random action `random.randint(0, 2)`
   - Actual training/evaluation behavior in runner:
     - action chosen by `self.cem.act(obs, weights)`
     - `CEM.act` computes:
       - `logits = obs @ weights`
       - action = `argmax(logits)`

### Environment action semantics
From `agents/forge/env.py`:
- `Discrete(3)`
- `0 = hold`
- `1 = long`
- `2 = short`

### Environment observation contents
Visible `observe()` fields:
1. `self._price_history[0]`
2. `self._price_history[1]`
3. `self._price_history[2]`
4. `self._price_history[3]`
5. `self._price_history[4]`
6. `self._current_volatility`
7. `self.passive_concentration`
8. `self.portfolio_values[agent]`
9. `self.cash[agent]`
10. `float(self.current_step)`

## 4. Seeds

Exact seed values used:
- `1337`
- `42`
- `9999`

Locations:
- `agents/forge/env.py`: `SEED_POLICY: "seeds = [1337, 42, 9999]"`
- `PAPER.md`: same
- `agents/forge/full_run.py`: `seeds = [1337, 42, 9999]`
- `agents/forge/modal_run.py`: `seeds = [1337, 42, 9999]`

Actual seeding in runner:
- `np.random.seed(self.seed)`
- `random.seed(self.seed)`

Environment reset optionally seeds NumPy:
- `reset(seed=...)` sets `np.random.seed(seed)` if provided

Sigma job also derives a seed for bootstrap:
- `seed = self._seed_from_pap_lock()`
- exact numeric value not visible in provided excerpt, so cannot report it

## 5. Thresholds

### Significance thresholds
Implemented/spec constants:
- Primary:
  - `p < 0.05` two-tailed
- Bonferroni:
  - `p < 0.0083`
  - `n_tests = 6`

Locations:
- `agents/forge/env.py`
- `PAPER.md`
- `sigma_job2.py` uses `_bonferroni(..., n_tests=6, ...)`

### Minimum effect size
Exact threshold:
- `-0.15` Sharpe units

Evidence:
- `PAPER.md`: minimum effect size `-0.15 Sharpe units`
- `agents/forge/env.py`: `MINIMUM_EFFECT_SIZE: "-0.15 Sharpe units"`
- `sigma_job2.py` writes:
  - `"threshold": -0.15`

### Other implemented thresholds / cutoffs relevant to spec
- Passive concentration scenarios:
  - `0.10`, `0.30`, `0.60`
- Hypothesis threshold / macro allocator default threshold:
  - `0.30`
- Mean reversion trigger bands:
  - upper: `obs[0] > obs[1] * 1.02`
  - lower: `obs[0] < obs[1] * 0.98`
- Bid-ask spread exclusion threshold:
  - `0.02` = `2%`
- Minimum trading history:
  - `100` trading days
- Macro exclusion window:
  - `5` days on each side
- Near-zero Sharpe std guard:
  - `std < 1e-8` returns `0.0`

## 6. Windows

Exact windows/lookbacks implemented:

1. **Momentum lookback window**
   - `252`
   - Locations:
     - `ForgeRunner.lookback_window = 252`
     - `MOMENTUM_LOOKBACK_WINDOW = 252`
   - Used for:
     - 12-month momentum signal

2. **Primary metric rolling window**
   - `252` days
   - `ROLLING_CORRELATION_WINDOW = 252`
   - `PAPER.md`: Sharpe ratio differential annualized over rolling `252`-day windows
   - `sigma_job2.py` computes:
     - `_rolling_sharpe_differential(sim_df)`

3. **Fitness trailing window**
   - trailing `252` episodes
   - evaluated every `1000` training steps
   - code:
     - `trailing = self.rewards_history[-252:]`
     - `if episode % 1000 == 0 or episode == self.n_episodes`

4. **Episode length**
   - default `252`
   - `CommodityFuturesEnv(..., episode_length: int = 252)`

5. **Macro exclusion window**
   - `5` days before/after listed macro dates
   - implemented as `exclusion_days=5`

## 7. Fitness function for MetaRL

Exact implemented formula from `agents/forge/runner.py`:

- Fitness is evaluated every `1000` episodes/training steps, and at the final episode.
- The fitness input series is:
  - `trailing = self.rewards_history[-252:]`
- `self.rewards_history` stores:
  - `float(np.max(scores))` per episode
  - where `scores` are candidate episode rewards for the CEM population
- Fitness computation:
  - `fitness = self.sharpe(trailing)`

Exact Sharpe formula in `ForgeRunner.sharpe(step_returns)`:
```python
arr = np.asarray(step_returns, dtype=np.float64)
mean = arr.mean()
std = arr.std()
if std < 1e-8:
    return 0.0
return float((mean / std) * np.sqrt(252))
```

So the implemented MetaRL fitness function is:

\[
\text{fitness} =
\begin{cases}
0.0 & \text{if } n < 2 \\
0.0 & \text{if } \sigma < 10^{-8} \\
\left(\frac{\bar{x}}{\sigma}\right)\sqrt{252} & \text{otherwise}
\end{cases}
\]

where:
- \(x\) is the trailing window of the last up to `252` values from `rewards_history`
- each `rewards_history` value is the **maximum candidate score** in that episode:
  - `np.max(scores)`
- each candidate score is the episode mean of MetaRL step rewards:
  - `_run_single_episode(weights)` returns `episode_mean = mean(meta_step_rewards)`

## Consolidated specification-level parameter list

### Statistical/econometric parameters
- Newey-West HAC lags: `4`
- Two-tailed significance: `p < 0.05`
- Bonferroni corrected threshold: `p < 0.0083`
- Number of simultaneous tests in Bonferroni: `6`
- GARCH parameters: `(p=1, q=1)`, Normal distribution
- Markov switching regimes: `k_regimes=2`
- Bootstrap resamples: `1000`
- Deflated Sharpe `n_trials=6`

### Data parameters
- Source actually implemented: `yfinance`
- Tickers: `CL=F`, `NG=F`
- Date range requested: `2000-01-01` to `2024-01-01` exclusive
- Effective stated coverage: through `2023-12-31`
- Price adjustment in download: `auto_adjust=True`
- Returns: log returns
- Minimum history filter: `100` trading days
- Macro exclusion window: `±5` days
- Bid-ask spread threshold: `2%`

### Simulation parameters
- Agents:
  - `passive_gsci`
  - `trend_follower`
  - `mean_reversion`
  - `liquidity_provider`
  - `macro_allocator`
  - `meta_rl`
- Passive concentration scenarios:
  - `0.10`, `0.30`, `0.60`
- Episode length:
  - `252`
- Training episodes default:
  - `500_000`

### Window parameters
- Momentum lookback: `252`
- Rolling primary metric window: `252`
- Fitness trailing window: `252`
- Fitness evaluation frequency: every `1000` steps/episodes

### Seed parameters
- Seeds: `[1337, 42, 9999]`

### Minimum effect
- Sharpe differential threshold: `-0.15`