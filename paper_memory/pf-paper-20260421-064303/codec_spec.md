# CODEC Pass 1 Specification Extraction

## 1. Statistical tests

### Implemented / specified in code context

1. **Two-tailed t-test with Newey-West HAC correction**
   - **Name:** Newey-West HAC t-test / two-tailed t-test
   - **Parameters:**
     - HAC lags: **4**
     - Primary significance threshold: **p < 0.05**
     - Two-tailed
   - **Library:**
     - `statsmodels.api as sm` imported in `agents/sigma_job2.py`
   - **Evidence:**
     - `ttest_result = self._newey_west_ttest(returns)`
     - `NEWEY_WEST_HAC_LAGS: "4 lags"`
     - `SIGNIFICANCE_THRESHOLD_PRIMARY: "p < 0.05 two-tailed"`

2. **Bonferroni correction**
   - **Name:** Bonferroni correction for simultaneous tests
   - **Parameters:**
     - Number of simultaneous tests: **6**
     - Adjusted threshold: **p < 0.0083**
     - Applied to p-values from:
       - t-test
       - GARCH alpha p-value
       - deflated Sharpe p-value
       - regime mean-difference p-value
       - bootstrap mean<0 p-value
       - Fama-MacBeth concentration p-value
   - **Library:** no external library shown; internal method `_bonferroni(...)`
   - **Evidence:**
     - `_bonferroni([...], n_tests=6, primary_metric=primary_metric)`
     - `BONFERRONI_CORRECTION: "Bonferroni correction for 6 simultaneous tests — adjusted threshold p < 0.0083"`

3. **GARCH(1,1) volatility model**
   - **Name:** GARCH(1,1)
   - **Parameters:**
     - `p=1`
     - `q=1`
     - Distribution: **Normal**
   - **Library:**
     - `arch`, via `from arch import arch_model`
   - **Evidence:**
     - `garch_result = self._garch_11(returns)`
     - `GARCH_MODEL: "GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution)"`

4. **Bootstrap confidence interval / bootstrap test**
   - **Name:** Bootstrap CI
   - **Parameters:**
     - `seed=1337` in `run()`
     - `n_resamples=1000`
     - Reported p-value key: `mean_lt_zero_p_value`
   - **Library:** not explicitly shown; likely internal implementation using NumPy/Pandas
   - **Evidence:**
     - `bootstrap_result = self._bootstrap_ci(returns, seed=seed, n_resamples=1000)`

5. **Deflated Sharpe test**
   - **Name:** Deflated Sharpe
   - **Parameters:**
     - `n_trials=6`
     - Reported p-value key: `p_value`
   - **Library:** not explicitly shown
   - **Evidence:**
     - `deflated_result = self._deflated_sharpe(returns, n_trials=6)`

6. **Markov switching regime detection / Markov autoregression**
   - **Name:** Markov switching regime detection
   - **Parameters:**
     - `k_regimes=2`
   - **Library:**
     - `statsmodels`
     - specifically `statsmodels.tsa.regime_switching.markov_autoregression.MarkovAutoregression`
   - **Evidence:**
     - `regime_result = self._markov_regime(returns)`
     - import of `MarkovAutoregression`
     - `MARKOV_SWITCHING_REGIME_DETECTION: "statsmodels, k_regimes=2"`

7. **Fama-MacBeth regression**
   - **Name:** Fama-MacBeth regression
   - **Parameters:**
     - concentration p-value reported as `concentration_pvalue`
   - **Library:** not directly imported in shown code; spec string references linearmodels/Fama-MacBeth
   - **Evidence:**
     - `fama_result = self._fama_macbeth_regression(sim_df)`
     - `FAMA_FRENCH_REGRESSION_SPEC: "Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)"`

8. **Fama-French three-factor OLS regression**
   - **Name:** Fama-French three-factor OLS regression
   - **Parameters:** three-factor OLS; no coefficient-level parameters shown
   - **Library:** spec string says `linearmodels`; actual import not shown in provided code
   - **Evidence:**
     - `fama_french_result = self._fama_french_three_factor_ols(sim_df)`
     - `FAMA_FRENCH_REGRESSION_SPEC: "Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)"`

