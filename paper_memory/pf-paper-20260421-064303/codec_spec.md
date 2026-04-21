# CODEC Pass 1 Spec Extraction

## Scope-relevant implemented methodology

The codebase implements two distinct empirical/statistical tracks:

1. **Commodity return correlation analysis** in `agents/miner/miner.py`, `agents/analyst/analyst.py`, `agents/writer/writer.py`, and `agents/vizier/vizier.py`
2. **FORGE simulation + econometric evaluation** in `agents/forge/*.py` and `agents/sigma_job2.py`

Below are only specification-level parameters and transformations actually implemented.

---

## 1. Data sources and exact transformations

### 1.1 Commodity data ingestion
**File:** `agents/miner/miner.py`

#### Assets/tickers
The implemented commodity panel is exactly 5 futures tickers:
- `CL=F` → `crude_oil_wti`
- `GC=F` → `gold`
- `ZC=F` → `corn`
- `NG=F` → `natural_gas`
- `HG=F` → `copper`

#### Date range
- `START_DATE = "2010-01-01"`
- `END_DATE_EXCLUSIVE = "2024-01-01"`
- Comment states this includes data through `2023-12-31`

#### Download settings
- Uses `yfinance.download(...)`
- `auto_adjust=True`
- `progress=False`

#### Synchronization / missing-data handling
- Individual close series: `dropna()`
- Combined panel: `pd.concat(..., axis=1, join="inner")`
  - This means only dates present for **all 5 series** are retained.
- Sorted by date ascending.
- Returns frame later uses `.dropna()` after lagging.

#### Return transformation
Exact formula:
- `returns = np.log(close_df / close_df.shift(1)).dropna()`

So returns are:
- **daily log returns**
- computed from **auto-adjusted close prices**
- on the **intersection of all ticker dates**

#### Naming
Columns renamed from tickers to commodity names above.
Index name set to `"date"`.

---

## 2. Correlation-analysis methods and parameters

**Primary file:** `agents/analyst/analyst.py`

### 2.1 Input preprocessing
- Reads `outputs/commodity_returns.csv`
- Parses `"date"` as datetime
- Sets `"date"` as index
- Sorts index ascending
- Drops any row with any missing value: `dropna(how="any")`

### 2.2 Rolling pairwise correlations
#### Implemented method
For every unordered pair of commodities:
- pairwise rolling Pearson correlation via pandas rolling correlation

#### Parameters
- `ROLLING_WINDOW = 252`
- `min_periods = 252`

#### Exact behavior
For each pair `(left, right)`:
- `returns[left].rolling(window=252, min_periods=252).corr(returns[right])`
- Rows with missing rolling correlation are dropped
- Pair label format: `"left__right"`
- Dates are output as strings formatted `%Y-%m-%d`

So the rolling-correlation series begins only after a full 252 observations.

### 2.3 Structural break detection on rolling correlations
#### Implemented method
For each pair’s rolling-correlation time series:
- `ruptures.Pelt(model="rbf", min_size=MIN_BREAK_SIZE)`

#### Parameters
- `MIN_BREAK_SIZE = 63`
- Cost model: `"rbf"`
- Penalty:
  - `pen = np.log(max(len(y), 2)) * np.var(y)`
  - prediction uses `max(pen, 1e-8)`

#### Eligibility rule
A pair is skipped unless:
- number of rolling-correlation observations `>= 2 * MIN_BREAK_SIZE`
- i.e. at least `126` observations

#### Breakpoint recording
- `breakpoints = model.predict(pen=...)`
- Final endpoint is excluded: `breakpoints[:-1]`
- For each breakpoint `bp`, recorded date is row at index `bp - 1`
- Saved fields:
  - `pair`
  - `break_date`
  - `break_index`

### 2.4 DCC-GARCH correlation estimation
#### Implemented method
Two-stage procedure:

1. **Univariate GARCH(1,1)** per return series
2. **Bivariate DCC optimization** for each pair using standardized residuals

#### Stage 1: univariate GARCH standardization
For each commodity return series:
- returns are scaled by `100.0`
- model:
  - `mean="Zero"`
  - `vol="GARCH"`
  - `p=1`
  - `q=1`
  - `dist="normal"`
- standardized residuals extracted as `fit.std_resid.dropna()`

Residual series across assets are then aligned by:
- `pd.concat(std_resids, axis=1, join="inner").dropna()`

So DCC uses only dates where all standardized residual series are jointly observed.

