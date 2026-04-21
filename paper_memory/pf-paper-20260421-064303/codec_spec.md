# Statistical tests

## Implemented in `agents/sigma_job2.py`

1. **Newey-West t-test**
   - Name used: `_newey_west_ttest`
   - Input/parameter visible from call site:
     - `returns`
   - Specification-level parameters evidenced elsewhere:
     - Newey-West HAC correction
     - **4 lags** from `PAPER.md`
     - **two-tailed**
   - Library:
     - `statsmodels.api as sm`

2. **GARCH(1,1) volatility model**
   - Name used: `_garch_11`
   - Input/parameter visible from call site:
     - `returns`
   - Specification-level parameters:
     - `p=1`, `q=1`
     - **Normal distribution**
   - Library:
     - `arch` via `from arch import arch_model`

3. **Bootstrap confidence interval / bootstrap test**
   - Name used: `_bootstrap_ci`
   - Parameters visible from call site:
     - `returns`
     - `seed=seed`
     - `n_resamples=1000`
   - Library:
     - not explicitly shown from imports beyond NumPy/Pandas/Scipy availability; only the call is visible in provided code

4. **Deflated Sharpe test**
   - Name used: `_deflated_sharpe`
   - Parameters visible from call site:
     - `returns`
     - `n_trials=6`
   - Output field used:
     - `p_value`
   - Library:
     - not explicitly shown in provided snippet

5. **Markov regime / Markov switching regime detection**
   - Name used: `_markov_regime`
   - Parameters/specification:
     - `returns`
     - `k_regimes=2` from `PAPER.md` and env constants
   - Library:
     - `statsmodels`
     - imported class: `statsmodels.tsa.regime_switching.markov_autoregression.MarkovAutoregression`

6. **Fama-MacBeth regression**
   - Name used: `_fama_macbeth_regression`
   - Input:
     - `sim_df`
   - Specification-level description:
     - `PAPER.md` says **Fama-French three-factor OLS regression (linearmodels, Fama-MacBeth)**
   - Library:
     - output version tracking includes `linearmodels`
     - exact import not shown in provided snippet

7. **DCC-GARCH cross-asset correlation summary**
   - Name used: `_dcc_garch_summary`
   - No explicit parameters at call site
   - Specification-level description:
     - DCC-GARCH cross-asset correlation
   - Library:
     - not explicitly shown in provided snippet

8. **Bonferroni correction**
   - Name used: `_bonferroni`
   - Parameters visible from call site:
     - p-values list of length 7:
       - Newey-West t-test p-value
       - GARCH alpha p-value
       - GARCH beta p-value
       - Deflated Sharpe p-value
       - Markov regime mean-difference p-value
       - Bootstrap `mean_lt_zero_p_value`
       - Fama-MacBeth `concentration_pvalue` defaulting to `1.0`
     - `n_tests=7`
     - `primary_metric=primary_metric`
   - Thresholds elsewhere:
     - `PAPER.md` / env constants specify Bonferroni threshold `p < 0.0083` for 6 simultaneous tests
   - Note:
     - actual `sigma_job2.py` call uses **7 tests**, not 6

# Data

## Actual implemented source
- File: `agents/miner/miner.py`
- Source used in code:
  - `yfinance` via `import yfinance as yf`
- Download function:
  - `yf.download(ticker, start=START, end=END, auto_adjust=True, progress=False)`

## Tickers
- `CL=F` mapped to `crude_oil_wti`
- `NG=F` mapped to `natural_gas`

## Date range
- Configured:
  - `START_DATE = "2000-01-01"`
  - `END_DATE_EXCLUSIVE = "2024-01-01"`
- Comment:
  - includes data through `2023-12-31`
- Passport written date range:
  - start: `2000-01-01`
  - end: `2023-12-31`

## Adjustment / roll method
- Actual download setting:
  - `auto_adjust=True`
- Returns construction:
  - log returns: `np.log(close_df / close_df.shift(1)).dropna()`
