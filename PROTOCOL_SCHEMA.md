# PROTOCOL.md — Research Protocol Schema

This document defines the normalized Paper-Forge protocol schema.

## research_question
- Type: free text
- Required: yes
- Description: the research question.

## research_mode
- Type: enum
- Required: yes
- Allowed: `confirmatory` | `exploratory`

## claim_type
- Type: enum
- Required: yes if `research_mode=confirmatory`, optional otherwise
- Allowed: `predictability` | `performance` | `causal` | `descriptive`

## hypothesis
- Type: free text
- Required: yes if `research_mode=confirmatory`
- Description: falsifiable claim text locked by PAP.

## primary_metric
- Type: free text
- Required: yes if `research_mode=confirmatory`
- Description: named main outcome metric and unit.

## minimum_effect_size
- Type: free text (numeric + unit)
- Required: yes if `research_mode=confirmatory`

## significance_threshold
- Type: free text
- Required: yes if `research_mode=confirmatory`

## data_source
- Type: free text
- Required: yes

## sample_period
- Type: free text
- Required: yes

## return_construction
- Type: free text
- Required: no

## exclusion_rules
- Type: markdown list
- Required: no

## seed_policy
- Type: free text
- Required: no

## training_episodes
- Type: free text / integer note
- Required: no

## statistical_tests
- Type: markdown list
- Required: no

## robustness_plan
- Type: markdown list
- Required: no

## limitations_commitment
- Type: free text
- Required: no

Validation behavior:
- Missing required fields produce errors.
- Unknown section headings are ignored.
- Empty values for required fields produce errors.
