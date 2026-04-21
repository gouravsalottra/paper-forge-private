# CODEC Pass 1 Spec Extraction

## Scope actually present in code

The codebase contains **two distinct methodological tracks**:

1. **Commodity data / correlation-analysis / paper-assembly track**
   - `agents/miner/miner.py`
   - `agents/analyst/analyst.py`
   - `agents/writer/writer.py`
   - `agents/vizier/vizier.py`
   - `agents/assembler/assembler.py`

2. **FORGE simulation / PAP / econometric audit track**
   - `agents/forge/*.py`
   - `agents/sigma_job1.py`
   - `agents/sigma_job2.py`

There is also orchestration and audit infrastructure:
- `agents/aria/*`
- `agents/codec*`
- `agents/quill/quill.py`
- `agents/hawk/hawk.py`
- `agents/scout/scout.py`

These tracks are not fully aligned in purpose. The commodity-analysis track uses real downloaded futures returns. The FORGE track uses a simulated multi-agent environment and separate statistical evaluation.

---

## 1) Data sources

## Real-data sources

### `agents/miner/miner.py`
Primary implemented real-data source:
- `yfinance.download(...)`
- Tickers:
  - `CL=F` → `crude_oil_wti`
  - `GC=F` → `gold`
  - `ZC=F` → `corn`
  - `NG=F` → `natural_gas`
  - `HG=F` → `copper`

Date range parameters:
- `START_DATE = "2010-01-01"`
- `END_DATE_EXCLUSIVE = "2024-01-01"`
- Comment says this includes data through `2023-12-31`

Downloaded field:
- Adjusted close via `auto_adjust=True`
- Extracts `"Close"` column from returned dataframe

Output:
- `outputs/commodity_returns.csv`
- `outputs/data_passport.json`

### WRDS path in `agents/miner/miner.py`
There is a WRDS-first policy helper, but the implemented `run_miner_pipeline(..., source="wrds")` does **not** fetch commodity futures. It calls:
- `agents.miner.sources.wrds_src.fetch(config)`
- with config:
  - `kind = "ff_factors"`
  - `start = START_DATE`
  - `end = END_DATE_EXCLUSIVE`

That writes:
- `outputs/commodity_returns_wrds.csv`

This is actually Fama-French 5-factor daily data, not commodity returns.

### Additional source adapters
These exist but are not shown as used by the main commodity pipeline:
- `agents/miner/sources/fred_src.py`
  - FRED API via `fredapi.Fred`
  - default API key fallback is hardcoded in code
- `agents/miner/sources/sec_src.py`
  - SEC EDGAR search API and filing text fetch
- `agents/miner/sources/wrds_src.py`
  - WRDS adapters for:
    - CRSP daily returns
    - Compustat fundamentals
    - Fama-French 5-factor daily data

## Simulation data source

### `agents/forge/env.py`
Synthetic data are generated internally by the environment:
- initial price fixed at `100.0`
- price evolves from:
  - aggregate agent order flow
  - Gaussian noise
  - passive concentration drag

No external market data are used in the FORGE environment.

### `agents/forge/full_run.py` / `modal_run.py`
Simulation outputs are written to:
- `outputs/sim_results.json`

Each row contains:
- `concentration`
- `seed`
- `sharpe`
- `mean_reward`
- `n_episodes`

## Literature / text sources

### `agents/scout/scout.py`
Searches:
- Semantic Scholar API
- fallback arXiv API
- fallback hardcoded seed papers if no search results

Input:
- `PAPER.md`

Output:
- literature map markdown file (save path not fully shown in excerpt)

### `agents/quill/quill.py`, `agents/hawk/hawk.py`, `agents/codec*.py`
These consume:
- `PAPER.md`
- generated artifacts in `paper_memory/<run_id>/...`
- stats tables
- codec outputs
- paper drafts

---

## 2) Transforms and processing

## Commodity returns pipeline

### `agents/miner/miner.py`

