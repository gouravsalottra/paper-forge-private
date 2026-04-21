# PASS1

## 1. Statistical tests actually implemented

### A. Newey-West HAC two-tailed t-test
- **Name/spec**: Newey-West HAC-corrected t-test on returns
- **Where used**: `SigmaJob2.run()` via `_newey_west_ttest(returns)`
- **Input tested**: `returns = sim_df["mean_reward"].to_numpy(dtype=float)`
- **Primary significance flag**: `primary_significance_pass = bool(ttest_result.get("passes_alpha", False))`
- **Parameters evidenced in provided context**
  - Paper spec says:
    - **two-tailed**
    - **alpha = 0.05**
    - **Newey-West HAC correction with 4 lags**
- **Library**
  - `statsmodels.api as sm` imported in `agents/sigma_job2.py`
- **Notes**
  - The helper body is not shown, so only the call and paper-level parameters can be stated from context.

### B. GARCH(1,1) volatility model
- **Name/spec**: GARCH(1,1) volatility model
- **Where used**: `SigmaJob2.run()` via `_garch_11(returns)`
- **Input tested**: same `returns` array from `sim_df["mean_reward"]`
- **Parameters**
  - **p = 1**
  - **q = 1**
  - **distribution = Normal**
- **Library**
  - `arch`, specifically `from arch import arch_model`
- **Output field referenced**
  - `garch_result["alpha_pvalue"]` is included in Bonferroni correction input list

### C. Bootstrap confidence interval / bootstrap tail probability
- **Name/spec**: bootstrap CI / bootstrap test on mean
- **Where used**: `SigmaJob2.run()` via `_bootstrap_ci(returns, seed=seed, n_resamples=1000)`
- **Parameters**
  - **seed = 1337** for this call
  - **n_resamples = 1000**
- **Library**
  - Not explicitly shown for the helper; likely NumPy-based, but not directly visible in provided code
- **Output field referenced**
  - `bootstrap_result["mean_lt_zero_p_value"]` is included in Bonferroni correction inputs

### D. Deflated Sharpe test
- **Name/spec**: deflated Sharpe evaluation
- **Where used**: `SigmaJob2.run()` via `_deflated_sharpe(returns, n_trials=6)`
- **Parameters**
  - **n_trials = 6**
- **Library**
  - Not shown in helper body
- **Output field referenced**
  - `deflated_result["p_value"]` is included in Bonferroni correction inputs

### E. Markov switching / regime detection
- **Name/spec**: Markov regime model / Markov switching regime detection
- **Where used**: `SigmaJob2.run()` via `_markov_regime(returns)`
- **Parameters**
  - Paper/env spec says **k_regimes = 2**
- **Library**
  - `statsmodels`
  - specifically `from statsmodels.tsa.regime_switching.markov_autoregression import MarkovAutoregression`
- **Output field referenced**
  - `regime_result["regime_mean_diff_p_value"]` is included in Bonferroni correction inputs

### F. Fama-MacBeth regression
- **Name/spec**: Fama-MacBeth regression
- **Where used**: `SigmaJob2.run()` via `_fama_macbeth_regression(sim_df)`
- **Input tested**: `sim_df`
- **Parameters**
  - No helper-body parameters shown
- **Library**
  - Paper string says `"Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)"`
  - `linearmodels` is not imported in shown code, but version is recorded in `library_versions.json`
- **Output field referenced**
  - `fama_result.get("concentration_pvalue", 1.0)` is included in Bonferroni correction inputs

### G. Fama-French three-factor OLS regression
- **Name/spec**: Fama-French three-factor OLS regression
- **Where used**: `SigmaJob2.run()` via `_fama_french_three_factor_ols(sim_df)`
- **Input tested**: `sim_df`
- **Parameters**
  - **three factors**
- **Library**
  - Spec string in code: `"Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)"`
  - Exact helper implementation not shown
- **Output handling**
  - Written to `fama_french_ols_results.csv`

