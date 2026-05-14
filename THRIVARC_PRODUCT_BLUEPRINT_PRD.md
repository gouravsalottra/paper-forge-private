# Thrivarc Product Blueprint PRD

Last updated: 2026-05-13

## 1. Product Definition

Thrivarc is an agentic empirical finance research operating system.

The product takes a research question from a human researcher, interviews the researcher only where the study is underspecified, builds a formal research blueprint, verifies the evidence route before execution, runs the required specialist agents, attacks its own findings like a serious reviewer, repairs concrete weaknesses through bounded reruns, verifies paper-code consistency, and writes the final paper package only after the evidence and defense gates pass.

Thrivarc is not a generic chatbot, a report generator, a parameter form, or a collection of canned finance templates. It is a research execution and defense system.

The core promise:

> Start with a research question. End with a result you can defend.

The product contract:

1. The human brings research intent, context, and judgment.
2. Thrivarc converts that intent into a defensible research blueprint.
3. Every downstream agent obeys the blueprint.
4. No compute starts until evidence is previewed and approved.
5. No paper is finalized until reviewer, audit, and consistency gates pass.

## 2. Problem Statements

### 2.1 Research Starts Too Ambiguously

Researchers often begin with an idea, not a clean hypothesis, dataset, method, and test battery. Most tools force them to pick parameters too early: model, frequency, data connector, compute type, test family, output type. That creates bad research because the tool asks implementation questions before understanding the research problem.

Thrivarc solves this by starting with natural language and letting the Research Architect infer the study shape.

### 2.2 Serious Finance Research Has Too Many Disconnected Steps

A finance research project may require literature framing, data sourcing, cleaning, feature construction, backtesting, event study design, causal identification, statistical testing, robustness checks, code review, reviewer simulation, paper drafting, and consistency verification. Today those steps happen across notebooks, spreadsheets, scripts, PDFs, chats, and memory.

Thrivarc solves this by putting the entire research lifecycle behind one blueprint and one orchestrated agent system.

### 2.3 Research Tools Overproduce Text And Underproduce Evidence

Most AI products can write plausible paragraphs. That is not enough. Serious researchers need evidence, assumptions, reproducibility, reviewer pressure, and defensible limitations.

Thrivarc solves this by treating writing as the final stage, not the starting point.

### 2.4 Data Reality Is Usually The Bottleneck

The right data path depends on the study. Some work can use public market data. Some requires upload. Some requires staged vendor exports. Some needs proprietary panels. Some asks for WRDS or other institutional sources, but these sources may be unavailable at a given time. A dropdown cannot truthfully model this.

Thrivarc solves this by asking for data reality in plain English, supporting upload/staged evidence, previewing the exact dataset, and blocking execution until evidence is real.

### 2.5 Methods Cannot Be Chosen From A Universal Dropdown

There is no universal "compute method." A TSX 60 rotation study, an FOMC event study, a transcript sentiment study, a systemic-risk network study, and an agent-based market simulation require different methods, data structures, validation burden, and reviewer attacks.

Thrivarc solves this by inferring the method family from the blueprint and loading research-type-specific agent skills.

### 2.6 Researchers Need Defense Before Submission

The best researchers try to kill their own results before someone else does. They ask whether the benchmark is fair, whether timing is correct, whether the effect survives costs, whether the result is overfit, whether the story matches the code, and whether the paper overclaims.

Thrivarc solves this with an adversarial review and repair layer before the writer produces final paper sections.

### 2.7 Product Trust Breaks When UI And Backend Disagree

If the website says the blueprint is blocked but the backend says evidence preview is ready, the product loses trust. If the site claims self-improvement but the backend only writes static critique, the product is dishonest.

Thrivarc solves this by making the Research Blueprint, completion contract, launch readiness, agent stack, and revision policy explicit backend objects that the UI displays directly.

## 3. Product Principles

1. Planner first. Evidence second. Execution third. Reviewer pressure before writing.
2. The Research Blueprint is the constitution for the run.
3. Examples are adversarial tests, not templates.
4. The system derives from the user brief, not inherited demo assumptions.
5. No fake persona segmentation. One universal research flow adapts to expertise.
6. No hidden p-hacking. Any change to claim, benchmark, data, or method is logged.
7. Clarify only what blocks the next correct step.
8. Upload and staged data are first-class paths, not afterthoughts.
9. Writer is last and never invents numbers.
10. Every visible promise must map to backend behavior.

## 4. Target Users And Buying Contexts

Thrivarc is universal in flow but strongest for people who care about empirical research quality.

### 4.1 World-Class Finance Economist

Example user: someone like Raghuram Rajan.

