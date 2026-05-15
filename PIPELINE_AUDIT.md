# PIPELINE AUDIT — Climate ETF Session 9139c632

Session audited: `9139c632-ea4b-46a0-94d8-3e86c457f98c`

Artifact source: live `/api/sessions/9139c632-ea4b-46a0-94d8-3e86c457f98c/artifacts` endpoint, downloaded to `/tmp/thrivarc_pipeline_audit_9139c632-ea4b-46a0-94d8-3e86c457f98c/files` for inspection.

Code source: current repository implementation, primarily `api/sessions.py`, `api/stats_agent.py`, `api/method_agent.py`, `api/code_audit_agent.py`, and `api/prompts.py`.

## Executive Summary

The pipeline produced a real six-page, artifact-backed summary paper, not a journal-style empirical finance paper. The strongest part is the Data/Compute kernel for this one Climate ETF event study: it downloads yfinance XLE/ICLN prices, computes `overnight_return = open(t) - close(t-1)`, creates 5,030 daily overnight-return rows, computes 10 event rows, computes `[-1,+1]` CAR rows, and writes CSV artifacts. That is real work.

But the product is still shallow relative to a 30-60 page empirical finance paper. The "agent pipeline" is currently a hybrid of real arithmetic, LLM-generated specifications, deterministic placeholders, and short templates. It does not yet perform real literature retrieval, full econometric execution, full paper writing, bibliography construction, figure generation, appendix generation, or reviewer-driven repair loops.

The three to five root causes are:

1. Literature Agent is a stub.
   - It does not call Semantic Scholar, arXiv, Crossref, SSRN, OpenAlex, or any paper source.
   - It writes `papers.json` as `{"papers": []}`.
   - It produces no citations, no abstracts, no verified references, no literature map, and no literature review text.
   - Estimated fix effort: high, 1-2 weeks for minimal external-search + citation pipeline; 3-6 weeks for credible full-paper reading and synthesis.

2. Writer Agent is not actually an LLM paper writer and the `WRITER_AGENT_PROMPT` is not used.
   - `api/prompts.py` defines `WRITER_AGENT_PROMPT`, but `api/sessions.py` never imports or calls it.
   - Climate paper writing is hardcoded in `_climate_paper_from_outputs()` and PDF rendering is hardcoded in `_render_research_paper_pdf()`.
   - The prompt itself only asks for three sections, not a full paper.
   - Estimated fix effort: high, 1-3 weeks for a real Writer input contract and section-generation pipeline; more if LaTeX compilation, references, tables, figures, appendices, and number verification are all required.

3. Statistics Agent mainly writes a test specification; it does not execute most tests it recommends.
   - `api/stats_agent.py` returns an LLM-generated test battery.
   - The actual executed tests are inside `_compute_climate_etf_event_study()` in `api/sessions.py`.
   - The artifact declares tests such as ADF, VIF, Breusch-Pagan, Durbin-Watson, Patell, CAR significance, parallel trends, Benjamini-Hochberg, alternative windows, subsample analysis, and alternative clustering, but most are not actually run.
   - Estimated fix effort: high, 2-4 weeks to build method-specific executable test adapters and artifact schemas.

4. Method Agent output is not binding execution.
   - The LLM method spec describes a PanelOLS event-study regression with ticker/date fixed effects and double-clustered standard errors.
   - The actual compute path does not run that model. It runs raw overnight-return arithmetic, simple t-tests, sign/placebo checks, bootstrap, and CAR sums.
   - Method spec and execution are therefore inconsistent.
   - Estimated fix effort: medium-high, 1-3 weeks to turn method specs into executable contracts and block when execution does not implement them.

5. Reviewer and audit gates are too lenient for journal readiness.
   - Code Audit found a major survivorship-bias issue and a minor multiple-testing issue, but only fatal violations block the run.
   - HAWK produced serious critiques but still passed the paper with 7.5/10.
   - The gate currently rewards transparent null reporting but does not require repair of issues that a real reviewer would likely demand.
   - Estimated fix effort: medium, 1-2 weeks to harden gate thresholds, route major issues to Repair Agent, and require artifact-backed fixes.

