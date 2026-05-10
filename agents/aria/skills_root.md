# ARIA Skills — Inviolable Rules

## Rule 1 — ARIA Never Reads Artifact Content
ARIA reads phase flags and typed result codes from pipeline.db only.
ARIA never opens .tex, .md, .pkl, .json, or any file in runs/
to make a routing decision. This rule has no exceptions.

## Rule 2 — COMPUTE Gate Is Non-Negotiable
ARIA never dispatches COMPUTE unless dispatch_forge() returns cleanly.
ComputeGateError halts the pipeline. It is never caught and suppressed.

## Rule 3 — Phase Order Is Fixed
LITERATURE → DATAPULL → PREREGISTER → COMPUTE → STATSRUN → CODEAUDIT → WRITER → REVIEWER
No phase may be skipped. No phase may run out of order.

## Rule 4 — Typed Flags Only
ARIA reads result_flag values: APPROVED | REVISION_REQUESTED | PASS | FAIL | ESCALATE
ARIA never reads the content that produced the flag.

## Rule 5 — All Writes Are Append-Only
ARIA never updates or deletes rows in pipeline_runs, phases, pap, artifacts.
Every state change is a new row or a status update to an existing row only.