#### Download and alignment
- Downloads each ticker separately
- Concatenates close series with `join="inner"`
  - only dates common to all series are retained
- Sorts by date

#### Return transform
- Computes daily log returns:
  - `np.log(close_df / close_df.shift(1)).dropna()`
- Renames columns from ticker symbols to commodity names
- Sets index name to `"date"`

#### Passport metadata
Writes metadata including:
- file hash
- row count
- intended and actual date range
- ticker mapping
- library versions
- roll convention and adjustment method both set to `"ratio_backward"`

Note: the code does not itself implement futures rolling logic; it records `"ratio_backward"` in the passport.

---

## Correlation analysis pipeline

### `agents/analyst/analyst.py`

Input:
- `outputs/commodity_returns.csv`

#### Load step
- Reads CSV with `parse_dates=["date"]`
- sets `date` as index
- sorts index
- drops any row with any missing value

#### Rolling pairwise correlations
Function:
- `compute_rolling_pairwise_corr(returns)`

For every pair of columns:
- computes rolling correlation with:
  - `window = 252`
  - `min_periods = 252`
- outputs long dataframe with columns:
  - `date`
  - `pair` as `"left__right"`
  - `correlation`
- drops missing rolling-correlation rows
- formats dates as `%Y-%m-%d`

#### Structural break detection
Function:
- `detect_breaks(rolling_corr)`

For each pair:
- sorts by date
- converts correlation series to `float64`, shape `(-1,1)`
- skips pair if fewer than `MIN_BREAK_SIZE * 2`
  - `MIN_BREAK_SIZE = 63`

Break model:
- `ruptures.Pelt(model="rbf", min_size=63).fit(y)`

Penalty:
- `pen = log(max(len(y), 2)) * var(y)`
- lower bounded by `1e-8`

Breakpoints:
- `model.predict(pen=float(max(pen, 1e-8)))`

For each breakpoint except final endpoint:
- stores:
  - `pair`
  - `break_date` = date at index `bp - 1`
  - `break_index` = integer breakpoint

#### DCC correlations
Function:
- `compute_dcc_correlations(returns)`

Step 1: univariate GARCH standardization for each asset
- scales returns by `100.0`
- fits:
  - `arch_model(series, mean="Zero", vol="GARCH", p=1, q=1, dist="normal")`
- extracts `fit.std_resid.dropna()`

Step 2: align standardized residuals
- concatenates all residual series with `join="inner"`
- drops missing rows
- resets columns to original return column names

Step 3: pairwise DCC fit
For each pair:
- extracts 2-column residual matrix
- calls `fit_dcc_pair(z_pair)`

##### DCC fitting details
- `qbar = np.cov(z_pair.T)`
- if covariance shape not `(2,2)`, fallback to identity
- adds `1e-10 * I` for stabilization

Optimization:
- objective: `_dcc_loglik`
- method: `SLSQP`
- initial guess: `[0.03, 0.95]`
- bounds:
  - `a in [1e-8, 0.95]`
  - `b in [1e-8, 0.95]`
- constraint:
  - `a + b <= 0.999`
- options:
  - `maxiter = 500`
  - `ftol = 1e-9`

If optimizer fails:
- fallback parameters:
  - `a = 0.03`
  - `b = 0.95`

Recursive update:
- `q_t = (1-a-b) * qbar + a * z_{t-1} z_{t-1}' + b * q_t`

Pairwise DCC output:
- time series of `rho_t = q_t[0,1] / sqrt(q11*q22)`
- clipped to `[-1, 1]`

##### DCC objective actually used
`_dcc_loglik` computes a penalized negative log-likelihood-like quantity:
- rejects invalid params with `1e9`
- constructs correlation matrix `r_t`
- forces diagonal entries `[0,0]` and `[1,1]` to `1.0`
- rejects nonpositive or nonfinite determinant with `1e9`
- accumulates:
  - `0.5 * (log(det(r_t)) + z_i' inv(r_t) z_i)`

