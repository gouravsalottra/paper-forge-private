# CODEC Pass 1 Specification Extraction

## 1. Statistical tests

### Newey-West HAC two-tailed t-test
- **Name:** Two-tailed t-test with Newey-West HAC correction
- **Library:** implied `statsmodels` usage in `agents/sigma_job2.py` (`import statsmodels.api as sm`)
- **Parameters/specification:**
  - Two-tailed
  - HAC / Newey-West correction
  - **Lags:** 4
- **Evidence:**
  - `PAPER.md`: “Two-tailed t-test, p < 0.05, Newey-West HAC correction (4 lags)”
  - `SigmaJob2.run()` calls `_newey_west_ttest(returns)`

### GARCH(1,1)
- **Name:** GARCH(1,1) volatility model
- **Library:** `arch` (`from arch import arch_model`)
- **Parameters/specification:**
  - `p=1`
  - `q=1`
  - Normal distribution
- **Evidence:**
  - `PAPER.md`: “GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution)”
  - `env.py` constant: `GARCH_MODEL = "GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution)"`
  - `SigmaJob2.run()` calls `_garch_11(returns)`

### Bootstrap confidence interval / bootstrap test
- **Name:** Bootstrap CI / bootstrap mean-below-zero test
- **Library:** not explicitly named beyond NumPy/Pandas context in `sigma_job2.py`
- **Parameters/specification actually visible:**
  - `n_resamples=1000`
  - `seed=<derived from _seed_from_pap_lock()>`
  - Output includes `mean_lt_zero_p_value`
- **Evidence:**
  - `SigmaJob2.run()` calls `_bootstrap_ci(returns, seed=seed, n_resamples=1000)`

### Deflated Sharpe
- **Name:** Deflated Sharpe ratio test
- **Library:** not explicitly specified
- **Parameters/specification actually visible:**
  - `n_trials=6`
  - Output includes `p_value`
- **Evidence:**
  - `SigmaJob2.run()` calls `_deflated_sharpe(returns, n_trials=6)`

### Markov switching regime detection / Markov autoregression
- **Name:** Markov switching regime detection
- **Library:** `statsmodels`
  - specifically `statsmodels.tsa.regime_switching.markov_autoregression.MarkovAutoregression`
- **Parameters/specification:**
  - `k_regimes=2`
- **Evidence:**
  - `PAPER.md`: “Markov switching regime detection (statsmodels, k_regimes=2)”
  - `env.py`: `MARKOV_SWITCHING_REGIME_DETECTION = "statsmodels, k_regimes=2"`
  - `SigmaJob2.run()` calls `_markov_regime(returns)`

### Fama-MacBeth regression
- **Name:** Fama-MacBeth regression
- **Library:** specification says `linearmodels`
- **Parameters/specification actually visible:**
  - Used as `_fama_macbeth_regression(sim_df)`
  - Output may include `concentration_pvalue`
- **Evidence:**
  - `SigmaJob2.run()` calls `_fama_macbeth_regression(sim_df)`
  - `PAPER.md`: “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)”  
    - This wording conflates Fama-French OLS and Fama-MacBeth, but both are invoked in code.

### Fama-French three-factor OLS
- **Name:** Fama-French three-factor OLS regression
- **Library:** specification says `linearmodels`
- **Parameters/specification actually visible:**
  - Three-factor OLS
  - Called as `_fama_french_three_factor_ols(sim_df)`
- **Evidence:**
  - `SigmaJob2.run()` calls `_fama_french_three_factor_ols(sim_df)`
  - `PAPER.md`: “Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)”

### DCC-GARCH cross-asset correlation
- **Name:** DCC-GARCH cross-asset correlation
- **Library:** not explicitly specified
- **Parameters/specification actually visible:**
  - Summary output fields:
    - `method`
    - `n_pairs`
    - `mean_dcc_correlation`
    - `error`
