# CODEC Pass 1 Specification Extract

## 1. Statistical tests actually implemented

### Newey-West HAC t-test
- **Name:** OLS intercept test with **HAC/Newey-West** covariance
- **Library:** `statsmodels.api` (`sm.OLS(...).fit(cov_type="HAC", cov_kwds={"maxlags": 4})`)
- **Input:** `returns = sim_df["mean_reward"].to_numpy(dtype=float)`
- **Parameters actually used:**
  - Regressand: `returns`
  - Regressor: constant only (`x = np.ones((len(y), 1), dtype=float)`)
  - Covariance type: `"HAC"`
  - `maxlags = 4`
- **Reported outputs:**
  - `coef_mean`
  - `std_error_hac`
  - `t_stat`
  - `p_value`
  - `n_obs`
  - `maxlags`

### GARCH(1,1)
- **Name:** GARCH(1,1) volatility model
- **Library:** `arch` via `from arch import arch_model`
- **Input:** `returns * 100.0`
- **Parameters partially visible in provided code:**
  - Mean: `"Constant"`
  - Volatility: `"GARCH"`
- **Additional parameters:** not fully visible in provided snippet, so `p=1`, `q=1`, distribution, etc. cannot be confirmed from code excerpt alone.
- **Used downstream outputs:**
  - `alpha_pvalue`
  - `beta_pvalue`

### Bootstrap confidence interval / bootstrap test
- **Name:** Bootstrap CI / bootstrap test on returns
- **Library:** not shown in excerpt; likely internal NumPy-based implementation, but exact implementation not visible
- **Invocation parameters actually visible:**
  - `seed = self._seed_from_pap_lock()`
  - `n_resamples = 1000`
- **Used downstream output:**
  - `mean_lt_zero_p_value`

### Deflated Sharpe
- **Name:** Deflated Sharpe ratio test
- **Library:** internal method in `SigmaJob2`; exact external library not shown
- **Invocation parameters actually visible:**
  - `n_trials = 6`
- **Used downstream output:**
  - `p_value`

### Markov regime-switching model
- **Name:** Markov regime detection / Markov autoregression
- **Library:** `statsmodels.tsa.regime_switching.markov_autoregression.MarkovAutoregression`
- **Invocation:** `self._markov_regime(returns)`
- **Imported model class:** `MarkovAutoregression`
- **Exact fitted parameters:** not visible in provided excerpt
- **Used downstream output:**
  - `regime_mean_diff_p_value`

### Fama-MacBeth
- **Name:** Fama-MacBeth regression/result
- **Library:** exact implementation library not visible in excerpt
- **Invocation:** `self._fama_macbeth(returns)`
- **Used downstream output:**
  - `concentration_pvalue` via `fama_macbeth_result.get("concentration_pvalue", 1.0)`

### Bonferroni correction
- **Name:** Bonferroni multiple-testing correction
- **Library:** internal method
- **Invocation parameters actually used:**
  - p-values corrected:
    1. Newey-West t-test `p_value`
    2. GARCH `alpha_pvalue`
    3. GARCH `beta_pvalue`
    4. Deflated Sharpe `p_value`
    5. Markov regime `regime_mean_diff_p_value`
    6. Bootstrap `mean_lt_zero_p_value`
    7. Fama-MacBeth `concentration_pvalue` defaulting to `1.0`
  - `n_tests = 7`

## 2. Data

### Implemented miner data source
- **Primary implemented dev source:** `yfinance`
- **Function:** `yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)`

### Tickers actually used in miner
- `CL=F` mapped to `crude_oil_wti`
- `NG=F` mapped to `natural_gas`

### Date range actually used
- `START_DATE = "2000-01-01"`
- `END_DATE_EXCLUSIVE = "2024-01-01"`
- Comment: includes data through `2023-12-31`

### Return construction
- Close series downloaded, inner-joined across tickers
- Sorted by date
- Returns computed as:
  - `np.log(close_df / close_df.shift(1)).dropna()`
- Output index name: `"date"`

### Adjustment / roll method actually recorded
- Download uses:
  - `auto_adjust=True`
- Passport records:
  - `"roll_convention": "ratio_backward"`
  - `"adjustment_method": "ratio_backward"`
  - Note explicitly says:
    - `yfinance auto_adjust=True used as proxy for ratio_backward`
    - full WRDS run would apply `ratio_backward` exactly
    - deviation acknowledged

