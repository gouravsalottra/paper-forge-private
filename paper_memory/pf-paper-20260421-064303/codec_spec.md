# CODEC Pass 1 Specification Extraction

## 1. Statistical tests

### Implemented / invoked in `agents/sigma_job2.py`
The run method invokes these tests / analyses:

1. **Newey-West t-test**
   - Method call: `_newey_west_ttest(returns)`
   - Input: `returns = sim_df["mean_reward"].to_numpy(dtype=float)`
   - Library evidence:
     - `statsmodels.api as sm` imported
   - Parameters explicitly visible from provided context:
     - Uses `returns`
   - Additional specification strings from codebase:
     - `PAPER.md`: **Two-tailed t-test**, **Newey-West HAC correction (4 lags)**, primary threshold **p < 0.05**
   - Exact implementation details beyond invocation are not visible in provided excerpt.

2. **GARCH(1,1) volatility model**
   - Method call: `_garch_11(returns)`
   - Library:
     - `arch.arch_model`
   - Parameters/specification:
     - `PAPER.md`: **GARCH(1,1)**, `p=1`, `q=1`, **Normal distribution**
     - `env.py` constant: `"GARCH(1,1) volatility model (arch library, p=1, q=1, Normal distribution)"`
   - Output field used later:
     - `garch_result["alpha_pvalue"]`

3. **Bootstrap confidence interval / bootstrap test**
   - Method call: `_bootstrap_ci(returns, seed=seed, n_resamples=1000)`
   - Library:
     - not explicitly shown in excerpt; likely NumPy/pandas-based internal implementation, but not visible
   - Parameters explicitly visible:
     - `seed = 1337`
     - `n_resamples = 1000`
   - Output field used later:
     - `bootstrap_result["mean_lt_zero_p_value"]`

4. **Deflated Sharpe test**
   - Method call: `_deflated_sharpe(returns, n_trials=6)`
   - Library:
     - not visible in excerpt
   - Parameters explicitly visible:
     - `n_trials = 6`
   - Output field used later:
     - `deflated_result["p_value"]`

5. **Markov regime / Markov switching regime detection**
   - Method call: `_markov_regime(returns)`
   - Library:
     - `statsmodels.tsa.regime_switching.markov_autoregression.MarkovAutoregression`
   - Specification:
     - `PAPER.md`: **Markov switching regime detection**, `k_regimes=2`
     - `env.py` constant: `"statsmodels, k_regimes=2"`
   - Output field used later:
     - `regime_result["regime_mean_diff_p_value"]`

6. **Fama-MacBeth regression**
   - Method call: `_fama_macbeth_regression(sim_df)`
   - Library:
     - not imported in visible code excerpt
   - Specification string:
     - `FAMA_FRENCH_REGRESSION_SPEC = "Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)"`
     - `PAPER.md` also lists: `"Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)"`
   - Output field used later:
     - `fama_result.get("concentration_pvalue", 1.0)`

7. **Fama-French three-factor OLS regression**
   - Method call: `_fama_french_three_factor_ols(sim_df)`
   - Library:
     - spec mentions `linearmodels`, but no visible import in excerpt
   - Specification:
     - three-factor OLS regression
     - associated with Fama-French momentum-factor control in `PAPER.md` hypothesis

8. **DCC-GARCH cross-asset correlation**
   - Method call: `_dcc_garch_summary()`
   - Library:
     - not visible in excerpt
   - Specification:
     - `PAPER.md`: **DCC-GARCH cross-asset correlation**
   - Output fields written:
     - `method`
     - `n_pairs`
     - `mean_dcc_correlation`
     - `error`

9. **Bonferroni multiple-testing correction**
   - Method call: `_bonferroni([...], n_tests=6, primary_metric=primary_metric)`
   - Parameters explicitly visible:
     - `n_tests = 6`
     - p-values included:
       - Newey-West t-test p-value
       - GARCH alpha p-value
       - Deflated Sharpe p-value
       - Markov regime mean-difference p-value
       - Bootstrap mean<0 p-value
       - Fama-MacBeth concentration p-value
   - Specification:
     - `PAPER.md`: adjusted threshold **p < 0.0083**
     - `env.py`: `"Bonferroni correction for 6 simultaneous tests — adjusted threshold p < 0.0083"`

## 2. Data

### Actual implemented data source
From `agents/miner/miner.py`:

