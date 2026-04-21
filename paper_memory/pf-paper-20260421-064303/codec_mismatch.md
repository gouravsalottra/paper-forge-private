# CODEC mismatch report
model: gpt-5.4
temperature: 0
timestamp_utc: 2026-04-21T06:56:33+00:00

## term_coverage
shared_terms: ['bonferroni', 'bootstrap', 'garch', 'hac', 'markov', 'regime', 'sharpe']
missing_in_pass2 (in code but not paper): ['newey', 'seed', 'west']
missing_in_pass1 (in paper but not code): ['concentration', 'momentum', 'threshold']
term_overlap_ratio: 0.538

## numeric_comparison
pass1_numeric_count: 4
pass2_numeric_count: 7
ks_statistic: insufficient_numeric_data

## verdict: FAIL
severity: Major
issue: paper_overstates: 3 method terms present in code are absent from paper description: ['newey', 'seed', 'west']
issue: description_ambiguous: 3 terms in paper not reflected in code: ['concentration', 'momentum', 'threshold']