- Passport fields:
  - `"roll_convention": "ratio_backward"`
  - `"adjustment_method": "ratio_backward"`
  - but note says actual dev proxy is `yfinance auto_adjust=True`
- Explicit note:
  - actual implementation acknowledges deviation from exact `ratio_backward`

## Exclusion handling
- `apply_macro_exclusion_window(df, exclusion_days=5)`
- Actual behavior in dev run:
  - **no-op**
  - returns unchanged
- Documented exclusion window:
  - `5` days around major macro announcements
- FOMC dates list present as approximate sample
- Additional specification constants in `env.py`:
  - exclude contracts with fewer than `100` trading days of history
  - exclude contracts where bid-ask spread exceeds `2%` of contract price
- These are specification constants; no implementation shown in provided miner code for those filters

# Simulation

## Environment
- Class: `CommodityFuturesEnv`
- Library:
  - `pettingzoo.AECEnv`
- Agents in environment:
  1. `passive_gsci`
  2. `trend_follower`
  3. `mean_reversion`
  4. `liquidity_provider`
  5. `macro_allocator`
  6. `meta_rl`

## Action space
- `Discrete(3)`
- Meaning:
  - `0=hold`
  - `1=long`
  - `2=short`

## Observation space
- `Box(..., shape=(10,), dtype=np.float32)`
- Observed fields shown:
  1. `price_history[0]`
  2. `price_history[1]`
  3. `price_history[2]`
  4. `price_history[3]`
  5. `price_history[4]`
  6. current volatility
  7. passive concentration
  8. portfolio value
  9. cash
  10. current step

## Episode length
- Default: `252`

## Passive capital scenarios
- Valid concentrations:
  - `0.10`
  - `0.30`
  - `0.60`

## Agent behaviors

### `PassiveGSCI`
- `act(obs) -> 1`
- Always takes action `1` = long

### `TrendFollower`
- In `agents/forge/agents.py`:
  - returns `1` if `obs[0] > obs[4]`, else `2`
- In `ForgeRunner._run_single_episode`, this agent is overridden with explicit momentum logic:
  - `p0 = obs[0]`
  - `lookback_idx = min(4, len(self.env._price_history) - 1)`
  - `lookback_price = self.env._price_history[lookback_idx]`
  - `momentum_signal = p0 - lookback_price`
  - action `1` if `momentum_signal > 0`, else `2`
- Runner metadata:
  - `momentum_lookback_steps = 252`
  - `momentum_signal = 'price_level_difference_over_lookback'`
- But actual episode logic shown compares current price to a stored lookback index capped at `4`

### `MeanReversion`
- If `obs[0] > obs[1] * 1.02`: action `2` (short)
- If `obs[0] < obs[1] * 0.98`: action `1` (long)
- Else: action `0` (hold)

### `LiquidityProvider`
- Internal counter starts at `0`
- Alternates:
  - even counter -> `1`
  - odd counter -> `2`
- Counter increments each action
- In `_run_single_episode`, runner reinstantiates `LiquidityProvider()` at episode start

### `MacroAllocator`
- Parameter:
  - `passive_threshold: float = 0.30`
- In runner, instantiated as:
  - `MacroAllocator(passive_threshold=self.passive_concentration)`
- Behavior:
  - action `1` if `obs[6] < passive_threshold`
  - else `0`

### `MetaRL`
- Placeholder policy class in `agents.py`:
  - random integer action in `[0, 2]`
- Actual training/evaluation behavior in runner:
  - action chosen by `self.cem.act(obs, weights)`
  - `CEM.act`: computes `logits = obs @ weights`, returns `argmax(logits)`

# Seeds

## Exact seed values
- `1337`
- `42`
- `9999`

## Where used
- `PAPER.md`: seed policy
- `agents/forge/env.py`: `SEED_POLICY = "seeds = [1337, 42, 9999]"`
- `agents/forge/full_run.py`: `seeds = [1337, 42, 9999]`
- `agents/forge/modal_run.py`: `seeds = [1337, 42, 9999]`

