# ARIA Skills — Inviolable Rules

## Rule 1 — ARIA Never Reads Artifact Content
ARIA reads phase flags and typed result codes from state.db only.
ARIA never opens .tex, .md, .pkl, .json, or any file in paper_memory/
to make a routing decision. This rule has no exceptions.

## Rule 2 — FORGE Gate Is Non-Negotiable
ARIA never dispatches FORGE unless dispatch_forge() returns cleanly.
ForgeGateError halts the pipeline. It is never caught and suppressed.

## Rule 3 — Phase Order Is Fixed
SCOUT → MINER → SIGMA_JOB1 → FORGE → SIGMA_JOB2 → CODEC → QUILL → HAWK
No phase may be skipped. No phase may run out of order.

## Rule 4 — Typed Flags Only
ARIA reads result_flag values: APPROVED | REVISION_REQUESTED | PASS | FAIL | ESCALATE
ARIA never reads the content that produced the flag.

## Rule 5 — All Writes Are Append-Only
ARIA never updates or deletes rows in pipeline_runs, phases, pap, artifacts.
Every state change is a new row or a status update to an existing row only.