Bottom line: the pipeline is good enough to create a transparent research memo with verified numbers for this one Climate ETF event-study kernel. It is not yet capable of producing a 30-60 page, top-journal submission-ready empirical finance paper.

## Phase-by-Phase Diagnosis

### Literature Agent

- Implementation depth: stub.

- What it actually does:
  - `api/prompts.py` contains `LITERATURE_AGENT_PROMPT`, but there is no implementation that calls a literature API or LLM for the live run.
  - `api/sessions.py` only formats `LITERATURE_AGENT_PROMPT` into `profile["literature_prompt_contract"]` at lines 2308-2315.
  - `api/sessions.py` writes literature artifacts directly at lines 2358-2362.
  - The papers artifact is hardcoded as `{"papers": []}` at line 2359.
  - The literature synthesis is constructed by `_profile()` from simple concept strings at lines 1469-1473.
  - Repository search found no implementation of Semantic Scholar, arXiv, OpenAlex, Crossref, SSRN, or full-paper retrieval in `api/`.

- What it produced:
  - `02_literature/papers.json`: `{"papers": []}`; 0 citations.
  - `02_literature/synthesis.json`: 319 bytes. It contains only four concept labels: `climate policy announcements`, `sector ETFs`, `overnight returns`, `event studies`.
  - `02_literature/gap_analysis.json`: 123 bytes. It says the run turns the question into an `event_study` design with evidence/audit/reviewer gates.
  - `02_literature/literature_prompt_contract.txt`: a prompt template, not a literature review.
  - The final paper has zero `\cite` commands and no bibliography.

- What it SHOULD produce for a 30-60 page paper:
  - Search results from Semantic Scholar/OpenAlex/Crossref/SSRN/arXiv/Google Scholar equivalent.
  - 40+ candidate papers with metadata, DOI/URL, abstract, venue, citation count, relevance score, and verification status.
  - At least 10-20 paper summaries with contribution, method, data, identification, result, and relevance to this study.
  - A 3-5 page literature review covering event studies, climate policy and asset prices, ETF sector responses, clean energy/fossil fuel transition risk, overnight returns, market microstructure timing, and event-window inference.
  - A BibTeX or CSL bibliography artifact and a `literature_map.md` or `literature_review.md` artifact.

- Gap:
  - There is no literature search, no paper reading, no citation extraction, no verified references, no bibliography, and no literature review section.

- Root cause:
  - The Literature Agent is represented as a prompt contract and deterministic placeholder profile fields, not as an executed retrieval/synthesis pipeline.

- Fix required:
  - Implement a real `literature_agent.py` with external paper-search connectors, citation verification, relevance scoring, abstract/full-text ingestion where available, BibTeX generation, and a section writer that emits a real literature review artifact. The Writer must consume that artifact.

### Data Agent

- Implementation depth: partial-to-strong for this specific Climate ETF study; partial as a general Data Agent.

- What it actually does:
  - `_compute_climate_etf_event_study()` in `api/sessions.py` is the real data/compute kernel for this topic.
  - It reads the staged event CSV from blob and verifies its SHA-256 at lines 651-659.
  - It downloads XLE and ICLN OHLC data from yfinance at lines 667-681.
  - It computes daily `overnight_return = open - previous close` at lines 686-709.
  - It aligns event dates to trading days at lines 715-724.
  - It writes `03_data/overnight_returns.csv` from the generated daily rows at lines 979-985 and artifact-write lines 2364-2372.

- What it produced:
  - `03_data/overnight_returns.csv`: 5,030 data rows plus header, columns `date,ticker,open,prev_close,overnight_return`.
  - `03_data/data_passport.json`: includes source, event SHA, price-result SHA, CSV artifact hashes, schema, and plain-English summary.
  - `03_data/schema_profile.json`: only six declared columns, but these are generic event fields, not the actual full CSV schema.
  - `03_data/data_quality_report.json`: only `{ "status": "pass", "blocking_issues": [] }`.
  - Important bug: `data_passport.json` says `rows: 1000` even though `overnight_returns.csv` has 5,030 rows. `_execution_profile()` correctly sets rows to `len(climate["daily_overnight_rows"])` at lines 1096-1106, but `_execute_session_pipeline()` overwrites `profile["data_passport"]["rows"]` with `1000` at lines 2328-2329 when no `design.sessions` exists.