9. **DCC-GARCH cross-asset correlation**
   - **Name:** DCC-GARCH summary / cross-asset correlation
   - **Parameters:**
     - outputs include `method`, `n_pairs`, `mean_dcc_correlation`, `error`
   - **Library:** not shown
   - **Evidence:**
     - `dcc_result = self._dcc_garch_summary()`
     - `PAPER.md` lists `DCC-GARCH cross-asset correlation`

### Notable implemented statistical output checks

10. **Minimum effect size check**
   - **Threshold:** **-0.15 Sharpe units**
   - **Observed field:** `sharpe_differential`
   - **Pass field:** `meets_minimum_effect`
   - **Conclusion field:** `economic_significance`
   - **Evidence:**
     - `min_effect_data = {"threshold": -0.15, ...}`

11. **Seed consistency validation**
   - **Rule:** finding valid only if consistent across all required seeds
   - **Outputs:** `consistent`, `finding_valid`, `conclusion`
   - **Evidence:**
     - `seed_consistency = self._validate_seed_consistency(sim_df)`

---

## 2. Data

### Actual implemented data source in code
- **Source:** `yfinance`
- **Library:** `import yfinance as yf`
- **Files:** `agents/miner/miner.py`

### Tickers actually used
- `CL=F` → `crude_oil_wti`
- `NG=F` → `natural_gas`

### Date range
- **Configured start:** `2000-01-01`
- **Configured end exclusive:** `2024-01-01`
- Therefore intended included data through **2023-12-31**
- Constants:
  - `START_DATE = "2000-01-01"`
  - `END_DATE_EXCLUSIVE = "2024-01-01"`

### Adjustment method actually used
- `yf.download(..., auto_adjust=True, ...)`
- So prices are **auto-adjusted** by yfinance.
- In `PAPER.md`, adjustment method is specified as `ratio_backward`, but the actual implemented downloader uses `auto_adjust=True`.

### Return construction
- Returns are computed as:
  - `np.log(close_df / close_df.shift(1)).dropna()`
- So returns are **log returns** from adjusted close series.

### Data filtering / exclusions actually implemented
1. **Minimum trading history**
   - Keep only columns with at least **100 trading days**
   - Rule:
     - `close_df[c].dropna().shape[0] >= 100`

2. **Macro announcement exclusion window**
   - Function: `apply_macro_exclusion_window`
   - Default `exclusion_days=5`
   - Removes rows within **±5 calendar days** of dates in `FOMC_DATES_APPROX`
   - Comment says FOMC and CPI, but provided list shown is only approximate FOMC dates
   - For dev run, code actually applies the date filter to daily rows

3. **Bid-ask spread filter**
   - Function: `apply_bid_ask_spread_filter`
   - Threshold: **0.02**
   - Proxy:
     - `(High - Low).abs() / Close`
     - note field says `"intraday_high_low_over_close"`
   - Removes rows where row-wise max spread proxy across assets exceeds threshold:
     - `aligned_spread.max(axis=1) > threshold`

### Data passport metadata written
- File: `outputs/data_passport.json`
- Includes:
  - file path
  - SHA-256
  - row count
  - configured date range start/end
  - actual date range start/end

### Spec/data mismatch visible in provided context
- `PAPER.md` says:
  - **Source:** WRDS Compustat Futures — GSCI energy sector
  - **Date range:** 2000–2024
  - **Adjustment method:** ratio_backward
- Actual implemented miner code uses:
  - **Source:** yfinance
  - **Tickers:** `CL=F`, `NG=F`
  - **Adjustment:** `auto_adjust=True`

---

## 3. Simulation: agent names and behaviors

From `agents/forge/agents.py` and `agents/forge/runner.py`.

### Agents in environment
`possible_agents`:
1. `passive_gsci`
2. `trend_follower`
3. `mean_reversion`
4. `liquidity_provider`
5. `macro_allocator`
6. `meta_rl`

### Action space
- `Discrete(3)`
- Meaning:
  - `0 = hold`
  - `1 = long`
  - `2 = short`

### Implemented behaviors

1. **PassiveGSCI / `passive_gsci`**
   - Behavior: always returns action `1`
   - So implemented as always **long**

