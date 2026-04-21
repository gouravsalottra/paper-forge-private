# CODEC Pass 1 Specification Extraction

## 1. Statistical tests actually implemented

### Newey-West HAC t-test
- **Name:** OLS mean test with **Newey-West / HAC** standard errors
- **Implementation location:** `agents/sigma_job2.py::_newey_west_ttest`
- **Library:** `statsmodels.api` (`sm.OLS(...).fit(cov_type="HAC", cov_kwds={"maxlags": 4})`)
- **Parameters actually used:**
  - Dependent variable: `returns = sim_df["mean_reward"].to_numpy(dtype=float)`
  - Regressor: constant only (`x = np.ones((len(y), 1), dtype=float)`)
  - Covariance type: `"HAC"`
  - `maxlags = 4`
- **Outputs recorded:**
  - `coef_mean`
  - `std_error_hac`
  - `t_stat`
  - `p_value`
  - `n_obs`
  - `maxlags`

### GARCH(1,1)
- **Name:** **GARCH(1,1)** volatility model
- **Implementation location:** `agents/sigma_job2.py::_garch_11`
- **Library:** `arch` via `arch_model`
- **Parameters visible in provided code/context:**
  - Input series: `returns * 100.0`
  - Mean model: `"Constant"`
  - Volatility model: `"GARCH"`
- **From `PAPER.md` specification and matching code intent:**
  - `p = 1`
  - `q = 1`
  - Distribution: `Normal`
- **Used in multiple-testing correction via returned fields:**
  - `alpha_pvalue`
  - `beta_pvalue`

### Bootstrap confidence interval / bootstrap test
- **Name:** Bootstrap CI / bootstrap test on mean reward
- **Implementation location:** `agents/sigma_job2.py::_bootstrap_ci`
- **Library:** not shown explicitly in snippet; uses NumPy-based workflow implied by surrounding code
- **Parameters actually used:**
  - `seed = self._seed_from_pap_lock()`
  - `n_resamples = 1000`
  - Input series: `returns`
- **Used output in Bonferroni list:**
  - `mean_lt_zero_p_value`

### Deflated Sharpe test
- **Name:** Deflated Sharpe
- **Implementation location:** `agents/sigma_job2.py::_deflated_sharpe`
- **Library:** internal implementation in `sigma_job2.py`; `scipy.stats.norm` imported and likely used
- **Parameters actually used:**
  - Input series: `returns`
  - `n_trials = 6`
- **Used output in Bonferroni list:**
  - `p_value`

### Markov regime-switching model
- **Name:** Markov regime detection / Markov switching autoregression
- **Implementation location:** `agents/sigma_job2.py::_markov_regime`
- **Library:** `statsmodels.tsa.regime_switching.markov_autoregression.MarkovAutoregression`
- **Parameters visible from context:**
  - Input series: `returns`
- **From `PAPER.md` specification and matching imported model intent:**
  - `k_regimes = 2`
- **Used output in Bonferroni list:**
  - `regime_mean_diff_p_value`

### Fama-MacBeth regression
- **Name:** Fama-MacBeth regression
- **Implementation location:** `agents/sigma_job2.py::_fama_macbeth`
- **Library:** implementation writes `fama_macbeth_results.csv`; `linearmodels` version is recorded in `library_versions.json`, indicating intended dependency
- **Parameters visible from context:**
  - Input series: `returns`
- **Used output in Bonferroni list:**
  - `concentration_pvalue` if present, else default `1.0`

### Bonferroni correction
- **Name:** Bonferroni multiple-testing correction
- **Implementation location:** `agents/sigma_job2.py::_bonferroni`
- **Parameters actually used:**
  - p-values corrected:
    1. Newey-West t-test `p_value`
    2. GARCH `alpha_pvalue`
    3. GARCH `beta_pvalue`
    4. Deflated Sharpe `p_value`
    5. Markov regime `regime_mean_diff_p_value`
    6. Bootstrap `mean_lt_zero_p_value`
    7. Fama-MacBeth `concentration_pvalue` or `1.0`
  - `n_tests = 7`