This is minimized.

#### Summary table
Function:
- `build_summary(rolling_corr, regimes, dcc_corr)`

Outputs per pair:
- `mean_rolling_corr`
- `std_rolling_corr`
- `regime_breaks`
- `dcc_mean_corr`

If no regimes:
- sets `regime_breaks = 0`

Sorts by pair.

#### Files written
- `outputs/rolling_correlations.csv`
- `outputs/correlation_regimes.csv`
- `outputs/dcc_correlations.csv`
- `outputs/analyst_summary.csv`
- `outputs/analyst_passport.json`

---

## Writer / visualization / assembly transforms

### `agents/writer/writer.py`

Inputs:
- `outputs/analyst_summary.csv`
- `outputs/rolling_correlations.csv`
- `outputs/commodity_returns.csv`

#### Table 1
For each commodity return series:
- mean
- std with `ddof=1`
- min
- max
- skew
- kurtosis

Writes LaTeX:
- `outputs/table1_summary_stats.tex`

#### Table 2
Uses columns from analyst summary:
- pair
- mean rolling corr
- regime breaks
- mean DCC corr

Formats pair names for display and writes LaTeX:
- `outputs/table2_correlation_summary.tex`

#### Narrative
Builds 3 paragraphs from computed outputs:
1. sample description
2. strongest and weakest average-correlation pairs
3. average and max regime-break counts

Writes:
- `outputs/findings_narrative.txt`

### `agents/vizier/vizier.py`

Inputs:
- rolling correlations
- analyst summary
- commodity returns
- optional regimes file

#### Figure 1
- 2x5 subplot layout
- plots rolling correlations by pair
- overlays vertical dashed lines at break dates
- y-limits `[-1, 1]`

Outputs:
- `fig1_rolling_correlations.png`
- `fig1_rolling_correlations.pdf`

#### Figure 2
- builds symmetric matrix from `mean_rolling_corr`
- diagonal fixed to 1
- seaborn heatmap with annotations

Outputs:
- `fig2_correlation_heatmap.png`
- `fig2_correlation_heatmap.pdf`

#### Figure 3
- interprets input returns as daily log returns
- computes cumulative gross returns as `exp(cumsum(log returns))`
- plots on log y-scale

Outputs:
- `fig3_cumulative_returns.png`
- `fig3_cumulative_returns.pdf`

### `agents/assembler/assembler.py`

Inputs required:
- table1 tex
- table2 tex
- findings narrative
- fig1 png
- fig2 png

Builds LaTeX paper:
- abstract from first two narrative paragraphs, clipped to 150 words
- fixed title and bibliography
- methodology section text is hardcoded, not inferred dynamically

Outputs:
- `outputs/paper_draft.tex`
- `outputs/assembler_passport.json`

---

## 3) FORGE simulation transforms

## Environment mechanics: `agents/forge/env.py`

### Agents
Possible agents:
- `passive_gsci`
- `trend_follower`
- `mean_reversion`
- `liquidity_provider`
- `macro_allocator`
- `meta_rl`

### Observation
10-dimensional float vector:
1. `price_history[0]`
2. `price_history[1]`
3. `price_history[2]`
4. `price_history[3]`
5. `price_history[4]`
6. current volatility
7. passive concentration
8. agent portfolio value
9. agent cash
10. current step

### Action space
Discrete(3):
- `0 = hold`
- `1 = long`
- `2 = short`

### Passive concentration parameter
Allowed values only:
- `0.10`
- `0.30`
- `0.60`

### Episode length
Default:
- `252`

### Price update
After all agents submit actions:
- convert actions to flows
- compute `net_order_flow = sum(flow)`
- `concentration_risk = 1 + 6 * concentration^2`
- `noise ~ Normal(0, 0.006 * concentration_risk)`
- `flow_impact = 0.0003 * (1 + 5 * concentration^2)`
- `concentration_drag = 0.0002 * concentration^2`

