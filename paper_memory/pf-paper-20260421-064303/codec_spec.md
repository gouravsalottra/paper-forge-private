# CODEC Pass 1 Forensic Extraction

## Scope actually present in the provided code

The codebase contains **two distinct methodological tracks**:

1. **A commodity-data analysis / paper-assembly track**
   - `agents/miner/miner.py`
   - `agents/analyst/analyst.py`
   - `agents/writer/writer.py`
   - `agents/vizier/vizier.py`
   - `agents/assembler/assembler.py`

2. **A simulation / RL / econometric-evaluation track**
   - `agents/forge/*`
   - `agents/sigma_job1.py`
   - `agents/sigma_job2.py`

There is also an orchestration/audit/writing layer:
- `agents/aria/*`
- `agents/codec*`
- `agents/quill/quill.py`
- `agents/hawk/hawk.py`
- `agents/scout/scout.py`

These tracks are not fully unified in the visible code. Some files imply a paper about commodity correlations; others imply a paper about passive concentration and momentum Sharpe in a simulated market.

---

## Data sources

## 1. Commodity returns data
**File:** `agents/miner/miner.py`

### Source used in `main()`
- Downloads from **Yahoo Finance** via `yfinance.download(...)`
- Tickers:
  - `CL=F` → `crude_oil_wti`
  - `GC=F` → `gold`
  - `ZC=F` → `corn`
  - `NG=F` → `natural_gas`
  - `HG=F` → `copper`

### Date range
- Start: `2010-01-01`
- End exclusive: `2024-01-01`
- Comment says this includes data through `2023-12-31`

### Download settings
- `auto_adjust=True`
- `progress=False`

### Alignment
- Individual close series are concatenated with `join="inner"` so only dates common to all tickers are retained.

---

## 2. Optional WRDS source
**Files:** `agents/miner/miner.py`, `agents/miner/sources/wrds_src.py`

### Policy logic
- `select_data_source(require_wrds=True, wrds_available=False)` raises if WRDS is required but unavailable.
- `run_miner_pipeline(..., source="wrds")` tries WRDS first.

### What WRDS actually fetches in `run_miner_pipeline`
- Calls `agents.miner.sources.wrds_src.fetch(...)` with:
  - `kind: "ff_factors"`
  - `start: START_DATE`
  - `end: END_DATE_EXCLUSIVE`

So the WRDS branch does **not** fetch commodity futures returns. It fetches **Fama-French 5-factor daily data plus rf** and writes:
- `outputs/commodity_returns_wrds.csv`

This filename suggests commodity returns, but the actual fetched content is FF factors.

### WRDS adapters available
- `fetch_crsp(...)`: CRSP daily returns
- `fetch_compustat(...)`: Compustat fundamentals
- `fetch_ff_factors(...)`: Fama-French 5-factor daily table

All return long-format DataFrames `[date, series_name, value]`.

---

## 3. FRED adapter
**File:** `agents/miner/sources/fred_src.py`

- Fetches FRED series via `fredapi.Fred`
- Returns long DataFrame `[date, series_name, value]`
- Requires `series_ids`, `start`, `end`
- API key source order:
  1. `config["api_key"]`
  2. env `FRED_API_KEY`
  3. hardcoded fallback string

Undocumented/security-relevant fact: there is a **hardcoded FRED API key fallback** in code.

---

## 4. SEC adapter
**File:** `agents/miner/sources/sec_src.py`

- Uses SEC search endpoint `https://efts.sec.gov/LATEST/search-index`
- Fetches filing metadata and filing text
- Rate-limited to about 10 req/sec
- Returns DataFrame `[date, series_name, value]` where `value` is filing text

This adapter exists but is not visibly used by the main commodity pipeline.

---

## 5. Literature search sources
**File:** `agents/scout/scout.py`

- Reads `PAPER.md`
- Searches:
  - Semantic Scholar API
  - fallback to arXiv API
  - fallback to hardcoded seed papers if both fail

---

## 6. Simulation data
**Files:** `agents/forge/full_run.py`, `agents/forge/modal_run.py`, `agents/forge/runner.py`

