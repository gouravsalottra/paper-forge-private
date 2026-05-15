# THRIVARC_MASTER_CONTEXT - Canonical Product Context

This repository is now Thrivarc: an evidence-first agentic research engine for
empirical finance and economics.

## Product Promise

Writer is last and never invents numbers.

The product takes a natural-language research question, creates a locked
Research Blueprint, runs evidence and method agents, defends the evidence
through reviewer and audit gates, and unlocks paper writing only when the gate
passes.

## Canonical State Contract

There is one production state path:

- PostgreSQL stores sessions, blueprints, phases, reviewer scores, repair logs,
  deviation register rows, co-author state, and billing counters.
- Azure Blob Storage stores DataPassport files, pre-registration certificates,
  analysis outputs, audit reports, reviewer scorecards, verification reports,
  and paper artifacts.
- Server-Sent Events on `/api/sessions/{id}/stream` are the realtime channel.
- The frontend reads from APIs and SSE only; it must not infer product truth in
  browser state.

SQLite is allowed only for local tests and isolated development. Production
must fail closed if `DATABASE_URL` is not PostgreSQL.

## Canonical API Surface

- `/guide/*` validates and explains the research contract.
- `/api/sessions/*` is the canonical product workflow.
- `/api/data/*` handles upload and preview.
- `/runs/*` exists only as a compatibility facade for old website links. It
  delegates to `/api/sessions/*` by default.

## Legacy Code Boundary

The following are legacy Paper-Forge artifacts. They are not the current product
source of truth and must not be used by production unless a non-production
legacy flag is explicitly enabled for historical testing:

- `pipeline.db`
- `paper_memory/`
- `runs/`
- `outputs/`
- `run_pipeline.py`
- `agents/conductor/*`
- direct legacy phase tables such as `pipeline_runs`

## Active Agent Architecture

The LLM-first path uses:

- `api/prompts.py` for versioned agent prompts.
- `api/llm_caller.py` for JSON-only LLM calls, retries, and model sanitation.
- `api/method_agent.py` for study-specific method specifications.
- `api/stats_agent.py` for study-specific statistical test batteries.
- `api/code_audit_agent.py` for code and leakage audit.
- `api/sessions.py` for canonical orchestration and SSE events.

Registries may remain as fallback only. They are not the primary research
engine.

## Deployment Truth

- Model deployment: `gpt-4o`.
- Azure OpenAI key environment variable: `OPENAI_API_KEY`.
- Azure OpenAI endpoint: configured in code for the deployed Thrivarc resource.
- Container production must include `ENVIRONMENT=production`.

## Working Rule For Future Agents

If a code path reads `pipeline.db`, `paper_memory`, `runs/`, or `outputs/` in
production, treat that as a bug unless the user explicitly asks to work on
legacy Paper-Forge tests.