Price update:
- `price *= 1 + flow_impact * net_order_flow + noise - concentration_drag`
- lower bounded at `1e-6`

### Volatility estimate
Uses trailing 20-step realized volatility from step returns:
- maintains rolling window of last 20 returns
- computes sample variance with `n-1` denominator
- volatility = sqrt(max(var, 0))

### Position and cash update
For each agent:
- position changes by flow, clipped to `[-50, 50]`
- cash reduced by `executed_flow * current_price`

### Reward function
For each agent each market step:
- `old_value = previous portfolio value`
- `new_value = cash + position * price`
- `pct = (new_value - old_value) / max(abs(old_value), 10000.0)`
- `rf_daily = 0.05 / 252`
- `crowding_cost = 0.00005 * concentration^2 * (abs(position) / max_position_units)`
- `volatility_penalty = 0.15 * concentration^2 * current_volatility`

Reward:
- `pct - rf_daily - crowding_cost - volatility_penalty`

This is the clearest explicit reward function in the codebase.

### Action-to-flow mapping
The function is truncated in the provided excerpt. Visible logic:
- if action `1`: return `1`
- rest not shown, but comments elsewhere imply:
  - `0=hold`
  - `1=long`
  - `2=short`
The exact implementation for action `2` is not visible in the provided text.

---

## 4) Agent policies and training

### `agents/forge/agents.py`

Policies:
- `PassiveGSCI.act` → always returns `1`
- `TrendFollower.act` → `1 if obs[0] > obs[4] else 2`
- `MeanReversion.act`
  - short if `obs[0] > obs[1] * 1.02`
  - long if `obs[0] < obs[1] * 0.98`
  - else hold
- `LiquidityProvider.act`
  - alternates long/short each call
- `MacroAllocator.act`
  - returns `1 if obs[6] < passive_threshold else 0`
- `MetaRL.act`
  - random integer in `[0,2]`

### `agents/forge/cem.py`
Cross-Entropy Method optimizer for MetaRL weights.

Parameters:
- `obs_dim = 10`
- `n_elite = 10`
- `population = 50`
- `noise = 0.1`

Weights shape:
- `(obs_dim, 3)`

Sampling:
- candidates drawn from Normal(mean, std)

Update:
- select top `n_elite` by score
- update mean and std from elites
- add `noise` to std

Action rule:
- logits = `obs @ weights`
- action = `argmax(logits)`

### `agents/forge/runner.py`

Runner parameters:
- `passive_concentration`
- `seed`
- `n_episodes = 500_000`
- `lookback_window = 252`

Seeds:
- sets both `np.random.seed(seed)` and `random.seed(seed)`

Environment:
- `CommodityFuturesEnv(passive_concentration=...)`

CEM:
- `CEM(obs_dim=10, n_elite=10, population=50, noise=0.1)`

#### Training loop
For each episode:
1. `candidates = cem.ask()`
2. For each candidate weight matrix:
   - run one episode
   - score = mean MetaRL step reward
3. `cem.tell(scores)`
4. append max score to `rewards_history`
5. every 100 episodes:
   - evaluate `cem.best()` on one episode
   - compute Sharpe from MetaRL step rewards

#### Episode scoring
`_run_single_episode(weights)`:
- resets liquidity provider state
- resets env
- iterates through PettingZoo AEC cycle
- for `meta_rl`:
  - appends current reward
  - action from `cem.act(obs, weights)`
- for `trend_follower`:
  - overrides class policy with custom momentum logic:
    - `lookback_idx = min(4, len(price_history)-1)`
    - `lookback_price = price_history[lookback_idx]`
    - `momentum_signal = current_price - lookback_price`
    - long if positive else short
- others use `_rule_policy`

Episode score returned to CEM:
- mean of MetaRL step rewards

#### Evaluation return series
`_run_episode_returns(best_weights)`:
- runs one episode
- collects MetaRL rewards only
- returns list of per-step MetaRL rewards