Needs:

- Sharp research framing.
- Clean separation between exploratory and confirmatory claims.
- Serious empirical identification.
- Transparent assumptions and limitations.
- Reviewer-grade critique before public circulation.
- Paper sections that respect evidence instead of overselling it.

Why they pay:

- Thrivarc saves research-assistant time.
- It keeps empirical claims disciplined.
- It exposes weaknesses early.
- It gives them a defensible audit trail.

What they will reject:

- Canned topic suggestions.
- Generic AI prose.
- Unclear data provenance.
- Methods chosen by dropdown.
- Any system that silently changes assumptions.

### 4.2 Academic Finance Researcher

Needs:

- Literature context.
- Data acquisition or upload handling.
- Formal study design.
- Statistical test discipline.
- Robustness checks.
- Audit trail.
- Paper-ready LaTeX.

Why they pay:

- Faster path from idea to working empirical package.
- Better pre-submission critique.
- Fewer avoidable reviewer rejections.

### 4.3 Quant Researcher Or PM

Needs:

- Backtest discipline.
- Universe and benchmark clarity.
- Turnover and transaction-cost analysis.
- Walk-forward and out-of-sample validation.
- Regime sensitivity.
- Reproducible pipeline outputs.

Why they pay:

- Faster strategy research.
- Clearer robustness pressure.
- Better investment committee evidence.

### 4.4 Policy Researcher

Needs:

- Event definition.
- Timing discipline.
- Confound checks.
- Plain-language findings.
- Strong limitations.
- Evidence suitable for policy memos.

Why they pay:

- Converts policy questions into empirical designs.
- Reduces weak causal claims.
- Produces a defensible result package.

### 4.5 Doctoral Student Or Independent Researcher

Needs:

- Guidance without dumbing down.
- Clarification questions.
- Learning through structure.
- Help turning curiosity into a study.
- Guardrails against overclaiming.

Why they pay:

- Thrivarc behaves like a research architect, RA team, reviewer, and writing assistant in one system.

### 4.6 Corporate Finance / Strategy User

Needs:

- Internal data upload.
- Evidence inspection.
- Decision-oriented outputs.
- Business-readable findings.
- Limitations and next actions.

Why they pay:

- Turns internal questions into structured evidence packages without requiring the user to know research pipeline internals.

## 5. Must-Buy Criteria

Thrivarc becomes worth paying for when it reliably delivers:

1. Better questions: it sharpens research intent into a defensible design.
2. Better evidence: it executes the right data and method path.
3. Better defense: it attacks, repairs, and limits claims before the outside world does.
4. Better time economics: it replaces weeks of manual research scaffolding.
5. Better reproducibility: it preserves blueprint, data preview, logs, outputs, review, and paper artifacts.

The product is not worth paying for if it only generates plausible research text.

## 6. Universal User Flow

Thrivarc uses one universal flow for all serious users.

### 6.1 Step 1: Question

The user enters the research question in plain English.

Examples of acceptable starting inputs:

- "Do sector ETF returns react to changes in earnings call sentiment after controlling for analyst surprises?"
- "I want to study whether defensive sectors outperform during high inflation regimes."
- "Can uploaded supplier-level revenue data predict semiconductor stock returns?"
- "Do FOMC surprise announcements create abnormal returns in regional bank ETFs?"

The user does not need to know:

- hypothesis form,
- method family,
- compute type,
- statistical test,
- data connector,
- rebalance frequency,
- output structure.

### 6.2 Step 2: Context

The user can add context in natural language:

- market or asset universe,
- benchmark,
- time horizon,
- cadence or frequency if relevant,
- strategy objective,
- risk lens,
- data they already have,
- validation expectations,
- publication or decision use case.

Context is optional but valuable. Thrivarc infers what it can and asks only for missing blockers.

### 6.3 Step 3: Data Access

The user chooses the evidence reality:

1. Fetch public market data.
2. Upload my dataset.
3. Connect or stage an external source.

This is not a connector dropdown wall. It is a research-level evidence route.

If the user selects upload or staged source, they can stage a file immediately. The file is carried into the evidence preview gate after blueprint approval.

### 6.4 Step 4: Live Architect Read

Before the API call, the UI gives a live read of the working brief:

- likely study stance,
- likely evidence route,
- universe/comparison cues,
- time/regime cues,
- likely proof burden,
- where the brief is fragile.

This makes the product feel like a research partner, not a static form.

### 6.5 Step 5: Thrivarc Blueprint

The Research Architect builds the formal blueprint:

- research stance,
- research archetype,
- decision problem,
- comparison set,
- evidence route,
- method family,
- cadence role,
- validation plan,
- burden of proof,
- initial reviewer attacks,
- working assumptions,
- agent stack,
- revision policy,
- completion contract,
- launch readiness.

The blueprint is shown before any data preview or execution.

### 6.6 Step 6: Clarifications

Thrivarc asks targeted clarification questions only when they block the next correct step.

Clarification categories:

- universe or benchmark,
- data schema,
- outcome variable,
- event definition,
- time horizon,
- cadence role,
- validation burden,
- claim discipline,
- evidence source availability.

Clarifications feed back into the blueprint. The blueprint is rebuilt after the answer.

### 6.7 Step 7: Blueprint Approval

The user approves the blueprint before the evidence gate opens.

Approval does not start the run. It only confirms the design is coherent enough to preview evidence.

### 6.8 Step 8: Data Preview

Thrivarc previews the exact evidence:

- source route,
- symbols or identifiers,
- date range,
- frequency,
- columns,
- sample rows,
- missingness,
- fingerprint hash,
- data quality status.

The run cannot start until this preview is approved.

### 6.9 Step 9: Run

Thrivarc creates the run from the approved blueprint and approved evidence preview.

The run status displays:

- current phase,
- completed phases,
- agent stack,
- revision policy,
- plan state,
- logs,
- cost/spend.

### 6.10 Step 10: Findings And Defense

After execution, Thrivarc shows:

- finding summary,
- key statistics,
- charts,
- tables,
- reviewer critique,
- weaknesses,
- recommended follow-up runs,
- repair actions,
- limitations.

### 6.11 Step 11: Paper Workspace

The writer creates paper-ready sections only after review and consistency gates.

The workspace separates:

- Thrivarc-written evidence-backed sections,
- researcher-written interpretation sections,
- editable prompts for introduction, literature framing, and conclusion,
- LaTeX export.

## 7. Research Blueprint Schema

The blueprint is the single source of truth.

Required fields:

- `research.topic`
- `research.research_state`
- `research.output_format`
- `research.persona`
- `datapull.connector`
- `datapull.symbols`
- `datapull.start_date`
- `datapull.end_date`
- `datapull.frequency`
- `datapull.fields`
- `compute.enabled`
- `compute.type`
- `compute.params`
- `statsrun.test_battery`
- `blueprint.agent_stack`
- `blueprint.revision_policy`
- `blueprint.architect_questions`
- `blueprint.launch_readiness`
- `blueprint.completion_contract`

Important invariant:

`completion_contract.ready_for_evidence_preview` must agree with `launch_readiness`.

If blocking clarifications exist:

- `validated = false`,
- `launch_readiness.headline = "Blueprint needs clarification"`,
- `completion_contract.state = "blocked"`,
- evidence preview is disabled.

If no blocking clarifications exist:

- `completion_contract.state = "ready_for_evidence_preview"`,
- evidence preview may open after blueprint approval.

## 8. Research Archetypes

Thrivarc does not hardcode one universal method. It classifies the study into an archetype and loads matching agent skills.

### 8.1 Exploratory Mapping

Purpose:

- discover structure,
- map patterns,
- summarize relationships,
- generate future hypotheses.

Typical methods:

- descriptive statistics,
- rolling correlations,
- clustering,
- regime summaries,
- visualization,
- exploratory regressions clearly labeled as exploratory.

Reviewer attacks:

- overclaiming,
- cherry-picked windows,
- weak comparison set,
- descriptive result framed as causal.

### 8.2 Confirmatory Predictive Study

Purpose:

- test whether a signal predicts an outcome.

Typical methods:

- out-of-sample prediction,
- train/test splits,
- cross-validation,
- factor controls,
- Newey-West errors,
- multiple-testing correction.

Reviewer attacks:

- lookahead bias,
- overfitting,
- data snooping,
- no holdout,
- weak benchmark.

### 8.3 Market Strategy / Backtest

Purpose:

- evaluate a strategy, allocation rule, signal, or rotation design.

Typical methods:

- backtest,
- transaction costs,
- turnover,
- walk-forward validation,
- benchmark comparison,
- drawdown analysis,
- Sharpe/Sortino/calmar,
- cadence sensitivity.

Reviewer attacks:

- survivorship bias,
- unrealistic costs,
- rebalance timing,
- benchmark mismatch,
- overfit parameters,
- poor out-of-sample behavior.

### 8.4 Event Study

Purpose:

- estimate abnormal returns around events.

Typical methods:

- event window,
- estimation window,
- abnormal return model,
- cumulative abnormal return,
- placebo windows,
- clustered standard errors.

Reviewer attacks:

- event timing,
- confounds,
- leakage,
- overlapping windows,
- benchmark model.

