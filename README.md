<div align="center">

```
██████╗  █████╗ ██████╗ ███████╗██████╗       ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗      ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
██████╔╝███████║██████╔╝█████╗  ██████╔╝█████╗█████╗  ██║   ██║██████╔╝██║  ███╗█████╗
██╔═══╝ ██╔══██║██╔═══╝ ██╔══╝  ██╔══██╗╚════╝██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
██║     ██║  ██║██║     ███████╗██║  ██║      ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
╚═╝     ╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝      ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
```

### The autonomous finance research pipeline.
### From idea to peer-review-ready paper — for any empirical finance question.
### Scientific integrity enforced by architecture, not by trust.

<br/>

[![CI](https://github.com/gouravsalottra/paper-forge-private/actions/workflows/ci.yml/badge.svg)](https://github.com/gouravsalottra/paper-forge-private/actions/workflows/ci.yml)
![Tests](https://img.shields.io/badge/tests-129%20passing-brightgreen?style=flat-square)
![Python](https://img.shields.io/badge/python-3.13+-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Model](https://img.shields.io/badge/model-gpt--5.4-8b5cf6?style=flat-square)
![DB](https://img.shields.io/badge/state-SQLite%20WAL-f97316?style=flat-square)
![Integrity](https://img.shields.io/badge/integrity-cryptographically%20enforced-red?style=flat-square)

</div>

---

## What Is Paper-Forge?

Paper-Forge is an **autonomous 11-agent research pipeline** for empirical finance. It takes a research idea and produces a fully auditable, reproducible, peer-review-ready paper — with every integrity guarantee enforced by the system, not by researcher discipline.

It works for **any empirical finance research question**. Momentum strategies, LLM sentiment analysis, climate risk pricing, systemic risk networks, ETF arbitrage, cryptocurrency session effects — any question with data and a testable claim.

The researcher provides their knowledge of their domain. Paper-Forge provides everything else: literature discovery, data fetching from institutional sources, statistical analysis, code-vs-paper auditing, hostile peer review, and LaTeX scaffolding.

> **The core insight:** Most research integrity failures are not caused by dishonest researchers. They are caused by systems that allow unconscious hypothesis adjustment after seeing results. Paper-Forge makes that adjustment architecturally impossible.

---

## The Problem It Solves

Finance research has a replication crisis. Studies estimate more than half of published factor discoveries do not replicate. The cause is rarely fraud — it is a workflow problem.

```
Traditional research workflow          Paper-Forge workflow
──────────────────────────────         ──────────────────────────────
1. Collect data                        1. Describe research idea to INTAKE
2. Explore what looks significant      2. INTAKE generates PROTOCOL.md
3. Form hypothesis around result   ←   3. Hypothesis locked in SQLite (SHA-256)
4. Run "confirmatory" tests            4. Data fetched after lock ✓
5. Write paper around significance     5. Tests run exactly as pre-specified ✓
6. Submit                              6. Code audited against paper claims ✓
                                       7. Hostile review before any prose ✓
                                       8. Paper written from verified stats ✓
```

Step 3 on the left is where the problem lives. Paper-Forge makes it structurally impossible.

---

## Who This Is For

**Finance researchers** — PhD students, postdocs, faculty — who want their empirical work to be reproducible, auditable, and defensible against the most hostile reviewer.

**Quantitative analysts** — who need to test investment hypotheses rigorously with a full audit trail that satisfies compliance requirements.

**Research infrastructure engineers** — building reproducibility tooling for financial institutions, academic departments, or regulatory bodies.

**Product builders in AI and finance** — the architecture (multi-agent orchestration, pre-registration enforcement, bidirectional LLM auditing, connector registries, compute adapters) is a reference implementation for reliable agentic systems in high-stakes domains.

**Investors and evaluators** — this README describes a fully implemented, 129-test system running on real research.

---

## How It Works

```
You have a research idea                Paper-Forge handles the rest
────────────────────────                ─────────────────────────────────────

"I want to know whether LLM            ┌─ INTAKE interviews you in plain English
 sentiment from earnings calls          ├─ Handles data source authentication
 predicts overnight ETF returns"        ├─ Recommends appropriate stat tests
                                        ├─ Generates and validates PROTOCOL.md
         ↓                             ├─ Locks hypothesis before data is touched
                                        ├─ Fetches data from your specified sources
  python intake.py                      ├─ Runs your specified statistical tests
                                        ├─ Audits: does code match your claims?
         ↓                             ├─ Hostile peer review before any prose
                                        └─ Produces verified LaTeX paper scaffold
  paper_draft_v2.tex
  ready to submit
```

---

## The Full Pipeline

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  INTAKE  — AI Research Design Wizard                                         │
│                                                                              │
│  Researcher describes idea in plain English                                  │
│  INTAKE interviews them, asks at most 3 clarifying questions                 │
│  Handles data source authentication (WRDS browser OAuth, FRED API keys)      │
│  Recommends statistical tests based on claim type                            │
│  Supports both confirmatory and exploratory research modes                   │
│  Generates and validates PROTOCOL.md — researcher never writes schema syntax │
└───────────────────────────────┬──────────────────────────────────────────────┘
                                │
                                ▼
                          PROTOCOL.md
                   (validated before pipeline starts)
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  CONDUCTOR  — Orchestrator                                                   │
│  Pure state machine. Reads only typed flags from pipeline.db.                │
│  Never reads artifact content. Routing is a data table, not logic.           │
│  Adding a new agent = one line in routing_config.py.                         │
└──┬───────────────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────────┐
   ├──┤  LITERATURE + DATAPULL  (run in parallel)                           │
   │  │                                                                      │
   │  │  LITERATURE                          DATAPULL                        │
   │  │  Semantic Scholar + arXiv            Reads PROTOCOL.md data spec     │
   │  │  40 papers scanned                   Connector registry dispatches:  │
   │  │  Top 10 read in full                   wrds_crsp / wrds_futures      │
   │  │  Deduplication by DOI + title          wrds_optionmetrics / fred     │
   │  │  Preprint flagging                     sec_edgar / yfinance          │
   │  │  Retry with backoff on rate limits     ccxt_crypto / upload          │
   │  │  → literature_map.md                 Browser OAuth for WRDS/LSEG     │
   │  │                                      SHA-256 signs every dataset     │
   │  │                                      → data_certificate.json        │
   │  └──────────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────────┐
   ├──┤  PREREGISTER  ← THE INTEGRITY GATE                                  │
   │  │                                                                      │
   │  │  Reads hypothesis from PROTOCOL.md                                   │
   │  │  Writes to pipeline.db                                               │
   │  │  Computes SHA-256 of PROTOCOL.md                                     │
   │  │  Seals hypothesis_lock table                                         │
   │  │                                                                      │
   │  │  ┌────────────────────────────────────────────────────────────────┐  │
   │  │  │  SELECT 1 FROM hypothesis_lock                                 │  │
   │  │  │  WHERE run_id = ?                                              │  │
   │  │  │    AND locked_at IS NOT NULL                                   │  │
   │  │  │    AND compute_started_at IS NULL                              │  │
   │  │  │                                                                │  │
   │  │  │  Fails → ComputeGateError → pipeline halts                    │  │
   │  │  │  No env-var overrides. No exceptions. No workarounds.          │  │
   │  │  └────────────────────────────────────────────────────────────────┘  │
   │  │                                                                      │
   │  │  On resume: re-verifies PROTOCOL.md hash against locked hash         │
   │  │  If modified → PROTOCOLTamperError — resume blocked                 │
   │  └──────────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────────┐
   ├──┤  COMPUTE                                                             │
   │  │  Reads PROTOCOL.md → compute.type                                   │
   │  │  Dispatches to adapter:                                              │
   │  │    none        → immediate passthrough (pure regression research)    │
   │  │    backtest    → strategy backtester                                 │
   │  │    event_study → event study engine                                  │
   │  │    rl          → RL agent (custom environment required)              │
   │  │    abm         → agent-based market model                            │
   │  │  Episodes and seeds come from PROTOCOL.md only — never hardcoded     │
   │  └──────────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────────┐
   ├──┤  STATSRUN                                                            │
   │  │  Reads PROTOCOL.md → statistical_tests list                         │
   │  │  Runs exactly those tests from the library — no hardcoded battery    │
   │  │    newey_west_hac   garch_11         bootstrap_ci                    │
   │  │    deflated_sharpe  fama_macbeth     regime_switching                │
   │  │    markov_switching event_study_car  placebo_test                    │
   │  │    out_of_sample_r2 granger_causality panel_regression              │
   │  │    descriptive_stats circular_stats                                  │
   │  │  Seed consistency: finding_valid=false if any seed disagrees         │
   │  │  Never suppresses null results                                        │
   │  └──────────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────────┐
   ├──┤  CODEAUDIT + SPECAUDIT  (subprocess-isolated, separate API keys)    │
   │  │                                                                      │
   │  │  CODEAUDIT                    SPECAUDIT                              │
   │  │  Input: source code only      Input: PROTOCOL.md only               │
   │  │  Key: OPENAI_API_KEY          Key: OPENAI_API_KEY_PASS2             │
   │  │  Output: codeaudit_spec.md    Output: specaudit_report.md           │
   │  │  "What does code implement?"  "What did researcher claim?"           │
   │  │        │                            │                                │
   │  │        └──────────┬─────────────────┘                               │
   │  │                   ▼                                                  │
   │  │          codec_mismatch.md                                           │
   │  │  Proven zero context leakage by test:                                │
   │  │  test_codeaudit_and_specaudit_files_have_different_sha               │
   │  └──────────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────────┐
   ├──┤  AUTOREPAIR  (when CODEAUDIT finds mismatches)                      │
   │  │  Categorizes: auto-fixable vs needs-human                            │
   │  │  Patches source files for auto-fixable items                         │
   │  │  Re-runs DATAPULL + STATSRUN to verify fix held                      │
   │  │  Explicit human escalation — never silent                            │
   │  └──────────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────────┐
   ├──┤  RESULTS GATE  (database-level constraint)                          │
   │  │                                                                      │
   │  │  WRITER cannot run unless pipeline.db results_gate shows:           │
   │  │    p_value_passes = TRUE                                             │
   │  │    seed_consistent = TRUE                                            │
   │  │    codeaudit_clean = TRUE                                            │
   │  │                                                                      │
   │  │  Computed boolean column in SQLite — not a runtime check.            │
   │  │  WriterGateError if any condition is false.                          │
   │  └──────────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────────┐
   ├──┤  REVIEWER  (before any prose is written)                            │
   │  │  Reads: stats CSVs, audit files, data certificate                   │
   │  │  Never reads: any LaTeX or prose                                     │
   │  │  Calibrated to target venue from PROTOCOL.md                         │
   │  │  Minimum score 7/10 on methodology rubric                            │
   │  │  Max 3 cycles → PipelineHaltError if unresolved                     │
   │  │  Routes revision items back to the correct agent                     │
   │  └──────────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────────┐
   └──┤  WRITER  (only if REVIEWER approves)                                │
      │  Deterministic LaTeX formatter — zero LLM prose generation           │
      │  Every number traced to a verified CSV                               │
      │  Every citation traced to literature_map.md                          │
      │  Every method claim traced to CODEAUDIT output                       │
      │  Never overwrites a prior draft — versioned v1, v2, v3              │
      └──────────────────────────────────────────────────────────────────────┘
```

---

## Two Research Modes

### Confirmatory

You have a hypothesis. You commit to it before any data is touched.

```
$ python intake.py

INTAKE: Tell me about your research idea.

You: Does conditioning sector ETF momentum on VIX term structure
     inversion reduce momentum crashes while preserving upside?

INTAKE: Based on what you've described, here is the hypothesis I'll
        pre-register. Review carefully — once committed this cannot
        change without starting a new run:

        "Conditioning 12-1 month sector ETF momentum allocation on
         VIX term structure inversion reduces maximum drawdown by at
         least 15% during momentum crash events while preserving at
         least 80% of unconditional Sharpe ratio."

        Type 'commit' to lock, or 'edit' to modify.

You: commit

🔒 Hypothesis locked. SHA-256: 7f3a91c4...
   PROTOCOL.md sealed. Pipeline starting.
```

### Exploratory

You do not have a hypothesis yet. Paper-Forge supports this honestly — exploration is logged separately and disclosed in the paper.

```
$ python intake.py

INTAKE: Tell me about your research idea.

You: I've noticed something in how energy ETFs respond overnight
     around climate policy announcements but I'm not sure what
     direction to expect or how large the effect is.

INTAKE: This sounds like exploratory research. I'll set up an
        exploratory run. Your analysis will be logged separately.

        After you see the results, I'll help you form a hypothesis
        and upgrade to a confirmatory run — with the exploration
        transparently disclosed in your methods section.
```

When ready to commit:

```
$ python intake.py --upgrade-to-confirmatory --run-id explore-20260509-143201

INTAKE: Your exploration found:
        - ICLN overnight: +0.18% on COP announcement dates (n=23)
        - XLE overnight: -0.31% on the same dates
        - Spread strengthened post-2018

        Here are three hypotheses you could pre-register.
        Which feels most honest given what you saw?
```

---

## Five Integrity Layers

```
┌─────────────────────────────────────────────────────────────────┐
│  Layer 1 — HYPOTHESIS LOCK                                      │
│  Hypothesis committed to SQLite and SHA-256 signed BEFORE       │
│  any data is fetched. On resume, PROTOCOL.md is re-hashed and   │
│  compared — any modification raises PROTOCOLTamperError.        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Layer 2 — DATA CERTIFICATE                                     │
│  Every dataset SHA-256 signed at download. Certificate records: │
│  source, query parameters, row counts, download timestamp,      │
│  library versions, acknowledged deviations.                     │
│  A reviewer can independently verify the exact data used.       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Layer 3 — BIDIRECTIONAL CODE AUDIT                             │
│  Two subprocess-isolated passes with separate API keys.         │
│  CODEAUDIT reads code only. SPECAUDIT reads PROTOCOL.md only.  │
│  Zero context leakage proven by SHA-256 file comparison test.   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Layer 4 — SEED CONSISTENCY                                     │
│  A finding is only valid if it holds qualitatively across all   │
│  pre-registered seeds. One seed disagrees → finding_valid:false │
│  → paper reports the failure. Never surfaces only the           │
│  favorable seeds.                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  Layer 5 — HOSTILE REVIEW BEFORE PROSE                         │
│  REVIEWER reads raw statistical outputs — never LaTeX.          │
│  Cannot be fooled by fluent writing. Calibrated to target       │
│  venue. Database-level WriterGateError blocks WRITER unless     │
│  p_value_passes, seed_consistent, and codeaudit_clean are all  │
│  true in pipeline.db.                                           │
└─────────────────────────────────────────────────────────────────┘
```

---

## Data Sources

```
Connector           Source                    Authentication
──────────────────  ────────────────────────  ────────────────────────────────
wrds_crsp           WRDS / CRSP               Browser OAuth → 2FA on phone
wrds_futures        WRDS / Compustat Futures  Browser OAuth → 2FA on phone
wrds_optionmetrics  WRDS / OptionMetrics      Browser OAuth → 2FA on phone
lseg                LSEG / Refinitiv          Browser OAuth → 2FA on phone
fred                Federal Reserve (FRED)    API key — stored once in .env
sec_edgar           SEC EDGAR                 Public — no auth required
yfinance            Yahoo Finance             Public — no auth required
ccxt_crypto         Any crypto exchange       API key + secret — stored once
bloomberg           Bloomberg Terminal        Local Terminal must be running
upload              Researcher's own file     Drop CSV/parquet in data/uploads/
```

Authenticate once per provider. Credentials stored securely. Every subsequent run fetches automatically.

INTAKE handles the entire auth flow in conversation:

```
INTAKE: You mentioned WRDS data. I'll open the WRDS login page in your
        browser. Sign in with your institutional credentials and complete
        the 2FA — I'll wait here until you're done.

[Browser opens → researcher logs in → 2FA on phone → token stored]

INTAKE: WRDS connected. What datasets do you need?
```

Adding a new connector: one file in `agents/datapull/connectors/`.

---

## Statistical Test Library

STATSRUN runs exactly the tests PROTOCOL.md specifies. No hardcoded battery.

```
Test                  Claim types it suits
────────────────────  ────────────────────────────────────────────────
newey_west_hac        Predictability, performance — t-test with HAC
garch_11              Any — volatility modeling and persistence
bootstrap_ci          Any — non-parametric confidence intervals
deflated_sharpe       Performance — Sharpe corrected for multiple testing
fama_macbeth          Predictability, performance — two-pass cross-sectional
regime_switching      Any — structural break detection
markov_switching      Any — hidden state regime identification
event_study_car       Causal — cumulative abnormal returns around events
placebo_test          Predictability, causal — false discovery validation
out_of_sample_r2      Predictability — genuine predictive power
granger_causality     Causal — temporal precedence testing
panel_regression      Predictability, performance — fixed/random effects
descriptive_stats     Exploratory — summary statistics
circular_stats        Crypto, intraday — time-of-day effects
```

INTAKE recommends defaults by claim type:

```
predictability → fama_macbeth, out_of_sample_r2, placebo_test, newey_west_hac
performance    → newey_west_hac, deflated_sharpe, bootstrap_ci, regime_switching
causal         → event_study_car, placebo_test, newey_west_hac, granger_causality
exploratory    → descriptive_stats, regime_switching, markov_switching
```

Adding a new test: one file in `agents/statsrun/tests/`.

---

## PROTOCOL.md — The Research Specification

INTAKE generates this through conversation. You never write schema syntax directly.

```yaml
research_question: |
  Does conditioning sector ETF momentum on VIX term structure inversion
  reduce momentum crashes while preserving upside in normal regimes?

research_mode: confirmatory
claim_type: performance

hypothesis: |
  Conditioning 12-1 month sector ETF momentum allocation on VIX term
  structure inversion reduces maximum drawdown by at least 15% during
  momentum crash events while preserving at least 80% of unconditional
  Sharpe ratio in low-volatility regimes.

primary_metric: "Conditional vs unconditional momentum Sharpe ratio"
minimum_effect_size: "0.25 Sharpe units improvement"
target_venue: "Journal of Financial Economics"

data_sources:
  - source: wrds_crsp
    dataset: sector_etf_daily_returns
    date_range: [1999-01-01, 2024-12-31]
    filters:
      - "Exclude months with fewer than 15 trading days"
  - source: fred
    series: [VIXCLS, T10Y3M]
    date_range: [1999-01-01, 2024-12-31]

compute:
  type: backtest
  parameters: "Monthly rebalancing, 12-1 momentum signal"
  seeds: [1337, 42, 9999]

statistical_tests:
  - newey_west_hac
  - deflated_sharpe
  - bootstrap_ci
  - regime_switching
  - out_of_sample_r2

significance_threshold: 0.05
multiple_test_correction: bonferroni

audit_requirements:
  codeaudit_required: true
  reviewer_min_score: 7
  max_review_cycles: 3
```

The validator checks every field before the pipeline starts and rejects any unfilled placeholder.

---

## Run Dashboard

```
$ python dashboard.py

RUN ID                    STATUS   STARTED              PHASES    COST
pf-live-20260423-203428   DONE     2026-04-23 20:34     9/9       $3.42
pf-live-20260423-185058   DONE     2026-04-23 18:50     9/9       $3.18
pf-live-20260423-040430   DONE     2026-04-23 04:04     9/9       $2.97

$ python dashboard.py --run-id pf-live-20260423-203428

Phase           Status   Duration    Cost     Notes
LITERATURE      done     4m 23s      $0.40    40 papers, 9 full reads
DATAPULL        done     2m 11s      —        WRDS + FRED, SHA-256 certified
PREREGISTER     done     0m 12s      $0.15    Hypothesis locked: 7f3a91c4...
COMPUTE         done     —           —        type: backtest, 3 seeds
STATSRUN        done     3m 44s      —        5 tests, finding_valid: true
CODEAUDIT       done     8m 22s      $1.12    1 mismatch → AUTOREPAIR patched
REVIEWER        done     6m 30s      $0.95    Approved cycle 2, score 8.1/10
WRITER          done     12m 10s     $0.80    paper_draft_v2.tex

Total cost: $3.42

$ python dashboard.py --cleanup-stale
Marked 3 runs as stale (running for > 48 hours)
```

---

## Quick Start

```bash
git clone https://github.com/gouravsalottra/paper-forge-private
cd paper-forge-private

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock          # fully pinned — identical environment

cp .env.example .env                      # add your OPENAI_API_KEY
```

**Start new research (recommended):**
```bash
python intake.py
# INTAKE guides you in plain English
# Handles all data source authentication
# Generates and validates PROTOCOL.md
# Then:
python run_pipeline.py
```

**Development mode (no institutional data required):**
```bash
export PAPER_FORGE_MINER_SOURCE=yfinance
python run_pipeline.py
```

**Resume a halted run:**
```bash
python run_pipeline.py --resume pf-live-20260422 --from CODEAUDIT
# Hypothesis lock preserved and re-verified on resume
```

**View run history:**
```bash
python dashboard.py
python dashboard.py --run-id <id>
python dashboard.py --cleanup-stale
```

**Run tests:**
```bash
pytest -q
# 129 passed, 1 skipped in 20.02s
```

---

## What Gets Produced Per Run

```
runs/pf-live-YYYYMMDD-HHMMSS/
│
├── literature_map.md           ← gap analysis, methodology summary, citations
├── data_certificate.json       ← SHA-256 signed data lineage for every input
├── hypothesis_lock.json        ← pre-registered hypothesis + timestamp + hash
│
├── stats_tables/
│   ├── seed_consistency.csv    ← READ THIS FIRST: finding_valid true/false
│   ├── primary_metric.csv      ← your primary result
│   ├── ttest_results.csv       ← p-values and effect sizes per test
│   └── library_versions.json   ← exact library versions for replication
│
├── codeaudit_spec.md           ← what the code actually implements
├── specaudit_report.md         ← what PROTOCOL.md claimed
├── codec_mismatch.md           ← where they diverged
├── autorepair_report.md        ← automated fixes and human escalations
│
├── reviewer_report_v1.md       ← full referee report with mandatory items
├── reviewer_scores_v1.json     ← methodology rubric scores 1-10
│
├── paper_draft_v1.tex          ← initial LaTeX scaffold — never overwritten
├── paper_draft_v2.tex          ← after REVIEWER revision cycle
│
└── pipeline.log                ← structured JSON log of every agent event
```

---

## What Honest Failure Looks Like

Most tools surface the favorable result. Paper-Forge surfaces everything.

```json
{
  "consistent": false,
  "finding_valid": false,
  "conclusion": "Finding does NOT hold across all 3 seeds — invalid per PROTOCOL.md",
  "seed_1337": { "direction": "negative", "significant": true },
  "seed_42":   { "direction": "positive", "significant": false },
  "seed_9999": { "direction": "negative", "significant": false }
}
```

The pipeline reports this honestly. The paper reports it honestly. That is the point. A null result is a valid output.

---

## System Design — For Engineers

**Orchestrator reads state, not content.**
CONDUCTOR reads only typed flags from `pipeline.db` — `APPROVED`, `REVISION_REQUESTED`, `PASS`, `FAIL`, `ESCALATE`. Never reads artifact content. Proven by `test_conductor_never_reads_artifact_content` which patches `builtins.open`.

**Routing is data, not logic.**
Adding a new agent is one line in `routing_config.py`. `conductor.py` is never modified for routing changes.

**PhaseRunner with retry and backoff.**
Every phase runs through `PhaseRunner` which handles retries with exponential backoff, timeout enforcement, and structured logging. Gate errors (`ComputeGateError`, `WriterGateError`) are never retried.

**Database-level results gate.**
`results_gate` table has a computed boolean column in SQLite. WRITER cannot be dispatched unless the database constraint is satisfied — not a runtime check, a schema constraint.

**Subprocess isolation for LLM audit.**
CODEAUDIT and SPECAUDIT run as separate subprocesses with separate API keys. Zero context leakage proven by SHA-256 file comparison: `test_codeaudit_and_specaudit_files_have_different_sha`.

**Token budget with hard limits.**
Every LLM call records token usage to `pipeline.db`. `TokenBudgetExceededError` halts the pipeline before spending exceeds the hard limit.

**Prompt versioning.**
Every agent system prompt lives in `prompts/<agent>.md`. SHA-256 recorded in `agent_results` per LLM call. Two runs with identical data but different prompts have different `prompt_sha256` values — auditable.

**Append-only artifact writes.**
CONDUCTOR never deletes or overwrites content rows. Full audit trail always reconstructible from `pipeline.db` alone.

**WAL-mode SQLite.**
`PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`. Any interrupted run resumes from last committed phase.

---

## Extending Paper-Forge

**Adding a data source:**
```python
# agents/datapull/connectors/my_source.py
from agents.datapull.connectors.registry import register
from agents.datapull.connectors.base import DataConnector

@register
class MySourceConnector(DataConnector):
    source_name = "my_source"

    def fetch(self, dataset, fields, date_range, filters, output_dir):
        # fetch data, return (dataframe, certificate_dict)
        ...
```
Available immediately in PROTOCOL.md as `source: my_source`.

**Adding a statistical test:**
```python
# agents/statsrun/tests/my_test.py
from agents.statsrun.tests.registry import register
from agents.statsrun.tests.base import StatTest

@register
class MyTest(StatTest):
    test_name = "my_test"

    def run(self, data, seed, params):
        # return dict with p_value, statistic, significant, effect_size
        ...
```
Available immediately in PROTOCOL.md as `- my_test`.

**Adding a compute adapter:**
```python
# agents/compute/adapters/my_adapter.py
from agents.compute.adapters.registry import register
from agents.compute.adapters.base import ComputeAdapter

@register
class MyAdapter(ComputeAdapter):
    adapter_type = "my_compute"

    def run(self, params, output_dir, seeds):
        # run computation, return results dict
        ...
```
Available immediately in PROTOCOL.md as `type: my_compute`.

**Adding a new agent:**
```python
# agents/conductor/routing_config.py
AGENT_SERVER_MAP: dict[str, str] = {
    ...
    "MY_AGENT": "my_server",   # ← one line
}
```

---

## MCP Servers

Three functional MCP servers expose pipeline capabilities as tools:

```
mcp_servers/arxiv_server.py   → search_arxiv, fetch_arxiv_paper
mcp_servers/latex_server.py   → compile_latex, validate_latex_syntax
mcp_servers/modal_server.py   → dispatch_compute_job, check_compute_status
```

---

## Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...

# Separate key for SPECAUDIT — true process isolation
OPENAI_API_KEY_PASS2=sk-...

# Data source: wrds (production) or yfinance (dev, default)
PAPER_FORGE_MINER_SOURCE=yfinance

# WRDS credentials
WRDS_USERNAME=your_wrds_username

# Token budget per run (defaults shown)
PAPERFORGE_SOFT_LIMIT_USD=10.0
PAPERFORGE_HARD_LIMIT_USD=25.0

# Override tamper detection on resume (expert use — logged as CRITICAL)
PAPERFORGE_OVERRIDE_PAP_TAMPER=1
```

---

## Examples

`examples/gsci_momentum/` contains the first paper produced by Paper-Forge: a study of passive investor concentration effects on commodity futures momentum profitability. It shows what a complete PROTOCOL.md looks like for a performance claim, how to design a custom RL compute environment, and what a full pipeline run produces end-to-end.

Reference material only — not maintained as runnable code. See `examples/gsci_momentum/README.md`.

---

## Repository Structure

```
paper-forge/
│
├── intake.py                          ← start here for new research
├── run_pipeline.py                    ← run existing PROTOCOL.md
├── dashboard.py                       ← view run history and costs
│
├── PROTOCOL.md                        ← blank template (fill via intake.py)
├── PROTOCOL_SCHEMA.md                 ← full schema documentation
│
├── agents/
│   ├── conductor/                     ← orchestrator state machine
│   │   ├── conductor.py
│   │   ├── phase_runner.py
│   │   ├── routing_config.py
│   │   ├── retry.py
│   │   └── exceptions.py
│   ├── intake/                        ← research design wizard
│   ├── literature/                    ← literature search
│   ├── datapull/                      ← data fetching
│   │   └── connectors/                ← 10 connectors + registry
│   ├── preregister/                   ← hypothesis lock
│   ├── compute/                       ← compute dispatch
│   │   └── adapters/                  ← rl, backtest, event_study, none, abm
│   ├── statsrun/                      ← statistical analysis
│   │   └── tests/                     ← 14 tests + registry
│   ├── codeaudit/                     ← code audit (pass 1)
│   ├── autorepair/                    ← auto-fix mismatches
│   ├── reviewer/                      ← hostile peer review
│   ├── writer/                        ← LaTeX scaffold
│   ├── logger.py                      ← structured JSON logging
│   ├── llm_client.py                  ← centralized LLM access
│   └── prompt_loader.py               ← prompt versioning
│
├── prompts/                           ← versioned agent system prompts
│
├── conductor/
│   └── validate_protocol.py           ← PROTOCOL.md validator
│
├── mcp_servers/                       ← functional MCP servers
│   ├── arxiv_server.py
│   ├── latex_server.py
│   └── modal_server.py
│
├── config/
│   └── model_config.json              ← LLM model versions + fallbacks
│
├── examples/
│   └── gsci_momentum/                 ← reference implementation
│
├── tests/                             ← 129 tests, 0 failing
├── .github/workflows/ci.yml           ← CI on every push
├── requirements.lock                  ← fully pinned dependencies
└── requirements.in                    ← direct dependencies
```

---

## Known Limitations

**WRITER produces a scaffold, not a finished paper.** Introduction, related work, discussion, and conclusion require human authorship. WRITER produces methodology, results, and tables — the sections that must be grounded in verified data.

**COMPUTE adapters for backtest and event_study are scaffolded.** The interface is defined and tested. The logic needs to be built for each research design. See `examples/gsci_momentum/compute/` for a complete RL adapter reference.

**WRDS requires institutional access.** Use `PAPER_FORGE_MINER_SOURCE=yfinance` for development. Public data validates pipeline mechanics but does not replace institutional data for publication.

---

## Contributing

| Area | File | What's needed |
|---|---|---|
| New data connector | `agents/datapull/connectors/` | Any institutional data source |
| New statistical test | `agents/statsrun/tests/` | Any test not in the library |
| Backtest adapter | `agents/compute/adapters/backtest_adapter.py` | Full strategy engine |
| Event study adapter | `agents/compute/adapters/event_study_adapter.py` | CAR computation |
| New research domain | Run `python intake.py` | All integrity infrastructure carries over |

Before any PR: `pytest -q` must show 0 failures.

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

REVIEWER models Journal of Finance / Review of Financial Studies / Journal of Financial Economics standards

Pre-registration inspired by OSF Pre-registration and AEA RCT Registry

Multiple testing correction: Harvey, Liu & Zhu (2016)

<br/>

*Built by [Gourav Salottra](https://github.com/gouravsalottra) · Boston University*

</div>