- **Evidence:**
  - `PAPER.md`: “DCC-GARCH cross-asset correlation”
  - `SigmaJob2.run()` calls `_dcc_garch_summary()`

### Bonferroni multiple-testing correction
- **Name:** Bonferroni correction
- **Library:** internal method
- **Parameters/specification:**
  - `n_tests=6`
  - Adjusted threshold `p < 0.0083`
  - Applied to these six p-values:
    1. Newey-West t-test `p_value`
    2. GARCH `alpha_pvalue`
    3. Deflated Sharpe `p_value`
    4. Markov regime `regime_mean_diff_p_value`
    5. Bootstrap `mean_lt_zero_p_value`
    6. Fama-MacBeth `concentration_pvalue` (default `1.0` if absent)
- **Evidence:**
  - `SigmaJob2.run()` explicit `_bonferroni([...], n_tests=6, primary_metric=primary_metric)`
  - `PAPER.md` and `env.py` constants specify adjusted threshold `p < 0.0083`

## 2. Data

### Actual implemented data source
- **Source:** `yfinance`
- **Library:** `import yfinance as yf`
- **Evidence:** `agents/miner/miner.py`

### Tickers actually used
- `CL=F` → `crude_oil_wti`
- `NG=F` → `natural_gas`

### Date range
- **Configured download range:**
  - `START_DATE = "2000-01-01"`
  - `END_DATE_EXCLUSIVE = "2024-01-01"`
- **Interpretation in code:**
  - Includes data through `2023-12-31`
- **Passport-reported range:**
  - `"start": "2000-01-01"`
  - `"end": "2023-12-31"`

### Adjustment method actually used
- **Method:** `auto_adjust=True` in `yf.download(...)`
- **Applied in:**
  - `download_close_series`
  - `download_spread_proxy_series`

### Return construction
- **Formula:** log returns
  - `returns = np.log(close_df / close_df.shift(1)).dropna()`

### Join/alignment
- Close series concatenated with `join="inner"`
- Spread proxy series concatenated with `join="inner"`
- Both sorted by index

### Exclusion / filtering rules actually implemented
- **Minimum trading history:**
  - retain only columns with at least `100` non-null trading days
- **Macro exclusion window:**
  - `apply_macro_exclusion_window(df, exclusion_days=5)`
  - removes rows within ±5 calendar days of dates in `FOMC_DATES_APPROX`
  - comment says CPI/FOMC exclusion; actual list shown is approximate FOMC dates sample
- **Bid-ask spread filter:**
  - `apply_bid_ask_spread_filter(..., threshold=0.02)`
  - spread proxy = `abs(high - low) / close`
  - removes rows where max spread proxy across assets exceeds `0.02`

### Specification-vs-implementation note
- `PAPER.md` specifies:
  - **Source:** WRDS Compustat Futures
  - **Universe:** GSCI energy sector
  - **Period:** 2000–2024
  - **Roll convention:** `ratio_backward`
  - **Adjustment method:** `ratio_backward`
- **But actual implemented miner code uses:** `yfinance`, adjusted Yahoo data, not WRDS roll-adjusted futures construction.

## 3. Simulation: agent names and behaviors

Defined in `CommodityFuturesEnv.possible_agents` and `agents/forge/agents.py`.

### `passive_gsci`
- **Behavior:** always returns action `1`
- **Action meaning:** from env action space comment, `1=long`
- **Implementation:** `PassiveGSCI.act()` ignores observation and always longs

### `trend_follower`
Two behaviors appear:

#### Base class behavior in `agents.py`
- **Rule:** `1 if obs[0] > obs[4] else 2`
- Long if current observed value exceeds `obs[4]`, else short

#### Actual runner episode behavior for training in `_run_single_episode`
- Overrides class logic for this agent
- **Rule:**
  - `p0 = obs[0]`
  - `lookback_idx = max(0, len(self.env._price_history) - self.lookback_window)`
  - `lookback_price = self.env._price_history[lookback_idx]`
  - `momentum_signal = p0 - lookback_price`
  - action `1` if `momentum_signal > 0`, else `2`
