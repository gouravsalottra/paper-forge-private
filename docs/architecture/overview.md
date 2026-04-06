# PAPER-FORGE — Architecture Overview

## Product thesis

PAPER-FORGE is an **auditable autonomous research system** for finance, fintech, and quantitative papers. The core promise is procedural: **commit hypotheses and analysis plans before consuming results**, run **bounded** simulation and empirical work, and retain enough structure to **prove** whether the finished paper matches the plan that was locked in advance.

This is not “LLM writes a paper.” It is a **governed research pipeline** where orchestration, state, and artifacts are first-class—and where the moat is verification, not volume.

## Why this architecture exists

Finance research fails in predictable ways when systems are opaque: silent p-hacking, moving goalposts, unrepeatable data pulls, and code that diverges from prose. PAPER-FORGE is built to make those failure modes **expensive to commit** and **cheap to detect**.

The architecture separates concerns deliberately:

- **Orchestration and truth** live in a small control plane (ARIA + SQLite).
- **Heavy work** runs in bounded agents with strict write lanes.
- **Scientific discipline** is enforced by a stacked verification layer—not by prompt text.

## Moat stack (ordered)

1. **PAP (Pre-Analysis Plan)** — Hypotheses and planned analyses are committed **before** FORGE consumes outcomes. `pap_lock` sealing is a hard gate.
2. **DataPassport** — A signed dataset manifest capturing **source, query, rolls, adjustments, and lineage**. This is the empirical anchor.
3. **CODEC** — A bidirectional audit engine between **implementation and narrative**:
   - Pass 1: code → extracted spec
   - Pass 2: paper → audit against code

Together, these create defensibility: competitors can copy a chat UI; they cannot copy **credible reproducibility under adversarial review**.

## The two methods layers

### Layer 1 — Market Ecology

This is the scientific framing for exploratory dynamics: heterogeneous agents, passive-capital-style experiments, mutation/selection pressure, population turnover, and meta-learning across runs. It is **not** a single monolithic “research worker”; it is a population of bounded processes whose outputs must still pass the verification stack.

### Layer 2 — Verification Stack

This is the discipline layer:

- **PAP commitment** freezes intent.
- **DataPassport** binds data to claims.
- **CODEC** audits code ↔ paper consistency.
- **HAWK** supplies hostile review pressure on the final artifact.

Market ecology generates candidates; verification decides what survives.

## Control plane

**ARIA** is the orchestrator and control plane. It:

- Parses `PAPER.md` (and related intent documents) into a task graph.
- Owns **`state.db`**: phases, routing, checkpoints, hashes, approvals, and locks.
- Enforces restart-safe transitions and audit-critical gates.

If ARIA is wrong, the system misroutes. If SQLite is wrong, you lose auditability. That is why the control plane stays small, explicit, and transactional.

## Data plane

The data plane is where agents execute: literature pulls, dataset construction, statistical work, simulation/training, LaTeX compilation, and review. Outputs are **artifacts** (files, tables, figures, bundles) referenced from control-plane state.

The data plane is allowed to be messy in *volume*; the control plane is not allowed to be messy in *truth*.

## Why SQLite first

SQLite is the **authoritative system of record** for orchestration: deterministic, embeddable, easy to hash, easy to back up, and trivial to diff. It supports transactional phase transitions and gives you a single artifact (`state.db`) that anchors the audit story.

Networked databases are not wrong in principle—they are **unnecessary Day 1 complexity** for the control plane’s job.

## Why PAP before FORGE

FORGE is where compute-heavy simulation and training live—the place where subtle overfitting and “result-driven coding” appear first. Requiring **PAP commitment** and **`pap_lock` sealing** before FORGE starts is the architectural embodiment of “hypotheses before results.”

## Why CODEC is the moat

PAP and DataPassport prevent casual cheating. **CODEC** is what makes cheating **detectable** under real-world messiness: code drifts, figures get relabeled, prose smuggles claims. A bidirectional audit loop turns consistency into an engineering problem with receipts.

## Daily operator mental model

- **Control plane** = ARIA + SQLite (`state.db`): phases, locks, checkpoints, routing, hashes.
- **Scientific discipline** = PAP + DataPassport + CODEC (+ HAWK as external pressure).
- **Heavy work** = literature + data + statistics + simulation + writing + review—each in its lane.

When in doubt, ask: **what changed in `state.db`, and what artifact proves it?**