- **Source library**: `yfinance`
- **Download function**: `yf.download(...)`
- This is the actual implemented source in provided code excerpt.

### Tickers actually implemented
`TICKERS = {`
- `"CL=F": "crude_oil_wti"`
- `"NG=F": "natural_gas"`
`}`

### Date range actually implemented
- `START_DATE = "2000-01-01"`
- `END_DATE_EXCLUSIVE = "2024-01-01"`
- Comment: includes data through `2023-12-31`

### Adjustment method actually implemented
- `yf.download(..., auto_adjust=True, ...)`
- So prices are downloaded with **auto-adjust enabled**
- `PAPER.md` also states:
  - **Roll Convention**: `ratio_backward`
  - **Adjustment Method**: `ratio_backward`
- But the actual visible implementation in `miner.py` uses **yfinance auto_adjust=True**, not a visible ratio-backward implementation.

### Derived data actually implemented
- Close series downloaded per ticker
- Spread proxy series downloaded per ticker using:
  - `High`
  - `Low`
  - `Close`
- Returns computed as:
  - `np.log(close_df / close_df.shift(1)).dropna()`

### Filters / exclusions actually implemented
1. **Minimum trading history**
   - Keep only columns with at least `100` non-null trading days
   - Rule:
     - `close_df[c].dropna().shape[0] >= 100`

2. **Macro exclusion window**
   - Function: `apply_macro_exclusion_window(df, exclusion_days=5)`
   - Window:
     - `±5` calendar days around dates in `FOMC_DATES_APPROX`
   - Comment says FOMC/CPI exclusion; visible list contains approximate FOMC dates only in excerpt
   - Applied to returns rows

3. **Bid-ask spread filter**
   - Function: `apply_bid_ask_spread_filter(..., threshold=0.02)`
   - Proxy:
     - `abs(high - low) / close`
   - Row removed if:
     - `aligned_spread.max(axis=1) > 0.02`

### Data passport metadata
Visible passport fields include:
- file path
- sha256
- row_count
- date_range:
  - start: `2000-01-01`
  - end: `2023-12-31`
- actual_date_range start/end if non-empty

## 3. Simulation: agent names and behaviors

From `agents/forge/env.py`, possible agents are:

1. `passive_gsci`
2. `trend_follower`
3. `mean_reversion`
4. `liquidity_provider`
5. `macro_allocator`
6. `meta_rl`

From `agents/forge/agents.py`, actual behaviors:

### 1. PassiveGSCI
- Class: `PassiveGSCI`
- Behavior:
  - ignores observation
  - always returns action `1`
- Action semantics from env:
  - `0=hold, 1=long, 2=short`
- So implemented behavior: **always long**

### 2. TrendFollower
- Class: `TrendFollower`
- Behavior in `agents.py`:
  - `return 1 if obs[0] > obs[4] else 2`
  - long if current observed value at index 0 exceeds obs index 4, else short
- Additional behavior in `runner.py` during `_run_single_episode`:
  - trend follower is overridden with a **12-month momentum signal**
  - `lookback_window = 252`
  - `lookback_price = self.env._price_history[max(0, len(self.env._price_history) - self.lookback_window)]`
  - `momentum_signal = current_price - lookback_price`
  - action `1` if momentum positive else `2`
- So actual simulation behavior in training episodes:
  - **long if current price exceeds 252-step lookback price, else short**

### 3. MeanReversion
- Class: `MeanReversion`
- Behavior:
  - if `obs[0] > obs[1] * 1.02`: return `2` (short)
  - if `obs[0] < obs[1] * 0.98`: return `1` (long)
  - else return `0` (hold)
- So:
  - short when current exceeds reference by 2%
  - long when current is below reference by 2%
  - otherwise hold

### 4. LiquidityProvider
- Class: `LiquidityProvider`
- Internal state:
  - `_counter`, initialized to `0`
- Behavior:
  - alternates actions:
    - even counter -> `1`
    - odd counter -> `2`
  - increments counter each act
- In `_run_single_episode`, liquidity agent is reinitialized each episode:
  - `self.liquidity_agent = LiquidityProvider()`
- So behavior:
  - **alternates long/short each action, resetting each episode**

### 5. MacroAllocator
- Class: `MacroAllocator`
- Parameter:
  - `passive_threshold: float = 0.30`
- In runner initialization:
  - `MacroAllocator(passive_threshold=self.passive_concentration)`
- Behavior:
  - `return 1 if obs[6] < self.passive_threshold else 0`
