# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T12:54:26+00:00

## term_coverage
shared_terms: ['annualized', 'bonferroni', 'concentration', 'fama', 'garch', 'hac', 'macbeth', 'markov', 'momentum', 'newey', 'p-value', 'regime', 'rolling', 'seed', 'sharpe', 'significance', 't-test', 'threshold', 'volatility', 'west', 'window']
missing_in_pass2 (in code but not paper): ['bootstrap', 'lookback']
missing_in_pass1 (in paper but not code): []
term_overlap_ratio: 0.913

## numeric_comparison
pass1_numeric_count: 377
pass2_numeric_count: 272
ks_statistic: 0.2890 (p=0.0000)

## verdict: PASS
No significant discrepancies detected between code and paper.
