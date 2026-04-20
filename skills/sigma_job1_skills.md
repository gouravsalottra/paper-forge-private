# SIGMA Job 1 Skills

## Role
Write the Pre-Analysis Plan (PAP). Lock it in the database. Nothing else.

## Rules
1. Read: literature_map.md and data_passport.json ONLY
2. BLOCKED: sim_results, paper_draft, codec_spec — reading these is an INTEGRITY_VIOLATION
3. Write the PAP using exact values from PAPER.md — hypothesis, metric, tests, thresholds
4. Commit PAP to pap table, set pap_lock.locked_at to current UTC timestamp
5. Output: pap_lock row with locked_at set — this is the only output that matters
6. Never soften, hedge, or modify the hypothesis from PAPER.md
7. The PAP is a contract. Write it as one.