- What it SHOULD produce for a 30-60 page paper:
  - Full raw and cleaned OHLCV data artifacts with source timestamps, yfinance query parameters, trading-calendar assumptions, missingness profiles, row counts, corporate-action/adjustment policy, and reproducibility metadata.
  - A full DataPassport document with raw data hash, clean data hash, event-file hash, row counts before/after exclusions, schema profile, data validation checks, and known limitations.
  - Summary statistics table(s), missingness table, event-date alignment table, and data appendix.

- Gap:
  - The data itself is real for XLE/ICLN, but the DataPassport is shallow and internally inconsistent. There is no raw-vs-clean separation, no OHLCV volume artifact, no corporate action adjustment discussion, no detailed missingness report, no source retrieval timestamp, and no data appendix.

- Root cause:
  - The Data Agent is not a standalone agent with a complete certification contract. It is embedded inside the Climate ETF compute function, then partially overwritten by generic session-pipeline logic.

- Fix required:
  - Separate Data Agent from compute, write raw and clean data artifacts, fix row-count overwrites, generate a full PDF/JSON DataPassport, and make schema/data-quality checks real rather than one-line `pass` artifacts.

### Statistics Agent

- Implementation depth: partial. It produces a decent test-battery specification, but only a small subset is executed.

- What it actually does:
  - `api/stats_agent.py` calls `STATISTICS_AGENT_PROMPT` through `call_agent_llm()` to generate a statistical test specification at lines 90-139.
  - It does not execute those tests.
  - Actual statistical computation occurs inside `_compute_climate_etf_event_study()` in `api/sessions.py`, not in `api/stats_agent.py`.
  - Actual computations include one-sample t-test on aligned spreads, binomial sign test, pre-event placebo t-test, next-overnight t-test, winsorized mean, leave-one-out, bootstrap CI, ticker event-vs-non-event Welch t-tests, summary statistics, and random non-event placebo.
  - These computations are at `api/sessions.py` lines 784-985.

- What it produced:
  - `07_statistics/statistical_test_battery.json`: a 6.6KB LLM-generated specification with 5 pre-estimation diagnostics, 4 post-estimation diagnostics, 2 inference tests, 2 identification tests, 3 robustness checks, and Benjamini-Hochberg multiple-testing correction declared.
  - `07_statistics/results_tables/t_tests.csv`: only 2 executed rows: XLE event-vs-non-event Welch t-test and ICLN event-vs-non-event Welch t-test.
  - `07_statistics/results_tables/placebo_tests.csv`: 1 random non-event placebo row.
  - `07_statistics/results_tables/summary_statistics.csv`: 6 summary-stat rows.
  - `07_statistics/results_tables/main_results.json`: contains primary numbers and robustness summaries.

- What it SHOULD produce for a 30-60 page paper:
  - Executed statistical tests corresponding to the entire test battery, not just a narrated battery.
  - HAC/Newey-West or event-study-specific standard errors where appropriate.
  - Patell test, BMP test, Corrado rank test, sign test, CAR inference, alternative event windows `[-10,+10]`, `[-5,+5]`, `[-3,+3]`, `[-1,+1]`, `[0,+1]`, event-date clustering checks, market-model residual diagnostics, multiple-testing correction, placebo distribution, power analysis, and regime/subsample analysis.
  - Tables for each family of tests, with coefficient/estimate, standard error, t-stat/z-stat, p-value, confidence interval, sample size, and interpretation.

- Gap:
  - The test battery is mostly LLM narration. The declared diagnostics and robustness checks are not all executed. There is no HAC correction. There is no market-model abnormal-return inference. The multiple-testing correction is declared but not applied to the output p-values. Alternative event windows are recommended but absent from the artifacts. No power analysis is computed.

- Root cause:
  - `api/stats_agent.py` is a specification agent only. The executable statistics remain hardcoded in `api/sessions.py` for this one Climate ETF path.

- Fix required:
  - Build executable statistics adapters keyed by method family. The pipeline should fail if the executed results do not cover all required tests in `statistical_test_battery.json`. Add explicit artifact rows for every required diagnostic, inference test, robustness check, and multiple-testing correction.