## 2. Data

### Implemented data source
- **Primary implemented dev source:** `yfinance`
- **Implementation location:** `agents/miner/miner.py`
- **Function:** `download_close_series`
- **Call:** `yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)`

### Alternate source path
- **Optional source contract:** `"wrds"` or `"yfinance"` in `run_miner_pipeline`
- If `source == "wrds"`, code attempts `agents.miner.sources.wrds_src.fetch(...)`
- However, the concrete commodity-return-building implementation shown is the `yfinance` path

### Tickers actually used in commodity return construction
- `CL=F` → `"crude_oil_wti"`
- `NG=F` → `"natural_gas"`

### Date range actually used
- `START_DATE = "2000-01-01"`
- `END_DATE_EXCLUSIVE = "2024-01-01"`
- Comment: includes data through `2023-12-31`

### Return construction
- Close series are concatenated with `join="inner"`
- Sorted by index
- Returns computed as:
  - `np.log(close_df / close_df.shift(1)).dropna()`
- Output index name: `"date"`

### Adjustment / roll method actually recorded
- `auto_adjust=True` in `yfinance` download
- Data passport records:
  - `"roll_convention": "ratio_backward"`
  - `"adjustment_method": "ratio_backward"`
  - `"adjustment_method_note": "yfinance auto_adjust=True used as proxy for ratio_backward..."`

### Data source note recorded
- Dev run note says:
  - yfinance is a proxy for WRDS Compustat Futures
  - tickers `CL=F` and `NG=F` approximate GSCI energy sector

## 3. Simulation agents and behaviors

Implementation location: `agents/forge/agents.py`, with some behavior overridden in `agents/forge/runner.py`

### `passive_gsci` / `PassiveGSCI`
- **Behavior in class:** always returns action `1`
- **Environment enforcement:** in `CommodityFuturesEnv.step`, if agent is `"passive_gsci"`, action is forced to `1`
- **Interpretation from action space:** always **long**

### `trend_follower` / `TrendFollower`
- **Class behavior:** `return 1 if obs[0] > obs[4] else 2`
  - compares current price-like field `obs[0]` to lookback field `obs[4]`
  - long if current > lookback, else short
- **Runner override during training episodes (`_run_single_episode`):**
  - `p0 = float(obs[0])`
  - `lookback_idx = min(4, len(self.env._price_history) - 1)`
  - `lookback_price = float(self.env._price_history[lookback_idx])`
  - `momentum_signal = p0 - lookback_price`
  - `trend_action = 1 if momentum_signal > 0 else 2`
- **Reported metadata in results:**
  - `momentum_lookback_steps = 252`
  - `momentum_signal = "price_level_difference_over_lookback"`

### `mean_reversion` / `MeanReversion`
- **Behavior:**
  - if `obs[0] > obs[1] * 1.02`: return `2` (short)
  - if `obs[0] < obs[1] * 0.98`: return `1` (long)
  - else return `0` (hold)

### `liquidity_provider` / `LiquidityProvider`
- **Behavior:**
  - alternates actions each call
  - starts with `_counter = 0`
  - returns `1` when counter even, `2` when odd
  - increments counter after each action
- **Episode reset behavior:** runner reinstantiates `LiquidityProvider()` at start of each `_run_single_episode`

### `macro_allocator` / `MacroAllocator`
- **Parameter:** `passive_threshold: float = 0.30`
- **Runner instantiation:** `MacroAllocator(passive_threshold=self.passive_concentration)`
- **Behavior:**
  - returns `1` if `obs[6] < self.passive_threshold`
  - else returns `0`
- Since `obs[6]` is `self.passive_concentration`, and threshold is set equal to that same concentration in runner, this condition is effectively false in normal operation, so it will typically return `0`

