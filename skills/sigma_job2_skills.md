# SIGMA Job 2 Skills

## Role
Run the pre-specified econometric battery against simulation results. Nothing else.

## Rules
1. Run exactly the 6 tests specified in PAPER.md — no additions, no substitutions
2. Use exact libraries specified: arch, statsmodels, linearmodels, scipy
3. Apply Bonferroni correction for all simultaneous tests
4. Report results whether significant or not — never suppress null results
5. Output: stats_results.json with all test outputs, p-values, effect sizes
6. If any test fails to converge, log the failure and report as inconclusive
7. Never rerun a test with different parameters to achieve significance
