# Infrastructure — Where to Run What

This document is an operator map: **which environment owns which risk**, and what must never run in the wrong place.

## Summary

| Surface | Best for | Owns | Avoid |
|--------|----------|------|------|
| **Cursor (local IDE)** | Repo work, ARIA/SQLite orchestration code, architecture, docs, codegen | Fast iteration on the control plane | Long GPU training jobs |
| **SQLite (`state.db`)** | Authoritative orchestration state | Phases, locks, checkpoints, hashes, routing | Large binary blobs (store paths + hashes) |
| **WRDS** | Institutional finance datasets (when entitled) | Canonical academic data pulls | Ad-hoc scraping substitutes without manifest updates |
| **Fallback public connectors** | Replication when WRDS unavailable | Transparent lineage via DataPassport | Silent substitution without disclosure |
| **Modal** | Remote GPU training, long batch simulations | Heavy FORGE workloads | Interactive debugging loops |
| **Colab Pro** | Notebooks, prototypes, SIGMA/FORGE debugging | Fast exploration | Authoritative manifests you do not snapshot |
| **Local machine** | Secrets, private connectors, “never leaves laptop” data | MINER connectors that require local-only access | Untracked manual edits to canonical artifacts |
| **LaTeX compiler + MCP latex** | QUILL compile pipeline | Deterministic PDF builds from pinned sources | Hand-editing PDFs as source of truth |
| **MCP servers** | Cross-cutting capabilities | arxiv literature, data connectors, modal job launcher, latex compile | Becoming a second memory backbone (Day 1) |

## Cursor vs Colab Pro vs Modal vs local

### Cursor (development home)

Use Cursor for:

- Implementing **ARIA** and SQLite migrations/schema discipline.
- Building the **task graph** and orchestration tooling.
- Writing **CODEC** audit tooling and tests.
- Authoring architecture docs (this cockpit).

**Why it exists:** it is the fastest loop for correctness in the **control plane**.

### Colab Pro (interactive lab)

Use Colab for:

- Exploratory plots and diagnostics.
- Quick SIGMA checks and FORGE prototypes.
- Reading intermediate outputs when iteration speed matters more than audit finality.

**Why it exists:** notebook speed.

**What should never happen:** treating a Colab notebook as the **authoritative** manifest or PAP record without exporting into the governed artifact paths + SQLite receipts.

### Modal (remote heavy compute)

Use Modal for:

- Long-running GPU training.
- Large batch simulation sweeps that benefit from cloud scale.

**Why it exists:** keeps heavy work off laptops and enables repeatable remote execution—**when** jobs are staged with clear inputs/outputs and logged back into artifacts.

**What should never happen:** thousands of tiny fragmented GPU kernels with no batching story—see performance notes in the dashboard.

### Local machine (secrets + sensitive connectors)

Use local for:

- API keys and credentials that must not transit unnecessarily.
- Connectors to data sources that are contractually local-only.

**Why it exists:** risk minimization.

**What should never happen:** “shadow pipelines” that produce figures without updating DataPassport + `state.db` checkpoints.

## MCP servers (capability plane, not memory backbone)

MCP servers are **tool endpoints** (arxiv, data, modal, latex). They are not the Day 1 memory backbone; **SQLite remains authoritative** for orchestration state.

Operational rule: every MCP-mediated action should still land as **a routed step + artifact pointers + hashes** in the control plane where applicable.

## Operational best practices

1. **One authoritative `state.db` per research run** (or explicit run IDs if you shard—still deterministic migrations).
2. **Never bypass PAP / `pap_lock` to start FORGE**—if you do, you are no longer running PAPER-FORGE; you are hacking.
3. **DataPassport follows the data**—if the query changes, the manifest changes.
4. **CODEC mismatches are serial adjudication**—don’t “fix the PDF” without a corresponding fix record.
5. **Checkpoint before irreversible transitions**—restart-safe operations are a product feature.

## What breaks when infra is misused

- **Colab as source of truth** → audit gaps.
- **Modal without staging** → cost blowups + fragmented GPU utilization.
- **Local secrets in CI** → leaks; keep them local or in a vault pattern explicitly.
- **MCP as implicit memory** → duplicated state; SQLite must remain SoT.