### `meta_rl` / `MetaRL`
- **Class placeholder behavior:** random integer action in `[0, 2]` via `random.randint(0, 2)`
- **Actual behavior in runner episodes:** not using `MetaRL.act`; instead uses `self.cem.act(obs, weights)`
- **CEM action rule:** `argmax(obs @ weights)`

### Agent set in environment
`CommodityFuturesEnv.possible_agents`:
1. `"passive_gsci"`
2. `"trend_follower"`
3. `"mean_reversion"`
4. `"liquidity_provider"`
5. `"macro_allocator"`
6. `"meta_rl"`

### Action meanings
From environment action spaces:
- `0 = hold`
- `1 = long`
- `2 = short`

## 4. Seeds

### Exact seed values used in simulation sweep
Implementation location: `agents/forge/full_run.py` and `agents/forge/modal_run.py`
- `1337`
- `42`
- `9999`

### Seed application in runner
Implementation location: `agents/forge/runner.py`
- `np.random.seed(self.seed)`
- `random.seed(self.seed)`

### Environment reset seed handling
Implementation location: `agents/forge/env.py`
- `reset(seed=...)` sets `np.random.seed(seed)` if seed is provided
- In runner, environment is usually reset without explicit seed during episodes

### Sigma bootstrap seed
Implementation location: `agents/sigma_job2.py`
- `seed = self._seed_from_pap_lock()`
- If PAP lock row exists:
  - seed derived from first 8 hex chars of `pap_sha256`
  - fallback: SHA-256 hash of token, then first 8 hex chars
- If no PAP lock seed derivation possible:
  - fallback seed = `1337`

## 5. Thresholds

### Statistical significance thresholds in spec
From `PAPER.md`:
- Primary significance: `p < 0.05` two-tailed
- Bonferroni-corrected significance: `p < 0.0083`

### Bonferroni threshold implied by implementation
- `n_tests = 7` in `sigma_job2.py`
- So implementation-level adjusted threshold would be `0.05 / 7 ≈ 0.00714` if computed conventionally
- The code excerpt explicitly shows `n_tests=7`; no explicit threshold value is shown in snippet

### Minimum effect size
From `PAPER.md`:
- `-0.15` Sharpe units
- Effects smaller than this are economically insignificant

### Passive concentration scenario thresholds
Implementation location: `agents/forge/env.py`, `agents/forge/full_run.py`, `PAPER.md`
- Valid concentrations:
  - `0.10`
  - `0.30`
  - `0.60`
- Hypothesis threshold / medium scenario:
  - `0.30`

### Mean reversion thresholds
Implementation location: `agents/forge/agents.py`
- Short if current price exceeds reference by **2%**
- Long if current price is below reference by **2%**
- Specifically:
  - `obs[0] > obs[1] * 1.02`
  - `obs[0] < obs[1] * 0.98`

### Numerical Sharpe guard threshold
Implementation location: `agents/forge/runner.py`
- If return std `< 1e-8`, Sharpe returned as `0.0`

### Environment concentration validation
Implementation location: `agents/forge/env.py`
- Allowed set exactly `{0.10, 0.30, 0.60}`

## 6. Windows

### Momentum lookback window
Implementation locations:
- `agents/forge/runner.py`: `self.lookback_window = 252`
- `agents/forge/env.py`: `MOMENTUM_LOOKBACK_WINDOW = 252`
- `PAPER.md`: 12-month momentum / rolling 252-day windows
- Reported in results as:
  - `momentum_lookback_steps: 252`

### Rolling correlation window
Implementation location: `agents/forge/env.py`
- `ROLLING_CORRELATION_WINDOW = 252`

### Episode length
Implementation location: `agents/forge/env.py`
- `episode_length = 252` by default

### HAC lag window
Implementation location: `agents/sigma_job2.py`
- `maxlags = 4`

### Volatility tracking window in environment
Implementation location: `agents/forge/env.py`
- `_returns_window` maintained
- visible truncation logic:
  - `if len(self._returns_window) > 20: ...`
