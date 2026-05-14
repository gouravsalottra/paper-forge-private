# MASTER_CONTEXT — Paper-Forge Ground Truth
# Last updated: 2026-04-23
# This file is the single source of truth for any new session.
# Read this before reading any other file.

## PRE-REGISTERED SPECIFICATION (from PAPER.md — do not contradict)
Seeds (pre-registered): [1337, 42, 9999]
Concentrations: [0.10, 0.30, 0.60]
Episodes required: 500,000 minimum
Significance threshold: p < 0.05 (primary), p < 0.0083 (Bonferroni, 6 tests)
Minimum effect size: Sharpe differential >= -0.15
Concentration threshold: 30% (pre-registered, not chosen after data)

# Paper-Forge Current State

## What works
- Full pipeline runs 8/8 phases and marks done in pipeline.db
- REVIEWER reviews research quality only (CSV/JSON) — never sees LaTeX
- REVIEWER gates WRITER behind approved_for_quill=true
- WRITER renders deterministic LaTeX scaffold from verified data only
- CODEAUDIT audit runs bidirectionally
- Statistical battery runs (HAC, GARCH, Bonferroni, Fama-MacBeth, Markov, DCC-GARCH)
- Modal authenticated (gouravsalottra workspace)
- MODEL: standardized to gpt-4o per STEP 0 audit
- Azure OpenAI connected (gpt-4o)
- 27 tests passing

## What is blocking publication

### BLOCKER 1 — Simulation underpowered (CRITICAL)
- Current: 2000 episodes local CPU, 3 seeds
- Required: 500000 episodes Modal GPU, 10+ seeds
- Fix: modal run --detach agents/forge/modal_run.py --n-episodes 500000
- Why blocked: p=0.250517, Bonferroni threshold=0.008333. Finding is not significant.
  This is a data problem not a code problem.

### BLOCKER 2 — CODEAUDIT mismatch (HARD BLOCK)
- 3 minor mismatches, 9 unverified params
- REVIEWER correctly blocks WRITER until CODEAUDIT is clean
- Fix: resolve mismatches in AUTOREPAIR, then re-run CODEAUDIT

### BLOCKER 3 — Seed consistency failed
- consistent=False across 3 seeds
- Required: 10 seeds with consistent directional evidence
- Fix: increase seeds in forge config, re-run simulation

### BLOCKER 4 — Fama-MacBeth uses proxy factors
- mkt_rf_proxy instead of real Fama-French factors
- Fix: DATAPULL must pull real FF factors from WRDS

## Architecture decisions made (do not revert)
- REVIEWER never reads LaTeX or PDF — reviews CSV/JSON only
- WRITER generates no LLM prose — deterministic scaffold only
- Human writes paper prose on top of WRITER scaffold
- AUTOREPAIR is diagnostic only, never blocks pipeline completion
- _paper_is_publishable gate: 1500 unique words, 1 WRITER+REVIEWER cycle

## Pipeline order
LITERATURE → DATAPULL → PREREGISTER → COMPUTE → STATSRUN → CODEAUDIT → REVIEWER → WRITER

## Key files
- agents/hawk/hawk.py — research quality reviewer
- agents/quill/quill.py — deterministic LaTeX formatter
- agents/aria/aria.py — pipeline conductor
- agents/forge/modal_run.py — Modal GPU simulation
- PAPER.md — research specification
- pipeline.db — pipeline state

## Next action
Run Modal simulation at 500k episodes with real data.
Nothing else should be worked on until this is done.
modal run --detach agents/forge/modal_run.py --n-episodes 500000
