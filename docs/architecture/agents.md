# Agents — Roles, Lanes, and Guardrails

Each agent has a **strict write scope**. ARIA coordinates; agents execute. This table is the operator contract.

| Agent | Role | Purpose | Inputs | Outputs | Reads from | Writes to | Tools used | Why it exists | Failure mode | Guardrails |
|------|------|---------|--------|---------|------------|-----------|------------|---------------|--------------|------------|
| **ARIA** | Orchestrator / control plane | Parse `PAPER.md`, build task graph, route work, enforce phases, checkpoints, and locks | Objectives, repo context, agent statuses, artifact pointers | Routed tasks, phase transitions, checkpoints, audit trail | Repo files, agent logs, artifact metadata | `state.db` (phases, routing, checkpoints, `pap_commit`, `pap_lock`), not agent artifact tables | Cursor/IDE, SQLite, MCP orchestration | Without ARIA, you get ad-hoc scripts—not a reproducible system | Wrong task graph → wasted work; bad routing → context drift | Transactional transitions; explicit checkpoints; hash receipts |
| **SCOUT** | Literature agent | Map prior work, extract claims, position novelty | Topic brief, constraints, seed papers | Literature map, bibliography artifacts, novelty notes | Open-access sources, internal library | **Literature artifacts only** | MCP arxiv server, PDF parsers, citation tooling | Finance moves fast; you need structured lit coverage before building | Missed key paper → false novelty | Bounded queries; store sources; no data-plane writes |
| **MINER** | Data agent | Retrieve, stitch, validate datasets; sign manifests | Data requirements, time windows, identifiers | Datasets + **DataPassport** manifest (lineage) | Raw vendor/public feeds | **Data + dataset manifest only** | WRDS (if entitled), fallback connectors, local secrets connectors | Empirical claims require anchored data | Bad joins / silent snooping | Manifest signing; validation checks; explicit fallbacks |
| **SIGMA** | Statistics + PAP | Pre-register hypotheses/analyses; later tables/figures | PAP inputs, cleaned datasets, model specs | **PAP rows**; stats tables; figures | Approved datasets, PAP drafts | **PAP rows, stats tables, figures** | Stats stack, notebooks (Colab), MCP modal hooks for jobs | Separates planning from peeking at results | Optional stopping; p-hacking | PAP before FORGE; bounded diagnostics lists |
| **FORGE** | Simulation / codegen / training | Build sim repo, environments, training/eval jobs | Sealed PAP + manifests + code sketches | Simulation code bundle, logs, metrics, checkpoints | Staged datasets, prior code | **Simulation code + sim outputs only** | Modal (GPU), vectorized sims, experiment runners | This is where compute lies—must be gated | Overfitting; code drift | **Blocked until PAP committed + `pap_lock` sealed** |
| **CODEC** | Code–paper consistency engine | Extract spec from code; audit paper claims vs implementation | Code bundle, paper draft, figure tables | Spec artifacts, audit reports, fix requests | Repo, outputs from FORGE/QUILL | **Spec, audits, fix requests only** | Static analysis, diff tools, test harnesses | Turns “trust us” into checkable structure | False negatives/positives if spec weak | Two-pass loop; mismatch adjudication serial |
| **QUILL** | Writing agent | Compile LaTeX from controlled artifacts | Structured outline, tables/figures, citations | LaTeX sources + PDF | Approved artifacts only | **LaTeX only** | LaTeX toolchain, MCP latex server | Paper is an output—not the source of truth | Manual edits bypass traceability | Build only from pinned artifact hashes |
| **HAWK** | Hostile referee | Attack claims, methods, robustness; force revisions | Near-final PDF + evidence bundle | Review report, required revisions list | Paper + appendix + data passport pointers | **Review artifacts only** | Rubric scoring, red-team prompts, checklist tools | Conferences reject for a reason—simulate early | “Friendly” review | Structured dimensions; cannot edit paper directly |

## Read vs write discipline

- **ARIA** may *read* widely; it *writes* orchestration tables and locks.
- **Execution agents** write **only** their lane tables / artifact namespaces.
- **Verification agents** (CODEC, HAWK) must not silently mutate implementation artifacts.

## Moat alignment

- **PAP** is primarily **SIGMA** output + **ARIA** commit/seal mechanics.
- **DataPassport** is primarily **MINER** output.
- **CODEC** is the bidirectional audit loop between **FORGE/QUILL** outputs and **spec truth**.
