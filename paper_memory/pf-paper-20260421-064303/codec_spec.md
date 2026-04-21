# CODEC Pass 1 Specification Extraction

## 1. Statistical tests implemented

### Newey-West HAC t-test
- **Name:** Two-tailed t-test with Newey-West HAC correction
- **Library:** `statsmodels` imported as `sm`
- **Parameters/specification found:**
  - HAC lags: **4**
  - Primary significance threshold: **p < 0.05**, two-tailed
- **Evidence in code/spec:**
  - `PAPER.md`: “Two-tailed t-test, p < 0.05, Newey-West HAC correction (4 lags)”
  - `agents/forge/env.py`: `NEWEY_WEST_HAC_LAGS = "4 lags"`
  - `agents/sigma_job2.py`: calls `_newey_west_ttest(returns)`

### Bonferroni multiple-testing correction
- **Name:** Bonferroni correction
- **Library:** not tied to a specific external stats library in shown code
- **Parameters/specification found:**
  - Number of simultaneous tests: **6**
  - Adjusted threshold: **p < 0.0083**
- **Evidence:**
  - `PAPER.md`: “Bonferroni correction for 6 simultaneous tests — adjusted threshold p < 0.0083”
  - `agents/forge/env.py`: `BONFERRONI_ADJUSTED_THRESHOLD = "p < 0.0083"`
  - `agents/sigma_job2.py`: `_bonferroni(..., n_tests=6, ...)`
- **P-values included in Bonferroni set in code:**
  1. t-test p-value
  2. GARCH alpha p-value
  3. deflated Sharpe p-value
  4. regime mean difference p-value
  5. bootstrap mean<0 p-value
  6. Fama-MacBeth concentration p-value

### GARCH volatility model
- **Name:** GARCH(1,1)
- **Library:** `arch` via `from arch import arch_model`
- **Parameters/specification found:**
  - `p=1`, `q=1`
  - Distribution: **Normal**
- **Evidence:**
  - `PAPER.md`: “GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution)”
  - `agents/forge/env.py`: `GARCH_MODEL = "GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution)"`
  - `agents/sigma_job2.py`: calls `_garch_11(returns)`

### Fama-French three-factor OLS regression
- **Name:** Fama-French three-factor OLS regression
- **Library/spec string:** `linearmodels`, `Fama-MacBeth`
- **Parameters/specification found:**
  - Three-factor model
- **Evidence:**
  - `PAPER.md`: “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)”
  - `agents/sigma_job2.py`: `FAMA_FRENCH_REGRESSION_SPEC = "Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)"`
  - `agents/sigma_job2.py`: calls `_fama_french_three_factor_ols(sim_df)`

### Fama-MacBeth regression
- **Name:** Fama-MacBeth regression
- **Library:** not directly imported in shown code; referenced in spec string/output naming
- **Evidence:**
  - `agents/sigma_job2.py`: calls `_fama_macbeth_regression(sim_df)`
  - output file: `fama_macbeth_results.csv`
  - `PAPER.md` bundles “linearmodels, Fama-MacBeth” with Fama-French regression spec

### Markov switching regime detection / Markov autoregression
- **Name:** Markov switching regime detection
- **Library:** `statsmodels`
- **Parameters/specification found:**
  - `k_regimes=2`
- **Evidence:**
  - `PAPER.md`: “Markov switching regime detection (statsmodels, k_regimes=2)”
  - `agents/forge/env.py`: `MARKOV_SWITCHING_REGIME_DETECTION = "statsmodels, k_regimes=2"`
  - `agents/sigma_job2.py` imports `MarkovAutoregression` from `statsmodels.tsa.regime_switching.markov_autoregression`
  - `agents/sigma_job2.py`: calls `_markov_regime(returns)`

### DCC-GARCH cross-asset correlation
- **Name:** DCC-GARCH cross-asset correlation
- **Library:** not shown in provided code
- **Parameters/specification found:**
  - No explicit hyperparameters shown
- **Evidence:**
  - `PAPER.md`: “DCC-GARCH cross-asset correlation”
  - `agents/sigma_job2.py`: calls `_dcc_garch_summary()`
  - output fields written: `method`, `n_pairs`, `mean_dcc_correlation`, `error`

### Bootstrap confidence interval / bootstrap test
- **Name:** Bootstrap CI
- **Library:** not shown in provided code
- **Parameters/specification found:**
  - `seed=1337`
  - `n_resamples=1000`
- **Evidence:**
  - `agents/sigma_job2.py`: `_bootstrap_ci(returns, seed=seed, n_resamples=1000)`

### Deflated Sharpe test
- **Name:** Deflated Sharpe
- **Library:** not shown in provided code
- **Parameters/specification found:**
  - `n_trials=6`