Simulation outputs are written to:
- `outputs/sim_results.json`

Each row contains:
- `concentration`
- `seed`
- `sharpe`
- `mean_reward`
- `n_episodes`

---

## Transforms

## 1. Commodity return construction
**File:** `agents/miner/miner.py`

### Steps
1. Download adjusted close prices for each ticker.
2. Extract `Close`.
3. Drop missing values per series.
4. Inner-join all series on date.
5. Sort by date.
6. Compute daily log returns:
   - `np.log(close_df / close_df.shift(1)).dropna()`
7. Rename columns from ticker symbols to commodity names.
8. Set index name to `date`.
9. Save to `outputs/commodity_returns.csv`

### Implicit/undocumented step
- Inner join removes any date not shared across all five contracts.
- This synchronization rule materially changes sample size.

---

## 2. Rolling pairwise correlations
**File:** `agents/analyst/analyst.py`

### Input
- `outputs/commodity_returns.csv`

### Steps
1. Read CSV with `parse_dates=["date"]`
2. Set `date` as index
3. Sort index
4. Drop any row with any missing value: `dropna(how="any")`
5. For every pair of return columns:
   - compute rolling correlation with:
     - `window=252`
     - `min_periods=252`
6. Drop rows where rolling correlation is NA
7. Output long table with columns:
   - `date`
   - `pair`
   - `correlation`
8. Dates are formatted as `%Y-%m-%d`

### Pair count implied
With 5 assets, combinations produce **10 pairs**.

---

## 3. Structural break detection on rolling correlations
**File:** `agents/analyst/analyst.py`

### Steps
For each pair:
1. Sort by date
2. Convert correlation series to `float64`, reshape to `(-1,1)`
3. Skip if fewer than `MIN_BREAK_SIZE * 2 = 126` observations
4. Fit `ruptures.Pelt(model="rbf", min_size=63)`
5. Penalty:
   - `pen = log(max(len(y), 2)) * var(y)`
   - lower bounded at `1e-8`
6. Predict breakpoints with `model.predict(pen=...)`
7. For each breakpoint except the terminal endpoint:
   - map breakpoint index `bp` to row `bp - 1`
   - record:
     - `pair`
     - `break_date`
     - `break_index`

### Output
- `outputs/correlation_regimes.csv`

### Implicit step
- Break detection is applied to **rolling correlations**, not raw returns or DCC correlations.
- The penalty is data-dependent and not externally configured.

---

## 4. DCC correlation estimation
**File:** `agents/analyst/analyst.py`

### Univariate preprocessing
For each return series:
1. Multiply returns by `100.0`
2. Fit `arch_model(..., mean="Zero", vol="GARCH", p=1, q=1, dist="normal")`
3. Extract standardized residuals `fit.std_resid.dropna()`

### Alignment
- Concatenate standardized residual series with `join="inner"`
- Drop NA
- Rename columns back to original return column names

### Pairwise DCC fitting
For each pair:
1. Convert two standardized residual columns to `float64` numpy array
2. Estimate DCC parameters `(a,b)` by minimizing `_dcc_loglik`

### DCC objective details
- Parameters constrained:
  - `a >= 0`
  - `b >= 0`
  - `a + b < 0.999`
- Bounds:
  - each in `[1e-8, 0.95]`
- Initial guess:
  - `[0.03, 0.95]`
- Optimizer:
  - `scipy.optimize.minimize`
  - method `SLSQP`
  - `maxiter=500`
  - `ftol=1e-9`

### DCC recursion
- `qbar = cov(z_pair.T)`; fallback to identity if shape not `(2,2)`
- add `1e-10 * I` for stabilization
- recursive update:
  - `q_t = (1-a-b) qbar + a z_{t-1} z_{t-1}' + b q_t`
- correlation extracted as:
  - `rho_t = q_t[0,1] / sqrt(q_t[0,0] q_t[1,1])`
  - clipped to `[-1,1]`

