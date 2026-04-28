<div align="center">

```
██████╗  █████╗ ██████╗ ███████╗██████╗       ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗      ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
██████╔╝███████║██████╔╝█████╗  ██████╔╝█████╗█████╗  ██║   ██║██████╔╝██║  ███╗█████╗
██╔═══╝ ██╔══██║██╔═══╝ ██╔══╝  ██╔══██╗╚════╝██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
██║     ██║  ██║██║     ███████╗██║  ██║      ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
╚═╝     ╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝      ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
```

**The autonomous research pipeline that commits to its hypothesis before seeing the data.**

*From research spec → literature → data → simulation → statistics → audit → paper.*
*Enforced by SQL. Unable to p-hack. By design.*

<br/>

![Tests](https://img.shields.io/badge/tests-11%20passing-brightgreen?style=flat-square)
![Python](https://img.shields.io/badge/python-3.11+-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Model](https://img.shields.io/badge/built%20with-OpenAI%20Codex-8b5cf6?style=flat-square)
![DB](https://img.shields.io/badge/state-SQLite%20WAL-f97316?style=flat-square)
![Sim](https://img.shields.io/badge/env-PettingZoo%20AEC-14b8a6?style=flat-square)
![GPU](https://img.shields.io/badge/compute-Modal%20GPU-ec4899?style=flat-square)

</div>

---

## What Is Paper-Forge?

Paper-Forge is an autonomous 8-agent pipeline that takes a research specification (`PAPER.md`) as input and produces a fully auditable, reproducible finance research paper as output.

Every integrity guarantee is **structural** — enforced by the architecture, not by asking researchers to behave honestly.

> **North Star:** Make it structurally impossible to produce a finance research paper that has not committed its hypothesis before seeing results, documented its data construction with cryptographic precision, and proven bidirectionally that the paper and the code say the same thing.

**You edit one file. The pipeline does the rest.**

---

## The Gate That Makes P-Hacking Architecturally Impossible

```sql
-- FORGE cannot start unless this query returns exactly one row.
-- ForgeGateError is raised and the pipeline halts. No env-var overrides. No workarounds.

SELECT 1
FROM   pap_lock
WHERE  run_id            = ?
  AND  locked_at         IS NOT NULL   -- hypothesis committed to SQLite
  AND  forge_started_at  IS NULL;      -- simulation has not started
```

Your hypothesis is SHA-256 hashed and committed to a SQLite `pap_lock` table **before FORGE runs a single episode**. This is a SQL constraint — Python cannot bypass it.

---

## Full Pipeline

```
┌─────────────┐
│  PAPER.md   │  ← The only file you write
└──────┬──────┘
       │
       ▼
   ┌───────┐     ┌───────┐     ┌───────┐
   │ ARIA  │────▶│ SCOUT │────▶│ MINER │    Phase 1-2: Literature + Data
   └───────┘     └───────┘     └───────┘
       │                           │
       ▼                           ▼
  ┌──────────┐              DataPassport
  │ SIGMA    │              SHA-256 signed
  │  JOB 1  │  ← Commits hypothesis, seals pap_lock
  └────┬─────┘
       │  SQL gate enforced ──────────────────────────────────┐
       ▼                                                       │
   ┌───────┐                                                   │
   │ FORGE │  500k episodes · PettingZoo · Modal GPU           │
   └───┬───┘                                              BLOCKED if
       │                                               hypothesis not locked
       ▼
  ┌──────────┐
  │  SIGMA   │  6-test statistical battery
  │  JOB 2  │  HAC · GARCH · Bonferroni · Fama-MacBeth · Markov · DCC-GARCH
  └────┬─────┘
       │
       ▼
  ┌─────────┐     ┌─────────┐
  │  CODEC  │────▶│  FIXER  │  ← Auto-patches code mismatches, re-runs SIGMA JOB 2
  └────┬────┘     └─────────┘
       │
       ▼
  ┌──────┐
  │ HAWK │  Reviews CSVs + JSON only. Never reads LaTeX.
  └──┬───┘  Routes mandatory fixes back to FORGE / SIGMA / MINER / FIXER
     │       Max 3 revision cycles. Halts pipeline if unresolved.
     │
     │  approved_for_quill: true ──────────────────────────────┐
     │                                                          │
     │  approved_for_quill: false ─── pipeline halts 🛑        │
     │                                                          ▼
     │                                                     ┌───────┐
     └────────────────────────────────────────────────────▶│ QUILL │
                                                           └───┬───┘
                                                               │
                                                               ▼
                                                      paper_draft_v*.tex
```

---

## Agent Reference

| Agent | Phase | What it does | Halts pipeline? |
|-------|-------|-------------|----------------|
| **ARIA** | Throughout | Orchestrator. State machine. Reads **only typed flags** from `state.db`. Never reads artifact content. | Coordinator |
| **SCOUT** | 1 | Searches 40 papers on Semantic Scholar + arXiv. Ranks 1–10. Reads top 8–10 in full. Writes `literature_map.md`. | No |
| **MINER** | 2 | Downloads data per `PAPER.md` spec. Constructs series. Produces `DataPassport` with SHA-256 checksums per file. | No |
| **SIGMA JOB 1** | 3 — *before data* | Writes complete Pre-Analysis Plan from `PAPER.md`. Commits hypothesis. Seals `pap_lock`. Sets SQL gate. | **Gate** |
| **FORGE** | 4 — *after PAP lock* | Multi-agent PettingZoo market simulation. 500k episodes on Modal GPU. CEM/PPO optimizer. | **Gate** |
| **SIGMA JOB 2** | 5 — *after FORGE* | Runs 6-test statistical battery against `sim_results.json`. Writes all stats CSVs to `stats_tables/`. | No |
| **CODEC** | 6 | Bidirectional code audit via 2 isolated subprocess passes. Writes `codec_mismatch.md`. | **Yes — FAIL** |
| **FIXER** | 7 | Reads CODEC mismatch. LLM auto-patches fixable items. Re-runs MINER + SIGMA JOB 2 to verify fix held. | **Yes — escalate** |
| **HAWK** | 8 — *before QUILL* | Research quality review from CSVs/JSON only. Never sees LaTeX. Routes fixes. Max 3 cycles. | **Yes — reject** |
| **QUILL** | 9 — *only if HAWK approved* | Deterministic LaTeX formatter. Reads verified stats CSVs. No LLM prose generation. Never overwrites prior draft. | No |

---

## SIGMA JOB 1 vs SIGMA JOB 2

These are completely different in timing, purpose, and inputs.

|  | SIGMA JOB 1 | SIGMA JOB 2 |
|--|-------------|-------------|
| **Runs** | Before FORGE | After FORGE |
| **Sees simulation data?** | ❌ Never | ✅ Yes |
| **Reads** | `PAPER.md` + DataPassport metadata only | `sim_results.json` + PAP |
| **Purpose** | **Lock the hypothesis** | **Test the hypothesis** |
| **Output** | `pap.md` + sealed `pap_lock` row | 6 stats CSVs in `stats_tables/` |
| **What happens if missing** | FORGE blocked by SQL gate | CODEC and HAWK have nothing to check |
| **Can be re-run?** | ❌ Re-running breaks pre-registration | ✅ FIXER re-runs after code fixes |

**SIGMA JOB 2 runs this 6-test battery (all pre-specified in `PAPER.md` before data is seen):**

```
1. Two-tailed t-test with Newey-West HAC correction (4 lags)
2. Bonferroni correction across all simultaneous tests
3. GARCH(1,1) volatility model          [arch library, p=1, q=1, Normal]
4. Fama-MacBeth two-pass regression     [linearmodels]
5. Markov regime switching detection    [statsmodels, k_regimes=2]
6. DCC-GARCH cross-asset correlation    [arch]
```

---

## CODEC — Bidirectional Code Audit

CODEC proves the code does what the paper claims **and** the paper describes what the code does. Two completely isolated passes.

```
PASS 1 — Code Reader                     PASS 2 — Spec Reader
──────────────────────────────────       ──────────────────────────────────
Input:  source code only                 Input:  PAPER.md methodology only
Cannot see: PAPER.md ✗                   Cannot see: any code ✗
API key: OPENAI_API_KEY                  API key: OPENAI_API_KEY_PASS2

Output: codec_spec.md                    Output: reimplementation from spec
"What the code actually does"            KS-test vs sim_results.json
                                         (pass threshold: KS stat < 0.05)
         │                                             │
         └──────────────────┬────────────────────────┘
                            ▼
                   codec_mismatch.md
         FAIL items ──► FIXER    PASS ──► HAWK
```

Each pass runs as a **subprocess** with a separate API key. The test `test_codec_passes_are_isolated` verifies zero context leakage between passes.

---

## HAWK — Why It Runs Before QUILL

> ⚠️ HAWK runs **before** QUILL. Most people assume the opposite. This is the most important ordering decision in the pipeline.

**Why:** A reviewer reading prose cannot detect weak research dressed in fluent language. Programmatic checks on raw statistical outputs cannot be fooled by surface features. HAWK checks the research first. QUILL only formats what passes.

**HAWK reads:** `pap.md`, `ttest_results.csv`, `primary_metric.csv`, `seed_consistency.csv`, `codec_mismatch.md`, `sim_results.json`

**HAWK never reads:** any `.tex`, `.pdf`, or prose

**Six programmatic checks:**

| Check | Source file | Hard block? |
|-------|------------|-------------|
| Finding matches pre-registered direction | `pap.md` vs `primary_metric.csv` | ✅ Yes |
| p-value clears Bonferroni threshold | `ttest_results.csv` | ✅ Yes |
| Seed consistency: `consistent: True` | `seed_consistency.csv` | ✅ Yes |
| CODEC clean: zero FAIL items | `codec_mismatch.md` | ✅ Yes |
| Minimum effect size met | `primary_metric.csv` | ✅ Yes |
| `n_episodes >= 500000` | `sim_results.json` | ⚠️ Warning only |

If HAWK rejects, it routes mandatory items back to the correct agent. After 3 cycles without `approved_for_quill: true`, the pipeline halts.

---

## QUILL — What It Does and Does Not Write

QUILL is a **deterministic LaTeX formatter**. It calls no LLM. It generates no prose.

**QUILL writes:**
- Title, authors, date (from `PAPER.md`)
- Abstract: 3 sentences — hypothesis / primary result with exact numbers / one limitation
- Methodology: rendered mechanically from `pap.md`
- Findings: one bullet per result, exact CSV value + what it means
- One LaTeX table per CSV in `stats_tables/`
- Bibliography from `references.bib` if present

**QUILL does not write:** Introduction, Related Work, Discussion, Conclusion. These require human judgment. The scaffold is the foundation — the writing is yours.

---

## File Structure and Skills Files

```
paper-forge/
│
├── PAPER.md                          ← THE ONLY FILE YOU EDIT TO START NEW RESEARCH
├── run_aria_pipeline.py              ← Entry point
├── state.db                          ← SQLite WAL: all phase status, pap_lock, full audit trail
│
├── agents/
│   ├── aria/
│   │   ├── aria.py                   ← Orchestrator state machine (never edit routing here)
│   │   └── routing_config.py         ← Add new agents with one line
│   │
│   ├── scout/scout.py
│   │
│   ├── miner/
│   │   ├── miner.py                  ← Edit data fetch logic here for new research
│   │   └── sources/
│   │       ├── wrds_src.py           ← Production: WRDS futures/equity data
│   │       └── yfinance_src.py       ← Dev proxy: edit tickers here
│   │
│   ├── sigma/
│   │   ├── sigma_job1.py             ← PAP lock — never modify the locking logic
│   │   └── sigma_job2.py             ← Edit statistical tests here for new research
│   │
│   ├── forge/
│   │   ├── env.py                    ← PettingZoo environment — edit for new simulation
│   │   ├── runner.py                 ← CEM/PPO training loop
│   │   ├── cem.py                    ← Cross-entropy method optimizer
│   │   └── modal_run.py              ← GPU dispatch
│   │
│   ├── codec/
│   │   ├── codec.py
│   │   ├── pass1_skills.md           ← Instructs Pass 1: extract state space, rewards from code
│   │   └── pass2_skills.md           ← Instructs Pass 2: "You have not seen the codebase."
│   │
│   ├── fixer/fixer.py
│   │
│   ├── hawk/
│   │   ├── hawk.py
│   │   └── hawk_skills.md            ← HAWK review rubric, routing rules, JF standards
│   │
│   └── quill/
│       ├── quill.py
│       └── quill_skills.md           ← LaTeX rendering rules, versioning behavior
│
├── outputs/
│   └── data_passport.json            ← SHA-256 signed data lineage
│
├── paper_memory/{run_id}/            ← All output per run (gitignored)
│   ├── literature_map.md
│   ├── codec_spec.md
│   ├── codec_mismatch.md
│   ├── fixer_report.md
│   ├── hawk_review_v*.md
│   ├── hawk_routing_v*.json
│   ├── stats_tables/
│   │   ├── primary_metric.csv
│   │   ├── ttest_results.csv
│   │   ├── sharpe_summary.csv
│   │   ├── garch_results.csv
│   │   ├── fama_macbeth_results.csv
│   │   ├── dcc_garch_results.csv
│   │   ├── seed_consistency.csv      ← Read this first. If False, finding is invalid.
│   │   └── library_versions.json    ← Pinned versions for exact replication
│   ├── paper_draft_v1.tex            ← Never overwritten
│   └── paper_draft_v2.tex            ← After HAWK revision cycle
│
└── tests/
    ├── test_pipeline.py
    ├── test_quality_gates.py
    └── test_runtime_hardening.py
```

### The `*_skills.md` Files

Every agent that makes an LLM call has a companion `*_skills.md` file. These are the **agent behavior contracts** — they define what the agent is allowed to do, what it must output, and what it must refuse.

| File | What it controls |
|------|-----------------|
| `pass1_skills.md` | CODEC Pass 1: extract state space, reward functions, hyperparameters from code. Refuse to read PAPER.md. |
| `pass2_skills.md` | CODEC Pass 2: first line is "You have not seen the codebase." Reconstruct method from paper text only. |
| `hawk_skills.md` | HAWK review rubric: JF/RFS/JFE standards. Route by severity. Never comment on prose quality. |
| `quill_skills.md` | LaTeX rendering rules. No prose generation. Every number must trace to a CSV. Never overwrite prior revision. |

**To change how an agent behaves — edit its `*_skills.md`.** Do not touch the Python unless you are changing data flow.

---

## Quick Start

```bash
git clone https://github.com/gouravsalottra/paper-forge-private
cd paper-forge-private

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env                            # add OPENAI_API_KEY
export PAPER_FORGE_MINER_SOURCE=yfinance        # dev mode — no WRDS needed
export PAPER_FORGE_FORGE_EPISODES=500           # fast smoke test

python run_aria_pipeline.py
```

**What you'll see:**
```
RUN_ID: pf-live-20260422-143201
▶ Running [SCOUT]...
▶ Running [MINER]...
🔒 PAP committed. SHA-256: 3f8a91b2...
▶ Running [FORGE]...           # SQL gate confirmed
▶ Running [SIGMA_JOB2]...
▶ Running [CODEC]...
==================================================
HAWK review cycle 1/3
==================================================
HAWK recommendation: MINOR_REVISION
▶ Running [QUILL] draft v2...
HAWK ACCEPTED on cycle 2.
Output: paper_memory/pf-live-20260422-143201/paper_draft_v2.tex
```

**Resume a halted run from any phase:**
```bash
python run_aria_pipeline.py --resume pf-live-20260422 --from CODEC
# PAP lock is preserved — hypothesis commitment unchanged
```

**Verify Modal GPU before production (do this first):**
```bash
modal profile list                                  # must show authenticated workspace
modal run agents/forge/modal_run.py --n-episodes 1000
modal app list                                      # must show a job appearing
# Only then run production:
PAPER_FORGE_FORGE_EPISODES=500000 python run_aria_pipeline.py
```

**Run tests:**
```bash
pytest -q
# 11 passed in 4.32s
```

---

## Running Your Own Finance Research

> Paper-Forge is research infrastructure, not a single-topic tool. Here is exactly what to change for any new empirical finance question.

### The One-File Rule

**Edit `PAPER.md` only.** Every agent reads from it. Nothing commits until SIGMA JOB 1 seals it. For most new research questions, you also update MINER (data sources) and FORGE (environment). Everything else — ARIA, CODEC, FIXER, HAWK, QUILL — stays unchanged.

### `PAPER.md` Format

```markdown
## Topic
[Research topic in one sentence]

## Hypothesis
[Exactly what you expect to find. Be specific: direction, magnitude, conditions.
This text is SHA-256 hashed and locked before any data is seen.
You cannot change it after SIGMA JOB 1 runs.]

## Primary Metric
[The single number that answers the question.
Be precise about how it is computed — SIGMA JOB 2 must produce exactly this.]

## Statistical Tests
[List every test. Include: library name, version, parameters, correction method.
Every test listed here must appear in SIGMA JOB 2 output or HAWK blocks QUILL.]

## Minimum Effect Size
[Smallest effect worth caring about economically.
Results below this are reported as insignificant regardless of p-value.]

## Seed Policy
seeds = [1337, 42, 9999]
[Finding only valid if it holds qualitatively across ALL seeds listed here.
One seed disagrees → finding_valid: false → paper reports the failure.]

## Data Sources
[Where MINER fetches data. WRDS symbols for production, yfinance symbols for dev.
Specify: tickers, date range, roll convention if futures, any transformations.]

## Exclusions
[Data filtering rules: minimum history length, outlier thresholds, event windows.]

## Pre-Analysis Plan Status
UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs.
```

---

## Worked Example: GSCI Sector Rotation with RL

**Research question:** Can a PPO reinforcement learning agent achieve risk-adjusted outperformance over the GSCI by dynamically rotating across commodity ETF sub-sectors?

### What Changes

| File | Change | Why |
|------|--------|-----|
| `PAPER.md` | Full rewrite (below) | New hypothesis, metric, tests, data |
| `agents/miner/sources/yfinance_src.py` | New tickers: XLE, GLD, DBA, COPX, PDBC, GSG | Different data |
| `agents/forge/env.py` | New environment: 5 ETF sectors, monthly rebalancing, PPO reward | Different simulation |
| `agents/forge/runner.py` | Switch to Stable Baselines 3 PPO, add SHAP post-training | Different optimizer |
| `agents/sigma/sigma_job2.py` | Add out-of-sample Sharpe vs benchmarks, drawdown comparison, SHAP | Different tests |

### What Does NOT Change

ARIA, SCOUT, SIGMA JOB 1 (PAP lock), CODEC, FIXER, HAWK, QUILL.
The entire integrity infrastructure is research-agnostic.

---

### New `PAPER.md`

```markdown
## Topic
Reinforcement Learning Agents for Dynamic Commodity Sector Rotation:
Outperforming the Goldman Sachs Commodity Index

## Hypothesis
A PPO reinforcement learning agent trained on 2004–2018 monthly rebalancing data
achieves statistically significant risk-adjusted outperformance over the GSCI total
return index on out-of-sample data 2019–2024, with a lower maximum drawdown during
the 2020 COVID commodity shock and the 2022 energy crisis.

## Primary Metric
Out-of-sample annualized Sharpe ratio differential: RL agent minus GSCI (2019–2024).
Positive differential required. Computed on monthly total returns.

## Statistical Tests
1. One-tailed t-test on monthly excess returns (RL vs GSCI), p < 0.05, NW-HAC (3 lags)
2. Bonferroni correction across 4 benchmark comparisons (GSCI, BCOM, EW, momentum)
3. Maximum drawdown comparison: RL agent vs GSCI at 2020-03 and 2022-03 event windows
4. SHAP feature importance: attribution of allocation decisions to state variables
5. Walk-forward validation: 3-year rolling train/test to detect strategy decay
6. Transaction cost sensitivity: repeat primary test at 0bp, 10bp, 30bp, 50bp

## Minimum Effect Size
Sharpe differential >= +0.15 annualized. Smaller outperformance is not economically
meaningful after implementation costs.

## Seed Policy
seeds = [1337, 42, 9999]
Policy must show positive Sharpe differential on all 3 seeds to be valid.

## Data Sources
# Dev mode (yfinance)
ETFs:       XLE (energy), GLD (gold), DBA (agriculture), COPX (copper), PDBC (broad ex-energy)
Benchmark:  GSG (GSCI proxy)
Macro:      UUP (dollar), ^VIX (volatility), ^VIX3M (term structure)
# Production (WRDS)
GSCI Total Return Index, Bloomberg Commodity Index, Fama-French factors

## State Space (19 dimensions)
- 12-month trailing momentum per sector (5)
- 1-month trailing return per sector (5)
- US Dollar Index level + 3-month change (2)
- VIX level + VIX term structure slope (2)
- Roll yield proxy per sector (5)

## Action Space
Portfolio weight vector over 5 sectors.
Constraint: no single sector > 40%.
Rebalancing: monthly.

## Reward Function
risk_adjusted_excess = (portfolio_return - gsci_return) / portfolio_volatility
transaction_cost_penalty = 10bp * abs(weight_change).sum()

## Exclusions
Exclude months where any ETF has fewer than 12 months of history.
Evaluation window (never touched during training): 2019-01-01 to 2024-12-31.

## Pre-Analysis Plan Status
UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs.
```

---

### MINER Changes

Edit `agents/miner/sources/yfinance_src.py`:

```python
SECTOR_ETFS = {
    "energy":          "XLE",
    "gold":            "GLD",
    "agriculture":     "DBA",
    "copper":          "COPX",
    "broad_ex_energy": "PDBC",
}
BENCHMARKS = {
    "gsci_proxy":  "GSG",
    "bcom_proxy":  "DJP",
    "dollar":      "UUP",
    "vix":         "^VIX",
    "vix3m":       "^VIX3M",
}
TRAIN_START, TRAIN_END = "2004-01-01", "2018-12-31"
EVAL_START,  EVAL_END  = "2019-01-01", "2024-12-31"
```

### FORGE Changes

Replace `agents/forge/env.py` with a single-agent Gym environment:

```python
class CommodityRotationEnv(gym.Env):
    """
    Replaces the multi-agent PettingZoo market environment.
    State:  19-dimensional vector per PAPER.md state space
    Action: 5-dimensional softmax weight vector (constrained: max 0.4 per sector)
    Reward: risk-adjusted excess return vs GSCI minus transaction cost penalty
    """
    def __init__(self, returns_df, benchmark_series, tc_bps=10):
        self.observation_space = spaces.Box(low=-np.inf, high=np.inf, shape=(19,))
        self.action_space = spaces.Box(low=0.0, high=0.4, shape=(5,))
        self.tc_bps = tc_bps / 10000
        ...
```

Switch `runner.py` to PPO:
```python
from stable_baselines3 import PPO
model = PPO("MlpPolicy", env, verbose=1, learning_rate=3e-4, n_steps=2048)
model.learn(total_timesteps=n_episodes)
```

### SIGMA JOB 2 Changes

Add to `agents/sigma/sigma_job2.py`:

```python
def run_rl_rotation_battery(eval_returns, gsci_returns, policy_model, state_data):
    results = {}

    # 1. Primary: out-of-sample Sharpe differential (NW-HAC)
    excess = eval_returns["rl"] - eval_returns["gsci"]
    results["ttest_results"] = newey_west_ttest(excess, lags=3)

    # 2. Benchmark comparisons
    results["benchmark_comparison"] = compare_all_benchmarks(
        eval_returns, benchmarks=["gsci", "bcom", "equal_weight", "momentum"]
    )

    # 3. Drawdown at event windows
    results["drawdown_events"] = compare_drawdowns(
        eval_returns, events=["2020-03", "2022-03"]
    )

    # 4. SHAP feature attribution
    results["shap_attribution"] = compute_shap_values(policy_model, state_data)

    # 5. Walk-forward validation
    results["walk_forward"] = rolling_train_test(returns_df, train_years=14, test_years=3)

    # 6. Transaction cost sensitivity
    results["tc_sensitivity"] = {
        tc: run_backtest(eval_returns, tc_bps=tc) for tc in [0, 10, 30, 50]
    }
    return results
```

---

## Five Integrity Layers

| Layer | Agent | What it enforces |
|-------|-------|-----------------|
| 🔒 **PAP Lock** | `SIGMA_JOB1` | Hypothesis committed to SQLite before any simulation. SHA-256 signed. FORGE SQL gate enforces this — not Python. |
| 🔍 **DataPassport** | `MINER` | Every input file SHA-256 signed. Download timestamp, tickers, row counts, acknowledged deviations all recorded. Byte-level hash verified by test. |
| 📋 **CODEC Audit** | `CODEC` | Two isolated subprocess passes — one reads code, one reads spec. Separate API keys. Zero context leakage. KS-test on output distributions. |
| 🌱 **Seed Consistency** | `SIGMA_JOB2` | Finding valid only if it holds across all pre-registered seeds. One seed disagrees → `finding_valid: false` → paper reports the failure honestly. |
| 🦅 **HAWK Review** | `HAWK` | Journal of Finance-standard review of raw statistical outputs. Never reads prose. Cannot be fooled by fluent language. Halts after 3 cycles. |

---

## Honest Failure — What It Looks Like

> Most tools surface the favorable result. Paper-Forge surfaces everything and invalidates the finding when the data says to.

At dev scale (2,000 episodes, yfinance proxy), seed consistency correctly reported:

```json
{
  "consistent": false,
  "finding_valid": false,
  "conclusion": "Finding does NOT hold across all 3 seeds — invalid per PAPER.md",
  "by_concentration": {
    "0.1": {
      "sharpes": [0.987, -1.129, 1.127],
      "consistent_direction": false,
      "direction": "mixed"
    }
  }
}
```

The pre-commitment worked exactly as intended. The finding was underpowered at 2k episodes. The 500k GPU run is the real test.

---

## Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...

# Optional: separate key for CODEC Pass 2 (true process isolation)
OPENAI_API_KEY_PASS2=sk-...

# Data source: 'wrds' (production) or 'yfinance' (dev, default)
PAPER_FORGE_MINER_SOURCE=yfinance

# WRDS credentials (production only)
WRDS_USERNAME=your_wrds_username

# Modal GPU secret name
MODAL_SECRET_NAME=paper-forge-runtime

# Episode count override (default: 500000)
PAPER_FORGE_FORGE_EPISODES=500
```

---

## Tests

```bash
pytest -q

test_forge_gate_blocks_without_pap_lock      PASSED
test_forge_gate_passes_with_pap_lock         PASSED
test_aria_never_reads_artifact_content       PASSED  ← patches builtins.open
test_sigma_job1_blocks_sim_results           PASSED
test_codec_passes_are_isolated               PASSED  ← verifies payload context separation
test_hawk_escalates_after_3_cycles           PASSED
test_quill_raises_on_forbidden_words         PASSED
test_artifact_versioning_no_overwrite        PASSED
test_full_pipeline_smoke_test                PASSED
test_miner_passport_sha256_matches_file      PASSED  ← byte-level hash check
test_forge_episodes_match_paper_md           PASSED  ← introspects function signature

11 passed in 4.32s
```

---

## Six Rules That Must Not Be Reverted

These were learned from real build failures. Do not undo them in any new session.

1. **HAWK must never read LaTeX or PDF.** It reads CSVs and JSON only.
2. **QUILL must not use LLM to generate prose.** Deterministic formatting only.
3. **FIXER must not block pipeline completion on escalation.** It is diagnostic, not a gate.
4. **Modal must not silently fall back to local runner.** If Modal fails — raise. Never fall back.
5. **Daily quota 429 errors must not be retried.** Detect `86400` in error string and raise immediately.
6. **ARIA must never read artifact content.** Typed flags from `state.db` only.

---

## Known Limitations

- **WRDS required for production.** Use `PAPER_FORGE_MINER_SOURCE=yfinance` for local dev. The proxy uses CL=F and NG=F as stand-ins for commodity futures.
- **GPU-intensive.** 500k-episode runs take ~24 hours on Modal A100. Use `PAPER_FORGE_FORGE_EPISODES=500` for smoke tests.
- **QUILL is a scaffold, not a finished paper.** Introduction, related work, discussion, and conclusion must be written by the researcher.
- **Bid-ask filter calibration.** The intraday H-L/close spread proxy is too aggressive on daily futures data. Production runs should use tick-level spread from WRDS.
- **This is research infrastructure, not a paper mill.** A null result is a valid output. The system reports failures honestly.

---

## Contributing

| Area | File | What's needed |
|------|------|---------------|
| WRDS production data | `agents/miner/sources/wrds_src.py` | Real GSCI futures fetch, FF factors |
| New RL policy | `agents/forge/runner.py` + `env.py` | PPO, SAC — any Stable Baselines 3 policy |
| New research domain | `PAPER.md` + `MINER` sources | PAP gate, CODEC, HAWK work on any spec |
| New statistical test | `agents/sigma/sigma_job2.py` | HAWK picks up any new CSV automatically |
| New agent | `agents/aria/routing_config.py` | One line — ARIA dispatch handles the rest |

Before any PR: `pytest -q` must pass, especially `test_forge_episodes_match_paper_md`.

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

HAWK models Journal of Finance / RFS / JFE review standards  
Pre-registration inspired by OSF and AEA PAP frameworks  
Statistical correction: Harvey, Liu & Zhu (2016)

<br/>

*Built by [Gourav Salottra](https://github.com/gouravsalottra)*

</div>