### H. DCC-GARCH cross-asset correlation summary
- **Name/spec**: DCC-GARCH cross-asset correlation
- **Where used**: `SigmaJob2.run()` via `_dcc_garch_summary()`
- **Parameters**
  - No helper-body parameters shown
- **Library**
  - Not shown in provided code
- **Output fields written**
  - `method`
  - `n_pairs`
  - `mean_dcc_correlation`
  - `error`

### I. Bonferroni multiple-testing correction
- **Name/spec**: Bonferroni correction
- **Where used**: `SigmaJob2.run()` via `_bonferroni([...], n_tests=6, primary_metric=primary_metric)`
- **Parameters**
  - **n_tests = 6**
  - Paper/env spec threshold: **p < 0.0083**
- **P-values corrected jointly**
  1. `ttest_result["p_value"]`
  2. `garch_result["alpha_pvalue"]`
  3. `deflated_result["p_value"]`
  4. `regime_result["regime_mean_diff_p_value"]`
  5. `bootstrap_result["mean_lt_zero_p_value"]`
  6. `fama_result.get("concentration_pvalue", 1.0)`

## 2. Data actually implemented

### Source actually used in code
- **Implemented source in MINER dev pipeline**: `yfinance`
  - `import yfinance as yf`
  - Used in:
    - `download_close_series()`
    - `download_spread_proxy_series()`
- **Paper spec source**: `WRDS Compustat Futures — GSCI energy sector`
- **Important distinction**
  - The code shown for actual return construction uses **yfinance**, not WRDS.
  - Comments indicate WRDS is intended for a fuller run, but the implemented extraction here is yfinance-based.

### Tickers actually used
- `CL=F` → `crude_oil_wti`
- `NG=F` → `natural_gas`

### Date range actually used
- `START_DATE = "2000-01-01"`
- `END_DATE_EXCLUSIVE = "2024-01-01"`
- Therefore download window is:
  - **start inclusive**: `2000-01-01`
  - **end exclusive**: `2024-01-01`
  - comment says this **includes data through 2023-12-31**
- Passport writes:
  - nominal date range start: `2000-01-01`
  - nominal date range end: `2023-12-31`

### Adjustment method actually used
- In yfinance downloads:
  - `auto_adjust=True`
- Paper spec also states:
  - **Roll convention**: `ratio_backward`
  - **Adjustment method**: `ratio_backward`
- But in the shown implemented MINER code, the actual download adjustment is **yfinance auto-adjust**, not an explicit ratio-backward futures roll implementation.

### Return construction
- Returns are computed as:
  - `np.log(close_df / close_df.shift(1)).dropna()`
- So:
  - **log returns**
  - on adjusted close series

### Exclusion/filter rules actually implemented on data
- **Minimum trading history**
  - retain only columns with at least **100 trading days**
- **Macro exclusion window**
  - `apply_macro_exclusion_window(df, exclusion_days=5)`
  - excludes rows within **±5 days** of listed approximate FOMC dates
  - comments say CPI/FOMC intended by paper, but shown list is `FOMC_DATES_APPROX`
- **Bid-ask spread filter**
  - `apply_bid_ask_spread_filter(..., threshold=0.02)`
  - spread proxy = `abs(high - low) / close`
  - removes rows where rowwise max spread proxy exceeds **0.02**

## 3. Simulation agents and behaviors actually implemented

Environment possible agents:
1. `passive_gsci`
2. `trend_follower`
3. `mean_reversion`
4. `liquidity_provider`
5. `macro_allocator`
6. `meta_rl`

### passive_gsci / `PassiveGSCI`
- **Behavior**: always returns action `1`
- In env action semantics:
  - `0 = hold`
  - `1 = long`
  - `2 = short`

### trend_follower / `TrendFollower`
Two behaviors appear in code:

#### Class behavior in `agents/forge/agents.py`
- `return 1 if obs[0] > obs[4] else 2`
- So class policy:
  - long if `obs[0] > obs[4]`
  - otherwise short