## Seeding behavior
- In `ForgeRunner.__init__`:
  - `np.random.seed(self.seed)`
  - `random.seed(self.seed)`
- In `CommodityFuturesEnv.reset(seed=...)`:
  - if seed provided, `np.random.seed(seed)`
- In `SigmaJob2.run()`:
  - bootstrap seed comes from `_seed_from_pap_lock()`
  - exact numeric value not visible in provided snippet

# Thresholds

## Significance thresholds
- Primary:
  - `p < 0.05`
  - `two-tailed`
- Bonferroni:
  - `p < 0.0083`
- Sources:
  - `PAPER.md`
  - `agents/forge/env.py` constants

## Minimum effect size
- `-0.15` Sharpe units
- In `SigmaJob2.run()` written to output:
  - `"threshold": -0.15`
- `PAPER.md`:
  - effects smaller than this are economically insignificant

## Other explicit thresholds in behaviors/spec
- `MacroAllocator.passive_threshold` default:
  - `0.30`
- Mean reversion thresholds:
  - upper extreme: `+2%` (`obs[0] > obs[1] * 1.02`)
  - lower extreme: `-2%` (`obs[0] < obs[1] * 0.98`)
- Passive concentration scenario threshold in hypothesis/spec:
  - above `30%` vs below `30%`
- Exclusion thresholds from spec constants:
  - minimum trading history: `100` trading days
  - bid-ask spread filter: `2%` of contract price
  - macro exclusion window: `5` days

# Windows

## Lookback periods / rolling windows
- Momentum lookback window:
  - `252`
  - `MOMENTUM_LOOKBACK_WINDOW = 252`
  - `ForgeRunner.lookback_window = 252`
- Rolling correlation / primary metric window:
  - `252`
  - `ROLLING_CORRELATION_WINDOW = 252`
- Primary metric in paper:
  - Sharpe differential annualized over rolling `252`-day windows
- Fitness trailing window:
  - trailing `252` episodes
- Fitness evaluation frequency:
  - every `1000` training steps
- Episode length:
  - `252`
- Newey-West HAC lags:
  - `4`
- Macro exclusion window:
  - `5` days

# Fitness function for MetaRL

## Exact implemented formula
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

So the implemented fitness/Shapre formula is:

\[
\text{Sharpe} = \frac{\text{mean}(r)}{\text{std}(r)} \times \sqrt{252}
\]

with guards:
- if fewer than 2 observations: `0.0`
- if `std < 1e-8`: `0.0`

## How it is applied during training
- Every `1000` episodes, or at final episode:
  - `trailing = self.rewards_history[-252:]`
  - `fitness = self.sharpe(trailing)`
- Runner comment/spec string:
  - `"Fitness = Sharpe ratio over trailing 252 episodes"`
- Returned metadata:
  - `'fitness_function': 'trailing_252_episode_sharpe_every_1000_steps'`

## Reward basis used
- `self.rewards_history` stores:
  - `float(np.max(scores))` per episode
- Each candidate score is:
  - mean of `meta_rl` per-step rewards in `_run_single_episode`
- Therefore training fitness is computed on:
  - trailing 252 values of **best candidate episode mean reward per episode**

# Notable implementation/spec mismatches visible in provided code

- `PAPER.md` says Bonferroni correction for **6** simultaneous tests, but `SigmaJob2._bonferroni(...)` is called with **7** p-values and `n_tests=7`.
- `PAPER.md` specifies WRDS Compustat Futures with `ratio_backward`; actual miner implementation uses `yfinance` with `auto_adjust=True` as a proxy.
- `PAPER.md` describes 12-month momentum; runner metadata says `252` lookback, but shown trend logic in `_run_single_episode` uses `lookback_idx = min(4, len(price_history)-1)` against a short stored history in the visible code.