### Method / Compute Agent

- Implementation depth: partial. Real arithmetic exists for this one topic; the method spec is not actually executed.

- What it actually does:
  - `api/method_agent.py` asks the LLM for a method specification at lines 76-111.
  - `_build_agent_contracts()` stores that LLM output as `profile["method_spec"]` at lines 1633-1649.
  - Execution does not run the LLM-provided scaffold. For the Climate ETF flavor, `_execution_profile()` calls `_compute_climate_etf_event_study()` directly at lines 1013-1015.
  - The Climate ETF compute function performs raw overnight return construction, event-day spreads, `[-1,+1]` CAR sums, simple t-tests/placebos, and summary stats.

- What it produced:
  - `06_compute/method_spec.json`: LLM method spec describing an `Event Study Regression` with `linearmodels.panel.PanelOLS`, ticker fixed effects, date fixed effects, and double-clustered standard errors.
  - `06_compute/method_outputs/climate_etf_event_study_results.json`: real event-study outputs, but not the PanelOLS model described in `method_spec.json`.
  - `06_compute/method_outputs/event_returns.csv`: 10 event rows.
  - `06_compute/method_outputs/event_window_car.csv`: 10 `[-1,+1]` CAR rows.

- What SHOULD it produce for a 30-60 page paper:
  - A coherent method spec that is binding on execution.
  - Full event-study methodology: estimation window, expected-return model, market model or Fama-French factor benchmark, abnormal returns, CAR/BHAR over multiple event windows, event clustering treatment, cross-sectional CAR regressions on event characteristics, controls such as SPY/VIX if declared, and standard-error correction.
  - Code and output artifacts that prove each method component ran.

- Gap:
  - Method spec and executed method diverge. The spec promises PanelOLS, fixed effects, double clustering, controls, and regression output. The compute artifact delivers raw return arithmetic and simple tests. Controls listed in `compute.controls` (`SPY overnight return`, `VIX level`) are not fetched or used.

- Root cause:
  - The method agent creates an advisory document, not an executable contract. The actual compute is a bespoke hardcoded function for Climate ETF.

- Fix required:
  - Make the Method Agent produce a machine-executable method plan. Add an execution planner that maps each method-plan step to code adapters. Block the run if the produced artifacts do not satisfy the method spec.

### Code Audit Agent

- Implementation depth: partial.

- What it actually does:
  - `api/code_audit_agent.py` calls `CODE_AUDIT_PROMPT` with a synthetic `analysis_code_contract`, not the actual full implementation code.
  - It uses `_remove_contradicted_violations()` to remove LLM findings contradicted by the locked analysis contract at lines 41-104.
  - It blocks only fatal violations at lines 142-151.
  - Major and minor violations do not route to Repair Agent in the current pipeline.
  - `code_audit_report.md` is a static PASS string generated by `_profile()` at `api/sessions.py` line 1503, independent of the JSON findings.

- What it produced:
  - `08_audit/code_audit_report.json`: `audit_passed: true`, `blocks_pipeline: false`, 2 remaining violations, and 2 overridden LLM audit findings.
  - Remaining violations:
    - Major survivorship-bias issue: universe existence/trading not explicitly validated for the whole sample.
    - Minor multiple-testing issue: no explicit log of all subsamples/windows tested.
  - `08_audit/code_audit_report.md`: says only `PASS. The canonical session pipeline used the event_study execution profile, locked inputs, and Blob-backed artifacts.`

- What SHOULD it produce for a 30-60 page paper:
  - Audit against the actual executed code or a generated reproducible script, not only a contract snippet.
  - Verification that every file read/written matches the locked artifacts.
  - Explicit pass/fail for overnight-return formula, event-day alignment, event-window boundaries, look-ahead bias, survivorship bias, adjusted/unadjusted price policy, event-file hash, universe construction, multiple-testing log, and hardcoded results.
  - Major violations should trigger Repair Agent or block Writer until waived by researcher with a Deviation Register entry.

- Gap:
  - It found real issues but allowed the paper to proceed. The human-readable audit report hides those issues by saying PASS. It does not inspect the full actual implementation.