#### Sharpe computation
`sharpe(step_returns)`:
- if fewer than 2 returns, return 0
- mean/std * `sqrt(252)`
- uses population std default from `np.std()` (ddof=0)

#### Final reported results
- concentration
- seed
- mean_reward = mean of MetaRL step rewards from one evaluation episode
- sharpe = Sharpe of MetaRL step rewards from one evaluation episode
- n_episodes
- rewards_history
- momentum_lookback_steps = 252
- momentum_signal = `'price_level_difference_over_lookback'`

---

## 5) Parameters/defaults explicitly present

## Commodity-analysis parameters
From `agents/miner/miner.py` and `agents/analyst/analyst.py`:
- tickers: 5 futures contracts
- date range: 2010-01-01 to 2023-12-31 inclusive by end-exclusive setting
- rolling correlation window: `252`
- minimum break size: `63`
- PELT model: `"rbf"`
- DCC univariate GARCH:
  - mean `"Zero"`
  - vol `"GARCH"`
  - `p=1`, `q=1`
  - dist `"normal"`
- DCC optimizer:
  - method `"SLSQP"`
  - init `[0.03, 0.95]`
  - bounds `[(1e-8,0.95),(1e-8,0.95)]`
  - constraint `a+b<=0.999`
  - `maxiter=500`
  - `ftol=1e-9`

## FORGE parameters
From `agents/forge/*`:
- passive concentration values: `0.10`, `0.30`, `0.60`
- seeds in full sweep: `1337`, `42`, `9999`
- episode length: `252`
- training episodes default: `500_000`
- CEM:
  - obs_dim `10`
  - n_elite `10`
  - population `50`
  - noise `0.1`
- max position units: `50.0`
- initial cash: `10_000.0`
- initial price: `100.0`
- volatility window: `20`
- risk-free daily subtraction: `0.05 / 252`
- crowding cost coefficient: `0.00005`
- volatility penalty coefficient: `0.15`
- price noise scale base: `0.006`
- flow impact coefficient base: `0.0003`
- concentration drag coefficient base: `0.0002`

## SIGMA Job 2 parameters
Visible in `agents/sigma_job2.py`:
- Newey-West HAC maxlags: `4`
- bootstrap resamples: `1000`
- deflated Sharpe `n_trials = 6`
- Bonferroni `n_tests = 7`

---

## 6) Reward function

## Explicit reward function in code
The only explicit environment reward function is in `agents/forge/env.py`:

For each agent at each market step:
\[
\text{reward} =
\frac{\text{new\_value} - \text{old\_value}}{\max(|\text{old\_value}|, 10000)}
- \frac{0.05}{252}
- 0.00005 \cdot c^2 \cdot \frac{|position|}{50}
- 0.15 \cdot c^2 \cdot volatility
\]
where `c = passive_concentration`.

## Optimization target actually used
In `agents/forge/runner.py`, CEM does **not** optimize Sharpe directly. It optimizes:
- **mean MetaRL step reward within an episode**

Sharpe is only printed/evaluated periodically and in final results.

## DCC objective
`agents/analyst/analyst.py` also contains an optimization objective:
- `_dcc_loglik(...)`
- minimized over DCC parameters `(a,b)`

This is not a reward function for RL, but it is the fitting criterion for DCC estimation.

---

## 7) Evaluation methods

## Commodity-analysis evaluation
There is no hypothesis-testing evaluation in `analyst.py`. Evaluation is descriptive:
- rolling correlation means and stds
- number of detected breakpoints
- mean DCC correlation by pair

Outputs summarized in:
- `analyst_summary.csv`

## FORGE evaluation
### `agents/forge/runner.py`
Evaluation metrics:
- MetaRL per-step reward series
- annualized Sharpe of MetaRL reward series from one episode
- mean reward from one episode

### `agents/forge/full_run.py`
Runs all combinations:
- concentrations `[0.10, 0.30, 0.60]`
- seeds `[1337, 42, 9999]`