### Numerical stabilization
- In loglikelihood:
  - diagonal clipped at `1e-12`
  - `r_t[0,0]=1`, `r_t[1,1]=1`
  - if determinant nonpositive or nonfinite, return `1e9`
- If optimizer fails:
  - fallback `(a,b) = (0.03, 0.95)`

### Output
- `outputs/dcc_correlations.csv`
- columns:
  - `date`
  - `pair`
  - `correlation`

### Implicit step
- DCC is implemented manually after univariate GARCH residualization; no packaged multivariate DCC estimator is used.

---

## 5. Analyst summary aggregation
**File:** `agents/analyst/analyst.py`

### Steps
1. From rolling correlations:
   - group by `pair`
   - compute:
     - `mean_rolling_corr`
     - `std_rolling_corr`
2. From regimes:
   - count breaks per pair as `regime_breaks`
   - if no regimes, set all to 0
3. From DCC correlations:
   - mean by pair as `dcc_mean_corr`
4. Merge all summaries by pair
5. Fill missing `regime_breaks` with 0 and cast to int
6. Sort by pair

### Output
- `outputs/analyst_summary.csv`

---

## 6. Writer transforms
**File:** `agents/writer/writer.py`

### Table 1
From `commodity_returns.csv`, for each commodity:
- Mean
- Std with `ddof=1`
- Min
- Max
- Skew
- Kurtosis

Then convert to LaTeX.

### Table 2
From `analyst_summary.csv`:
- pair
- mean_rolling_corr
- regime_breaks
- dcc_mean_corr

Formats pair names into readable labels and converts to LaTeX.

### Narrative
Builds 3 paragraphs from:
- sample start/end dates
- number of days
- number of assets
- highest and lowest mean rolling correlation pairs
- average regime breaks
- pair with max regime breaks

Notably, `rolling` is passed into `build_narrative(...)` but not actually used in the visible logic.

---

## 7. Visualization transforms
**File:** `agents/vizier/vizier.py`

### Figure 1
- Plot rolling correlations by pair in a fixed 2x5 grid
- Overlay vertical dashed lines at break dates if available
- y-limits `[-1,1]`

### Figure 2
- Build symmetric correlation matrix from `mean_rolling_corr` in analyst summary
- Diagonal set to 1
- Heatmap with annotations

### Figure 3
- Treat input returns as daily log returns
- Compute cumulative gross returns as:
  - `exp(cumsum(log returns))`
- Plot on log y-scale

---

## 8. Paper assembly transforms
**File:** `agents/assembler/assembler.py`

### Inputs required
- `table1_summary_stats.tex`
- `table2_correlation_summary.tex`
- `findings_narrative.txt`
- `fig1_rolling_correlations.png`
- `fig2_correlation_heatmap.png`

### Steps
1. Read narrative and split into paragraphs on blank lines
2. Use first two paragraphs to create abstract, clipped to 150 words
3. Insert fixed title, intro, methodology text, bibliography
4. Insert table and figure files by relative filename
5. Write `outputs/paper_draft.tex`

### Important literal fact
The methodology section in assembled LaTeX is **hardcoded prose**, not generated from actual parameter introspection.

---

## 9. FORGE environment transforms
**File:** `agents/forge/env.py`

### Environment structure
- PettingZoo AEC environment
- 6 agents:
  - `passive_gsci`
  - `trend_follower`
  - `mean_reversion`
  - `liquidity_provider`
  - `macro_allocator`
  - `meta_rl`

### Observation vector, shape `(10,)`
For each agent:
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

### Actions
- Discrete(3):
  - `0=hold`
  - `1=long`
  - `2=short`

### Forced action
- `passive_gsci` is always forced to action `1` in `step()`

### Market step transform
After all agents submit actions:
1. Convert actions to flows via `_action_to_flow`
   - visible mapping:
     - `1 -> 1`
     - function is truncated, but code elsewhere implies `2 -> -1`, `0 -> 0`