#### Stage 2: DCC estimation
**Optimization target:** custom `_dcc_loglik`

##### DCC parameter constraints
Parameters:
- `a >= 0`
- `b >= 0`
- `a + b < 0.999`

Implementation details:
- bounds: `[(1e-8, 0.95), (1e-8, 0.95)]`
- inequality constraint: `0.999 - x[0] - x[1]`

##### Initialization
- initial guess: `x0 = [0.03, 0.95]`

##### Optimizer
- `scipy.optimize.minimize`
- method: `"SLSQP"`
- options:
  - `maxiter = 500`
  - `ftol = 1e-9`

##### Covariance initialization
- `qbar = np.cov(z_pair.T)`
- if shape is not `(2,2)`, fallback to identity
- numerical ridge added: `qbar += I * 1e-10`

##### Numerical safeguards in likelihood
- invalid parameter region returns objective `1e9`
- diagonal clipped at `1e-12`
- determinant nonpositive/nonfinite returns `1e9`
- correlation output clipped to `[-1.0, 1.0]`

##### Failure fallback
If optimizer fails:
- uses fixed `a=0.03`, `b=0.95`

#### Output
For each pair:
- date
- pair name `"left__right"`
- dynamic correlation series

### 2.5 Summary statistics produced from correlation outputs
`build_summary(...)` computes, by pair:
- `mean_rolling_corr = mean` of rolling correlations
- `std_rolling_corr = std` of rolling correlations
- `regime_breaks = count` of detected breaks, else 0
- `dcc_mean_corr = mean` of DCC correlations

---

## 3. Visualization/data transformations derived from returns

### 3.1 Cumulative return transformation
**File:** `agents/vizier/vizier.py`

Input returns are treated explicitly as **daily log returns**.

Exact cumulative transformation:
- `cumulative = np.exp(r[value_cols].cumsum())`

This yields cumulative **gross returns**, plotted on a **log y-scale**.

### 3.2 Correlation heatmap matrix construction
Heatmap is not computed from raw return correlations directly.
Instead:
- starts from identity matrix
- fills off-diagonals using `mean_rolling_corr` from analyst summary for each pair

So Figure 2 is a matrix of **average rolling correlations**, not static sample correlations.

---

## 4. FORGE simulation parameters actually implemented

### 4.1 Scenario grid
**Files:** `agents/forge/full_run.py`, `agents/forge/modal_run.py`

#### Passive concentration levels
Exactly:
- `0.10`
- `0.30`
- `0.60`

#### Seeds
Exactly:
- `1337`
- `42`
- `9999`

#### Episode count
Default full sweep:
- `n_episodes = 500_000`

This is used in:
- `run_full_sweep(n_episodes=500_000)`
- modal `run_scenario(..., n_episodes=500_000)`
- modal `run_all(n_episodes=500_000)`

So total scenario combinations:
- `3 concentrations × 3 seeds = 9 scenarios`

### 4.2 Environment parameters
**File:** `agents/forge/env.py`

#### Episode length
- default `episode_length = 252`

#### Allowed passive concentration values
Only:
- `{0.10, 0.30, 0.60}`
Any other value raises `ValueError`.

#### Observation vector
Length 10:
1. price history lag 0
2. lag 1
3. lag 2
4. lag 3
5. lag 4
6. current volatility
7. passive concentration
8. portfolio value
9. cash
10. current step

#### Action space
- `Discrete(3)`
- semantics:
  - `0 = hold`
  - `1 = long`
  - `2 = short`

#### Hard-coded market dynamics parameters
In `_apply_market_step()`:
- concentration risk multiplier: `1.0 + 6.0 * concentration^2`
- noise std: `0.006 * concentration_risk`
- flow impact coefficient: `0.0003 * (1.0 + 5.0 * concentration^2)`
- concentration drag: `0.0002 * concentration^2`

#### Volatility estimator
Rolling window length:
- last `20` step returns only

Sample variance formula:
- `(sumsq - n * mean^2) / (n - 1)` for `n >= 2`
- volatility = `sqrt(max(var, 0.0))`

#### Position/capital parameters
- initial price: `100.0`
- initial cash per agent: `10_000.0`
- max absolute position: `50.0` units
- minimum price floor: `1e-6`

#### Reward function parameters
Per-agent reward:
- `pct = (new_value - old_value) / max(abs(old_value), 10_000.0)`
- risk-free daily subtraction: `0.05 / 252`
- crowding cost:
  - `0.00005 * concentration^2 * (abs(position) / max_position_units)`