### 8.5 Policy / Causal Study

Purpose:

- evaluate the effect of an intervention, policy, or shock.

Typical methods:

- difference-in-differences,
- synthetic control,
- instrumental variables,
- event study regressions,
- placebo tests,
- pre-trend checks.

Reviewer attacks:

- identification weakness,
- parallel trends,
- omitted variables,
- treatment timing,
- external validity.

### 8.6 Text / NLP Finance Study

Purpose:

- analyze filings, transcripts, news, policy speeches, or research text.

Typical methods:

- embedding metrics,
- sentiment extraction,
- semantic shift,
- topic modeling,
- text-to-return linkage,
- controlled regressions.

Reviewer attacks:

- label validity,
- text leakage,
- model drift,
- multiple testing,
- interpretability.

### 8.7 Network / Systemic Risk Study

Purpose:

- analyze connectedness, holdings networks, contagion, systemic risk.

Typical methods:

- graph construction,
- centrality,
- network regression,
- GNN if available,
- stress simulation,
- CoVaR/SRISK linkage if data exists.

Reviewer attacks:

- network construction,
- missing holdings,
- lookahead bias,
- target availability,
- interpretability.

### 8.8 Agent-Based Market Simulation

Purpose:

- study market microstructure, flash crashes, liquidity shocks, AI-agent behavior.

Typical methods:

- agent simulation,
- order book dynamics,
- correlated strategy scenarios,
- stress tests,
- recovery-time measurement.

Reviewer attacks:

- simulation realism,
- calibration,
- parameter sensitivity,
- external validity.

## 9. Cadence And Frequency Logic

Cadence is not a universal dropdown. It can play different roles:

1. Fixed by data: macro series may be monthly or quarterly.
2. Fixed by market convention: daily close data for many equity studies.
3. Part of the experiment: rotation frequency may be a design variable.
4. Robustness dimension: primary monthly result with weekly/quarterly checks.
5. Event-window logic: event studies care about windows, not rebalance frequency.
6. Irrelevant: some descriptive studies do not need cadence as a central concept.

The Research Architect must infer which role applies from the brief.

Blueprint fields:

- `recommended_frequency`
- `cadence_role`
- `cadence_explanation`

## 10. Agent Roster

### 10.1 Research Architect

Role:

- interpret research intent,
- identify research archetype,
- decide exploratory vs confirmatory stance,
- ask blocking clarifications,
- produce the blueprint,
- assemble agent stack,
- define revision policy.

Inputs:

- question,
- context,
- data instructions,
- design instructions,
- validation notes,
- uploaded/staged evidence metadata,
- user expertise mode.

Outputs:

- Research Blueprint,
- architect questions,
- launch readiness,
- completion contract.

Core skill:

- research design reasoning.

Prompt contract:

```text
You are the Research Architect for empirical finance.
Read the user's research intent, evidence reality, design constraints, and validation burden.
Return a blueprint that a data agent, method agent, stats agent, reviewer, and writer can execute.
Ask only clarifications that block the next correct step.
Do not turn examples into defaults.
Do not choose a method before identifying the claim, evidence route, comparison set, and burden of proof.
Return structured JSON only.
```

### 10.2 Literature Agent

Role:

- map prior evidence,
- find closest literature,
- identify contribution,
- warn when novelty is weak.

Inputs:

- blueprint research topic,
- archetype,
- method family,
- claimed contribution.

Outputs:

- `literature_map.md`,
- theory frame,
- closest papers,
- contribution statement,
- prior-method warnings.

Skills vary by topic:

- asset pricing literature,
- corporate finance literature,
- macro-finance literature,
- market microstructure literature,
- text-as-data finance literature,
- systemic risk literature.

Prompt contract:

```text
You are the Literature Agent.
Use the Research Blueprint as the only source of study intent.
Map the closest empirical finance literature.
Separate established evidence from the proposed contribution.
Identify what a reviewer will say is already known.
Do not invent citations.
```

### 10.3 Data Agent

Role:

- fetch public data,
- accept uploads,
- stage vendor/internal extracts,
- inspect schema,
- map identifiers,
- validate timing,
- create data preview and fingerprint.

Inputs:

- blueprint datapull section,
- data access mode,
- uploaded file,
- source availability.

Outputs:

- data preview,
- schema map,
- date range,
- missingness report,
- fingerprint,
- data certificate.

Skills vary by evidence route:

- yfinance,
- FRED,
- EDGAR,
- upload parser,
- staged external extract parser,
- future institutional connectors when available.

WRDS note:

WRDS must not be assumed available when paused or inaccessible. If unavailable, Thrivarc should either ask for upload/staged export or redesign the study around available evidence.

