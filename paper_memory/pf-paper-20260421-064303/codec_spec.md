# CODEC Pass 1 Specification Extraction

## 1. Statistical tests

### Newey-West HAC two-tailed t-test
- **Name:** Two-tailed t-test with Newey-West HAC correction
- **Library:** `statsmodels` is imported in `agents/sigma_job2.py` as `statsmodels.api as sm`
- **Parameters/specification found:**
  - HAC / Newey-West correction
  - **Lags:** 4
  - **Primary significance threshold:** `p < 0.05` two-tailed
- **Evidence in code/spec:**
  - `SigmaJob2.run()` calls `_newey_west_ttest(returns)`
  - `PAPER.md`: “Two-tailed t-test, p < 0.05, Newey-West HAC correction (4 lags)”

### GARCH(1,1)
- **Name:** GARCH(1,1) volatility model
- **Library:** `arch` via `from arch import arch_model`
- **Parameters/specification found:**
  - `p=1`
  - `q=1`
  - **Distribution:** Normal
- **Evidence in code/spec:**
  - `SigmaJob2.run()` calls `_garch_11(returns)`
  - `agents/forge/env.py`: `GARCH_MODEL = "GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution)"`
  - `PAPER.md` repeats same specification

### Bootstrap confidence interval / bootstrap test
- **Name:** Bootstrap CI / bootstrap test on returns
- **Library:** not explicitly named beyond NumPy/Pandas context in provided snippet
- **Parameters/specification found:**
  - `seed=seed`
  - `n_resamples=1000`
  - Output includes `mean_lt_zero_p_value`
- **Evidence in code:**
  - `SigmaJob2.run()` calls `_bootstrap_ci(returns, seed=seed, n_resamples=1000)`

### Deflated Sharpe test
- **Name:** Deflated Sharpe
- **Library:** not explicitly shown in provided snippet
- **Parameters/specification found:**
  - `n_trials=6`
- **Evidence in code:**
  - `SigmaJob2.run()` calls `_deflated_sharpe(returns, n_trials=6)`

### Markov switching / regime detection
- **Name:** Markov switching regime detection / Markov autoregression
- **Library:** `statsmodels`
  - imported as `from statsmodels.tsa.regime_switching.markov_autoregression import MarkovAutoregression`
- **Parameters/specification found:**
  - `k_regimes=2`
- **Evidence in code/spec:**
  - `SigmaJob2.run()` calls `_markov_regime(returns)`
  - `agents/forge/env.py`: `MARKOV_SWITCHING_REGIME_DETECTION = "statsmodels, k_regimes=2"`
  - `PAPER.md`: “Markov switching regime detection (statsmodels, k_regimes=2)”

### Fama-MacBeth regression
- **Name:** Fama-MacBeth regression
- **Library:** intended/spec says `linearmodels`
- **Parameters/specification found:**
  - `SigmaJob2.run()` calls `_fama_macbeth_regression(sim_df)`
  - `PAPER.md` says: “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)”
  - `SigmaJob2` writes `fama_macbeth_results.csv`
  - `SigmaJob2` records library versions including `"linearmodels"`
- **Note:** The provided code snippet does not show the implementation body, only the call and the paper-level specification.

### DCC-GARCH cross-asset correlation
- **Name:** DCC-GARCH cross-asset correlation summary
- **Library:** not shown in provided snippet
- **Parameters/specification found:**
  - `SigmaJob2.run()` calls `_dcc_garch_summary()`
  - Output fields written:
    - `method`
    - `n_pairs`
    - `mean_dcc_correlation`
    - `error`
- **Evidence in code/spec:**
  - `PAPER.md`: “DCC-GARCH cross-asset correlation”

### Bonferroni correction
- **Name:** Bonferroni correction
- **Library:** internal method in `SigmaJob2`
- **Parameters/specification found:**
  - `n_tests=7` in `SigmaJob2.run()`
  - p-values passed into correction:
    1. t-test p-value
    2. GARCH alpha p-value
    3. GARCH beta p-value
    4. deflated Sharpe p-value
    5. regime mean difference p-value
    6. bootstrap mean<0 p-value
    7. Fama-MacBeth concentration p-value
  - Paper/env constants specify adjusted threshold `p < 0.0083`
- **Evidence in code/spec:**
  - `SigmaJob2.run()` calls `_bonferroni(..., n_tests=7, primary_metric=primary_metric)`
  - `agents/forge/env.py`:
    - `SIGNIFICANCE_THRESHOLD_BONFERRONI = "p < 0.0083"`
    - `BONFERRONI_CORRECTION = "Bonferroni correction for 6 simultaneous tests — adjusted threshold p < 0.0083"`