- volatility penalty:
  - `0.15 * concentration^2 * current_volatility`

Final reward:
- `pct - rf_daily - crowding_cost - volatility_penalty`

### 4.3 Agent policy thresholds
**File:** `agents/forge/agents.py`

#### MeanReversion
- short if `obs[0] > obs[1] * 1.02`
- long if `obs[0] < obs[1] * 0.98`
- else hold

So thresholds are ±2% relative to previous price.

#### MacroAllocator
- constructor default `passive_threshold = 0.30`
- action long if `obs[6] < passive_threshold`, else hold

But in `ForgeRunner`, it is instantiated as:
- `MacroAllocator(passive_threshold=self.passive_concentration)`

So actual threshold used in runs equals the scenario concentration itself, not the class default.

### 4.4 Runner-level parameters
**File:** `agents/forge/runner.py`

#### Seeds
At runner initialization:
- `np.random.seed(self.seed)`
- `random.seed(self.seed)`

#### Lookback parameter
- `self.lookback_window = 252`

#### CEM configuration
Not reporting per instruction (“Do NOT report: CEM internals”).

#### Sharpe computation
For per-step returns within one episode:
- if fewer than 2 observations: `0.0`
- standard deviation uses `np.std()` default ddof=0
- if std `< 1e-8`: `0.0`
- annualization factor: `sqrt(252)`

Formula:
- `(mean / std) * sqrt(252)`

#### Evaluation cadence during training
- every `100` episodes, evaluates best weights on one episode and prints Sharpe

### 4.5 Implemented momentum signal differs from stated 252-step lookback
**File:** `agents/forge/runner.py`

Although comments/state claim:
- `lookback_window = 252`
- “12-month momentum”

the actual trend-follower override in `_run_single_episode()` uses:
- `lookback_idx = min(4, len(self.env._price_history) - 1)`
- `lookback_price = self.env._price_history[lookback_idx]`
- `momentum_signal = current_price - lookback_price`

Since `_price_history` stores only the last 5 prices, the implemented momentum comparison is effectively against at most **4 steps back**, not 252 steps back.

This is a specification-level mismatch between stated parameterization and actual implementation.

---

## 5. SIGMA Job 2 econometric battery and parameters

**File:** `agents/sigma_job2.py`

### 5.1 Input data used for inference
- Loads `outputs/sim_results.json`
- Uses `sim_df["mean_reward"]` as the return series for most tests

So inference is run on the **9 scenario-level mean rewards**, not on episode-level or step-level returns.

### 5.2 Seed used for bootstrap
- Derived from `pap_lock.pap_sha256`
- If available: first 8 hex chars converted to integer
- fallback: `1337`

This is distinct from the FORGE simulation seeds `[1337, 42, 9999]`.

### 5.3 Newey-West t-test
Method:
- OLS of returns on constant only
- HAC covariance

Parameters:
- `cov_type="HAC"`
- `maxlags = 4`

Outputs:
- mean coefficient
- HAC standard error
- t-stat
- p-value
- `n_obs`
- `maxlags`

### 5.4 GARCH(1,1)
Method:
- `arch_model(y, mean="Constant", vol="GARCH", p=1, q=1, dist="normal")`

Transformation:
- `y = returns * 100.0`

Outputs include:
- `mu`
- `omega`
- `alpha1`
- `beta1`
- `alpha1 + beta1`
- loglikelihood
- AIC
- BIC
- alpha/beta p-values
- `n_obs`

### 5.5 Bootstrap confidence interval
Method:
- nonparametric bootstrap of the mean with replacement

Parameters:
- `n_resamples = 1000`
- RNG: `np.random.default_rng(seed)`

Exact CI:
- percentile interval at `[2.5, 97.5]`

Additional p-value:
- `mean_lt_zero_p_value = mean(boot_means < 0.0)`

### 5.6 Deflated Sharpe
Method name implemented:
- `_deflated_sharpe(returns, n_trials=6)`

Parameter:
- `n_trials = 6`

The provided code excerpt truncates before full formula details, so only this parameter is directly visible.

### 5.7 Markov regime model
Method name implemented:
- `_markov_regime(returns)`

The excerpt shows import:
- `MarkovAutoregression` from `statsmodels.tsa.regime_switching.markov_autoregression`

But the visible snippet does not include the function body, so regime count/order parameters are not recoverable from provided context.

### 5.8 Fama-MacBeth
Method name implemented:
- `_fama_macbeth(returns)`