Prompt contract:

```text
You are the Data Agent.
Use only the evidence route approved in the blueprint.
Inspect identifiers, dates, frequency, missingness, and schema.
Do not let compute start until the researcher approves the preview.
If evidence is unavailable, return a blocker instead of inventing data.
```

### 10.4 Feature / Mining Agent

Role:

- transform raw evidence into research-ready features.

Inputs:

- approved data,
- blueprint feature definitions,
- method family.

Outputs:

- feature matrix,
- transformation log,
- leakage checks,
- alignment checks.

Skills vary by topic:

- returns and volatility construction,
- sentiment features,
- event-time alignment,
- network construction,
- portfolio weights,
- macro surprise variables.

Prompt contract:

```text
You are the Feature Agent.
Build only the variables required by the blueprint.
Record every transformation.
Check for lookahead bias and timing leakage.
Return a feature manifest and any blockers.
```

### 10.5 Preregistration Agent

Role:

- lock confirmatory claims before analysis.

Inputs:

- blueprint,
- hypothesis,
- test plan,
- data preview.

Outputs:

- preregistration lock,
- claim scope,
- exclusion rules,
- primary outcomes,
- primary tests.

Runs only when:

- research state is confirmatory,
- claim is specific enough,
- data preview is approved.

Prompt contract:

```text
You are the Preregistration Agent.
Lock the claim, primary outcome, test plan, and exclusion rules before analysis.
If the study is exploratory, do not pretend it is preregistered.
If the hypothesis is not specific, return a blocker.
```

### 10.6 Method / Compute Agent

Role:

- execute the approved method family.

Inputs:

- approved data,
- blueprint method,
- feature matrix,
- compute params.

Outputs:

- method outputs,
- charts,
- model artifacts,
- diagnostics.

Skills vary by archetype:

- backtest engine,
- event study engine,
- regression engine,
- causal design engine,
- text analysis engine,
- network engine,
- simulation engine.

Prompt contract:

```text
You are the Method Agent.
Execute only the method approved in the blueprint.
Do not silently change benchmark, window, costs, cadence, model family, or target variable.
If the approved method cannot run with the available data, return a concrete blocker.
```

### 10.7 Statistics Agent

Role:

- test evidence strength.

Inputs:

- method outputs,
- blueprint validation plan,
- research state.

Outputs:

- statistical tables,
- robustness checks,
- p-values or confidence language,
- multiple testing notes,
- inference limitations.

Skills vary by method:

- t-tests,
- Newey-West,
- clustered errors,
- bootstrap,
- placebo,
- sensitivity analysis,
- multiple-testing correction,
- out-of-sample metrics.

Prompt contract:

```text
You are the Statistics Agent.
Run only the test battery required by the blueprint and method outputs.
Separate exploratory evidence from confirmatory evidence.
Report uncertainty honestly.
Return null or inconclusive findings when evidence does not support the claim.
```

### 10.8 Code Audit Agent

Role:

- check code-to-method alignment.

Inputs:

- blueprint,
- code,
- method outputs.

Outputs:

- code audit report,
- mismatches,
- severity,
- repair recommendations.

Prompt contract:

```text
You are the Code Audit Agent.
Read the code and the blueprint.
Verify that the implementation matches the approved method.
Find mismatches in data joins, windows, costs, benchmarks, variables, and tests.
Do not judge writing quality. Judge implementation fidelity.
```

### 10.9 Spec Audit Agent

Role:

- check spec-to-code and protocol-to-code consistency.

Inputs:

- blueprint,
- preregistration lock,
- method code,
- results.

Outputs:

- spec audit report,
- violations,
- required fixes.

Prompt contract:

```text
You are the Spec Audit Agent.
Compare the approved research blueprint against the executed pipeline.
Identify any deviation from the plan.
If a deviation is legitimate, require disclosure.
If a deviation changes the claim, route back to Research Architect.
```

### 10.10 Reviewer Agent

Role:

- attack the study like a serious referee, PM, IC member, or policy reviewer.

Inputs:

- blueprint,
- literature map,
- data certificate,
- method outputs,
- stats tables,
- audit reports,
- draft claims.

Outputs:

- reviewer report,
- strengths,
- weaknesses,
- issue severity,
- owner,
- rerun scope,
- recommended follow-up,
- reviewer score.

Prompt contract:

```text
You are the Reviewer Agent.
Attack the study before the outside world does.
Focus on benchmark choice, identification, timing, data quality, robustness, overfitting, and claim discipline.
Each weakness must have severity, owner, rerun scope, and pass/fail criterion.
Do not ask for vague improvement.
```