2. Sum to `net_order_flow`
3. Compute concentration-dependent terms:
   - `concentration_risk = 1 + 6 * concentration^2`
   - `noise ~ Normal(0, 0.006 * concentration_risk)`
   - `flow_impact = 0.0003 * (1 + 5 * concentration^2)`
   - `concentration_drag = 0.0002 * concentration^2`
4. Update price:
   - `price *= 1 + flow_impact * net_order_flow + noise - concentration_drag`
   - floor at `1e-6`
5. Compute step return:
   - `(price / old_price) - 1`
6. Maintain rolling 20-step volatility estimate using running sums
7. Update price history to last 5 prices
8. Update positions with cap ±50 units
9. Update cash by executed trade cost
10. Recompute portfolio values

---

## Parameters/defaults

## Commodity analysis parameters
**Files:** `agents/miner/miner.py`, `agents/analyst/analyst.py`

- Commodity tickers: 5 listed above
- Date range: `2010-01-01` to `2024-01-01` exclusive
- Rolling correlation window: `252`
- Minimum break size: `63`
- Break model: `PELT`, `model="rbf"`
- DCC univariate model:
  - mean `"Zero"`
  - vol `"GARCH"`
  - `p=1`, `q=1`
  - dist `"normal"`
- DCC optimizer:
  - method `"SLSQP"`
  - initial guess `[0.03, 0.95]`
  - bounds `[(1e-8,0.95),(1e-8,0.95)]`
  - constraint `a+b<0.999`
  - `maxiter=500`
  - `ftol=1e-9`

---

## FORGE simulation parameters
**Files:** `agents/forge/env.py`, `agents/forge/runner.py`, `agents/forge/cem.py`, `agents/forge/full_run.py`

### Environment
- Valid passive concentrations: `{0.10, 0.30, 0.60}`
- Episode length: `252`
- Initial price: `100.0`
- Initial cash per agent: `10_000.0`
- Max position units: `50.0`
- Volatility window length: `20`

### Reward-related constants
- Daily risk-free rate: `0.05 / 252`
- Crowding cost coefficient: `0.00005`
- Volatility penalty coefficient: `0.15`

### CEM
- `obs_dim=10`
- `n_elite=10`
- `population=50`
- `noise=0.1`

### Runner
- Default `n_episodes=500_000`
- Seeds used in full sweep:
  - `1337`
  - `42`
  - `9999`

### Full sweep
- Concentrations:
  - `0.10`
  - `0.30`
  - `0.60`
- Total scenarios: `3 x 3 = 9`

---

## Rule-based agent policies

## `agents/forge/agents.py`

- **PassiveGSCI**
  - always returns action `1`

- **TrendFollower**
  - returns `1 if obs[0] > obs[4] else 2`

- **MeanReversion**
  - if `obs[0] > obs[1] * 1.02`: short (`2`)
  - if `obs[0] < obs[1] * 0.98`: long (`1`)
  - else hold (`0`)

- **LiquidityProvider**
  - alternates long/short each call using internal counter

- **MacroAllocator**
  - parameter `passive_threshold`
  - returns `1 if obs[6] < passive_threshold else 0`
  - In runner, `passive_threshold` is set equal to the scenario concentration, so since `obs[6]` is also the concentration, this policy will return `0` unless floating-point comparison makes it strictly less. Literal behavior from code: likely always hold.

- **MetaRL**
  - in `agents.py`, random action `randint(0,2)`, but in training/evaluation the runner actually uses CEM weights for `meta_rl`.

---

## Reward function

## Commodity analysis track
There is **no reward function** in the miner/analyst/writer/vizier/assembler pipeline.

---

## FORGE environment reward
**File:** `agents/forge/env.py`

For each agent after each market step:

1. Compute old and new portfolio value
2. Normalize portfolio change:
   - `pct = (new_value - old_value) / max(abs(old_value), 10_000.0)`

3. Subtract daily risk-free rate:
   - `rf_daily = 0.05 / 252`

4. Subtract crowding cost:
   - `crowding_cost = 0.00005 * concentration^2 * (abs(position) / max_position_units)`

5. Subtract volatility penalty:
   - `volatility_penalty = 0.15 * concentration^2 * current_volatility`