Stores scenario-level results in `outputs/sim_results.json`.

## Econometric evaluation
### `agents/sigma_job2.py`
Uses `outputs/sim_results.json` and computes:
- Newey-West HAC t-test on `mean_reward`
- GARCH(1,1) on `mean_reward * 100`
- bootstrap CI on mean reward
- deflated Sharpe
- Markov regime model
- Fama-MacBeth regression
- Bonferroni correction across 7 p-values

Because the file is truncated, only some implementations are fully visible:
- `_newey_west_ttest`
- `_garch_11`
- `_bootstrap_ci`
- start of `_deflated_sharpe`

The run method clearly calls:
- `_markov_regime`
- `_fama_macbeth`
- `_bonferroni`

Outputs:
- `sharpe_summary.csv`
- `ttest_results.csv`
- `garch_results.csv`
- `fama_macbeth_results.csv`
- `stats_summary.tex`
- `library_versions.json`

---

## 8) Undocumented / implicit / inconsistent steps

## Commodity pipeline undocumented or implicit steps

### Futures rolling is not implemented
`miner.py` writes passport fields:
- `"roll_convention": "ratio_backward"`
- `"adjustment_method": "ratio_backward"`

But the actual data retrieval is just:
- `yfinance.download(..., auto_adjust=True)`
- close extraction

No explicit futures contract roll construction appears in the shown code.

### Inner join synchronizes all assets
The commodity panel keeps only dates present for all five series:
- `pd.concat(..., join="inner")`

This can materially reduce sample size, but is not discussed in code comments beyond implementation.

### Missing data are dropped twice
- returns construction drops first NA from differencing
- analyst load drops any row with any NA across columns

### DCC is pairwise, not multivariate panel DCC
The code fits DCC separately for each pair, not one multivariate DCC across all assets.

### Standardized residual alignment may shorten sample
Residuals from separate GARCH fits are concatenated with `join="inner"`.

### Break detection is on rolling correlations, not raw returns
Structural breaks are detected on the derived rolling-correlation series.

---

## FORGE pipeline undocumented or implicit steps

### Trend follower implementation mismatch inside runner
There are two trend-following definitions:
- `TrendFollower.act(obs)` in `agents.py`: compares `obs[0]` vs `obs[4]`
- `_run_single_episode` in `runner.py`: overrides trend logic using `self.env._price_history`

So the class policy is not consistently used during training episodes.

### Claimed 12-month momentum is not actually 252-step lookback in observation
Comments say:
- `MOMENTUM_LOOKBACK_WINDOW = 252`
- `lookback_window = 252`
- “12-month momentum”

But the observation only contains 5 price-history values, and the runner uses:
- `lookback_idx = min(4, len(price_history)-1)`

So the effective momentum signal shown in code is based on at most a 5-point stored history, not 252 historical prices.

### MetaRL class itself is unused for policy logic
`MetaRL.act` returns random action, but runner uses:
- `self.cem.act(obs, weights)`
for `meta_rl`.
So `MetaRL` object is instantiated but not used for actual decision-making.

### Evaluation uses one episode only
Final `results()` computes Sharpe and mean reward from a single episode using best weights, not an average over multiple evaluation episodes.

### Sigma Job 2 treats scenario-level mean rewards as return series
`returns = sim_df["mean_reward"].to_numpy(dtype=float)`

Thus econometric tests are run on the 9 scenario-level mean rewards from concentration-seed combinations, not on within-episode time series.

### Seed derivation in Sigma Job 2 is indirect
Bootstrap seed is derived from:
- `pap_lock.pap_sha256`
- first 8 hex chars converted to int
not directly from the PAP seed list.

### WRDS-first policy conflicts with actual commodity pipeline
`ARIA` routes `MINER` to `"wrds"` server, and `miner.py` has WRDS-first helpers, but the default standalone `main()` uses yfinance commodity downloads. The WRDS branch shown fetches Fama-French factors, not commodity returns.

---

