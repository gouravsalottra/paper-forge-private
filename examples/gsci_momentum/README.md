# GSCI Momentum Paper — Reference Example

This directory contains the first paper produced by Paper-Forge:
an empirical study of passive investor concentration effects on
commodity futures momentum profitability.

## Research Question
Does passive GSCI index investor concentration above 30% of open
interest reduce 12-month momentum strategy Sharpe ratios?

## Status
Reference implementation only. Not maintained as runnable code.
The compute environment (PettingZoo + CEM) requires:
  - WRDS institutional subscription for production data
  - CUDA GPU with ~15 minutes compute time for 500k episodes
  - Modal account for cloud GPU dispatch

## What This Example Shows
- How to write a PROTOCOL.md for a performance claim
- How to design a multi-agent RL market simulation
- How to use the STATSRUN test library for commodity futures
- What a full Paper-Forge run produces end-to-end

## Results (Dev Scale — 2,000 episodes, yfinance proxy)
Finding: INVALID at dev scale — seed consistency failed.
p=0.25 against Bonferroni threshold p<0.008.
Full 500k GPU run required for publication-grade results.

## Files
- PROTOCOL.md — pre-registered research specification
- compute/ — PettingZoo AEC market environment + CEM optimizer
- stats/ — GSCI-specific six-test battery configuration
- results/ — placeholder for run outputs (gitignored)