- **Important discrepancy actually present in codebase:**
  - `PAPER.md` / env constants say **6 simultaneous tests**
  - `SigmaJob2.run()` actually passes **7 tests** to `_bonferroni`

---

## 2. Data

### Source
- **Specified source:** `WRDS Compustat Futures — GSCI energy sector`
- **Actual implemented dev source:** `yfinance`
- **Evidence:**
  - `agents/miner/miner.py` imports `yfinance as yf`
  - `download_close_series()` uses `yf.download(...)`
  - `write_data_passport()` explicitly states:
    - `"Dev run: yfinance proxy for WRDS Compustat Futures."`
    - `"Full run requires WRDS access."`

### Tickers
- **Actual implemented tickers in dev run:**
  - `CL=F` → `crude_oil_wti`
  - `NG=F` → `natural_gas`
- **Evidence:**
  - `TICKERS = {"CL=F": "crude_oil_wti", "NG=F": "natural_gas"}`

### Date range
- **Configured download range:**
  - `START_DATE = "2000-01-01"`
  - `END_DATE_EXCLUSIVE = "2024-01-01"`
- **Effective included data through:** `2023-12-31`
- **Passport-reported date range:**
  - start: `2000-01-01`
  - end: `2023-12-31`
- **Evidence:**
  - `yf.download(..., start=START, end=END, ...)`
  - `END = END_DATE_EXCLUSIVE`
  - `write_data_passport()` writes `"date_range": {"start": START_DATE, "end": "2023-12-31"}`

### Adjustment method
- **Actual implemented download adjustment:** `auto_adjust=True` in `yfinance`
- **Declared adjustment/roll convention in passport:** `ratio_backward`
- **Acknowledged deviation note:**
  - `"yfinance auto_adjust=True used as proxy for ratio_backward"`
- **Evidence:**
  - `download_close_series()` uses `yf.download(..., auto_adjust=True, ...)`
  - `write_data_passport()`:
    - `"roll_convention": "ratio_backward"`
    - `"adjustment_method": "ratio_backward"`
    - `"adjustment_method_note": "yfinance auto_adjust=True used as proxy for ratio_backward..."`

### Return construction
- **Implemented returns:** log returns
- **Formula:** `np.log(close_df / close_df.shift(1)).dropna()`
- **Evidence:**
  - `build_returns_frame()`

### Exclusion handling
- **Macro exclusion window function exists:** `apply_macro_exclusion_window(df, exclusion_days=5)`
- **Actual dev-run behavior:** no-op
- **Recorded note:**
  - `macro_exclusion_applied: False`
  - `exclusion_window_days: 5`
- **Evidence:**
  - Function returns original `df` unchanged plus note
- **Other exclusion rules present only as specification constants / paper text:**
  - fewer than 100 trading days of history
  - bid-ask spread exceeds 2% of contract price

---

## 3. Simulation: agent names and behaviors

### Agent set in environment
`CommodityFuturesEnv.possible_agents`:
1. `passive_gsci`
2. `trend_follower`
3. `mean_reversion`
4. `liquidity_provider`
5. `macro_allocator`
6. `meta_rl`

### Action space
- **Library:** `gymnasium.spaces.Discrete`
- **Actions:** `Discrete(3)`
  - `0 = hold`
  - `1 = long`
  - `2 = short`
- **Evidence:**
  - `agents/forge/env.py`

### Observation vector
Each agent observes a 10-dimensional vector:
1. `price_history[0]`
2. `price_history[1]`
3. `price_history[2]`
4. `price_history[3]`
5. `price_history[4]`
6. `current_volatility`
7. `passive_concentration`
8. `portfolio_value[agent]`
9. `cash[agent]`
10. `current_step`

### Implemented agent behaviors

#### `PassiveGSCI`
- **Behavior:** always returns action `1`
- **Interpretation:** always long
- **Evidence:**
  - `PassiveGSCI.act()` returns `1`
  - Environment also forces `passive_gsci` action to `1` in `step()`

#### `TrendFollower`
- **Class behavior in `agents.py`:**
  - returns `1` if `obs[0] > obs[4]`, else `2`
- **Runner override during episode simulation:**
  - For `trend_follower` inside `_run_single_episode`, action is recomputed as:
    - `p0 = obs[0]`
    - `lookback_idx = min(4, len(self.env._price_history) - 1)`
    - `lookback_price = self.env._price_history[lookback_idx]`
    - `momentum_signal = p0 - lookback_price`
    - action `1` if momentum positive else `2`
- **Declared metadata in results:**
  - `momentum_lookback_steps = 252`
  - `momentum_signal = 'price_level_difference_over_lookback'`
- **Important implementation detail actually present:**
  - Although `lookback_window` is set to `252`, the shown trend logic compares against index `4` of `_price_history`, and env reset initializes `_price_history = [self.price] * 5`