## 9) File-by-file forensic summary

## `agents/miner/miner.py`
Actually does:
- download 5 commodity futures adjusted close series from Yahoo Finance
- align on common dates
- compute daily log returns
- save CSV and passport

Also contains:
- optional WRDS/yfinance source selection logic
- WRDS branch that fetches FF5 factors instead of commodity returns

## `agents/analyst/analyst.py`
Actually does:
- read commodity returns CSV
- compute 252-day rolling pairwise correlations
- detect changepoints in rolling correlations using PELT/RBF/min segment 63
- fit pairwise DCC correlations using univariate GARCH standardized residuals
- summarize pair-level mean/std/break counts/DCC mean
- write outputs and passport

## `agents/writer/writer.py`
Actually does:
- create summary-statistics LaTeX table
- create correlation-summary LaTeX table
- generate 3-paragraph narrative from computed outputs
- write passport

## `agents/vizier/vizier.py`
Actually does:
- plot rolling correlations with break dates
- plot average-correlation heatmap
- plot cumulative returns from log returns
- write passport

## `agents/assembler/assembler.py`
Actually does:
- require writer/vizier outputs
- build fixed-structure LaTeX paper draft
- abstract is clipped from narrative paragraphs
- write passport

## `agents/forge/env.py`
Actually does:
- simulate a 6-agent commodity market with one synthetic price
- update price from order flow, concentration-scaled noise, and drag
- maintain positions/cash/portfolio values
- assign per-step rewards penalized by rf, crowding, volatility

## `agents/forge/runner.py`
Actually does:
- train MetaRL weights with CEM
- optimize mean MetaRL reward
- report Sharpe only as evaluation metric
- run one evaluation episode for final metrics

## `agents/sigma_job1.py`
Actually does:
- parse required sections from `PAPER.md`
- ask OpenAI for strict JSON PAP, or fallback to direct extraction
- commit PAP JSON and SHA256 to sqlite tables

## `agents/sigma_job2.py`
Actually does:
- load `outputs/sim_results.json`
- run econometric battery on scenario-level `mean_reward`
- save CSV/TeX summaries and library versions
- write result flag

## `agents/codec/codec.py`, `agents/codec_pass1.py`, `agents/codec_pass2.py`
Actually do:
- Pass 1: summarize codebase behavior from code text only
- Pass 2: reimplement methodology from `PAPER.md` only
- compare term overlap and numeric claims
- classify PASS/WARN/FAIL based on mismatch report text

---

## 10) Reward function / evaluation method requested explicitly

## Reward function
- **FORGE RL reward**: per-step portfolio return minus daily rf minus crowding cost minus volatility penalty, all concentration-dependent.
- **CEM optimization target**: mean MetaRL step reward over one episode.
- **DCC fitting objective**: minimized negative log-likelihood-like function over `(a,b)`.

## Evaluation method
- **Commodity track**: descriptive summary of rolling correlations, break counts, and DCC means.
- **FORGE track**:
  - annualized Sharpe of MetaRL step rewards from one episode
  - mean reward from one episode
  - full sweep over 3 concentrations × 3 seeds
- **SIGMA Job 2**:
  - HAC t-test
  - GARCH(1,1)
  - bootstrap CI
  - deflated Sharpe
  - Markov regime model
  - Fama-MacBeth
  - Bonferroni correction

---

## 11) Main inconsistencies visible from code alone

1. **Commodity real-data analysis and FORGE simulation are separate pipelines.**
2. **WRDS branch in miner does not fetch commodity returns; it fetches FF5 factors.**
3. **“12-month momentum” comments do not match the visible 5-price-history implementation.**
4. **CEM optimizes mean reward, not Sharpe, despite Sharpe prominence in outputs/comments.**
5. **Sigma Job 2 tests scenario-level summary rewards, not episode-level or step-level returns.**
6. **Assembler hardcodes methodology prose rather than deriving it from actual code outputs.**

These are directly inferable from the provided code text.