- **Interpretation:** 12-month momentum, long if current price above lookback price, otherwise short
- **Lookback:** `252`

### `mean_reversion`
- **Rule:**
  - if `obs[0] > obs[1] * 1.02`: action `2` (short)
  - if `obs[0] < obs[1] * 0.98`: action `1` (long)
  - else action `0` (hold)
- **Interpretation:** fade ±2% deviations relative to `obs[1]`

### `liquidity_provider`
- **Rule:** alternates actions each call
  - even counter: `1`
  - odd counter: `2`
- **Stateful:** internal `_counter`
- **Runner behavior:** reinitialized at start of each `_run_single_episode`

### `macro_allocator`
- **Parameter:** `passive_threshold: float = 0.30`
- **Runner instantiation:** `MacroAllocator(passive_threshold=self.passive_concentration)`
- **Rule:** `1 if obs[6] < passive_threshold else 0`
- **Interpretation:** long when observation slot 6 is below threshold, otherwise hold

### `meta_rl`
- **Base class behavior in `agents.py`:**
  - random action `random.randint(0, 2)`
- **Actual runner behavior:**
  - action chosen by `self.cem.act(obs, weights)`
  - `CEM.act`: compute `logits = obs @ weights`, choose `argmax(logits)`
- **Interpretation:** learned allocation/policy over 3 discrete actions via linear logits over 10-dim observation

### Environment/action setup
- **Agents:** 6 total
  - `passive_gsci`
  - `trend_follower`
  - `mean_reversion`
  - `liquidity_provider`
  - `macro_allocator`
  - `meta_rl`
- **Observation space:** shape `(10,)`, dtype `float32`
- **Action space:** `Discrete(3)`
  - `0=hold`
  - `1=long`
  - `2=short`

### Passive capital scenarios
- Valid concentrations in env:
  - `0.10`
  - `0.30`
  - `0.60`
- Labels in spec:
  - Low = 10%
  - Medium = 30%
  - High = 60%

## 4. Seeds

### Exact seed values
- `[1337, 42, 9999]`

### Where used
- `PAPER.md`: seed policy
- `env.py`: `SEED_POLICY = "seeds = [1337, 42, 9999]"`
- `full_run.py`: `seeds = [1337, 42, 9999]`
- `modal_run.py`: `seeds = [1337, 42, 9999]`

### Seeding behavior in runner
- In `ForgeRunner.__init__`:
  - `np.random.seed(self.seed)`
  - `random.seed(self.seed)`

### Additional sigma seed usage
- `SigmaJob2.run()`:
  - `seed = self._seed_from_pap_lock()`
  - bootstrap uses this seed: `_bootstrap_ci(..., seed=seed, n_resamples=1000)`

### Seed consistency requirement
- `PAPER.md`: all three seeds must produce qualitatively consistent results
- finding valid only if it holds across all three seeds
- `SigmaJob2.run()` calls `_validate_seed_consistency(sim_df)`

## 5. Thresholds

### Statistical significance thresholds
- **Primary:** `p < 0.05`, two-tailed
- **Bonferroni-adjusted:** `p < 0.0083`
- **Number of simultaneous tests:** `6`

### Minimum effect threshold
- **Minimum effect size:** `-0.15 Sharpe units`
- In `SigmaJob2.run()` minimum effect output:
  - `"threshold": -0.15`

### Hypothesis threshold for passive concentration
- Above `30%` of open interest is the hypothesis threshold
- Scenarios include low `10%`, medium `30%`, high `60%`

### Data exclusion thresholds
- **Bid-ask spread filter:** `> 2%` of contract price, implemented as threshold `0.02`
- **Minimum trading history:** fewer than `100` trading days excluded
- **Macro exclusion window:** ±`5` days around macro announcement dates