- Root cause:
  - Audit severity handling is too weak, and the markdown report is not generated from the actual audit JSON. The audit artifact and phase status do not communicate risk honestly enough.

- Fix required:
  - Make major violations require repair/approval, generate markdown from JSON findings, audit actual reproducible analysis code, and prevent HAWK/Writer from ignoring unresolved major audit issues.

### HAWK Reviewer

- Implementation depth: partial; too lenient for journal-readiness.

- What it actually does:
  - `HAWK_PROMPT` is rigorous in tone, but includes an explicit rule not to penalize null findings if transparently documented.
  - `_run_hawk_review()` sends HAWK the blueprint, method spec, stats spec, and selected result package at lines 1777-1805.
  - If no client exists, `_reviewer_scorecard()` auto-passes with scores around 7.1-8.2 at lines 1808-1838.
  - `_calibrate_defensible_null_scorecard()` can also lift a failed Climate ETF null-result study above gate floors if required robustness keys exist at lines 1711-1774.
  - In this run, HAWK returned a passing 7.5 score despite serious issues.

- What it produced:
  - `09_review/reviewer_scorecard_v1.json`: average `7.5`, gate passed.
  - Scores:
    - identification_validity: `6.5`
    - data_integrity: `7.0`
    - statistical_rigor: `7.5`
    - economic_significance: `8.0`
    - benchmark_fairness: `8.5`
    - robustness_burden: `7.0`
    - overclaiming_risk: `8.0`
  - Top issues:
    - No explicit parallel trends validation.
    - Potential survivorship bias in ETF universe.
    - Absence of alternative event window and single-clustering robustness checks.

- What SHOULD it produce for a 30-60 page paper:
  - A referee-style report that requires repair before Writer when major method/audit gaps remain.
  - Specific desk-rejection risks tied to actual artifacts.
  - A score that distinguishes "transparent research memo" from "top-journal submission-ready paper."
  - A mandatory repair contract for major missing robustness checks and unresolved audit findings.

- Gap:
  - The score was generous. A real JF/RFS/JFE referee would not likely pass a paper that has zero citations, no literature review, no market model, no abnormal-return benchmark, no alternative event windows, unresolved survivorship concerns, and declared-but-unexecuted statistical tests.

- Root cause:
  - The gate is calibrated to unlock Writer for transparent null results, not to enforce top-journal completeness. HAWK evaluates the package as "defensible scoped evidence" rather than as "30-60 page publishable article."

- Fix required:
  - Add separate gate modes: evidence memo gate, working paper gate, and journal submission gate. For journal mode, unresolved major audit findings and missing literature/method robustness should block Writer or force a repair cycle.

### Writer Agent

- Implementation depth: partial template, not a real Writer Agent.

- What it actually does:
  - `WRITER_AGENT_PROMPT` exists in `api/prompts.py`, but `api/sessions.py` does not import or call it.
  - Repository search shows `WRITER_AGENT_PROMPT` only defined, not used.
  - Climate paper generation happens through `_climate_paper_from_outputs()` at `api/sessions.py` lines 1934-2090.
  - PDF generation happens through `_render_research_paper_pdf()` at lines 2130-2301. This is a ReportLab document, not a compiled LaTeX PDF.
  - Generic non-Climate papers use an even shorter fallback template at lines 2093-2127.

- What it produced:
  - `11_paper/final.tex`: 9,846 characters, 13 sections, 4 tables, 0 citations, no bibliography.
  - `11_paper/final.pdf`: 10,356 bytes, 6 PDF pages.
  - Sections: abstract, research question/contribution, data, methodology, verified CSV sources, summary statistics, event returns, CAR estimates, inference/placebo tests, results, robustness, interpretation, reviewer gate/integrity statement, conclusion.
  - Good: no placeholders, real numbers, 4 tables.
  - Bad: no introduction of journal-paper length, no full literature review, no citation apparatus, no theory/hypothesis-development section, no detailed methodology appendix, no figures, no references, no robustness appendix, no referee-response-quality discussion.

