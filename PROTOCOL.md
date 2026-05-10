## research_question
Does higher passive concentration in energy commodity futures correspond to lower momentum profitability?

## research_mode
confirmatory

## claim_type
performance

## hypothesis
When passive concentration is high (>=30%), the annualized Sharpe ratio of the momentum strategy is lower than when concentration is low (<30%).

## primary_metric
Annualized Sharpe differential (high concentration minus low concentration)

## minimum_effect_size
-0.15 Sharpe units

## significance_threshold
Primary alpha 0.05; Bonferroni-adjusted alpha 0.0083 for six tests

## data_source
yfinance CL=F and NG=F (dev); WRDS Compustat Futures in production

## sample_period
2000-01-01 to 2023-12-31

## statistical_tests
- newey_west_hac
- garch_11
- bootstrap_ci
- deflated_sharpe
- fama_macbeth
- markov_switching