- So a **20-step rolling returns window** is implemented for internal volatility tracking

### Fitness evaluation cadence from spec
From `PAPER.md`:
- trailing `252` episodes
- evaluated every `1000` training steps
- **Not matched by runner implementation**

### Actual runner reporting cadence
Implementation location: `agents/forge/runner.py`
- Every `100` episodes:
  - computes `step_returns = self._run_episode_returns(self.cem.best())`
  - computes `sharpe(step_returns)`
  - prints best Sharpe

## 7. Fitness function for MetaRL

## Actual implemented optimization target
Implementation location: `agents/forge/runner.py::_run_single_episode`

For each CEM candidate `weights`:
1. Run one episode
2. Collect `meta_step_rewards` only when `agent == "meta_rl"`
3. Compute:
   - `episode_mean = float(np.mean(meta_step_rewards)) if meta_step_rewards else 0.0`
4. Return `episode_mean`

Then in training loop:
- `scores.append(float(total_reward))`
- `self.cem.tell(scores)`

### Exact implemented fitness formula
\[
\text{fitness}(w) = \frac{1}{T}\sum_{t=1}^{T} r_t^{(\text{meta\_rl})}
\]
where:
- \(w\) = candidate weight matrix
- \(r_t^{(\text{meta\_rl})}\) = per-step reward observed when the active agent is `meta_rl`
- \(T\) = number of `meta_rl` decision steps in the episode

If there are no meta-RL rewards collected:
\[
\text{fitness}(w) = 0.0
\]

## Sharpe formula used for reporting, not fitness
Implementation location: `agents/forge/runner.py::sharpe`

For a list of per-step returns `arr`:
\[
\text{Sharpe} =
\begin{cases}
0.0, & \text{if } \text{len}(arr) < 2 \\
0.0, & \text{if } \sigma(arr) < 10^{-8} \\
\left(\frac{\mu(arr)}{\sigma(arr)}\right)\sqrt{252}, & \text{otherwise}
\end{cases}
\]

So:
- **MetaRL fitness actually used for optimization:** mean meta-step reward per episode
- **Sharpe is only used for monitoring and final reporting**, not as the CEM objective in the shown implementation

## Additional implementation-level simulation parameters

### Training episodes
- Default `n_episodes = 500_000`
- Used in:
  - `ForgeRunner.__init__`
  - `run_full_sweep`
  - `modal_run`

### Passive concentration scenarios
- `0.10`, `0.30`, `0.60`

### Environment observation vector (10-dimensional)
Implementation location: `agents/forge/env.py::observe`
Order:
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

### Environment action space
- `Discrete(3)` for all agents
- `0=hold, 1=long, 2=short`

### Market-step parameters
Implementation location: `agents/forge/env.py::_apply_market_step`
- `concentration_risk = 1.0 + 6.0 * (concentration**2)`
- `noise ~ Normal(0.0, 0.006 * concentration_risk)`
- `flow_impact = 0.0003 * (1.0 + 5.0 * (concentration**2))`
- `concentration_drag = 0.0002 * (concentration**2)`

## Summary of spec/code mismatches visible from provided code

### Statistical tests
- `PAPER.md` says Bonferroni for **6** simultaneous tests and threshold `p < 0.0083`
- `sigma_job2.py` actually applies Bonferroni to **7** p-values with `n_tests=7`

### MetaRL fitness
- `PAPER.md`: fitness = Sharpe ratio over trailing 252 episodes, evaluated every 1000 training steps
- `runner.py`: fitness actually optimized = **mean meta-step reward within a single episode**, with progress Sharpe printed every **100** episodes

### Trend-following lookback
- `PAPER.md` and runner metadata say 12-month / 252-step momentum
- Actual decision logic shown compares current price to a very short stored history index (`obs[4]` or `_price_history[4]`), not a 252-step history in the visible code