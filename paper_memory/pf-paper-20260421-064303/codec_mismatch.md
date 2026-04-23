# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T15:57:50+00:00

## parameter_comparison (PAPER.md-specified only)
total_specified_params: 43
matched: 34
mismatched: 2
not_found_in_code: 7
match_ratio: 0.791

## mismatched_parameters
- Adjustment method: paper=ratio_backward | code=yfinance auto_adjust=True
- Seed policy: paper=seeds = [1337, 42, 9999] | code=Seed consistency validation implemented; bootstrap shown with seed=1337; full seed list [1337, 42, 9999] NOT FOUND in provided code context

## not_found_in_code
- Roll convention (paper specifies: ratio_backward)
- Fitness evaluation frequency (paper specifies: evaluated every 1000 training steps)
- Training episodes (paper specifies: 500,000 minimum across all scenarios and seeds)
- Pre-Analysis Plan Status (paper specifies: UNCOMMITTED — must be committed by SIGMA_JOB1 before FORGE runs. FORGE gate will reject any run where this status is not COMMITTED in pap_lock.)
- CODEC bidirectional audit requirement (paper specifies: required before QUILL writes paper)
- HAWK minimum score (paper specifies: 7/10 on methodology rubric)
- Maximum HAWK revision cycles (paper specifies: 3)

## acknowledged_deviations
acknowledged: 1 (WRDS/yfinance proxy, roll convention — documented in DataPassport)
genuine_mismatches: 1

## verdict: WARN
severity: Minor
issue: description_ambiguous: 1 minor mismatches, 1 acknowledged deviations documented in DataPassport, 7 unverified params. QUILL will address in limitations section.