- What SHOULD it produce for a 30-60 page paper:
  - A full LaTeX manuscript with abstract, introduction, literature review, institutional background, hypothesis development, data, methodology, results, robustness, limitations, conclusion, references, appendices, tables, figures, and reproducibility appendix.
  - 20-100 citations with BibTeX.
  - Multiple sections generated from upstream artifacts, not a single deterministic template.
  - Number verification after writing, table/figure cross-reference verification, bibliography verification, and PDF compile logs.

- Gap:
  - The Writer is a short deterministic report generator. It is intentionally constrained to available CSV numbers and cannot produce a journal-scale manuscript because it has no literature inputs, no figure artifacts, no appendix artifacts, no bibliography, and no long-form writing plan.

- Root cause:
  - Writer is not wired to `WRITER_AGENT_PROMPT`, and the prompt itself only asks for three short sections totaling roughly 1,550-2,050 words. The actual template is even more constrained.

- Fix required:
  - Build a real Writer pipeline: outline planner, section writer, citation-aware literature writer, table/figure inserter, appendix writer, bibliography generator, LaTeX compiler, and post-write Paper-Code Verifier.

## The Writer Problem

The paper is six pages because the Writer is not a paper-writing agent. It is a deterministic template plus ReportLab renderer.

Exactly why it is six pages, not 30-60:

1. `WRITER_AGENT_PROMPT` is never used.
   - It is defined at `api/prompts.py` lines 523-602.
   - `api/sessions.py` does not import it and does not call `call_agent_llm()` for Writer.
   - The run calls `_paper_from_outputs()` and `_render_research_paper_pdf()` at `api/sessions.py` lines 2465-2472.

2. The actual Climate Writer is `_climate_paper_from_outputs()`.
   - It hardcodes a compact manuscript structure at lines 1934-2090.
   - It writes only the sections it has data for.
   - It cannot write literature review or references because no literature artifacts exist.

3. The PDF is not compiled from `final.tex`.
   - `final.tex` is written as an artifact, but `final.pdf` is produced independently through ReportLab in `_render_research_paper_pdf()`.
   - This avoids LaTeX compile failures but also bypasses true paper-layout control, bibliography handling, cross-references, and appendix compilation.

4. The Writer inputs are narrow.
   - It has real CSV outputs and HAWK scorecard.
   - It has no verified literature review, no references, no figures, no model-output tables beyond simple CSVs, no appendix artifacts, and no execution logs for a full econometric battery.

5. Even the unused Writer prompt asks only for three sections.
   - Data: 350-450 words.
   - Methodology: 500-700 words.
   - Results: 700-900 words.
   - That is not a 30-60 page article contract.

What needs to change:

- Replace deterministic paper template with a multi-stage Writer Agent.
- Feed it real literature artifacts, BibTeX, method artifacts, stats artifacts, tables, figures, reviewer issues, and appendices.
- Require a target article class and page budget.
- Compile LaTeX and verify page count, references, citations, tables, figures, and placeholders.
- Add a final Paper-Code Verifier that checks every numeric claim and every citation key.

## The Literature Problem

Real papers were not found or cited.

Evidence:

- `02_literature/papers.json` is empty.
- `final.tex` contains zero `\cite` commands.
- `final.tex` contains no bibliography environment and no BibTeX reference.
- Repository search found no Semantic Scholar, arXiv, OpenAlex, Crossref, SSRN, or full-paper retrieval implementation in `api/`.
- `LITERATURE_AGENT_PROMPT` exists, but the live pipeline only writes the formatted prompt contract and deterministic concept tags.

The literature review is not hallucinated; it is essentially absent. That is better than fake citations, but it means the paper is not a paper. It is a research memo with no literature foundation.

What is needed:

- A real literature search toolchain.
- Citation verification.
- Relevance scoring.
- Full abstract/paper summaries.
- BibTeX artifact.
- Literature-map artifact.
- 3-5 pages of literature review and positioning text consumed by Writer.

## The Statistics Problem

Some statistical computations are real, but the statistical system is not yet journal-grade.

Real computations performed:

- Event-day XLE/ICLN overnight returns for 10 events.
- Direction-aligned clean-minus-fossil spread.
- One-sample t-test of aligned spread.
- Ticker-level event-vs-non-event Welch t-tests.
- `[-1,+1]` CAR sums.
- Pre-event placebo.
- Next-overnight sensitivity.
- Sign test.
- Bootstrap confidence interval.
- Leave-one-out range.
- Winsorized mean.
- Random non-event placebo distribution with 1,000 draws.

Not actually executed despite being specified or expected:

- HAC/Newey-West corrected inference.
- Patell standardized residual test.
- BMP test.
- Corrado rank test.
- Market-model abnormal returns.
- Fama-French or sector benchmark abnormal returns.
- Alternative event windows such as `[-10,+10]`, `[-5,+5]`, `[-3,+3]`, `[0,+1]`.
- Cross-sectional regression of CARs on event characteristics.
- SPY/VIX controls, despite being listed in the compute contract.
- Benjamini-Hochberg or Harvey-Liu-Zhu-style multiple-testing correction applied to output p-values.
- Power analysis.
- Event-clustering correction.
- Standard-error clustering robustness.

The statistical tests are partly real computations and partly LLM narration/specification. The paper reports only a subset of the real computations.

## Priority Fix List

Ordered by impact on paper quality:

1. Build a real Literature Agent.
   - Add paper search, metadata, verified citations, BibTeX, relevance scoring, and literature-review artifacts. Without this, no 30-60 page academic paper is possible.

2. Make Method Agent output executable and binding.
   - Convert method specs into required executable steps and block if compute artifacts do not implement them.

3. Build executable Statistics Agent adapters.
   - Every required test in `statistical_test_battery.json` must either produce an output artifact or be explicitly waived with a reason.

4. Harden HAWK and Code Audit gates.
   - Major audit/reviewer issues should trigger Repair Agent or block journal-mode Writer. A 7.5 should not pass when required robustness/literature components are absent.

5. Replace deterministic Writer template with a true manuscript pipeline.
   - Outline -> section drafts -> tables/figures -> citations -> appendices -> LaTeX compile -> verification.

6. Add figure generation.
   - Event-time plots, CAR timelines, placebo distribution, cumulative return windows, robustness graphs, and data coverage charts.

7. Fix DataPassport correctness and depth.
   - Correct row count, raw/clean hash separation, schema profile, missingness, source timestamp, and adjustment policy.

8. Add Paper-Code Verifier for full manuscript claims.
   - Verify every number, every table, every figure, every citation key, and every claim scope before final PDF.

9. Create separate quality gates by output type.
   - Evidence memo, working paper, and journal submission should have different thresholds and required artifacts.

10. Generalize beyond the Climate ETF hardcoded path.
   - Other topic flavors currently still use hardcoded profile numbers or registry-driven contracts. They are not real research engines yet.

## What a Real Paper Needs That This Pipeline Cannot Currently Produce

Be blunt: the current pipeline cannot yet produce a JF/RFS/JFE-style submission-ready paper. It can produce a verified short research memo for one bespoke Climate ETF event-study path.

Missing capabilities:

- 20-100 verified citations.
- Real literature review.
- BibTeX/reference management.
- Full paper outline with introduction, theory, hypothesis development, literature, data, methodology, results, robustness, conclusion, references, and appendices.
- External paper search and full-paper reading.
- Market-model or factor-model abnormal returns.
- Multiple event windows and full event-study inference.
- HAC/Newey-West/clustered standard-error execution where required.
- Multiple-testing correction applied to results.
- Cross-sectional CAR regressions on event attributes.
- Controls that are actually fetched and used, such as SPY and VIX.
- Figures.
- Appendix tables.
- Reproducible analysis script/package.
- LaTeX compilation with references and cross-references.
- A strict reviewer gate that blocks when major issues remain.
- Repair Agent execution for missing robustness and audit issues.
- Full DataPassport and data-quality documentation.
- Journal-mode quality distinction.
- General dynamic research execution across finance topics.

Current capability statement:

- The Climate ETF run produced real yfinance-based event arithmetic and verified CSV-backed numbers.
- It produced a transparent, scoped, six-page null-result memo.
- It did not produce a full empirical finance paper.
- The shallow output is not an accident; it follows directly from the current implementation depth of Literature, Method, Statistics, Reviewer, and Writer phases.