- **Evidence:**
  - `agents/sigma_job2.py`: `_deflated_sharpe(returns, n_trials=6)`

## 2. Data

### Source actually used in code
- **Primary implemented source in provided runnable miner code:** `yfinance`
- **Library:** `import yfinance as yf`
- **Function calls:** `yf.download(...)`
- **Downloaded fields used:**
  - Close prices for return construction
  - High, Low, Close for spread proxy

### Source stated in research spec
- **Specified source in `PAPER.md`:** WRDS Compustat Futures — GSCI energy sector
- **Date range in spec:** **2000–2024**
- **Roll convention:** `ratio_backward`
- **Adjustment method:** `ratio_backward`

### Tickers actually used in code
- `CL=F` → `crude_oil_wti`
- `NG=F` → `natural_gas`

### Date range actually used in miner code
- `START_DATE = "2000-01-01"`
- `END_DATE_EXCLUSIVE = "2024-01-01"`
- Comment: includes data through **2023-12-31**
- Passport writes:
  - start: `2000-01-01`
  - end: `2023-12-31`

### Adjustment method actually used in miner code
- `yf.download(..., auto_adjust=True, ...)`
- So the implemented download uses **Yahoo auto-adjusted prices**
- This differs from the paper spec’s `ratio_backward`

### Return construction
- Returns are computed as:
  - `np.log(close_df / close_df.shift(1)).dropna()`
- So implemented returns are **daily log returns**

### Exclusion/filter rules actually implemented on data
- **Minimum trading history:** retain only series with at least **100 trading days**
- **Macro exclusion window:** remove rows within **±5 days** of approximate FOMC dates
  - Function parameter: `exclusion_days=5`
  - Comment says FOMC and CPI, but provided list is `FOMC_DATES_APPROX`
- **Bid-ask spread filter:** remove rows where spread proxy exceeds **0.02**
  - Proxy: `(High - Low).abs() / Close`
  - Applied row-wise using `aligned_spread.max(axis=1) > threshold`

## 3. Simulation agents and behaviors

Environment has **six agents**:
1. `passive_gsci`
2. `trend_follower`
3. `mean_reversion`
4. `liquidity_provider`
5. `macro_allocator`
6. `meta_rl`

### PassiveGSCI
- **Class:** `PassiveGSCI`
- **Behavior:** always returns action `1`
- **Interpretation from env action space:** `1 = long`
- **Spec-level behavior:** mechanically always long / passive exposure

### TrendFollower
- **Class:** `TrendFollower`
- **Behavior in class implementation:** returns `1` if `obs[0] > obs[4]`, else `2`
- **Interpretation:** long if current signal exceeds comparison value, otherwise short

### Trend follower behavior actually used during training episodes
- In `ForgeRunner._run_single_episode`, trend follower is overridden with explicit momentum logic:
  - `lookback_window = 252`
  - `lookback_idx = max(0, len(self.env._price_history) - self.lookback_window)`
  - `lookback_price = self.env._price_history[lookback_idx]`
  - `momentum_signal = current_price - lookback_price`
  - action `1` if momentum positive, else `2`
- **Spec-level behavior actually implemented in runner:** 12-month momentum, long if positive momentum, short otherwise

### MeanReversion
- **Class:** `MeanReversion`
- **Behavior:**
  - if `obs[0] > obs[1] * 1.02`: return `2` (short)
  - if `obs[0] < obs[1] * 0.98`: return `1` (long)
  - else return `0` (hold)
- **Spec-level behavior:** fades ±2% deviations relative to `obs[1]`

### LiquidityProvider
- **Class:** `LiquidityProvider`
- **Behavior:** alternates actions each call
  - even counter: `1`
  - odd counter: `2`
- Counter resets when a new `LiquidityProvider()` is created
- In `_run_single_episode`, liquidity agent is reinitialized each episode
- **Spec-level behavior:** alternates long/short every turn

### MacroAllocator
- **Class:** `MacroAllocator`
- **Parameter:** `passive_threshold: float = 0.30`
- **Behavior:** returns `1` if `obs[6] < passive_threshold`, else `0`
- In runner, instantiated as:
  - `MacroAllocator(passive_threshold=self.passive_concentration)`
- **Spec-level behavior:** goes long when observation component 6 is below the scenario concentration threshold; otherwise hold

### MetaRL
- **Class:** `MetaRL`
- **Placeholder behavior in class:** random integer action in `{0,1,2}`
- **Actual training/evaluation behavior in runner:** action chosen by CEM policy
  - `self.cem.act(obs, weights)`
  - computes `logits = obs @ weights`
  - action is `argmax(logits)`
- **Spec-level behavior:** learned allocation/policy over 3 discrete actions using weight matrix over 10-dim observations

### Action space
- For all agents:
  - `Discrete(3)`
  - `0 = hold`
  - `1 = long`
  - `2 = short`