### 10.11 Repair Agent

Role:

- perform bounded issue-driven reruns.

Inputs:

- reviewer issue,
- owning phase,
- rerun scope,
- previous outputs.

Outputs:

- repaired artifact,
- diff summary,
- before/after comparison,
- pass/fail status.

Prompt contract:

```text
You are the Repair Agent.
Repair only the concrete issue assigned by the reviewer or audit layer.
Stay within the blueprint unless the Research Architect explicitly revises it.
Record what changed and rerun dependent checks.
Stop if the issue cannot be fixed honestly.
```

### 10.12 Paper-Code Verifier

Role:

- verify paper claims against code and outputs.

Inputs:

- paper draft,
- tables,
- charts,
- stats outputs,
- code artifacts.

Outputs:

- claim verification report,
- unsupported claims,
- wrong numbers,
- missing limitations.

Prompt contract:

```text
You are the Paper-Code Verifier.
Every number and claim in the paper must be traceable to an output artifact.
Flag unsupported claims, overstated conclusions, and mismatched statistics.
The writer cannot finalize until this passes.
```

### 10.13 Writer Agent

Role:

- write final paper sections from verified outputs.

Inputs:

- approved blueprint,
- final findings,
- reviewer-approved limitations,
- verified tables and charts.

Outputs:

- abstract,
- methodology,
- results,
- limitations,
- conclusion scaffold,
- LaTeX file.

Prompt contract:

```text
You are the Writer Agent.
Write only from verified findings and approved outputs.
Do not invent numbers, citations, methods, or claims.
Preserve limitations.
If reviewer or verifier gates fail, do not finalize the paper.
```

## 11. Agent Skill Selection

Agent skills are selected from the blueprint.

Selection inputs:

- research archetype,
- evidence source,
- method style,
- research state,
- cadence role,
- output intent,
- reviewer burden.

Examples:

- Backtest study: Data Agent loads market data or upload parser; Method Agent loads backtest skill; Stats Agent loads performance and robustness battery; Reviewer focuses on costs, overfit, benchmark, drawdown.
- Event study: Data Agent loads event-time data; Method Agent loads event-window skill; Stats Agent loads abnormal-return inference; Reviewer focuses on timing, confounds, leakage.
- Text finance study: Data Agent loads EDGAR/upload text; Feature Agent loads NLP extraction; Method Agent loads regression or predictive design; Reviewer focuses on text validity and leakage.
- Network study: Data Agent loads holdings/upload network data; Feature Agent builds graph; Method Agent loads network statistics or GNN; Reviewer focuses on construction and target validity.

## 12. Orchestration

The pipeline is a state machine controlled by the blueprint.

Default stage order:

1. Research Architect
2. Literature
3. Data
4. Feature / Mining
5. Preregistration if confirmatory
6. Method / Compute if needed
7. Statistics
8. Code Audit
9. Spec Audit
10. Reviewer
11. Repair loop if needed
12. Paper-Code Verification
13. Writer
14. Final package

Exploratory skip logic:

- Exploratory runs skip preregistration.
- Exploratory outputs are labeled exploratory.
- Reviewer prevents exploratory findings from being written as confirmatory claims.

Compute-none skip logic:

- Descriptive or evidence-mapping studies can skip heavy compute.
- Stats Agent still runs appropriate descriptive or diagnostic checks.
- Writer can only describe what was actually tested.

## 13. Self-Improvement Loop

Thrivarc self-improves within one research run through bounded issue-driven loops.

### 13.1 Micro Loops

Scope:

- one agent,
- one local issue,
- low cost.

Examples:

- fix symbol mapping,
- repair date parsing,
- rerun failed chart generation,
- correct a missing column mapping.

Max cycles:

- Data Agent: 2
- Feature Agent: 2
- Method Agent: 2
- Stats Agent: 2

### 13.2 Cross-Layer Loops

Scope:

- reviewer or audit issue causes an upstream rerun and downstream re-check.

Examples:

- Reviewer flags missing transaction costs.
- Method Agent reruns backtest with costs.
- Stats Agent reruns inference.
- Reviewer reassesses.
- Writer updates claims.

Max cycles:

- Reviewer cross-layer loop: 3

### 13.3 Hard Stops

The system halts instead of pretending success when:

- no valid data exists,
- the claim is not identifiable,
- the uploaded schema cannot support the research question,
- confirmatory claim was formed after seeing results,
- paper claims exceed evidence,
- reviewer score remains below threshold after repair cycles.

### 13.4 Issue Object

Each improvement issue must include:

- issue id,
- severity,
- owner,
- rerun scope,
- required artifact,
- pass criterion,
- downstream checks to rerun,
- before/after comparison.

## 14. Backend Architecture

### 14.1 Current Active Components

Active bridge:

- `api/main.py`
- `api/guide.py`
- `api/data.py`
- `api/runs.py`
- `api/artifacts.py`

Frontend:

- `frontend/index.html`
- `frontend/app.html`

Core pipeline:

- `run_pipeline.py`
- `agents/`
- `conductor/`
- `aria/`
- `prompts/`

### 14.2 Azure Architecture

Production target:

- Domain: `app.thrivarc.studio`
- Frontend: static HTML served by API container or app route.
- API: FastAPI bridge.
- Model provider: Azure OpenAI for planner and LLM agents.
- Container registry: Azure Container Registry.
- Runtime: Azure Container Apps.
- Worker: Azure Container Apps Job for long-running research execution.
- Database: Azure PostgreSQL for run state, phase state, budgets, results.
- Blob storage: Azure Blob for run artifacts, uploads, previews, paper packages.
- Observability: logs, phase events, cost table, run status endpoints.

### 14.3 API Routes

Required routes:

- `GET /health`
- `POST /guide/validate`
- `POST /guide/build_runspec`
- `POST /data/upload`
- `POST /data/preview`
- `POST /runs/create`
- `GET /runs`
- `GET /runs/{run_id}/status`
- `GET /runs/{run_id}/log`
- `GET /runs/{run_id}/findings`
- `GET /runs/{run_id}/reviewer_report`
- `GET /runs/{run_id}/charts`
- `GET /runs/{run_id}/tables`
- `GET /runs/{run_id}/paper`
- `GET /runs/{run_id}/files/{filename}`

### 14.4 Storage Contract

Postgres stores:

- runs,
- phases,
- token budget,
- agent results,
- result gates,
- metadata,
- blueprint state,
- completion contract,
- reviewer issues.

Blob stores:

- uploaded files,
- data previews,
- data certificates,
- logs,
- charts,
- tables,
- audit reports,
- reviewer reports,
- paper drafts,
- LaTeX package.

Local storage may exist for development, but production truth must be shared storage.

## 15. Frontend Product Surfaces

### 15.1 Landing Page

Purpose:

- explain product category,
- establish credibility,
- route directly into research flow.

Required message:

- research operating system for finance,
- question to evidence to defense,
- blueprint before compute,
- writer last.

Primary CTA:

- `Start Researching Free` -> `app.html#new`

### 15.2 Research Home

Purpose:

- control surface for studies.

Shows:

- total studies,
- completed studies,
- in-progress studies,
- spend,
- studies needing blueprint attention,
- studies needing evidence approval,
- studies needing defense review.

### 15.3 Start Research

Purpose:

- universal research intake.

Contains:

- question,
- context,
- data access,
- staged evidence upload,
- optional research design notes,
- live architect read.

### 15.4 Blueprint Screen

Purpose:

- show formal design before evidence preview.

Shows:

- research stance,
- evidence source,
- method style,
- validation plan,
- cadence logic,
- decision problem,
- comparison set,
- burden of proof,
- if true,
- evidence readiness,
- output plan,
- universe hints,
- historical window,
- assumptions,
- reviewer attacks,
- agent stack,
- revision policy,
- architect questions,
- launch readiness,
- completion contract.

### 15.5 Evidence Preview

Purpose:

- block compute until evidence is real.

Shows:

- source route,
- uploaded file status,
- identifiers,
- date range,
- frequency,
- columns,
- sample rows,
- quality,
- fingerprint.

### 15.6 Run Page

Purpose:

- show research execution truth.

Shows:

- current stage,
- completed stages,
- agent stack,
- revision policy,
- logs,
- findings,
- reviewer issues,
- follow-up research,
- paper workspace.

## 16. Prompt Strategy

Prompts must be:

- blueprint-first,
- role-specific,
- research-type aware,
- artifact-grounded,
- output-structured.

Prompts must not:

- reuse example topics as defaults,
- hallucinate unavailable data,
- silently change study design,
- write final claims before evidence,
- collapse exploratory work into confirmatory language.

Each agent prompt includes:

- role,
- allowed inputs,
- forbidden actions,
- required outputs,
- failure/blocker format,
- artifact references.

## 17. Inspiration From Reference Repos

Thrivarc borrows ideas from the user's inspiration repos without copying their specific product surface.

### 17.1 Hermes Agent / DeepAgents / OpenClaw

Influence:

- persistent agent identity,
- specialist subagents,
- planning before execution,
- agent context handoff,
- tool-using autonomy.

Thrivarc application:

- Research Architect builds blueprint.
- Specialist agents execute slices.
- Agent stack is visible.
- Agents hand off artifacts through the blueprint.

### 17.2 Kestra / Itential MCP / Remote Claws

Influence:

- workflow orchestration,
- jobs,
- retries,
- evented execution,
- external tool connectivity.

Thrivarc application:

- Azure worker jobs execute runs.
- Phases are stateful.
- Reruns are bounded and owned.
- Connectors are explicit.

### 17.3 Paper2Code / Feynman

Influence:

- idea-to-code and paper-to-code fidelity,
- research decomposition,
- artifact consistency.

Thrivarc application:

- blueprint-to-code,
- code-to-paper verification,
- writer last.

### 17.4 Darwinian Evolver / Claw-Code

Influence:

- evaluator/mutator loops,
- failure-driven improvement.

Thrivarc application:

- reviewer issues trigger bounded repairs,
- before/after comparisons,
- hard stops.

### 17.5 UI Dojo / Nanochat

Influence:

- clear control surfaces,
- inspectable state,
- fast interaction.

Thrivarc application:

- Research Home as cockpit,
- live architect read,
- visible agent contract,
- evidence preview gate.

## 18. Quality Gates

### 18.1 Product Truth Gates

- UI readiness must match backend completion contract.
- Blocking clarifications must block evidence preview.
- Evidence preview must precede run creation.
- Writer cannot finalize before reviewer/audit gates.
- Exploratory work must be labeled exploratory.
- Confirmatory work must lock claims before analysis.

### 18.2 Data Gates

- no data, no compute,
- no preview, no run,
- unavailable connector triggers blocker,
- uploaded schema must map to research question,
- date range and identifiers must be shown.

### 18.3 Method Gates

- method must match archetype,
- compute-none studies skip compute,
- backtests include cost/turnover assumptions,
- event studies include event and estimation windows,
- causal studies include identification checks.

### 18.4 Review Gates

- reviewer issues require owner and rerun scope,
- severe unresolved issue blocks final writer,
- repair loops are bounded,
- limitations are preserved.

### 18.5 Paper Gates

- every claim traceable,
- every number traceable,
- every table and chart traceable,
- unsupported claims removed or qualified,
- LaTeX generated only from verified outputs.

## 19. Success Metrics

### 19.1 User Metrics

- question-to-blueprint completion rate,
- blueprint approval rate,
- evidence preview approval rate,
- run completion rate,
- follow-up acceptance rate,
- paper export rate,
- repeat study rate.

### 19.2 Research Quality Metrics

- reviewer score improvement after repair,
- unresolved severe issues per run,
- data preview failure rate,
- code/spec mismatch rate,
- paper/code mismatch rate,
- null/inconclusive honesty rate.

### 19.3 Business Metrics

- paid conversion,
- cost per completed defensible study,
- average revenue per research run,
- repeat usage by researcher,
- saved research hours estimated by user.

## 20. Non-Goals

Thrivarc should not:

- promise investment advice,
- guarantee significant findings,
- hide limitations,
- generate fake citations,
- run unavailable institutional data,
- let examples become defaults,
- ask users to configure pipeline internals as primary UX,
- replace expert judgment.

## 21. Release Definition Of Complete

The product is ready to call complete for the current milestone when:

1. A user can enter a research question and context in natural language.
2. Thrivarc builds a blueprint with correct stance, method, evidence route, agent stack, and revision policy.
3. Blocking clarifications block evidence preview consistently in UI and backend.
4. Upload/staged evidence can be provided and previewed.
5. Public data preview works for supported public studies.
6. Run creation uses the approved blueprint and data fingerprint.
7. Pipeline phases follow the blueprint, including exploratory and compute-none skip logic.
8. Reviewer issues can route follow-up work with owner and rerun scope.
9. Paper workspace uses verified outputs only.
10. Live website copy matches actual backend behavior.
11. Full regression suite passes.
12. Azure deployment is verified on `app.thrivarc.studio`.

## 22. Open Risks

1. Agent specialization must continue to deepen by research archetype.
2. Azure worker dispatch and shared storage must remain the production source of truth.
3. Institutional data connectors must degrade honestly when unavailable.
4. Reviewer-driven repair loops need strict before/after metrics.
5. UI polish must serve repeated research work, not become marketing decoration.

## 23. North Star

Thrivarc should feel like a serious research partner:

- sharp enough for a top economist,
- practical enough for a quant researcher,
- disciplined enough for an academic referee,
- usable enough for a smart researcher who does not want to manage pipeline machinery.

The user should feel that Thrivarc is not merely helping them write research.

It is helping them survive the research process.