#### `MeanReversion`
- **Behavior:**
  - if `obs[0] > obs[1] * 1.02`: return `2` (short)
  - if `obs[0] < obs[1] * 0.98`: return `1` (long)
  - else return `0` (hold)

#### `LiquidityProvider`
- **Behavior:**
  - alternates between `1` and `2`
  - starts with counter `0`
  - even counter → `1`
  - odd counter → `2`
  - increments counter each action

#### `MacroAllocator`
- **Parameter:** `passive_threshold: float = 0.30`
- **Behavior:**
  - returns `1` if `obs[6] < passive_threshold`
  - else returns `0`
- **Runner instantiation:**
  - `MacroAllocator(passive_threshold=self.passive_concentration)`
- **So in runner, threshold equals scenario concentration**

#### `MetaRL`
- **Class placeholder behavior in `agents.py`:**
  - random action `random.randint(0, 2)`
- **Actual training/evaluation behavior in runner:**
  - `meta_rl` actions are chosen by `self.cem.act(obs, weights)`
  - `CEM.act(obs, weights)` computes:
    - `logits = obs @ weights`
    - action = `argmax(logits)`
- **Reward tracked for MetaRL:**
  - per-step rewards collected when `agent == "meta_rl"`
  - candidate episode score = mean of `meta_step_rewards`

### Passive capital scenarios
- Implemented concentrations:
  - `0.10`
  - `0.30`
  - `0.60`
- Environment validates concentration must be one of `{0.10, 0.30, 0.60}`

### Episode length
- `CommodityFuturesEnv(..., episode_length: int = 252)`

### Training episodes
- `ForgeRunner(..., n_episodes: int = 500_000)`
- Full sweep default: `run_full_sweep(n_episodes: int = 500_000)`

---

## 4. Seeds

### Exact seed values used
- `1337`
- `42`
- `9999`

### Where used
- `PAPER.md`: `seeds = [1337, 42, 9999]`
- `agents/forge/full_run.py`: `seeds = [1337, 42, 9999]`
- `agents/forge/modal_run.py`: `seeds = [1337, 42, 9999]`

### Seed application in simulation
- In `ForgeRunner.__init__`:
  - `np.random.seed(self.seed)`
  - `random.seed(self.seed)`

### Seed consistency requirement
- Paper specification:
  - “All three seeds must produce qualitatively consistent results.”
  - “A finding is only valid if it holds across all three seeds.”
- `SigmaJob2.run()` also calls `_validate_seed_consistency(sim_df)`

### Additional seed in SigmaJob2
- `seed = self._seed_from_pap_lock()`
- Exact numeric value is **not shown** in provided snippet.

---

## 5. Thresholds

### Statistical significance thresholds
- **Primary:** `p < 0.05` two-tailed
- **Bonferroni-adjusted:** `p < 0.0083`
- **Evidence:**
  - `PAPER.md`
  - `agents/forge/env.py` constants:
    - `SIGNIFICANCE_THRESHOLD_PRIMARY = "p < 0.05 two-tailed"`
    - `SIGNIFICANCE_THRESHOLD_BONFERRONI = "p < 0.0083"`

### Minimum effect size
- **Threshold:** `-0.15` Sharpe units
- **Interpretation in hypothesis:** high-concentration minus low-concentration Sharpe differential reduced by at least 0.15
- **Evidence:**
  - `PAPER.md`: “Minimum Effect Size -0.15 Sharpe units”
  - `agents/forge/env.py`: `MINIMUM_EFFECT_SIZE = "-0.15 Sharpe units"`
  - `SigmaJob2.run()` writes:
    - `"threshold": -0.15`

### Passive concentration threshold
- **Hypothesis threshold / medium scenario:** `30%`
- **Evidence:**
  - `PAPER.md`
  - `MacroAllocator` default `passive_threshold=0.30`

### Mean reversion thresholds
- **Upper extreme:** `obs[0] > obs[1] * 1.02`
- **Lower extreme:** `obs[0] < obs[1] * 0.98`

### Numerical stability threshold in Sharpe computation
- **Std floor:** if `std < 1e-8`, Sharpe returns `0.0`
- **Evidence:**
  - `ForgeRunner.sharpe()`

### Exclusion thresholds/spec constants
- **Minimum trading history:** `100` trading days
- **Bid-ask spread filter:** `2%` of contract price
- **Macro exclusion window:** `5` days around FOMC/CPI
- **Evidence:**
  - `PAPER.md`
  - `agents/forge/env.py` constants
  - `apply_macro_exclusion_window(..., exclusion_days=5)`

---

## 6. Windows