### Numerical stability threshold in Sharpe computation
- In `ForgeRunner.sharpe`:
  - if `std < 1e-8`, return `0.0`

## 6. Windows

### Momentum lookback window
- **Value:** `252`
- **Meaning:** 12-month momentum
- **Locations:**
  - `ForgeRunner.lookback_window = 252`
  - `env.py`: `MOMENTUM_LOOKBACK_WINDOW = 252`

### Rolling primary metric window
- **Value:** `252` days
- **Meaning:** rolling Sharpe differential annualized over rolling 252-day windows
- **Locations:**
  - `PAPER.md`: primary metric
  - `env.py`: `ROLLING_CORRELATION_WINDOW = 252`
  - `SigmaJob2.run()` calls `_rolling_sharpe_differential(sim_df)`

### Fitness trailing window
- **Value:** trailing `252` episodes
- **Evaluation frequency:** every `1000` training steps / episodes, and at final episode
- **Location:** `ForgeRunner.run()`

### Episode length
- **Default:** `252`
- **Location:** `CommodityFuturesEnv.__init__(..., episode_length: int = 252)`

### Macro exclusion window
- **Value:** `5` days on each side of listed macro dates
- **Function:** `apply_macro_exclusion_window(..., exclusion_days=5)`

## 7. Fitness function for MetaRL

### Exact implemented formula
From `ForgeRunner.sharpe(step_returns)`:
```python
arr = np.asarray(step_returns, dtype=np.float64)
mean = arr.mean()
std = arr.std()
if std < 1e-8:
    return 0.0
return float((mean / std) * np.sqrt(252))
```

### How it is used for MetaRL fitness during training
- Every `1000` episodes, or at the final episode:
  - `trailing = self.rewards_history[-252:]`
  - `fitness = self.sharpe(trailing)`
- So the training fitness is:
  - **annualized Sharpe ratio of the trailing 252 episode-level rewards**
- Stored description:
  - `'fitness_function': 'trailing_252_episode_sharpe_every_1000_steps'`

### Episode scoring feeding fitness history
- For each CEM candidate in `_run_single_episode(weights)`:
  - collect `meta_step_rewards`
  - return `episode_mean = np.mean(meta_step_rewards)` if non-empty else `0.0`
- `self.rewards_history.append(np.max(scores))`
- Therefore the trailing series used in fitness is the history of **best candidate episode mean rewards per episode**
- Then Sharpe is computed on that trailing history using:
  - `mean(trailing_rewards) / std(trailing_rewards) * sqrt(252)`

## Consolidated specification-level parameter list

### Statistical/econometric parameters
- Newey-West HAC lags: `4`
- GARCH: `(1,1)` with Normal distribution
- Markov switching regimes: `2`
- Bootstrap resamples: `1000`
- Deflated Sharpe trials: `6`
- Bonferroni simultaneous tests: `6`

### Data parameters
- Actual source: `yfinance`
- Tickers: `CL=F`, `NG=F`
- Renamed series: `crude_oil_wti`, `natural_gas`
- Download start: `2000-01-01`
- Download end exclusive: `2024-01-01`
- Included through: `2023-12-31`
- Adjustment: `auto_adjust=True`
- Returns: log returns
- History filter: minimum `100` trading days
- Spread filter threshold: `0.02`
- Macro exclusion window: `5` days

### Simulation parameters
- Passive concentrations: `0.10`, `0.30`, `0.60`
- Episode length: `252`
- Observation dimension: `10`
- Action count: `3` (`hold`, `long`, `short`)
- Training episodes default: `500_000`

### Seed parameters
- Seeds: `1337`, `42`, `9999`

### Thresholds/windows
- Primary significance: `p < 0.05`
- Bonferroni significance: `p < 0.0083`
- Minimum effect: `-0.15` Sharpe units
- Momentum lookback: `252`
- Rolling/fitness window: `252`
- Fitness evaluation interval: `1000` episodes