#### Overridden behavior during training episode in `ForgeRunner._run_single_episode`
- For `agent == "trend_follower"`:
  - `p0 = float(obs[0])`
  - `lookback_idx = max(0, len(self.env._price_history) - self.lookback_window)`
  - `lookback_price = float(self.env._price_history[lookback_idx])`
  - `momentum_signal = p0 - lookback_price`
  - `trend_action = 1 if momentum_signal > 0 else 2`
- So training-time trend behavior is:
  - **12-month momentum using current price minus lookback price**
  - **lookback_window = 252**
  - long if positive momentum, else short

### mean_reversion / `MeanReversion`
- If `obs[0] > obs[1] * 1.02`: return `2` (short)
- If `obs[0] < obs[1] * 0.98`: return `1` (long)
- Else return `0` (hold)
- So:
  - fades deviations beyond **±2%** relative to `obs[1]`

### liquidity_provider / `LiquidityProvider`
- Alternates actions each call:
  - even counter → `1`
  - odd counter → `2`
- Counter increments every action
- In `_run_single_episode`, this agent is reinitialized each episode:
  - `self.liquidity_agent = LiquidityProvider()`
- So per episode it starts alternating from `1`

### macro_allocator / `MacroAllocator`
- Constructor parameter:
  - `passive_threshold: float = 0.30`
- In runner it is instantiated as:
  - `MacroAllocator(passive_threshold=self.passive_concentration)`
- Behavior:
  - `return 1 if obs[6] < self.passive_threshold else 0`
- So:
  - long if `obs[6]` is below threshold
  - otherwise hold

### meta_rl / `MetaRL`
Two behaviors appear:

#### Placeholder class behavior in `agents/forge/agents.py`
- `return random.randint(0, 2)`

#### Actual training/evaluation behavior in runner
- In both `_run_single_episode` and `_run_episode_returns`, when `agent == "meta_rl"`:
  - action = `self.cem.act(obs, weights)`
- `CEM.act(obs, weights)` computes:
  - `logits = np.asarray(obs) @ np.asarray(weights)`
  - returns `argmax(logits)`
- So actual trained policy behavior:
  - linear score over 10-dim observation into 3 actions
  - choose argmax action

## 4. Seeds: exact values used

### Required seed policy
- `REQUIRED_SEEDS = [1337, 42, 9999]`
- Also encoded as strings:
  - `SEED_POLICY_SPEC: "seeds = [1337, 42, 9999]"`
  - env `SEED_POLICY: "seeds = [1337, 42, 9999]"`

### Seed used inside `SigmaJob2.run()`
- `seed = REQUIRED_SEEDS[0]`
- Therefore:
  - **1337** is used for bootstrap call in shown code

### Seeds used for simulation sweeps
- In `agents/forge/full_run.py`:
  - `seeds = [1337, 42, 9999]`
- In `agents/forge/modal_run.py`:
  - `seeds = [1337, 42, 9999]`

### RNG seeding in runner
- In `ForgeRunner.__init__`:
  - `np.random.seed(self.seed)`
  - `random.seed(self.seed)`

### Environment reset seeding
- In `CommodityFuturesEnv.reset(seed=...)`:
  - if seed is not `None`, `np.random.seed(seed)`

## 5. Thresholds: significance levels, minimum effects

### Statistical significance thresholds
- **Primary significance threshold**
  - `p < 0.05`
  - **two-tailed**
- **Bonferroni-corrected threshold**
  - `p < 0.0083`
  - for **6 simultaneous tests**

### Minimum effect size / economic significance
- **Minimum effect size**: `-0.15 Sharpe units`
- In `SigmaJob2.run()` written to CSV as:
  - `"threshold": -0.15`
- Primary metric output checks:
  - `primary_metric.get("meets_minimum_effect")`
  - `primary_metric.get("economic_significance")`

### Passive concentration thresholds/scenarios
- Valid concentrations in env:
  - `0.10`
  - `0.30`
  - `0.60`
- Paper/env labels:
  - Low: **10%**
  - Medium: **30%**
  - High: **60%**
- Hypothesis threshold:
  - above **30%** concentration