### Momentum lookback window
- **Value:** `252`
- **Evidence:**
  - `ForgeRunner.lookback_window = 252`
  - `agents/forge/env.py`: `MOMENTUM_LOOKBACK_WINDOW = 252`
  - `PAPER.md`: 12-month momentum
- **Reported in results as:** `momentum_lookback_steps: 252`

### Rolling correlation / primary metric window
- **Value:** `252`
- **Evidence:**
  - `agents/forge/env.py`: `ROLLING_CORRELATION_WINDOW = 252`
  - `PAPER.md`: Sharpe differential annualized over rolling 252-day windows
  - `SigmaJob2.run()` computes `primary_metric = self._rolling_sharpe_differential(sim_df)`

### Fitness trailing window
- **Value:** trailing `252` episodes
- **Evaluation frequency:** every `1000` training steps/episodes
- **Evidence:**
  - In `ForgeRunner.run()`:
    - `if episode % 1000 == 0 or episode == self.n_episodes:`
    - `trailing = self.rewards_history[-252:]`
    - `fitness = self.sharpe(trailing)`

### Episode length
- **Value:** `252`
- **Evidence:**
  - `CommodityFuturesEnv(..., episode_length: int = 252)`

### Macro exclusion window
- **Value:** `5` days
- **Evidence:**
  - `apply_macro_exclusion_window(..., exclusion_days: int = 5)`

---

## 7. Fitness function for MetaRL

### Exact implemented formula
In `ForgeRunner.sharpe(step_returns)`:
```python
arr = np.asarray(step_returns, dtype=np.float64)
mean = arr.mean()
std = arr.std()
if std < 1e-8:
    return 0.0
return float((mean / std) * np.sqrt(252))
```

### How it is used for MetaRL fitness
- During training:
  - `self.rewards_history.append(float(np.max(scores)))`
  - every 1000 episodes:
    - `trailing = self.rewards_history[-252:]`
    - `fitness = self.sharpe(trailing)`
- Therefore the implemented MetaRL fitness is:
  - **annualized Sharpe ratio of the trailing 252 values of `rewards_history`**
  - where each `rewards_history` entry is the **maximum candidate score** from that episode’s CEM population
- Returned metadata string:
  - `'fitness_function': 'trailing_252_episode_sharpe_every_1000_steps'`

### Candidate episode score definition
- In `_run_single_episode(weights)`:
  - collect `meta_step_rewards` for `meta_rl`
  - return `episode_mean = mean(meta_step_rewards)` if non-empty else `0.0`
- So each candidate score is:
  - **mean MetaRL per-step reward within one episode**

### Evaluation Sharpe in final results
- `results()` computes:
  - `step_returns = self._run_episode_returns(best_weights)`
  - `sharpe_val = self.sharpe(step_returns)`
- This final reported Sharpe is the same formula applied to per-step rewards from one episode using best weights.

---

## Exhaustive parameter summary

### Libraries used for specification-level stats/data/simulation
- `statsmodels`
- `arch`
- `scipy.stats`
- `numpy`
- `pandas`
- `yfinance`
- `gymnasium`
- `pettingzoo`

### Concentration scenarios
- `0.10`, `0.30`, `0.60`

### Seeds
- `1337`, `42`, `9999`

### Training episodes
- `500_000`

### Episode length
- `252`

### Momentum lookback
- `252`

### Rolling primary metric window
- `252`

### Fitness evaluation interval
- every `1000` episodes

### Bootstrap resamples
- `1000`

### Deflated Sharpe trials
- `6`

### Newey-West lags
- `4`

### Markov regimes
- `2`

### GARCH order
- `(1,1)`

### GARCH distribution
- `Normal`

### Significance thresholds
- primary: `0.05`
- Bonferroni: `0.0083`

### Minimum economic effect
- `-0.15` Sharpe units

### Data tickers
- `CL=F`
- `NG=F`

### Data date range
- start: `2000-01-01`
- end exclusive download bound: `2024-01-01`
- included through: `2023-12-31`

### Adjustment
- implemented download: `yfinance auto_adjust=True`
- declared method/roll convention: `ratio_backward`

### Exclusion thresholds
- macro window: `5` days
- minimum history: `100` trading days
- bid-ask spread: `2%` of contract price

## Notable implementation/spec discrepancies actually visible
- Bonferroni:
  - paper/env constants say **6 simultaneous tests**
  - `SigmaJob2.run()` applies `_bonferroni(..., n_tests=7, ...)`
- Data source:
  - paper specifies WRDS Compustat Futures
  - implemented dev run uses `yfinance`
- Adjustment:
  - paper specifies exact `ratio_backward`
  - implemented dev run uses `auto_adjust=True` as proxy
- Momentum:
  - runner declares `lookback_window = 252`
  - shown trend logic compares current price to `_price_history[4]` / `obs[4]` in provided code snippets