### Passive capital scenarios
- Allowed concentrations in environment:
  - `0.10`
  - `0.30`
  - `0.60`
- Interpreted as:
  - Low: 10%
  - Medium: 30%
  - High: 60%

## 4. Seeds

### Exact seed values
- `[1337, 42, 9999]`

### Where used
- `agents/sigma_job2.py`
  - `REQUIRED_SEEDS = [1337, 42, 9999]`
  - `seed = REQUIRED_SEEDS[0]` for bootstrap call, so bootstrap seed is **1337**
- `agents/forge/full_run.py`
  - `seeds = [1337, 42, 9999]`
- `agents/forge/modal_run.py`
  - `seeds = [1337, 42, 9999]`
- `agents/forge/runner.py`
  - `np.random.seed(self.seed)`
  - `random.seed(self.seed)`

### Seed policy
- All three seeds must produce qualitatively consistent results
- A finding is valid only if it holds across all three seeds

## 5. Thresholds

### Statistical significance thresholds
- **Primary:** `p < 0.05`, two-tailed
- **Bonferroni-adjusted:** `p < 0.0083`
- **Number of simultaneous tests:** `6`

### Minimum effect threshold
- **Minimum effect size:** `-0.15 Sharpe units`
- In `sigma_job2.py`, written to output as:
  - `"threshold": -0.15`

### Passive concentration threshold in hypothesis/spec
- Hypothesis threshold: **above 30% of open interest**
- Scenarios:
  - Low: 10%
  - Medium: 30%
  - High: 60%

### Data exclusion thresholds
- **Minimum trading history:** `100` trading days
- **Bid-ask spread threshold:** `2%` of contract price, implemented as `0.02`
- **Macro exclusion window:** `±5` days around macro dates

### Mean reversion thresholds
- Upper trigger: `obs[0] > obs[1] * 1.02`
- Lower trigger: `obs[0] < obs[1] * 0.98`

### Macro allocator threshold
- Default constructor threshold: `0.30`
- In simulation runner, threshold is set equal to scenario `passive_concentration`

## 6. Windows

### Momentum / lookback windows
- **Momentum lookback window:** `252`
- In runner:
  - `self.lookback_window: int = 252`
- In env constants:
  - `MOMENTUM_LOOKBACK_WINDOW: int = 252`
- Interpreted as **12-month momentum**

### Rolling window for primary metric
- **Rolling Sharpe / rolling correlation window:** `252`
- In env constants:
  - `ROLLING_CORRELATION_WINDOW: int = 252`
- `PAPER.md`:
  - “Sharpe ratio differential: high-concentration periods minus low-concentration periods, annualized over rolling 252-day windows.”

### Episode length
- Environment default episode length: `252`

### Fitness evaluation window
- **Trailing window for MetaRL fitness:** `252` episodes
- Evaluated every **1000** training steps/episodes

### Macro exclusion window
- `exclusion_days = 5`
- Applied as ±5 calendar days around listed dates

## 7. Fitness function for MetaRL

### Exact implemented formula
In `ForgeRunner.sharpe(step_returns)`:
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

### How it is used for training fitness
- During training, every 1000 episodes or at final episode:
  - `trailing = self.rewards_history[-252:]`
  - `fitness = self.sharpe(trailing)`
- `self.rewards_history` stores:
  - `float(np.max(scores))` per episode
  - where each score is the candidate episode’s `episode_mean`
- `episode_mean` is:
  - mean of `meta_step_rewards` collected during one episode
- Therefore the implemented MetaRL fitness is:

**Fitness = annualized Sharpe ratio of the trailing 252 values in `rewards_history`, where each value is the maximum candidate score for that episode, and each candidate score is the mean MetaRL per-step reward within that episode.**

### String label returned in results
- `'fitness_function': 'trailing_252_episode_sharpe_every_1000_steps'`

## Additional specification-level simulation parameters

### Training episodes
- Default / minimum used across sweep:
  - `500_000`

### Concentration scenarios run in sweep
- `[0.10, 0.30, 0.60]`

### Observation dimension
- Observation shape: `(10,)`

### Action dimension
- 3 actions: hold/long/short

## Data/spec mismatches visible in provided code
Only reporting directly observable mismatches:
- `PAPER.md` specifies **WRDS Compustat Futures** with **ratio_backward** adjustment, but `agents/miner/miner.py` actually downloads from **yfinance** with `auto_adjust=True`.
- `PAPER.md` says 2000–2024; miner code actually requests `2000-01-01` to `2024-01-01` exclusive, i.e. through **2023-12-31**.
- `PAPER.md` describes trend follower as 12-month momentum; runner implements that explicitly with a **252-step lookback**, while the standalone `TrendFollower` class itself uses `obs[0] > obs[4]`.