### Alternate source path
- `run_miner_pipeline(..., source="wrds")` supports `"wrds"` or `"yfinance"`
- If `source == "wrds"`:
  - imports `agents.miner.sources.wrds_src.fetch as wrds_fetch`
  - config passed:
    - `"kind": "ff_factors"`
    - `"start": "2000-01-01"`
    - `"end": "2024-01-01"`
- This WRDS branch writes `commodity_returns_wrds.csv`, but the actual fetched dataset contents are not visible here.

### Data consumed by SigmaJob2
- Source file: `outputs/sim_results.json`
- Required columns:
  - `concentration`
  - `seed`
  - `sharpe`
  - `mean_reward`
  - `n_episodes`

## 3. Simulation agents and behaviors

Environment defines six agents:
1. `passive_gsci`
2. `trend_follower`
3. `mean_reversion`
4. `liquidity_provider`
5. `macro_allocator`
6. `meta_rl`

### PassiveGSCI
- **Class:** `PassiveGSCI`
- **Behavior:** always returns action `1`
- In env, if current agent is `"passive_gsci"`, action is forcibly set to `1`
- Action space meaning:
  - `0 = hold`
  - `1 = long`
  - `2 = short`

### TrendFollower
- **Class:** `TrendFollower`
- **Behavior in class policy:** returns `1` if `obs[0] > obs[4]`, else `2`
- **Behavior actually used during training episodes in `_run_single_episode`:**
  - overrides class policy for `"trend_follower"`
  - computes:
    - `p0 = float(obs[0])`
    - `lookback_idx = min(4, len(self.env._price_history) - 1)`
    - `lookback_price = float(self.env._price_history[lookback_idx])`
    - `momentum_signal = p0 - lookback_price`
  - action:
    - `1` if `momentum_signal > 0`
    - else `2`
- In results metadata:
  - `momentum_lookback_steps = 252`
  - `momentum_signal = "price_level_difference_over_lookback"`
- But actual observation/history used in visible code is based on `obs[0]` vs `obs[4]` / `_price_history[4]`.

### MeanReversion
- **Class:** `MeanReversion`
- **Behavior:**
  - if `obs[0] > obs[1] * 1.02`: action `2`
  - if `obs[0] < obs[1] * 0.98`: action `1`
  - else: action `0`

### LiquidityProvider
- **Class:** `LiquidityProvider`
- **Behavior:** alternates each call
  - even counter: action `1`
  - odd counter: action `2`
- Counter increments every action
- Reset behavior in training:
  - `self.liquidity_agent = LiquidityProvider()` at start of each `_run_single_episode`

### MacroAllocator
- **Class:** `MacroAllocator(passive_threshold: float = 0.30)`
- **Behavior:**
  - returns `1` if `obs[6] < self.passive_threshold`
  - else `0`
- In runner initialization:
  - `passive_threshold=self.passive_concentration`
- Since `obs[6]` is environment `passive_concentration`, this means:
  - action `1` when concentration is below threshold
  - action `0` otherwise

### MetaRL
- **Class:** `MetaRL`
- Placeholder class behavior:
  - `random.randint(0, 2)`
- **Actual behavior used in runner episodes:**
  - action chosen by `self.cem.act(obs, weights)`
  - `CEM.act(obs, weights)` computes:
    - `logits = np.asarray(obs) @ np.asarray(weights)`
    - action = `argmax(logits)`

## 4. Seeds

### Exact seed values used in simulation sweep
- `1337`
- `42`
- `9999`

These appear in:
- `agents/forge/full_run.py`
- `agents/forge/modal_run.py`

### Seeding in ForgeRunner
- `np.random.seed(self.seed)`
- `random.seed(self.seed)`

### Environment reset seeding
- `CommodityFuturesEnv.reset(seed=...)` sets:
  - `np.random.seed(seed)` if seed is not `None`
- In visible runner code, `env.reset()` is called without explicit seed during episodes.

### SigmaJob2 seed
- Derived by `_seed_from_pap_lock()`
- Logic:
  - query latest `pap_sha256` from `pap_lock` for `run_id`
  - if present:
    - try `int(token[:8], 16)`
    - else hash token with SHA-256 and use `int(digest[:8], 16)`
  - fallback seed: `1337`

### Bootstrap seed
- Bootstrap called with:
  - `seed = self._seed_from_pap_lock()`

## 5. Thresholds

### Statistical significance thresholds actually visible in code
- No explicit primary alpha threshold is enforced in visible implementation excerpt.
- Bonferroni correction is applied with:
  - `n_tests = 7`

### Minimum effect size
- No minimum effect threshold is enforced in visible implementation code excerpt.