- So:
  - long if observation index 6 is below passive threshold
  - otherwise hold

### 6. MetaRL
- Class: `MetaRL`
- Behavior in `agents.py`:
  - ignores observation
  - returns `random.randint(0, 2)`
- But in actual FORGE training/evaluation in `runner.py`, `meta_rl` actions are chosen via CEM:
  - training/evaluation action:
    - `self.cem.act(obs, weights)`
  - `CEM.act` computes:
    - `logits = obs @ weights`
    - action = `argmax(logits)`
- So actual simulation behavior:
  - **MetaRL is controlled by CEM linear policy over 10-dim observation to 3 actions**
  - placeholder random `MetaRL.act()` exists but is not the operative policy in runner episodes

### Environment action space
- `Discrete(3)`
- Semantics:
  - `0 = hold`
  - `1 = long`
  - `2 = short`

### Passive capital scenarios
From `env.py`, `full_run.py`, `modal_run.py`:
- Low: `0.10`
- Medium: `0.30`
- High: `0.60`

### Episode length
From `CommodityFuturesEnv.__init__`:
- `episode_length: int = 252`

## 4. Seeds: exact values used

Exact seeds used across codebase:

- `REQUIRED_SEEDS = [1337, 42, 9999]` in `sigma_job2.py`
- `SEED_POLICY_SPEC = "seeds = [1337, 42, 9999]"` in `sigma_job2.py`
- `SEED_POLICY = "seeds = [1337, 42, 9999]"` in `env.py`
- `full_run.py`: `seeds = [1337, 42, 9999]`
- `modal_run.py`: `seeds = [1337, 42, 9999]`

Actual seed usage:
- `ForgeRunner.__init__`:
  - `np.random.seed(self.seed)`
  - `random.seed(self.seed)`
- `SigmaJob2.run()`:
  - bootstrap seed uses `seed = REQUIRED_SEEDS[0] = 1337`

## 5. Thresholds: significance levels, minimum effects

### Significance thresholds
From `PAPER.md` and mirrored constants in `env.py`:

1. **Primary significance threshold**
   - `p < 0.05`
   - explicitly **two-tailed**

2. **Bonferroni-corrected threshold**
   - `p < 0.0083`
   - for `6` simultaneous tests

### Minimum effect size
- `-0.15 Sharpe units`
- In `sigma_job2.py`, written out as:
  - `"threshold": -0.15`
- `PAPER.md`:
  - effects smaller than this are economically insignificant regardless of statistical significance

### Other thresholds / cutoffs actually implemented
1. **Bid-ask spread exclusion threshold**
   - `0.02` = `2%` of contract price

2. **Minimum trading history**
   - `100` trading days

3. **Macro exclusion window**
   - `5` days on either side of event dates

4. **Mean reversion trigger thresholds**
   - upper trigger: `obs[0] > obs[1] * 1.02`
   - lower trigger: `obs[0] < obs[1] * 0.98`

5. **Macro allocator threshold**
   - default constructor threshold `0.30`
   - in runner, threshold equals scenario passive concentration (`0.10`, `0.30`, or `0.60`)

6. **Sharpe computation near-zero std cutoff**
   - if `std < 1e-8`, Sharpe returns `0.0`

## 6. Windows: lookback periods, rolling windows

### Momentum / lookback windows
1. **Momentum lookback window**
   - `252`
   - `ForgeRunner.lookback_window = 252`
   - `env.py`: `MOMENTUM_LOOKBACK_WINDOW = 252`
   - Comment/spec: 12-month momentum

2. **Episode length**
   - `252`
   - `CommodityFuturesEnv(..., episode_length: int = 252)`

### Rolling windows
1. **Primary metric rolling window**
   - `252-day` rolling windows
   - `PAPER.md`: Sharpe ratio differential annualized over rolling 252-day windows
   - `env.py`: `ROLLING_CORRELATION_WINDOW = 252`

2. **MetaRL fitness trailing window**
   - trailing `252` episodes
   - evaluated every `1000` training steps / episodes checkpoint
   - code:
     - `if episode % 1000 == 0 or episode == self.n_episodes:`
     - `trailing = self.rewards_history[-252:]`

### HAC lag window
- Newey-West HAC correction:
  - `4 lags` from `PAPER.md`

### Macro exclusion window
- `±5 days`

## 7. Fitness function: exact formula used for MetaRL