Function body is not visible in provided excerpt, so exact regression specification is not recoverable here.

### 5.9 Bonferroni correction
Bonferroni is applied over exactly **7 tests**:
1. Newey-West t-test p-value
2. GARCH alpha p-value
3. GARCH beta p-value
4. Deflated Sharpe p-value
5. Markov regime mean-difference p-value
6. Bootstrap mean<0 p-value
7. Fama-MacBeth concentration p-value

Parameter:
- `n_tests = 7`

---

## 6. PAPER.md-facing mismatches visible from code/comments

Only mismatches inferable from the provided code/context:

### 6.1 Momentum lookback mismatch
**Files:** `agents/forge/env.py`, `agents/forge/runner.py`

Comments/state claim:
- momentum lookback window = `252`
- “12-month momentum”

Actual implementation:
- momentum signal in `_run_single_episode()` compares current price to a price at index `min(4, len(price_history)-1)`
- `_price_history` length is only 5

So implemented momentum signal is effectively **~4-step price difference**, not a 252-step lookback.

### 6.2 MacroAllocator threshold default vs actual run-time threshold
**Files:** `agents/forge/agents.py`, `agents/forge/runner.py`

Class default:
- `passive_threshold = 0.30`

Actual run-time instantiation:
- threshold set equal to scenario concentration (`0.10`, `0.30`, or `0.60`)

If PAPER.md specifies a fixed 30% threshold, the code does **not** consistently use that; it uses scenario-specific thresholds.

### 6.3 WRDS-vs-yfinance data source discrepancy
**File:** `agents/miner/miner.py`

`run_miner_pipeline(..., source="wrds")` defaults to WRDS and, for WRDS, fetches:
- `kind = "ff_factors"`
- writes `commodity_returns_wrds.csv`

This is not commodity futures return data.

Meanwhile `main()` and `build_returns_frame()` implement the actual commodity-futures panel via yfinance.

So if PAPER.md specifies commodity futures returns, the WRDS branch does not implement the same dataset.

---

## 7. Parameters explicitly implemented in paper-drafting text that match analyst code

**File:** `agents/assembler/assembler.py`

The generated methodology text states:
- rolling `252`-day pairwise correlations
- PELT with `RBF` cost
- quarterly minimum segment length
- DCC-GARCH(1,1)

These align with analyst code as:
- rolling window `252`
- PELT `model="rbf"`
- minimum segment length `63` trading days
- univariate GARCH(1,1) + DCC recursion

---

## 8. Concise parameter inventory

### Commodity correlation pipeline
- Assets: 5 (`crude_oil_wti`, `gold`, `corn`, `natural_gas`, `copper`)
- Date range: `2010-01-01` to `2023-12-31` inclusive via exclusive end `2024-01-01`
- Returns: `log(P_t / P_{t-1})`
- Price adjustment: `auto_adjust=True`
- Panel alignment: inner join across all assets
- Rolling correlation window: `252`
- Rolling correlation min periods: `252`
- Break detection method: PELT
- Break cost model: `rbf`
- Minimum break segment size: `63`
- Break penalty: `log(n) * var(y)`, floored at `1e-8`
- Univariate volatility model: zero-mean GARCH(1,1), normal
- Return scaling before GARCH: `×100`
- DCC optimizer: SLSQP
- DCC init: `(a,b)=(0.03,0.95)`
- DCC bounds: `[1e-8,0.95]` each
- DCC stationarity cap: `a+b < 0.999`
- DCC optimizer maxiter: `500`
- DCC optimizer ftol: `1e-9`

### FORGE simulation
- Concentrations: `0.10, 0.30, 0.60`
- Seeds: `1337, 42, 9999`
- Episodes per scenario: `500000`
- Episode length: `252`
- Action space: 3 actions
- Initial price: `100.0`
- Initial cash: `10000.0`
- Max position: `50.0`
- Volatility window: `20`
- Risk-free daily rate in reward: `0.05/252`
- Crowding cost coefficient: `0.00005`
- Volatility penalty coefficient: `0.15`
- Mean-reversion thresholds: `+2% / -2%`
- Sharpe annualization factor: `sqrt(252)`

### SIGMA Job 2
- Newey-West HAC maxlags: `4`
- GARCH return scaling: `×100`
- Bootstrap resamples: `1000`
- Bootstrap CI: `2.5%, 97.5%`
- Deflated Sharpe `n_trials`: `6`
- Bonferroni number of tests: `7`

---