### Simulation scenario thresholds / discrete concentration levels
- Valid `passive_concentration` values in environment:
  - `0.10`
  - `0.30`
  - `0.60`
- Any other value raises `ValueError`

### MacroAllocator threshold
- `passive_threshold` defaults to `0.30`
- In runner, set to current scenario concentration

### MeanReversion thresholds
- Upper trigger: `obs[0] > obs[1] * 1.02`
- Lower trigger: `obs[0] < obs[1] * 0.98`

### Sharpe numerical threshold
- In `ForgeRunner.sharpe`:
  - if `len(step_returns) < 2`: return `0.0`
  - if `std < 1e-8`: return `0.0`

## 6. Windows

### Lookback / rolling windows actually implemented
- `ForgeRunner.lookback_window = 252`
- `MOMENTUM_LOOKBACK_WINDOW = 252`
- `ROLLING_CORRELATION_WINDOW = 252`
- `CommodityFuturesEnv.__init__(..., episode_length: int = 252)`

### Newey-West lag window
- `maxlags = 4`

### Volatility window in environment
- Environment maintains `_returns_window`
- Visible code shows:
  - append each `step_return`
  - if `len(self._returns_window) > 20`: trim/remove oldest
- So a **20-step rolling returns window** is implemented for volatility-related state updates.

### Observation history window actually visible
- `_price_history = [self.price] * 5`
- Observations include five price-history entries:
  - `self._price_history[0]` through `[4]`

### Bootstrap resampling count
- `n_resamples = 1000`

## 7. Fitness function for MetaRL

### Actual optimization target used in training
In `ForgeRunner.run()`:
- For each CEM candidate weights:
  - `total_reward = self._run_single_episode(weights)`
  - `scores.append(float(total_reward))`
- Then:
  - `self.cem.tell(scores)`

In `_run_single_episode(weights)`:
- Collects `meta_step_rewards` from rewards observed when `agent == "meta_rl"`
- Returns:
  - `episode_mean = float(np.mean(meta_step_rewards)) if meta_step_rewards else 0.0`

### Therefore the exact implemented MetaRL fitness is:
\[
\text{fitness}(w) = \operatorname{mean}(\text{meta\_step\_rewards during one episode under weights } w)
\]

Equivalent code formula:
```python
episode_mean = float(np.mean(meta_step_rewards)) if meta_step_rewards else 0.0
return episode_mean
```

### Not the training fitness, but reported evaluation metric
`ForgeRunner.sharpe(step_returns)` computes:
\[
\text{Sharpe} = \left(\frac{\bar r}{\sigma(r)}\right)\sqrt{252}
\]
with:
- `r = np.asarray(step_returns, dtype=np.float64)`
- `mean = arr.mean()`
- `std = arr.std()`
- returns `0.0` if `len(step_returns) < 2` or `std < 1e-8`

This Sharpe is used for:
- periodic printing every 100 episodes
- final reported results

## Additional specification-level environment details

### Observation vector (length 10)
For each agent, observation is:
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

### Action space
- `Discrete(3)`
- Semantics:
  - `0 = hold`
  - `1 = long`
  - `2 = short`

### Episode length
- Default: `252`

### Market-impact / concentration mechanism
Visible implemented parameters in `_apply_market_step()`:
- `concentration_risk = 1.0 + 6.0 * (concentration**2)`
- `noise ~ Normal(0.0, 0.006 * concentration_risk)`
- `flow_impact = 0.0003 * (1.0 + 5.0 * (concentration**2))`
- `concentration_drag = 0.0002 * (concentration**2)`
- Price update:
\[
\text{price}_{t+1} = \text{price}_t \cdot \left(1 + \text{flow\_impact}\cdot \text{net\_order\_flow} + \text{noise} - \text{concentration\_drag}\right)
\]
- Lower bound:
  - `price = max(price, 1e-6)`

## Implementation vs spec mismatches visible from code

Only reporting what code shows:

- **Bonferroni tests actually corrected:** `7`, not `6`
- **MetaRL fitness actually used:** mean meta-step reward per episode, **not** Sharpe over trailing 252 episodes
- **Periodic evaluation frequency:** every `100` episodes for printed Sharpe, not every `1000` training steps
- **Data source actually implemented for dev path:** `yfinance` with `auto_adjust=True` proxy
- **Trend signal implementation visible in code:** based on short visible price-history entries (`obs[0]`, `obs[4]` / `_price_history[4]`), despite metadata claiming 252-step momentum lookback