From `agents/forge/runner.py`:

### Declared fitness policy
- Comment:
  - `Fitness = Sharpe ratio over trailing 252 episodes`
  - evaluated every `1000` training steps
- Returned metadata:
  - `'fitness_function': 'trailing_252_episode_sharpe_every_1000_steps'`

### Exact Sharpe formula implementation
Method:
```python
@staticmethod
def sharpe(step_returns: list) -> float:
    if len(step_returns) < 2:
        return 0.0
    arr = np.asarray(step_returns, dtype=np.float64)
    mean = arr.mean()
    std = arr.std()
    if std < 1e-8:
        return 0.0
    return float((mean / std) * np.sqrt(252))
```

So the exact formula is:

\[
\text{Sharpe} =
\begin{cases}
0.0 & \text{if } n < 2 \\
0.0 & \text{if } \sigma < 10^{-8} \\
\left(\frac{\mu}{\sigma}\right)\sqrt{252} & \text{otherwise}
\end{cases}
\]

where:
- `arr` is the input list converted to float64
- `μ = arr.mean()`
- `σ = arr.std()`

### What series the fitness is applied to
During training:
- `self.rewards_history.append(float(np.max(scores)))`
- every 1000 episodes:
  - `trailing = self.rewards_history[-252:]`
  - `fitness = self.sharpe(trailing)`

Thus the training fitness is computed on:
- the **last 252 values of `rewards_history`**
- where each `rewards_history` entry is the **maximum candidate score** in that episode's CEM population
- each candidate score is:
  - `_run_single_episode(weights)` return value
  - which is `episode_mean = mean(meta_step_rewards)` for that episode

So operationally:

1. For each candidate policy in an episode:
   - run one episode
   - collect `meta_step_rewards`
   - score candidate as:
     \[
     \text{candidate score} = \text{mean}(\text{meta step rewards})
     \]

2. For each training episode:
   - append best candidate score:
     \[
     r_t = \max(\text{candidate scores in episode } t)
     \]

3. Every 1000 episodes:
   - compute fitness on trailing 252 `r_t` values:
     \[
     \text{fitness}_t = \frac{\operatorname{mean}(r_{t-251:t})}{\operatorname{std}(r_{t-251:t})}\sqrt{252}
     \]
   - with guards:
     - return `0.0` if fewer than 2 observations
     - return `0.0` if std `< 1e-8`

## Concise implementation summary

### Statistical tests implemented/spec'd
- Newey-West HAC two-tailed t-test, 4 lags, `statsmodels`
- GARCH(1,1), `arch`, `p=1`, `q=1`, Normal
- Bootstrap CI/test, `n_resamples=1000`, seed `1337`
- Deflated Sharpe, `n_trials=6`
- Markov switching / Markov autoregression, `statsmodels`, `k_regimes=2`
- Fama-MacBeth regression
- Fama-French three-factor OLS
- DCC-GARCH cross-asset correlation
- Bonferroni correction over 6 tests

### Data actually implemented
- Source: `yfinance`
- Tickers: `CL=F`, `NG=F`
- Date range: `2000-01-01` to `2024-01-01` exclusive
- Effective included end date: `2023-12-31`
- Adjustment: `auto_adjust=True`
- Returns: log returns
- Filters:
  - min history `100` days
  - macro exclusion `±5` days
  - spread threshold `2%`

### Simulation agents
- `passive_gsci`: always long
- `trend_follower`: long/short momentum; in runner uses 252-step price difference
- `mean_reversion`: short above +2%, long below -2%, else hold
- `liquidity_provider`: alternates long/short
- `macro_allocator`: long if `obs[6] < threshold`, else hold
- `meta_rl`: actual runner uses CEM linear argmax policy

### Seeds
- `[1337, 42, 9999]`

### Thresholds
- primary significance: `p < 0.05` two-tailed
- Bonferroni: `p < 0.0083`
- minimum effect: `-0.15` Sharpe units

### Windows
- momentum lookback: `252`
- rolling primary metric: `252`
- fitness trailing window: `252`
- fitness evaluation interval: `1000`
- episode length: `252`
- Newey-West lags: `4`
- macro exclusion: `±5 days`

### MetaRL fitness formula
- exact implemented Sharpe:
  - `(mean / std) * sqrt(252)`
  - on trailing 252 entries of `rewards_history`
  - `rewards_history[t] = max candidate episode mean reward at training episode t`