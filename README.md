<div align="center">

```
██████╗  █████╗ ██████╗ ███████╗██████╗       ███████╗ ██████╗ ██████╗  ██████╗ ███████╗
██╔══██╗██╔══██╗██╔══██╗██╔════╝██╔══██╗      ██╔════╝██╔═══██╗██╔══██╗██╔════╝ ██╔════╝
██████╔╝███████║██████╔╝█████╗  ██████╔╝█████╗█████╗  ██║   ██║██████╔╝██║  ███╗█████╗
██╔═══╝ ██╔══██║██╔═══╝ ██╔══╝  ██╔══██╗╚════╝██╔══╝  ██║   ██║██╔══██╗██║   ██║██╔══╝
██║     ██║  ██║██║     ███████╗██║  ██║      ██║     ╚██████╔╝██║  ██║╚██████╔╝███████╗
╚═╝     ╚═╝  ╚═╝╚═╝     ╚══════╝╚═╝  ╚═╝      ╚═╝      ╚═════╝ ╚═╝  ╚═╝ ╚═════╝ ╚══════╝
```

### The autonomous finance research pipeline. From idea to peer-review-ready paper.
### Enforced by architecture. Unable to p-hack. By design.

<br/>

[![CI](https://github.com/gouravsalottra/paper-forge-private/actions/workflows/ci.yml/badge.svg)](https://github.com/gouravsalottra/paper-forge-private/actions/workflows/ci.yml)
![Tests](https://img.shields.io/badge/tests-87%20passing-brightgreen?style=flat-square)
![Python](https://img.shields.io/badge/python-3.13+-blue?style=flat-square)
![License](https://img.shields.io/badge/license-MIT-green?style=flat-square)
![Model](https://img.shields.io/badge/model-gpt--5.4-8b5cf6?style=flat-square)
![DB](https://img.shields.io/badge/state-SQLite%20WAL-f97316?style=flat-square)
![Integrity](https://img.shields.io/badge/integrity-cryptographically%20enforced-red?style=flat-square)

</div>

---

## What Is Paper-Forge?

Paper-Forge is an **autonomous 11-agent research pipeline** that takes a finance research idea and produces a fully auditable, reproducible, peer-review-ready paper — with every integrity guarantee enforced by the system, not by researcher honesty.

It handles literature discovery, data fetching from institutional sources, statistical analysis, code-vs-paper auditing, hostile peer review, and LaTeX drafting. You describe your research. The pipeline does the rest.

**It works for any empirical finance research** — not one hardcoded topic. Momentum strategies, LLM sentiment analysis, climate risk pricing, systemic risk networks, cryptocurrency session effects, ETF arbitrage cycles — any question with data and a testable claim.

> **The core insight:** Most research integrity problems are not caused by dishonest researchers. They are caused by systems that make it easy to unconsciously adjust hypotheses after seeing results. Paper-Forge makes that adjustment architecturally impossible.

---

## The Problem It Solves

The finance research replication crisis is real. Studies estimate that **more than half of published factor discoveries do not replicate**. The cause is rarely fraud — it is a workflow problem. When a researcher can see their results before committing to a hypothesis, specification search happens naturally, even innocently.

```
Traditional research workflow          Paper-Forge workflow
──────────────────────────────         ──────────────────────────────
1. Collect data                        1. Describe research idea to INTAKE
2. Explore what looks significant      2. INTAKE generates PROTOCOL.md
3. Form hypothesis around finding  ←   3. Hypothesis locked in SQLite (SHA-256)
4. Run "confirmatory" tests            4. Data fetched after lock ✓
5. Write paper around significance     5. Tests run exactly as pre-specified ✓
6. Submit                              6. Code audited against paper claims ✓
                                       7. Hostile review before any prose ✓
                                       8. Paper written from verified stats ✓
```

The left side is how most papers are written. The right side is what Paper-Forge enforces.

---

## Who This Is For

**Finance researchers** — PhD students, postdocs, professors — who want their empirical work to be reproducible, auditable, and defensible to the most hostile reviewer. The system handles the entire technical pipeline so you can focus on the science.

**Quantitative analysts and portfolio managers** — who need to test investment hypotheses rigorously before acting on them, with a full audit trail that satisfies compliance requirements.

**Research infrastructure engineers** — building reproducibility tooling for financial institutions, academic departments, or regulatory bodies.

**Product builders in AI + finance** — the architecture (multi-agent orchestration, pre-registration enforcement, bidirectional LLM auditing, connector registries) is a reference implementation for reliable agentic systems in high-stakes domains.

**Investors and evaluators** — this README is the product. The architecture described here is fully implemented, tested with 87 passing tests, and running on real research.

---

## How It Works — The Simple Version

```
You have an idea                       Paper-Forge does the rest
────────────────                       ─────────────────────────

"Does passive investor                 ┌─ Searches 40+ papers, reads top 10 in full
 concentration reduce                  ├─ Fetches data from WRDS, FRED, yfinance
 momentum profitability?"              ├─ Locks your hypothesis before touching data
                                       ├─ Runs 500,000-episode simulation
        ↓                              ├─ Executes 6-test statistical battery
                                       ├─ Audits: does code match what you claimed?
python intake.py                       ├─ Hostile peer review (Journal of Finance standard)
                                       └─ Produces verified LaTeX paper draft
        ↓

paper_draft_v2.tex  ←  ready to submit
```

The only thing you provide is your research question. Everything else — data, analysis, audit, paper — is automated with full integrity enforcement at every step.

---

## The Full Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                                                                             │
│   INTAKE  (AI Research Design Wizard)                                       │
│                                                                             │
│   Researcher describes idea in plain English → INTAKE interviews them       │
│   → Handles data source authentication (WRDS OAuth, FRED API keys)         │
│   → Recommends appropriate statistical tests by claim type                  │
│   → Generates validated PROTOCOL.md — researcher never writes schema syntax │
│                                                                             │
└────────────────────────────┬────────────────────────────────────────────────┘
                             │
                             ▼
                       PROTOCOL.md
              (validated before pipeline starts)
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  CONDUCTOR  (Orchestrator)                                                  │
│  Pure state machine. Reads only typed flags from pipeline.db.               │
│  Never reads artifact content. Routing is data, not logic.                  │
└──┬──────────────────────────────────────────────────────────────────────────┘
   │
   │  ┌─────────────────────────────────────┐
   ├──┤  LITERATURE + DATAPULL  (parallel)  │
   │  │                                     │
   │  │  LITERATURE                         │
   │  │  Semantic Scholar + arXiv           │
   │  │  40 papers scanned, top 10 read     │
   │  │  Deduplication by DOI + title       │
   │  │  Preprint flagging for citations    │
   │  │  → literature_map.md               │
   │  │                                     │
   │  │  DATAPULL                           │
   │  │  Reads PROTOCOL.md data spec        │
   │  │  Connector registry dispatches:     │
   │  │    wrds_crsp / wrds_futures         │
   │  │    wrds_optionmetrics / fred        │
   │  │    sec_edgar / yfinance             │
   │  │    ccxt_crypto / upload             │
   │  │  Browser OAuth for WRDS/LSEG        │
   │  │  SHA-256 signs every dataset        │
   │  │  → data_certificate.json           │
   │  └─────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────┐
   ├──┤  PREREGISTER  ← THE INTEGRITY GATE                              │
   │  │                                                                  │
   │  │  Reads PROTOCOL.md hypothesis                                    │
   │  │  Writes to pipeline.db                                           │
   │  │  Computes SHA-256 of PROTOCOL.md                                 │
   │  │  Seals hypothesis_lock                                           │
   │  │                                                                  │
   │  │  ┌──────────────────────────────────────────────────────────┐   │
   │  │  │  SELECT 1 FROM hypothesis_lock                           │   │
   │  │  │  WHERE run_id = ?                                        │   │
   │  │  │    AND locked_at IS NOT NULL                             │   │
   │  │  │    AND compute_started_at IS NULL                        │   │
   │  │  │                                                          │   │
   │  │  │  Returns nothing → HypothesisLockError → pipeline halts  │   │
   │  │  │  No env-var overrides. No exceptions. No workarounds.    │   │
   │  │  └──────────────────────────────────────────────────────────┘   │
   │  │                                                                  │
   │  │  On resume: re-verifies PROTOCOL.md hash against locked hash     │
   │  │  → PROTOCOLTamperError if mismatch                              │
   │  └──────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────┐
   ├──┤  COMPUTE                                                         │
   │  │  Reads PROTOCOL.md → compute.type                               │
   │  │  Dispatches to adapter:                                          │
   │  │    rl          → RL agent (PettingZoo + CEM/PPO, CUDA GPU)      │
   │  │    backtest    → Strategy backtester                             │
   │  │    event_study → Event study engine                              │
   │  │    abm         → Agent-based market model                        │
   │  │    none        → Passthrough (pure regression research)          │
   │  │  Seeds [1337, 42, 9999] across all adapters                     │
   │  └──────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────┐
   ├──┤  STATSRUN                                                        │
   │  │  Reads PROTOCOL.md → statistical_tests list                     │
   │  │  Runs exactly those tests from the library:                      │
   │  │    newey_west_hac  │ garch_11        │ bootstrap_ci              │
   │  │    deflated_sharpe │ fama_macbeth    │ regime_switching           │
   │  │    markov_switching│ event_study_car │ placebo_test               │
   │  │    out_of_sample_r2│ granger_causality│ panel_regression         │
   │  │  Seed consistency enforced: finding_valid=false if any seed fails│
   │  │  Never suppresses null results                                    │
   │  └──────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────┐
   ├──┤  CODEAUDIT + SPECAUDIT  (subprocess-isolated)                   │
   │  │                                                                  │
   │  │  CODEAUDIT          SPECAUDIT                                    │
   │  │  reads: code only   reads: PROTOCOL.md only                     │
   │  │  key: API_KEY       key: API_KEY_PASS2                          │
   │  │  "what does the     "what did the researcher                     │
   │  │   code actually do?" say they would do?"                        │
   │  │       │                    │                                     │
   │  │       └────────┬───────────┘                                     │
   │  │                ▼                                                  │
   │  │       codec_mismatch.md                                          │
   │  │  Two passes with zero shared context.                            │
   │  │  Proven by test: test_codec_passes_are_isolated                  │
   │  └──────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────┐
   ├──┤  AUTOREPAIR  (when CODEAUDIT finds mismatches)                  │
   │  │  Categorizes: auto-fixable vs needs-human                        │
   │  │  Patches source files, re-runs DATAPULL + STATSRUN to verify     │
   │  │  Human escalation is explicit — never silent                     │
   │  └──────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────┐
   ├──┤  REVIEWER  (before any prose is written)                        │
   │  │  Journal of Finance / RFS / JFE standard                         │
   │  │  Reads: stats CSVs, audit files, data certificate               │
   │  │  Never reads: any LaTeX or prose                                 │
   │  │  Knows target venue — calibrates standards accordingly           │
   │  │  Minimum score: 7/10 methodology rubric                          │
   │  │  Max 3 cycles → PipelineHaltError if unresolved                 │
   │  │  Routes revision items back to the correct agent                 │
   │  └──────────────────────────────────────────────────────────────────┘
   │
   │  ┌──────────────────────────────────────────────────────────────────┐
   └──┤  WRITER  (only if REVIEWER approves)                            │
      │  Deterministic LaTeX formatter — no LLM prose generation         │
      │  Every number traced to a verified CSV                           │
      │  Every citation traced to literature_map.md                      │
      │  Every method claim traced to CODEAUDIT output                   │
      │  Never overwrites a prior draft (versioned: v1, v2, v3...)       │
      └──────────────────────────────────────────────────────────────────┘
```

---

## Two Research Modes

Paper-Forge supports the full real-world research process — not just the idealized version where researchers always have hypotheses before looking at data.

### Confirmatory Mode

You have a clear hypothesis. You know what you expect to find. Paper-Forge locks it before any data is touched.

```
python intake.py

INTAKE: "Tell me about your research idea."

You: "I think passive index investor concentration above 30% of open
      interest in commodity futures reduces momentum strategy profitability
      by reducing the price informativeness of roll-yield signals."

INTAKE: "Here's the hypothesis I'll pre-register for you. Review carefully —
         once committed, this cannot be changed without starting a new run:

         'Passive GSCI index investor concentration above 30% of open interest
          reduces 12-month momentum strategy Sharpe ratios by at least 0.15
          units, controlling for GARCH(1,1) volatility clustering and
          Fama-French momentum factor exposure.'

         Type 'commit' to lock, or 'edit' to modify."

You: commit

🔒 Hypothesis locked. SHA-256: 3a5273ac6fb202...
   PROTOCOL.md sealed. Pipeline starting.
```

### Exploratory Mode

You don't have a hypothesis yet. You want to understand whether there's something interesting before committing to a direction. This is legitimate science — and Paper-Forge supports it honestly.

```
python intake.py

INTAKE: "Tell me about your research idea."

You: "I'm not sure yet. I've noticed that energy ETFs seem to respond
      differently overnight versus intraday around major climate policy
      announcements. I want to understand the pattern before I commit
      to any direction."

INTAKE: "That sounds like exploratory research — you want to understand
         the data before forming a hypothesis. I'll set up an exploratory
         run. Your exploration will be logged separately from any
         confirmatory analysis.

         After you've seen the patterns, I'll help you form a hypothesis
         and upgrade to a confirmatory run — with the exploration
         transparently disclosed in your methods section."
```

The exploration is logged with timestamp. When you're ready to commit:

```
python intake.py --upgrade-to-confirmatory --run-id explore-20260509-143201

INTAKE: "Your exploration found:
         - ICLN overnight returns: +0.18% on COP announcement dates (n=23)
         - XLE overnight returns: -0.31% on the same dates
         - The spread strengthened post-2018

         Based on this, here are three hypotheses you could commit to:

         Option A [Strongest]: ICLN-XLE overnight spread is positive and
         significant on major climate policy dates, after controlling for
         VIX and oil price changes. Implies event-study CAR + placebo test.

         Option B [Conservative]: Climate policy dates predict positive ICLN
         and negative XLE overnight returns independently.

         Option C [Descriptive]: Document the pattern and estimate effect
         size with confidence intervals.

         Which feels most honest given what you've seen?"
```

The resulting paper transparently discloses that the hypothesis was formed after initial data exploration — which is methodologically legitimate when disclosed, and what Paper-Forge enforces.

---

## Five Integrity Layers

Every layer is enforced by code, not by researcher discipline.

```
Layer 1 — HYPOTHESIS LOCK
┌─────────────────────────────────────────────────────────────┐
│ Hypothesis committed to SQLite and SHA-256 signed BEFORE    │
│ any data is fetched. COMPUTE cannot start unless the SQL    │
│ gate passes. On pipeline resume, PROTOCOL.md is re-hashed   │
│ and compared — any modification raises PROTOCOLTamperError. │
└─────────────────────────────────────────────────────────────┘

Layer 2 — DATA CERTIFICATE
┌─────────────────────────────────────────────────────────────┐
│ Every dataset is SHA-256 signed at download time. The       │
│ certificate records: source, query parameters, row counts,  │
│ download timestamp, acknowledged deviations, library        │
│ versions. Byte-level hash verified by test suite.           │
│ A reviewer can independently verify the exact data used.    │
└─────────────────────────────────────────────────────────────┘

Layer 3 — BIDIRECTIONAL CODE AUDIT
┌─────────────────────────────────────────────────────────────┐
│ Two subprocess-isolated LLM passes with separate API keys.  │
│ Pass 1 reads code only — extracts what was implemented.     │
│ Pass 2 reads PROTOCOL.md only — extracts what was claimed.  │
│ The two passes genuinely cannot share context. Proven by    │
│ test: test_codeaudit_specaudit_passes_are_isolated.         │
└─────────────────────────────────────────────────────────────┘

Layer 4 — SEED CONSISTENCY
┌─────────────────────────────────────────────────────────────┐
│ A finding is only valid if it holds qualitatively across    │
│ all pre-registered seeds [1337, 42, 9999]. One seed         │
│ disagrees → finding_valid: false → the paper reports the    │
│ failure honestly. The system never surfaces only the        │
│ favorable seeds.                                            │
└─────────────────────────────────────────────────────────────┘

Layer 5 — HOSTILE REVIEW BEFORE PROSE
┌─────────────────────────────────────────────────────────────┐
│ REVIEWER reads raw statistical outputs — never LaTeX.       │
│ Cannot be fooled by fluent writing. Knows target venue      │
│ standards. Halts pipeline after 3 failed cycles rather      │
│ than approving a weak paper. WRITER only runs if REVIEWER   │
│ issues approved_for_quill: true.                            │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Sources — Any Institutional Provider

Paper-Forge connects to real institutional data sources through a connector registry. Adding a new source is one file.

```
Connector          Source                    Auth Method
──────────────     ──────────────────────    ────────────────────────────
wrds_crsp          WRDS / CRSP               Browser OAuth → 2FA on phone
wrds_futures       WRDS / Compustat Futures  Browser OAuth → 2FA on phone
wrds_optionmetrics WRDS / OptionMetrics      Browser OAuth → 2FA on phone
wrds_compustat     WRDS / Compustat          Browser OAuth → 2FA on phone
lseg               LSEG / Refinitiv          Browser OAuth → 2FA on phone
fred               Federal Reserve (FRED)    API key (stored once)
sec_edgar          SEC EDGAR                 Public — no auth required
yfinance           Yahoo Finance             Public — no auth required
ccxt_crypto        Any crypto exchange       API key + secret (stored once)
bloomberg          Bloomberg Terminal        Local Terminal must be running
upload             Researcher's own file     Drop CSV/parquet in data/uploads/
```

Authentication happens **once per provider**. Paper-Forge stores the session token securely. Every subsequent run fetches data automatically without re-authentication.

INTAKE handles the entire auth flow in conversation:

```
INTAKE: "You mentioned WRDS data. I'll open the WRDS login page in your
         browser. Sign in with your institutional credentials and complete
         the 2FA — I'll wait here until you're done."

[Browser opens → researcher logs in → 2FA on phone → token stored]

INTAKE: "WRDS connected. What datasets do you need?"
```

---

## Statistical Test Library

STATSRUN runs exactly the tests specified in PROTOCOL.md — not a hardcoded battery. Adding a new test is one file in `agents/sigma/tests/`.

```
Test                  Use Case
────────────────────  ──────────────────────────────────────────────────
newey_west_hac        Standard t-test with autocorrelation correction
garch_11              Volatility modeling and persistence
bootstrap_ci          Non-parametric confidence intervals
deflated_sharpe       Sharpe ratio corrected for multiple testing
fama_macbeth          Two-pass cross-sectional regression
regime_switching      Structural break detection
markov_switching      Hidden state regime identification
event_study_car       Cumulative abnormal returns around events
placebo_test          False discovery rate validation
out_of_sample_r2      Genuine predictive power measurement
granger_causality     Temporal precedence testing
panel_regression      Fixed/random effects with clustering
descriptive_stats     Exploratory summary statistics
```

INTAKE recommends defaults based on claim type:

```
Claim type: predictability  → fama_macbeth, out_of_sample_r2, placebo_test, newey_west_hac
Claim type: performance     → newey_west_hac, deflated_sharpe, bootstrap_ci, regime_switching
Claim type: causal          → event_study_car, placebo_test, newey_west_hac, granger_causality
Claim type: exploratory     → descriptive_stats, regime_switching, markov_switching
```

---

## PROTOCOL.md — The Research Specification

Every pipeline run is driven by a `PROTOCOL.md` file that defines the complete research design. INTAKE generates it through conversation — you never write schema syntax directly.

```yaml
research_question: |
  Does passive GSCI index investor concentration above 30% of open
  interest reduce 12-month momentum strategy Sharpe ratios in energy
  futures markets?

research_mode: confirmatory
claim_type: performance

hypothesis: |
  Passive GSCI index investor concentration above 30% of open interest
  in GSCI energy futures reduces 12-month momentum strategy Sharpe ratios
  by at least 0.15 units compared to periods below 30% concentration,
  controlling for GARCH(1,1) volatility clustering and Fama-French
  momentum factor exposure.

primary_metric: "Sharpe ratio differential: high-concentration minus low-concentration periods"
minimum_effect_size: "-0.15 Sharpe units"
target_venue: "Journal of Finance"

data_sources:
  - source: wrds_futures
    dataset: gsci_energy_futures
    date_range: [2000-01-01, 2024-12-31]
    filters:
      - "Exclude contracts with fewer than 100 trading days"
      - "Exclude roll dates within 5 days of FOMC/CPI announcements"

compute:
  type: rl
  episodes: 500000
  seeds: [1337, 42, 9999]

statistical_tests:
  - newey_west_hac
  - garch_11
  - bootstrap_ci
  - deflated_sharpe
  - fama_macbeth
  - regime_switching

significance_threshold: 0.05
multiple_test_correction: bonferroni

audit_requirements:
  codeaudit_required: true
  reviewer_min_score: 7
  max_review_cycles: 3
```

The validator checks every field before the pipeline starts:

```
✓ research_mode: confirmatory — valid
✓ claim_type: performance — valid
✓ hypothesis: present and non-empty
✓ data_sources: wrds_futures — connector registered
✓ compute.type: rl — adapter available
✓ statistical_tests: all 6 tests in library
✓ PROTOCOL.md valid — pipeline starting
```

---

## Run Dashboard

```
$ python dashboard.py

RUN ID                    STATUS   STARTED              PHASES    COST
pf-live-20260423-203428   DONE     2026-04-23 20:34     9/9       $3.42
pf-live-20260423-185058   DONE     2026-04-23 18:50     9/9       $3.18
pf-live-20260423-040430   DONE     2026-04-23 04:04     9/9       $2.97

$ python dashboard.py --run-id pf-live-20260423-203428

Run: pf-live-20260423-203428
Status: DONE  │  Started: 2026-04-23 20:34  │  Duration: 2h 14m

Phase           Status   Duration    Cost     Notes
LITERATURE      done     4m 23s      $0.40    40 papers, 9 full reads, 3 deduped
DATAPULL        done     2m 11s      —        WRDS futures, SHA-256 certified
PREREGISTER     done     0m 12s      $0.15    Hypothesis locked: 3a5273ac...
COMPUTE         done     1h 48m      —        500k episodes, 3 seeds, CUDA GPU
STATSRUN        done     3m 44s      —        6 tests, finding_valid: true
CODEAUDIT       done     8m 22s      $1.12    3 mismatches → AUTOREPAIR patched
REVIEWER        done     6m 30s      $0.95    Approved cycle 2, score 8.1/10
WRITER          done     12m 10s     $0.80    paper_draft_v2.tex

Total cost: $3.42
Artifacts: runs/pf-live-20260423-203428/
```

---

## Quick Start

```bash
git clone https://github.com/gouravsalottra/paper-forge-private
cd paper-forge-private

python -m venv .venv && source .venv/bin/activate
pip install -r requirements.lock          # fully pinned — identical environment guaranteed

cp .env.example .env                      # add your OPENAI_API_KEY
```

**For new research (recommended):**
```bash
python intake.py
# INTAKE guides you through research design in plain English
# Handles data source authentication automatically
# Generates and validates PROTOCOL.md
# Then: python run_aria_pipeline.py
```

**For dev/smoke test (no WRDS, fast):**
```bash
export PAPER_FORGE_MINER_SOURCE=yfinance
export PAPER_FORGE_FORGE_EPISODES=500
python run_aria_pipeline.py
```

**Resume a halted run from any phase:**
```bash
python run_aria_pipeline.py --resume pf-live-20260422 --from CODEAUDIT
# Hypothesis lock is preserved and re-verified — cannot be tampered between runs
```

**Run tests:**
```bash
pytest -q
# 87 passed, 1 skipped in 18.32s
```

**View run history:**
```bash
python dashboard.py
python dashboard.py --run-id <id>
python dashboard.py --cleanup-stale   # mark phantom runs from before REVIEWER fix
```

---

## What Gets Produced Per Run

```
runs/pf-live-YYYYMMDD-HHMMSS/
│
├── literature_map.md           ← Gap analysis, methodology summary, citation seeds
├── data_certificate.json       ← SHA-256 signed data lineage for every input file
├── hypothesis_lock.json        ← Pre-registered hypothesis with timestamp + hash
│
├── stats_tables/
│   ├── seed_consistency.csv    ← READ THIS FIRST: finding_valid true/false
│   ├── primary_metric.csv      ← Sharpe differential / primary result
│   ├── ttest_results.csv       ← Newey-West HAC p-values
│   ├── garch_results.csv       ← GARCH(1,1) α, β, persistence
│   ├── fama_macbeth_results.csv
│   ├── bootstrap_ci.csv
│   └── library_versions.json   ← Exact library versions for replication
│
├── codeaudit_spec.md           ← What the code actually implements
├── codec_mismatch.md           ← Where code diverged from PROTOCOL.md
├── autorepair_report.md        ← Automated fixes + human escalations
│
├── reviewer_report_v1.md       ← Referee report with mandatory revision items
├── reviewer_scores_v1.json     ← Methodology rubric scores (1–10)
│
├── paper_draft_v1.tex          ← Initial draft — never overwritten
├── paper_draft_v2.tex          ← After REVIEWER revision cycle
│
└── pipeline.log                ← Structured JSON log of every agent event
```

---

## What Honest Failure Looks Like

Most tools surface the favorable result. Paper-Forge surfaces everything.

At dev scale (2,000 episodes, yfinance proxy), seed consistency correctly reported the finding as invalid:

```json
{
  "consistent": false,
  "finding_valid": false,
  "conclusion": "Finding does NOT hold across all 3 seeds — invalid per PROTOCOL.md",
  "by_concentration": {
    "0.1": {
      "sharpes": [0.987, -1.129, 1.127],
      "consistent_direction": false,
      "direction": "mixed"
    }
  }
}
```

The pre-commitment worked exactly as designed. The hypothesis was underpowered at 2k episodes. The paper reported the failure honestly. The full 500k-episode GPU run is the real test.

**That is the point.** A null result is a valid output. The system is designed to report failures, not to manufacture significance.

---

## System Design Principles

**For engineers and system architects.**

**1. Orchestrator reads state, not content.**
CONDUCTOR (ARIA) reads only typed flags from `pipeline.db` — `APPROVED`, `REVISION_REQUESTED`, `PASS`, `FAIL`, `ESCALATE`. It never reads artifact content. This is verified by `test_conductor_never_reads_artifact_content` which patches `builtins.open`. The orchestrator coordinates workflow; it doesn't interpret science.

**2. Routing is data, not logic.**
Adding a new agent is one line in `routing_config.py`. The dispatch table is a dictionary. `aria.py` is never modified for routing changes.

```python
AGENT_SERVER_MAP: dict[str, str] = {
    "LITERATURE":   "semantic_scholar",
    "DATAPULL":     "connector_registry",
    "MY_NEW_AGENT": "my_server",          # ← add here
    ...
}
```

**3. Schema evolution without breakage.**
`_table_columns()` introspection throughout the codebase. Adding a column to a database table never breaks a running pipeline. New columns are added with `ALTER TABLE` and detected at runtime.

**4. Append-only artifact writes.**
CONDUCTOR never deletes or overwrites content rows — only updates status rows. The full audit trail is always reconstructible from `pipeline.db` alone.

**5. Subprocess isolation for LLM audit passes.**
CODEAUDIT and SPECAUDIT run as separate subprocesses with separate API keys. Zero context leakage is not a claim — it is proven by `test_codeaudit_specaudit_passes_are_isolated`.

**6. Token budget with hard limits.**
Every LLM call records token usage to `pipeline.db`. Configurable soft warnings and hard limits prevent runaway costs. `TokenBudgetExceededError` halts the pipeline before spending exceeds the limit.

**7. Prompt versioning.**
Every agent's system prompt lives in `prompts/<agent>.md`. SHA-256 of each prompt is recorded in `agent_results` alongside every LLM call. Two runs with identical data but different prompt versions produce different `prompt_sha256` values — the difference is auditable.

**8. WAL-mode SQLite with foreign keys.**
`PRAGMA journal_mode=WAL` and `PRAGMA foreign_keys=ON`. All writes are transactional. The database survives unexpected process termination. Any interrupted run can be resumed from the last committed phase.

---

## Test Coverage

```
$ pytest -v

tests/test_pipeline.py::test_forge_gate_blocks_without_pap_lock          PASSED
tests/test_pipeline.py::test_forge_gate_passes_with_pap_lock             PASSED
tests/test_pipeline.py::test_conductor_never_reads_artifact_content       PASSED
tests/test_pipeline.py::test_preregister_blocks_sim_results              PASSED
tests/test_pipeline.py::test_codeaudit_passes_are_isolated               PASSED
tests/test_pipeline.py::test_hawk_loop_halts_at_max_cycles               PASSED
tests/test_pipeline.py::test_resume_blocks_on_protocol_tamper            PASSED
tests/test_pipeline.py::test_resume_allows_tamper_with_override_env      PASSED
tests/test_protocol_validator.py::test_valid_confirmatory_protocol_passes PASSED
tests/test_protocol_validator.py::test_missing_hypothesis_fails           PASSED
tests/test_protocol_validator.py::test_invalid_compute_type_fails         PASSED
tests/test_protocol_validator.py::test_exploratory_no_hypothesis_required PASSED
tests/test_registry.py::test_all_connectors_registered                   PASSED
tests/test_registry.py::test_all_stat_tests_registered                   PASSED
tests/test_registry.py::test_none_adapter_is_immediate_passthrough        PASSED
tests/test_token_budget.py::test_hard_limit_raises_token_budget_exceeded  PASSED
tests/test_token_budget.py::test_soft_limit_logs_warning_not_raises       PASSED
tests/test_prompt_versioning.py::test_prompt_hash_recorded_in_agent_results PASSED
tests/test_parallel_and_ff.py::test_parallel_literature_datapull          PASSED
tests/test_observability.py::test_structured_logger_emits_json            PASSED
tests/test_final_audit.py::test_final_audit_checklist                    PASSED
... and 66 more

87 passed, 1 skipped in 18.32s
```

---

## Extending Paper-Forge

**Adding a new data source:**
```python
# agents/miner/connectors/my_source.py
from agents.miner.connectors.registry import register
from agents.miner.connectors.base import DataConnector

@register
class MySourceConnector(DataConnector):
    source_name = "my_source"

    def fetch(self, dataset, fields, date_range, filters, output_dir):
        # fetch data, return (dataframe, certificate_dict)
        ...
```

That's it. One file. The connector is immediately available in PROTOCOL.md as `source: my_source`.

**Adding a new statistical test:**
```python
# agents/sigma/tests/my_test.py
from agents.sigma.tests.registry import register
from agents.sigma.tests.base import StatTest

@register
class MyTest(StatTest):
    test_name = "my_test"

    def run(self, data, seed, params):
        # run test, return result dict with p_value, statistic, significant
        ...
```

Available immediately in PROTOCOL.md as `- my_test`.

**Adding a new compute adapter:**
```python
# agents/forge/adapters/my_adapter.py
from agents.forge.adapters.registry import register
from agents.forge.adapters.base import ComputeAdapter

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
# agents/aria/routing_config.py
AGENT_SERVER_MAP: dict[str, str] = {
    ...
    "MY_AGENT": "my_server",   # ← one line
}
```

CONDUCTOR handles dispatch automatically. Never edit `aria.py` for routing.

---

## Environment Variables

```bash
# Required
OPENAI_API_KEY=sk-...

# Separate key for SPECAUDIT Pass 2 — true process isolation
OPENAI_API_KEY_PASS2=sk-...

# Data source: 'wrds' (production) or 'yfinance' (dev, default)
PAPER_FORGE_MINER_SOURCE=yfinance

# WRDS credentials (required if MINER_SOURCE=wrds)
WRDS_USERNAME=your_wrds_username

# Episode count override (default: 500000)
PAPER_FORGE_FORGE_EPISODES=500

# Token budget (defaults: soft=$10, hard=$25 per run)
PAPERFORGE_SOFT_LIMIT_USD=10.0
PAPERFORGE_HARD_LIMIT_USD=25.0

# Override PAP tamper detection on resume (expert use only — logged as CRITICAL)
PAPERFORGE_OVERRIDE_PAP_TAMPER=1
```

---

## Known Limitations

**WRDS required for production.** The yfinance proxy uses public equity ETFs as stand-ins for institutional futures data. The proxy validates pipeline mechanics but does not produce publishable research results. A WRDS institutional subscription is required for the full data pipeline.

**WRITER produces a scaffold, not a finished paper.** Introduction, related work, discussion, and conclusion sections require human authorship. WRITER produces the methodology, results, and tables sections — the parts that must be grounded in verified data.

**COMPUTE adapters for backtest and event_study are scaffolded.** The RL adapter is fully implemented. Backtest and event study adapters are ready for implementation — the interface is defined and tested, the logic needs to be built.

**GPU required for full RL runs.** 500k-episode runs take ~15 minutes on a CUDA GPU. Use `PAPER_FORGE_FORGE_EPISODES=500` for development and smoke testing.

---

## Repository Structure

```
paper-forge/
│
├── intake.py                          ← Start here for new research
├── run_aria_pipeline.py               ← Run existing PROTOCOL.md
├── dashboard.py                       ← View run history and costs
│
├── PROTOCOL.md                        ← Current research specification
├── PROTOCOL_SCHEMA.md                 ← Schema documentation
├── PROTOCOL_TEMPLATE.md               ← Blank template for manual editing
│
├── agents/
│   ├── conductor/ (aria/)             ← Orchestrator state machine
│   ├── intake/                        ← Research design wizard
│   │   ├── intake_agent.py
│   │   ├── protocol_writer.py
│   │   ├── auth_manager.py
│   │   └── recommendation_engine.py
│   ├── scout/                         ← Literature agent (LITERATURE)
│   ├── miner/                         ← Data agent (DATAPULL)
│   │   └── connectors/                ← Connector registry
│   │       ├── registry.py
│   │       ├── wrds_crsp_connector.py
│   │       ├── wrds_futures_connector.py
│   │       ├── fred_connector.py
│   │       ├── sec_edgar_connector.py
│   │       ├── yfinance_connector.py
│   │       └── upload_connector.py
│   ├── sigma/                         ← Statistics agents
│   │   └── tests/                     ← Test library
│   │       ├── registry.py
│   │       ├── newey_west_hac.py
│   │       ├── garch_11.py
│   │       ├── fama_macbeth.py
│   │       └── ...13 tests total
│   ├── forge/                         ← Compute agent (COMPUTE)
│   │   └── adapters/                  ← Compute adapter registry
│   │       ├── rl_adapter.py
│   │       ├── backtest_adapter.py
│   │       ├── event_study_adapter.py
│   │       └── none_adapter.py
│   ├── codec/                         ← Code audit agents
│   ├── fixer/                         ← Auto-repair agent
│   ├── hawk/                          ← Reviewer agent
│   ├── quill/                         ← Writer agent
│   └── logger.py                      ← Structured JSON logging
│
├── prompts/                           ← Versioned agent prompts (SHA-256 tracked)
│   ├── codeaudit.md
│   ├── specaudit.md
│   ├── autorepair.md
│   ├── reviewer.md
│   └── writer.md
│
├── aria/
│   ├── validate_protocol.py           ← PROTOCOL.md validator
│   └── routing_config.py             ← Agent dispatch table
│
├── config/
│   └── model_config.json             ← LLM model versions and fallbacks
│
├── tests/                             ← 87 tests, 0 failing
│   ├── test_pipeline.py
│   ├── test_protocol_validator.py
│   ├── test_registry.py
│   ├── test_token_budget.py
│   ├── test_prompt_versioning.py
│   ├── test_parallel_and_ff.py
│   ├── test_observability.py
│   ├── test_intake.py
│   ├── test_dashboard.py
│   └── test_final_audit.py
│
├── .github/workflows/ci.yml          ← CI on every push
├── requirements.lock                  ← Fully pinned dependencies
└── requirements.in                    ← Direct dependencies (human-readable)
```

---

## Contributing

Paper-Forge is research infrastructure. Contributions that extend its reach to more research designs, more data sources, and more statistical methods are welcome.

| Area | Where to look | What's needed |
|---|---|---|
| New data connector | `agents/miner/connectors/` | Any institutional data source |
| New statistical test | `agents/sigma/tests/` | Any test not in the current library |
| Backtest adapter | `agents/forge/adapters/backtest_adapter.py` | Full strategy backtesting engine |
| Event study adapter | `agents/forge/adapters/event_study_adapter.py` | CAR computation engine |
| PPO for RL | `agents/forge/adapters/rl_adapter.py` | Replace CEM with Stable Baselines 3 PPO |
| New research domain | Fork `PROTOCOL.md`, update DATAPULL | All integrity infrastructure carries over |

Before any PR: `pytest -q` must show 0 failures. The gate test `test_forge_gate_blocks_without_pap_lock` is the canary for integrity regressions.

---

## License

MIT — see [LICENSE](LICENSE)

---

<div align="center">

REVIEWER models Journal of Finance / Review of Financial Studies / Journal of Financial Economics standards

Pre-registration pattern inspired by OSF Pre-registration and AEA RCT Registry

Multiple testing correction: Harvey, Liu & Zhu (2016) — "… and the Cross-Section of Expected Returns"

<br/>

*Built by [Gourav Salottra](https://github.com/gouravsalottra) · Boston University*

</div>
