# PROTOCOL.md Template

## research_question
[FILL IN: Your research question in plain English]

## research_mode
confirmatory

## claim_type
[FILL IN: predictability | performance | causal | descriptive]

## hypothesis
[FILL IN: Your falsifiable hypothesis]

## primary_metric
[FILL IN: The single number that answers the question]

## minimum_effect_size
[FILL IN: e.g. 0.15 Sharpe units]

## target_venue
[FILL IN: e.g. Journal of Finance]

## data_source
- source: yfinance
- dataset: [FILL IN]
- fields: []
- date_range: ["YYYY-MM-DD", "YYYY-MM-DD"]
- filters: []

## sample_period
[FILL IN: Start and end dates for your sample]

## compute
- type: none
- parameters: [FILL IN or remove if no simulation needed]
- seeds: [1337, 42, 9999]

## statistical_tests
- descriptive_stats

## significance_threshold
0.05

## multiple_test_correction
bonferroni

## audit_requirements
- codeaudit_required: true
- reviewer_min_score: 7
- max_review_cycles: 3