### Data exclusion thresholds
- **Bid-ask spread threshold**: `0.02` = **2%**
- **Minimum trading history**: `100` trading days
- **Macro exclusion window**: `5` days on either side of listed dates

### Mean reversion thresholds
- Short if price > reference by **2%**
- Long if price < reference by **2%**
- Otherwise hold

### Numerical stability threshold in Sharpe function
- If `std < 1e-8`, Sharpe returns `0.0`

## 6. Windows: lookback periods, rolling windows

### Momentum lookback
- `lookback_window = 252`
- `MOMENTUM_LOOKBACK_WINDOW = 252`
- Interpreted as **12-month momentum**

### Rolling primary metric window
- `ROLLING_CORRELATION_WINDOW = 252`
- Paper primary metric:
  - Sharpe ratio differential annualized over **rolling 252-day windows**

### Fitness trailing window
- Fitness evaluated on:
  - `trailing = self.rewards_history[-252:]`
- So fitness uses **trailing 252 episodes**

### Evaluation frequency
- Fitness evaluated every **1000 training steps/episodes**
  - condition: `if episode % 1000 == 0 or episode == self.n_episodes`

### Episode length
- `CommodityFuturesEnv(..., episode_length: int = 252)`
- So default episode length is **252**

### Macro exclusion window
- `exclusion_days = 5`
- Applied as **±5 days**

## 7. Fitness function: exact formula used for MetaRL

### Declared fitness function
- In results:
  - `'fitness_function': 'trailing_252_episode_sharpe_every_1000_steps'`

### When computed
- Every **1000** episodes, and at final episode:
  - uses `self.rewards_history[-252:]`

### What `rewards_history` contains
- Each episode appends:
  - `self.rewards_history.append(float(np.max(scores)))`
- `scores` are candidate episode scores for current CEM population
- Each candidate score is:
  - `total_reward = self._run_single_episode(weights)`
- `_run_single_episode(weights)` returns:
  - `episode_mean = float(np.mean(meta_step_rewards)) if meta_step_rewards else 0.0`
- Therefore each element of `rewards_history` is:
  - **the maximum across candidates of the episode mean meta_rl step reward**

### Exact Sharpe formula used
From `ForgeRunner.sharpe(step_returns)`:
```python
if len(step_returns) < 2:
    return 0.0
arr = np.asarray(step_returns, dtype=np.float64)
mean = arr.mean()
std = arr.std()
if std < 1e-8:
    return 0.0
return float((mean / std) * np.sqrt(252))
```

### Therefore MetaRL fitness is exactly
For the trailing window `trailing = self.rewards_history[-252:]`:

\[
\text{fitness} =
\begin{cases}
0.0, & \text{if } |\text{trailing}| < 2 \\
0.0, & \text{if } \operatorname{std}(\text{trailing}) < 10^{-8} \\
\left(\frac{\operatorname{mean}(\text{trailing})}{\operatorname{std}(\text{trailing})}\right)\sqrt{252}, & \text{otherwise}
\end{cases}
\]

where each trailing element is the **best candidate's episode mean meta_rl reward** from that training episode.

## Additional specification-level implemented items

### Simulation scenarios
- Concentrations swept:
  - `0.10`, `0.30`, `0.60`
- Seeds swept:
  - `1337`, `42`, `9999`
- Total scenarios:
  - 9 concentration-seed combinations

### Training episodes
- Default:
  - `n_episodes = 500_000`
- Present in:
  - `ForgeRunner.__init__`
  - `run_full_sweep`
  - Modal entrypoints

### Action space
- `Discrete(3)`
- Semantics:
  - `0 = hold`
  - `1 = long`
  - `2 = short`

### Observation space
- `Box(..., shape=(10,), dtype=np.float32)`
- So observation dimension is **10**

### Seed consistency requirement
- Encoded in paper and checked in SigmaJob2:
  - all three seeds must produce qualitatively consistent results
  - finding valid only if it holds across all three seeds
- `SigmaJob2.run()` calls:
  - `_validate_seed_consistency(sim_df)`
- Output fields written:
  - `consistent`
  - `finding_valid`
  - `conclusion`