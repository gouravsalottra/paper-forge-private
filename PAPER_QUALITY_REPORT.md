# Paper Quality Report

## Current Render State
- Climate ETF paper: 20 pages after rerender.
- VIX momentum paper: 21 pages after rerender.
- Raw LaTeX visibility: none observed in the latest rendered PDFs.
- Section repetition: none observed after splitting prose and table generation.
- Table rendering: booktabs tables compile and display correctly.

## Prompt Fixes Applied
1. The prose prompt now instructs the model to open with the economic phenomenon under study rather than with product or process framing.
2. The introduction requirements now explicitly demand anchor-paper citations, an economic mechanism, differentiation from prior literature, a numbered finding preview, and a roadmap.
3. Positive prompt labels were changed to academic labels such as research design, review notes, and CSV data tables so internal product vocabulary is not introduced as writing material.
4. The table-generation prompt now refers to CSV data rather than internal file terminology.

## Remaining Quality Gaps
1. Economic interpretation can still be deeper: the paper should connect magnitudes to transaction costs, institutional frictions, or economically meaningful benchmarks wherever possible.
2. Robustness remains bounded by executed tests. Stronger papers should add alternative definitions, placebo windows, and subsample choices that follow from the topic.
3. Literature synthesis should continue moving from citation listing toward thematic argumentation.
4. Conclusions should emphasize external-validity limits and the exact conditions under which the findings may not generalize.

## Deployment Requirement
These changes must be pushed, built, deployed, and verified by rerendering both existing papers before treating the fix as complete.