2. **TrendFollower / `trend_follower`**
   - In `agents.py`:
     - returns `1` if `obs[0] > obs[4]`, else `2`
   - In actual episode execution for `_run_single_episode`, this is overridden with a 12-month momentum rule:
     - `lookback_window = 252`
     - `lookback_idx = max(0, len(self.env._price_history) - self.lookback_window)`
     - `lookback_price = self.env._price_history[lookback_idx]`
     - `momentum_signal = current_price - lookback_price`
     - action `1` if momentum positive, else `2`
   - So the runner actually implements:
     - **12-month momentum long/short based on current price minus 252-step lookback price**

3. **MeanReversion / `mean_reversion`**
   - Behavior:
     - if `obs[0] > obs[1] * 1.02`: action `2` (short)
     - if `obs[0] < obs[1] * 0.98`: action `1` (long)
     - else `0` (hold)
   - So it fades ±2% deviations relative to `obs[1]`

4. **LiquidityProvider / `liquidity_provider`**
   - Behavior:
     - alternates between `1` and `2`
     - starts with `1`
     - internal counter increments each action
   - In `_run_single_episode`, this agent is reinitialized each episode:
     - `self.liquidity_agent = LiquidityProvider()`

5. **MacroAllocator / `macro_allocator`**
   - Parameter:
     - `passive_threshold` default `0.30`
   - In runner, instantiated as:
     - `MacroAllocator(passive_threshold=self.passive_concentration)`
   - Behavior:
     - returns `1` if `obs[6] < passive_threshold`
     - else `0`
   - So implemented as long when observation component 6 is below threshold, otherwise hold

6. **MetaRL / `meta_rl`**
   - Placeholder class behavior in `agents.py`:
     - random integer action in `[0, 2]`
   - Actual training/execution in runner:
     - action chosen by `self.cem.act(obs, weights)`
     - `CEM.act` computes:
       - `logits = obs @ weights`
       - action = `argmax(logits)`
   - So operationally, MetaRL is a **linear policy over 10-dim observations with argmax over 3 actions**, trained by CEM.

### Passive capital scenarios
- Concentrations run:
  - `0.10`
  - `0.30`
  - `0.60`
- Interpreted in spec strings as:
  - Low: 10% of open interest
  - Medium: 30%
  - High: 60%

### Episode length
- Environment default:
  - `episode_length = 252`

### Training episodes
- Runner default:
  - `n_episodes = 500_000`

---

## 4. Seeds

### Exact seed values used
- `[1337, 42, 9999]`

### Where used
- `REQUIRED_SEEDS = [1337, 42, 9999]`
- `SEED_POLICY_SPEC: "seeds = [1337, 42, 9999]"`
- `run_full_sweep()` uses:
  - `seeds = [1337, 42, 9999]`
- `modal_run.py` uses:
  - `seeds = [1337, 42, 9999]`

### RNG seeding in simulation
In `ForgeRunner.__init__`:
- `np.random.seed(self.seed)`
- `random.seed(self.seed)`

### Seed used in bootstrap
In `SigmaJob2.run()`:
- `seed = REQUIRED_SEEDS[0]`
- therefore bootstrap uses **1337**
- call:
  - `_bootstrap_ci(returns, seed=seed, n_resamples=1000)`

### Seed validity rule
- All three seeds must produce qualitatively consistent results
- Finding valid only if it holds across all three seeds
- Implemented via `_validate_seed_consistency(sim_df)`

---

## 5. Thresholds

### Significance thresholds
1. **Primary significance threshold**
   - `p < 0.05`
   - two-tailed

2. **Bonferroni-adjusted threshold**
   - `p < 0.0083`
   - for **6 simultaneous tests**

### Minimum effect threshold
- **-0.15 Sharpe units**
- Used as economic significance threshold
- Written explicitly in output:
  - `"threshold": -0.15`

### Passive concentration threshold relevant to hypothesis
- Hypothesis threshold:
  - above **30%** of open interest vs below **30%**
- Scenarios actually run:
  - 10%, 30%, 60%

### Bid-ask spread threshold
- **2% of contract price**
- Implemented as threshold `0.02`

