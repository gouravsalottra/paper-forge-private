# Shim Pattern

Paper-Forge intentionally keeps a small set of compatibility shims so old import paths continue to work during refactors.

## Why this exists
- We renamed/moved several agent modules into package directories.
- External scripts and historical tests may still import legacy paths.
- Shims prevent breaking those callers while keeping canonical code in one place.

## Canonical rule
- **Implementation lives only in canonical package modules** (for example `agents/literature/literature.py`).
- **Shim files must contain imports only** (no logic).

## Current shim families
- Root compatibility packages: `aria/`, `conductor/` (thin imports to canonical modules).
- Flat agent shims: `agents/hawk.py`, `agents/miner.py`, `agents/quill.py`, `agents/scout.py`.

## Dependency files
- Canonical source: `requirements.in`
- Canonical lock/install target: `requirements.lock`
- `requirements.txt` is a legacy forwarder to `requirements.lock`
