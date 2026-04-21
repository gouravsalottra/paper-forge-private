# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T13:13:28+00:00

## term_coverage
shared_terms: ['bonferroni', 'concentration', 'fama', 'garch', 'hac', 'lookback', 'macbeth', 'markov', 'momentum', 'newey', 'regime', 'rolling', 'seed', 'sharpe', 't-test', 'threshold', 'volatility', 'west', 'window']
missing_in_pass2 (in code but not paper): ['bootstrap', 'p-value']
missing_in_pass1 (in paper but not code): ['annualized', 'significance']
term_overlap_ratio: 0.826

## numeric_comparison
pass1_numeric_count: 258
pass2_numeric_count: 234
ks_statistic: 0.4149 (p=0.0000)

## verdict: FAIL
severity: Major
issue: code_deviates: KS statistic 0.4149 exceeds threshold 0.30 — numeric parameter distributions differ significantly between code implementation and paper specification