### Minimum trading history threshold
- **100 trading days**

### Macro exclusion window threshold
- **5 days** around macro announcement dates

### Numerical stability threshold in Sharpe computation
- In `ForgeRunner.sharpe`:
  - if `std < 1e-8`, return `0.0`

---

## 6. Windows

### Lookback periods
1. **Momentum lookback window**
   - `252`
   - Comment: 12-month momentum
   - Constant:
     - `MOMENTUM_LOOKBACK_WINDOW = 252`
   - Runner:
     - `self.lookback_window = 252`

2. **Rolling correlation / primary metric window**
   - `252`
   - Constant:
     - `ROLLING_CORRELATION_WINDOW = 252`
   - `PAPER.md` primary metric:
     - annualized over rolling 252-day windows

### Rolling / trailing windows
3. **Fitness trailing window**
   - trailing **252 episodes**
   - evaluated every **1000 training steps**

4. **Episode length**
   - `252`

5. **Macro exclusion window**
   - ±**5 days**

6. **Minimum history window**
   - **100 trading days**

### Trend follower execution window detail
- In `_run_single_episode`, trend signal uses:
  - current price minus price at `len(price_history) - 252`, floored at index 0

---

## 7. Fitness function for MetaRL

### Exact implemented formula
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

### How it is used during training
- Every **1000 episodes** (and at final episode), compute:
  - `trailing = self.rewards_history[-252:]`
  - `fitness = self.sharpe(trailing)`
- So training fitness is:
  - **annualized Sharpe ratio of the trailing 252 episode-level rewards history**
- Returned descriptor:
  - `'fitness_function': 'trailing_252_episode_sharpe_every_1000_steps'`

### Episode scoring feeding fitness history
- For each candidate policy weights:
  - `_run_single_episode(weights)` returns:
    - `episode_mean = mean(meta_step_rewards)` over the episode
- `scores` are these episode means
- `self.rewards_history.append(np.max(scores))`
- Therefore the trailing series used for fitness is the history of:
  - **best candidate episode mean reward per training episode**
- Then Sharpe is computed on that trailing 252-length history using:
  - `mean / std * sqrt(252)`

---

## Exhaustive parameter summary

### Statistical/econometric parameters
- Newey-West HAC lags: **4**
- Primary alpha: **0.05**
- Bonferroni tests: **6**
- Bonferroni alpha: **0.0083**
- GARCH: **(1,1)** with **Normal** distribution
- Markov switching regimes: **2**
- Bootstrap resamples: **1000**
- Bootstrap seed: **1337**
- Deflated Sharpe trials: **6**

### Data parameters
- Source actually implemented: **yfinance**
- Tickers: **CL=F**, **NG=F**
- Renamed series: **crude_oil_wti**, **natural_gas**
- Start: **2000-01-01**
- End exclusive: **2024-01-01**
- Included through: **2023-12-31**
- Adjustment: **auto_adjust=True**
- Returns: **log returns**
- Spread proxy: **(High-Low)/Close**
- Spread threshold: **0.02**
- Minimum history: **100 trading days**
- Macro exclusion: **±5 days**

### Simulation parameters
- Agents: **passive_gsci, trend_follower, mean_reversion, liquidity_provider, macro_allocator, meta_rl**
- Action space: **0 hold / 1 long / 2 short**
- Concentration scenarios: **0.10, 0.30, 0.60**
- Episode length: **252**
- Training episodes default: **500,000**

### Seed parameters
- Seeds: **1337, 42, 9999**
- RNGs seeded: **NumPy** and Python `random`

### Window parameters
- Momentum lookback: **252**
- Rolling primary metric window: **252**
- Fitness trailing window: **252 episodes**
- Fitness evaluation frequency: **every 1000 episodes**

### MetaRL fitness formula
- **Sharpe = (mean / std) * sqrt(252)** on trailing 252 rewards
- Return `0.0` if fewer than 2 observations or `std < 1e-8`

## Important implementation/spec distinction
- The codebase includes `PAPER.md` specifications, but the **actual implemented data pipeline in provided code** uses **yfinance with auto-adjusted prices**, not WRDS ratio-backward futures data.