6. Reward:
   - `reward = pct - rf_daily - crowding_cost - volatility_penalty`

This is the actual per-step reward.

### Optimization target in runner
**File:** `agents/forge/runner.py`

For each CEM candidate:
- Run one episode
- Collect `meta_rl` step rewards only
- Candidate score = **mean of meta_rl step rewards over the episode**

So the training objective is:
- maximize **episode mean meta_rl reward**

Not Sharpe directly.

---

## Evaluation method

## Commodity analysis track
Evaluation is descriptive/statistical, not predictive.

### Outputs used as evaluation summaries
**File:** `agents/analyst/analyst.py`
- mean rolling correlation
- std rolling correlation
- number of detected regime breaks
- mean DCC correlation

### Writer narrative highlights
**File:** `agents/writer/writer.py`
- highest average rolling-correlation pair
- lowest average rolling-correlation pair
- average break count
- pair with most breaks

No hypothesis test or out-of-sample evaluation is present in this track.

---

## FORGE evaluation
**Files:** `agents/forge/runner.py`, `agents/forge/full_run.py`

### During training
Every 100 episodes:
- evaluate current best CEM weights on one episode
- compute Sharpe from meta_rl per-step rewards:
  - `mean / std * sqrt(252)`

### Final result per scenario
- `mean_reward`: mean of meta_rl per-step rewards from one episode using best weights
- `sharpe`: Sharpe of meta_rl per-step rewards from one episode using best weights
- `n_episodes`

### Full sweep evaluation
- Run all 9 `(concentration, seed)` scenarios
- Save scenario-level results to `outputs/sim_results.json`

---

## Econometric evaluation over simulation outputs
**File:** `agents/sigma_job2.py`

### Input
- `outputs/sim_results.json`

### Returns used
- `returns = sim_df["mean_reward"].to_numpy(dtype=float)`

So all econometric tests are run on the vector of **scenario-level mean rewards**, not on time-series step returns.

### Tests run
1. **Newey-West t-test**
   - OLS on constant only
   - HAC covariance with `maxlags=4`

2. **GARCH(1,1)**
   - on `returns * 100`
   - mean `"Constant"`
   - vol `"GARCH"`
   - `p=1`, `q=1`
   - dist `"normal"`

3. **Bootstrap CI**
   - `n_resamples=1000`
   - seed derived from PAP lock hash

4. **Deflated Sharpe**
   - visible call: `_deflated_sharpe(returns, n_trials=6)`
   - implementation is truncated in provided context

5. **Markov regime model**
   - visible call: `_markov_regime(returns)`
   - implementation not shown in provided context

6. **Fama-MacBeth**
   - visible call: `_fama_macbeth(returns)`
   - implementation not shown in provided context

7. **Bonferroni correction**
   - applied across 7 p-values

### Outputs written
- `sharpe_summary.csv`
- `ttest_results.csv`
- `garch_results.csv`
- `fama_macbeth_results.csv`
- `stats_summary.tex`
- `library_versions.json`

---

## Undocumented / implicit / inconsistent steps

## 1. Two different research stories coexist
- Commodity correlation analysis pipeline says the paper is about:
  - rolling correlations
  - structural breaks
  - DCC-GARCH
- FORGE/SIGMA/QUILL prompts imply a paper about:
  - passive concentration
  - momentum Sharpe
  - simulation
  - pre-analysis plan

These are materially different methodologies.

---

## 2. WRDS branch does not match commodity-return naming
`run_miner_pipeline(..., source="wrds")` writes FF factor data to:
- `outputs/commodity_returns_wrds.csv`

This is a naming/content mismatch.

---

## 3. MacroAllocator likely degenerates to hold
In `ForgeRunner.__init__`:
- `MacroAllocator(passive_threshold=self.passive_concentration)`

In env observations:
- `obs[6] = self.passive_concentration`

Policy:
- `return 1 if obs[6] < self.passive_threshold else 0`

Since these are equal, literal behavior is usually `0` always.

---

