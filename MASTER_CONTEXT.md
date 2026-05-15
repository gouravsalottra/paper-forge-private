# MASTER_CONTEXT - Thrivarc Ground Truth

Read `THRIVARC_MASTER_CONTEXT.md` first. That file is the canonical product
and engineering context for current Thrivarc work.

The old Paper-Forge context that referenced `pipeline.db`, `paper_memory`,
the deterministic Topic 4 simulation, and the legacy 8-phase conductor is no
longer the source of truth for product implementation.

## Current Canonical Runtime

- API state: PostgreSQL through `DATABASE_URL` and `db.connection.get_db_connection`.
- Production environment: `ENVIRONMENT=production`.
- Artifact state: Azure Blob Storage through `storage.blob`.
- Frontend state: API responses plus Server-Sent Events only.
- Canonical session routes: `/api/sessions/*`.
- Website compatibility routes: `/runs/*`, delegated to canonical sessions unless
  non-production legacy mode is explicitly enabled.

## Legacy Boundary

Legacy code is kept only for historical tests and compatibility shims. It must
not be treated as active product truth:

- `pipeline.db`
- `paper_memory/`
- `runs/`
- `outputs/`
- `run_pipeline.py`
- `agents/conductor/*`

Production must never read or write legacy SQLite state.