## 4. Trend-following implementation mismatch inside runner
There are two trend-following definitions:
- `agents/forge/agents.py`: `obs[0] > obs[4]`
- `agents/forge/runner.py`: custom branch for `trend_follower` computes momentum using `self.env._price_history[lookback_idx]`, where `lookback_idx = min(4, len(_price_history)-1)`

So the runner overrides the class policy for trend follower.

Also, despite comments about 12-month momentum / 252 lookback, the actual observation/history used is only the last **5 prices**, so the implemented momentum signal is not a 252-step lookback.

---

## 5. Claimed 12-month momentum is not actually implemented
Constants/comments:
- `MOMENTUM_LOOKBACK_WINDOW = 252`
- `lookback_window: int = 252`
- comments say “12-month momentum”

Actual signal:
- compares current price to one of the last 5 stored prices

So the code contains a documented parameter that is not operationalized in the visible environment state.

---

## 6. Sigma Job 2 tests are run on only 9 scenario-level observations
`sim_results.json` from full sweep has 9 rows.
`SigmaJob2` uses `mean_reward` across those rows as `returns`.

Thus:
- Newey-West
- GARCH
- bootstrap
- regime model
- Fama-MacBeth

are being applied to a very small cross-scenario vector, not a long time series.

---

## 7. Assembler hardcodes methodology prose
The LaTeX methodology section is fixed text and may not reflect actual code if code changes.

---

## 8. CODEC comparison is lexical/proxy-based
**File:** `agents/codec/codec.py`

Comparison uses:
- extracted numeric claims
- presence/absence of a fixed set of method terms
- KS test on numeric values in text

This is not semantic equivalence checking of implementations.

---

## 9. Passports/hash tracking
Many stages write passports with:
- file paths
- SHA-256 hashes
- row counts
- timestamps

This is an implicit reproducibility/integrity mechanism across stages.

---

## 10. Analyst file is truncated at end
`agents/analyst/analyst.py` ends mid-call:
- `write_passport(file...`

So the exact final `main()` passport-writing arguments are not visible in provided context, though earlier functions define intended behavior.

---

## 11. Several implementations are truncated in provided context
Not fully visible:
- end of `agents/forge/env.py` `_action_to_flow`
- end of `agents/codec/codec.py` `_compare`
- end of `agents/hawk/hawk.py`
- end of `agents/quill/quill.py`
- end of `agents/scout/scout.py`
- end of `agents/sigma_job2.py`

Therefore only visible behavior should be treated as confirmed.

---

## Reward function summary

## Confirmed reward functions
### FORGE environment
Per-step reward for each agent:
`portfolio_pct_change - rf_daily - crowding_cost - volatility_penalty`

### CEM optimization target
Mean episode reward of `meta_rl` agent.

### Reported evaluation metric
Sharpe ratio of `meta_rl` per-step rewards from one episode.

### Commodity analysis track
No reward function.

---

## Evaluation summary

## Commodity analysis track
- Descriptive summary statistics
- Rolling correlations
- PELT break counts
- Mean DCC correlations
- Narrative ranking of strongest/weakest pairs and instability

## Simulation/econometric track
- Scenario sweep over 3 concentrations × 3 seeds
- Final scenario metrics:
  - mean reward
  - Sharpe
- Sigma Job 2 econometric battery on scenario-level `mean_reward` vector:
  - HAC t-test
  - GARCH(1,1)
  - bootstrap CI
  - deflated Sharpe
  - Markov regime
  - Fama-MacBeth
  - Bonferroni correction

---

## Literal bottom line

The code actually implements:

1. A **real-data commodity correlation pipeline** using Yahoo Finance daily futures returns, 252-day rolling correlations, PELT break detection, and pairwise DCC-GARCH diagnostics.

2. A separate **simulated multi-agent commodity market** where a MetaRL agent is optimized by CEM to maximize mean per-step reward under different passive concentration settings, followed by econometric tests on aggregated simulation outputs.

These are both present, but they are not cleanly reconciled into one single coherent methodology in the visible code.