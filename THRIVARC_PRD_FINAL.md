# THRIVARC PRD FINAL

Status: V1 product blueprint grounded in the current repository implementation as of 2026-05-14. Anything not implemented in this pass is marked `[v2]`. Two canonical API patterns: Pipeline API at `/runs/*` (research execution layer) and Session API at `/api/sessions/*` (session lifecycle and collaboration layer). Both are V1. PostgreSQL state through `db/connection.py`, Azure Blob artifacts through `storage/blob.py`, and real-time updates through Server-Sent Events.

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

Non-negotiable trust principle: Writer is last and never invents numbers.

## 2. Problem Statements

### 2.1 Research Starts Too Ambiguously
Researchers often begin with an idea, not a clean hypothesis, dataset, method, and test battery. Most tools force them to pick parameters too early: model, frequency, data connector, compute type, test family, output type. Thrivarc starts with natural language and lets the Research Architect infer the study shape.

### 2.2 Serious Finance Research Has Too Many Disconnected Steps
A finance research project can require literature framing, data sourcing, cleaning, feature construction, backtesting, event study design, causal identification, statistical testing, robustness checks, code review, reviewer simulation, paper drafting, and consistency verification. Thrivarc puts the lifecycle behind one Blueprint and one orchestrated agent system.

### 2.3 Research Tools Overproduce Text And Underproduce Evidence
Most AI products can write plausible paragraphs. Serious researchers need evidence, assumptions, reproducibility, reviewer pressure, and defensible limitations. Thrivarc treats writing as the final stage, not the starting point.

### 2.4 Data Reality Is Usually The Bottleneck
The right data path depends on the study. Some work can use public market data. Some requires upload. Some requires staged vendor exports. Some needs proprietary panels. WRDS is not a V1 default because current access is paused. Thrivarc supports upload, staged evidence, public sources, exact preview, and blocking when evidence is not real.

### 2.5 Methods Cannot Be Chosen From A Universal Dropdown
A TSX 60 rotation study, an FOMC event study, a transcript sentiment study, a systemic-risk network study, and an agent-based market simulation require different methods, data structures, validation burden, and reviewer attacks. Thrivarc infers method family from the Blueprint and loads research-type-specific agent behavior.

### 2.6 Researchers Need Defense Before Submission
The best researchers try to kill their own results before someone else does. They ask whether the benchmark is fair, timing is correct, costs erase the effect, code matches claims, and the paper overclaims. Thrivarc has an adversarial review and repair layer before writing.

### 2.7 Product Trust Breaks When UI And Backend Disagree
If the website says blocked but the backend says ready, trust is gone. Thrivarc uses truth contracts, DB-backed state, Blob-backed artifacts, and SSE events so visible UI state maps to a declared backend source.

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
11. Paper is earned not default. The gate decides.

## 4. Target Users and Willingness to Pay

### 4.1 World-Class Finance Economist
Example: a researcher with the standards of Raghuram Rajan.

Why they pay: they buy disciplined empirical leverage, not text generation. They value a system that preserves the distinction between exploratory and confirmatory claims, logs deviations, exposes identification weaknesses, and drafts only after the evidence clears.

Current alternative: research assistants, notebooks, spreadsheets, manual literature notes, and repeated private critique loops.

Value: fewer avoidable empirical mistakes, faster first defensible package, stronger pre-submission discipline.

### 4.2 Academic Finance Researcher or PhD Student
Why they pay: they need a research architect, data RA, method RA, skeptical reviewer, and LaTeX assistant in one controlled workflow.

Current alternative: ChatGPT for prose, scripts for data, Zotero/Google Scholar for literature, notebooks for tests, manual reviewer guessing.

Value: faster movement from idea to Blueprint, evidence preview, statistical battery, reviewer scorecard, and paper-ready sections.

### 4.3 Quant Researcher or Portfolio Manager
Why they pay: they need investment committee quality evidence. The system enforces universe, benchmark, timing, turnover, transaction costs, out-of-sample validation, and auditability.

Current alternative: fragile notebooks, overfit backtests, slide decks detached from code, and manual model risk review.

Value: reduced backtest storytelling risk, reusable audit artifacts, faster strategy triage.

### 4.4 Policy, Risk, or Institutional Research User
Why they pay: they need an auditable evidence package from an ambiguous economic question without personally operating every empirical step.

Current alternative: consultant memos, analyst spreadsheets, generic AI summaries.

Value: traceable assumptions, reproducible evidence, plain-English artifacts for non-technical stakeholders.

## 5. The Research Integrity System

### DataPassport
Implemented in `integrity/data_passport.py`.

Output: JSON and PDF in Azure Blob Storage under `sessions/{session_id}/03_data/`.

Content:
- Plain-English summary first.
- Data identity: sources, parameters, date range, universe, frequency, rows before/after exclusions, exclusions.
- Hashes: raw SHA-256, clean SHA-256, locked timestamp.
- Schema profile: columns, types, missingness.

Purpose: certify what data was used and allow an editor, risk manager, mentor, or compliance reviewer to verify the hash.

### Pre-registration Certificate
Implemented in `integrity/preregistration_certificate.py`.

Output: JSON and PDF under `sessions/{session_id}/05_preregistration/`.

Content:
- Plain-English statement that hypothesis, primary test, and significance threshold were locked before analysis.
- Locked claims: hypothesis, primary test, secondary tests, threshold, effect-size minimum, exclusion rules.
- Lock record: timestamp, Blueprint hash, session ID, verification instruction.
- Deviation summary.

Compatibility: V1 is a Thrivarc-native certificate. `[v2]` OSF and AEA Registry export adapters.

### Deviation Register
Implemented in `integrity/deviation_register.py`.

Output: JSON and PDF under `sessions/{session_id}/01_integrity/`.

Content:
- Header explaining that every post-lock change is recorded.
- Chronological entries: timestamp, field, before, after, reason, automatic vs researcher-approved, triggering agent.
- Footer totals: deviations, automatic, researcher-approved, integrity statement.

## 6. The Agent System

All agents use the canonical I/O wrapper in `agents/io_wrapper.py`: phase start to DB, inputs from DB/Blob, outputs to Blob, phase completion to DB, SSE event, structured failure state on error.

### 1. Research Architect
Responsibility: turn natural language into the Research Blueprint.
Input: session topic, context, constraints, target outcome.
Behavior: infer research type, sub-domain, method family, evidence route, clarification policy.
Output: Blueprint draft.
DB write: `blueprints`, `phases`.
SSE event: `phase_update`.
Failure modes: `needs_clarification`, `failed_resumable`.
Former names changed away from code-name style: GUIDE/architect logic is now role-named.

### 2. Literature Agent
Responsibility: map related research and gaps.
Input: Blueprint, domain, method family.
Behavior: search and cluster papers into established, contested, adjacent.
Output: papers, synthesis, gap analysis.
DB write: `papers`, `phases`.
SSE event: `section_ready`.
Failure modes: too few relevant papers, paywall-limited evidence.
Former name: Scout-style code path.

### 3. Data Agent
Responsibility: ingest or fetch evidence.
Input: evidence route, upload refs, public connector parameters.
Behavior: preview schema, detect dates/identifiers/numeric fields, compute SHA-256, block bad data.
Output: DataPassport preview and data quality report.
DB write: `phases`.
Blob write: `03_data/*`.
SSE event: `section_ready`.
Failure modes: source unavailable, schema mismatch, missing dates.
Former name: Miner/DataPull style path.

### 4. Feature / Mining Agent
Responsibility: create features without leakage.
Input: approved evidence and Blueprint timing rules.
Behavior: construct features, check timing, write leakage report.
Output: feature manifest, leakage report.
DB write: `phases`.
SSE event: `phase_update`.
Failure modes: leakage detected, missing identifiers.

### 5. Preregistration Agent
Responsibility: lock confirmatory design.
Input: Blueprint.
Behavior: compute Blueprint hash, create lock record, generate certificate seed.
Output: PAP and pre-registration certificate.
DB write: `pap_locks`, `blueprints.status=locked`.
SSE event: `section_ready`.
Failure modes: missing hypothesis or primary test.
Former name: preregister/SIGMA_JOB1 style path.

### 6. Method / Compute Agent
Responsibility: execute approved method.
Input: Blueprint, certified data, feature manifest.
Behavior: run backtest, event study, regression, descriptive, or method adapter.
Output: method outputs.
DB write: `phases`.
SSE event: `phase_update`.
Failure modes: method cannot run on certified evidence, timeout.
Former name: Forge-style compute path.

### 7. Code Audit Agent
Responsibility: technical correctness.
Input: code, outputs, artifact schema.
Behavior: check execution, approved libraries, edge cases, output format.
Output: code audit report.
DB write: `phases`.
SSE event: `section_ready`.
Failure modes: code/output mismatch, missing artifact.
Former name: CODEC/codeaudit pass.

### 8. Statistics Agent
Responsibility: run statistical battery.
Input: method outputs and locked tests.
Behavior: compute inference, robustness, economic significance.
Output: tables and economic significance report.
DB write: `phases`.
SSE event: `section_ready`.
Failure modes: weak evidence, invalid assumptions, missing output columns.
Former name: statsrun/SIGMA_JOB2 style path.

### 9. Spec Audit Agent
Responsibility: research integrity correctness.
Input: Blueprint, outputs, planned tests, reported tables.
Behavior: verify outputs match Blueprint and claims stay in track.
Output: spec audit report.
DB write: `phases`.
SSE event: `section_ready`.
Failure modes: test not in plan, claim exceeds evidence.

### 10. Reviewer Agent
Responsibility: conditional paper gate.
Input: Blueprint, literature, data quality, stats, economic significance, audit reports.
Behavior: score seven dimensions independently and decide pass, repair, or paper lock.
Output: reviewer scorecard.
DB write: `reviewer_scores`, `repair_log`, `deviation_register` when needed.
Blob write: `09_review/reviewer_scorecard_v{n}.json`.
SSE event: `gate_result`, `repair_triggered`, `writer_unlocked`, `paper_locked`.
Failure modes: below threshold, cycle exhausted.
Former name: Hawk-style reviewer path.

### 11. Repair Agent
Responsibility: bounded issue-driven reruns.
Input: Repair Contract.
Behavior: rerun only the named scope and pass criterion.
Output: repair log and versioned artifacts.
DB write: `repair_log`, `phases`, `deviation_register` if Blueprint changes.
SSE event: `repair_triggered`, `repair_complete`.
Failure modes: repair exhausted, approval denied.

### 12. Paper-Code Verifier
Responsibility: verify paper claims match code outputs.
Input: evidence tables, draft claims, output artifacts.
Behavior: block Writer if numbers or claims are unsupported.
Output: verification report.
DB write: `phases`.
Blob write: `10_verification/paper_code_verification.json`.
SSE event: `phase_update`.
Failure modes: mismatch, unsupported claim.

### 13. Writer Agent
Responsibility: write only from verified evidence.
Input: approved Blueprint, final results, reviewer scorecard, verifier pass.
Behavior: draft LaTeX without inventing numbers.
Output: `.tex` and final package.
DB write: `sessions.status=paper_unlocked` after successful package.
Blob write: `11_paper/*`.
SSE event: `run_complete`.
Failure modes: verifier mismatch, missing evidence artifact.
Former name: Quill-style writer path.

## 7. The Reviewer Agent Gate

Implemented in `agents/reviewer_agent.py`.

Dimensions:
1. identification_validity
2. data_integrity
3. statistical_rigor
4. economic_significance
5. benchmark_fairness
6. robustness_burden
7. overclaiming_risk

Thresholds:
- Pass only if average score is at least 7.0.
- Pass only if every dimension is at least 6.0.
- Maximum repair cycles: 3.

Score bands:
- Average >= 7.0 and all dimensions >= 6.0: Writer unlocked.
- Average 5.0 to 6.9 or any dimension 4.0 to 5.9: repair required if cycles remain.
- Average < 5.0 or any dimension < 4.0: red gate; still may repair until cycle ceiling, then paper locked.
- Cycle 3 failure: `sessions.status=paper_locked` and Writer remains blocked.

DB writes:
- `reviewer_scores` every cycle.
- `repair_log` when repair is triggered.
- `deviation_register` when repair changes Blueprint fields.

SSE events:
- `gate_result`
- `repair_triggered`
- `writer_unlocked`
- `paper_locked`

## 8. The Repair Agent Contract

Every repair has:
- trigger agent
- trigger finding
- scope
- pass criterion
- cycle number
- approval requirement
- outcome
- deviation_registered flag

Automatic repairs:
- rerun failed parser
- regenerate chart from existing outputs
- run robustness already named in Blueprint
- fix formatting that does not change a claim

Researcher approval required:
- Blueprint change
- data source change
- benchmark or universe change
- method-family change
- claim-type upgrade

Rules:
- No repair silently changes the Blueprint.
- Blueprint changes write the Deviation Register.
- Cycle ceiling is 3.
- If cycle ceiling is exhausted, paper writing is locked and the researcher receives report/fork/download options.

## 9. Finance Sub-domains

### Asset Pricing and Factor Studies
Data sources: yfinance, uploaded panels, staged vendor extracts, FRED for macro controls. WRDS is `[v2]` until stable access exists.
Test battery: factor regressions, Fama-MacBeth `[v2]`, Newey-West, spanning tests `[v2]`, out-of-sample validation, transaction costs.
Reviewer rubric emphasis: benchmark fairness, investability, economic significance, overfitting, costs.

### Corporate Finance and Event Studies
Data sources: uploaded event lists, EDGAR/public filings, yfinance market data, staged analyst/vendor data.
Test battery: CAR, BHAR, market model abnormal returns, bootstrap inference, cross-sectional CAR regression.
Reviewer rubric emphasis: event definition, timing leakage, confounds, clustering, causal language.

### Time-Series Macro and Financial Econometrics
Data sources: FRED, yfinance, uploaded macro panels, staged institutional extracts.
Test battery: ADF, structural breaks, VAR, Granger causality, GARCH `[v2]`, cointegration `[v2]`.
Reviewer rubric emphasis: stationarity, regime stability, lag structure, forecast evaluation, policy interpretation.

## 10. Screen-by-Screen User Journey

### Landing
Researcher sees the operating-system promise: question to evidence to defense before writing. CTA opens universal intake. API offline banner is hidden on first load and only appears after failed checks.

### Universal Research Intake
Researcher writes question, context, data reality, design burden, validation expectations, and optional file. No method dropdown is required. The system does not compute here.

### Live Architect Read
Research Architect shows inferred stance, evidence route, method family, cadence role, universe cue, and fragility. The researcher can edit or answer questions.

### Clarification Workspace
Blocking questions appear one at a time with why they matter and which downstream phase depends on them. Answers are folded back into the Blueprint and completion contract is recomputed.

### Blueprint Review
Researcher sees research package, clarification policy, reviewer gate, repair contract, integrity artifacts, audit boundary, leakage policy, statistical battery, and economic significance policy. Approval opens evidence preview only.

### Evidence Preview
Researcher previews uploaded or public data, schema, missingness, identifiers, date range, sample rows, SHA-256, and DataPassport preview. Blocking issues stop launch.

### Blueprint Lock
Confirmatory studies lock Blueprint, hash, hypothesis, primary test, threshold, and pre-registration certificate seed. Exploratory studies are labeled hypothesis-generating.

### Persona Adaptation
The UI adapts depth and language to the researcher's declared persona (explorer, researcher, expert) without changing the underlying pipeline behavior. Explorer mode uses plain-English labels and hides SHA-256 hashes, run IDs, raw logs, and p-values. Expert mode exposes agent code names, raw JSON previews, and technical identifiers. Persona selection is stored in `localStorage` and applied through `PERSONA_CONFIG` in `frontend/app.html`.

### Run Page
Researcher watches live phase updates through Server-Sent Events. The frontend connects to `GET /api/sessions/{id}/stream` for session-level event replay and `GET /runs/{id}/stream` for pipeline phase polling. Phase cards read from `phases.status`.

### Reviewer Gate
Researcher sees scorecard, dimension-level findings, pass/fail outcome, repair scope, and expected next action.

### Repair Loop
If repair is safe, the repair can run automatically. If it changes Blueprint/data/benchmark/method/claim type, owner approval is required and Deviation Register is written.

### Paper Workspace
Writer appears only after reviewer and verifier gates pass. Paper links appear only when `sessions.status=paper_unlocked`.

### Failure Card
Failures render structured error state: error code, human message, system state, available actions, and resume/fork/download options.

## 11. Session History and Resumption

Implemented in `/api/sessions`, `/api/sessions/{id}/resume`, `/api/sessions/{id}/fork`, `/api/sessions/{id}/compare/{other_id}`.

History item fields:
- id
- topic
- research_type
- status
- last_phase
- next_action
- resume_route
- created_at
- last_activity_at
- credits_spent
- artifact_count
- coauthor_status
- parent_run_id
- reviewer_average_score

Resumption states:
- `draft` or `initializing`: route to intake.
- `needs_clarification`: route to Blueprint clarifications.
- `evidence_blocked`: route to data preview.
- `scope_confirmed`: route to Blueprint approval.
- `running`: route to run page and SSE stream.
- `failed_resumable`: route to failure card.
- `failed_terminal`: route to download/fork package.
- `paper_unlocked`: route to paper workspace.

Fork rule: child session gets `parent_run_id`; parent session and parent artifacts are not modified.

Compare rule: compare returns diff for topic, research type, method, data source, reviewer average score.

## 12. Failure State Catalogue

Every failure writes DB state before emitting SSE.

- Research Architect: `needs_clarification`, missing research question, action: answer clarification.
- Literature Agent: too few papers, action: sharpen question or continue with warning.
- Data Agent: source unavailable, schema mismatch, missing date, action: upload data or adjust source.
- Feature / Mining Agent: leakage detected, action: repair feature timing.
- Preregistration Agent: missing hypothesis/test, action: complete confirmatory fields.
- Method / Compute Agent: method incompatible with evidence, timeout, action: repair method scope or fork.
- Code Audit Agent: execution/output mismatch, action: repair code artifact.
- Statistics Agent: invalid assumptions or weak/null evidence, action: accept null report or run robustness.
- Spec Audit Agent: outputs do not match Blueprint, action: repair or register deviation.
- Reviewer Agent: below threshold, action: repair, fork, or accept report.
- Repair Agent: cycle exhausted or approval denied, action: fork or download partial package.
- Paper-Code Verifier: paper claim mismatch, action: repair claim/table mismatch.
- Writer Agent: Writer blocked, action: wait for gate/verifier pass.

### Migration Artifact Fallback
The Pipeline API artifact routes (`/runs/{id}/findings`, `/runs/{id}/charts`, etc.) check `research_memory/{run_id}/` first and fall back to the legacy `paper_memory/{run_id}/` directory if the primary path does not exist. This is a V1 migration behavior for runs created before the directory rename. Remove this fallback when all legacy runs have been migrated or archived.

## 13. Co-Author Permission Model

Implemented in `auth/permissions.py` and `coauthor_invitations` table.

Permission table:

| Action | Owner | Co-author |
|---|---:|---:|
| Create session | YES | NO |
| Edit scope before lock | YES | YES |
| Answer clarifications | YES | YES |
| Lock Blueprint | YES | NO |
| Approve Blueprint deviation | YES | NO |
| Approve safe repair | YES | YES |
| Approve Blueprint-changing repair | YES | NO |
| Trigger fork | YES | NO |
| Download artifacts | YES | YES |
| View Deviation Register | YES | YES |
| View Reviewer scores | YES | YES |
| View truth contract | YES | YES |
| Invite co-author | YES | NO |
| Remove co-author | YES | NO |

Invitation flow: owner creates pending invitation. Access is not granted until accepted.

Concurrency rule: optimistic locking rejects stale Blueprint edits with `CONCURRENT_EDIT`, system state `conflict`, actions `refresh` and `view_current`.

Post-lock removal: removing a co-author after Blueprint lock writes a Deviation Register entry.

## 14. Backend Truth Matrix

| UI element | Source | Writer | SSE event |
|---|---|---|---|
| Session status badge | `sessions.status` | Pipeline orchestrator | `phase_update` |
| Blueprint lock button | `blueprints.status` | Research Architect | `phase_update` |
| Phase indicators | `phases.status` | Each agent | `phase_update` |
| Reviewer gate card | `reviewer_scores` | Reviewer Agent | `gate_result` |
| Repair approval card | `repair_log` | Repair Agent | `repair_triggered` |
| Writer unlock banner | `reviewer_scores.gate_passed` | Reviewer Agent | `writer_unlocked` |
| Paper download link | `sessions.status=paper_unlocked` | Writer Agent | `run_complete` |
| Deviation badge | `COUNT(deviation_register)` | Post-lock change handlers | `deviation_logged` |
| DataPassport download | Blob signed URL | Data Agent | `section_ready` |
| Pre-reg cert download | Blob signed URL | Preregistration Agent | `section_ready` |
| Deviation Register PDF | Blob signed URL | Integrity generator | N/A |
| Co-author status | `sessions.coauthor_id` | Owner action | N/A |
| Credits spent | `sessions.credits_spent` | Billing service | N/A |

Frontend enforcement: `frontend/app.html` declares `FRONTEND_TRUTH_STATE_MAP`, uses `EventSource`, and gates lock/writer/download controls from backend state.

SSE stream endpoints:
- `GET /api/sessions/{id}/stream`: replays stored session events from `session_events` table. Used by the frontend for UI state updates. Event types match the truth matrix above.
- `GET /runs/{id}/stream`: polls `pipeline_runs` for phase state changes. Emits `event: status` with full run object payload. Used for pipeline progress monitoring. Terminates on `done`, `failed`, or `cancelled`.

Both endpoints return `Content-Type: text/event-stream` and emit SSE-formatted messages.

## 15. Agent Execution Graph

Canonical order:

1. Research Architect -> Blueprint.
2. Parallel after Blueprint lock: Literature Agent and Data Agent.
3. Feature / Mining Agent after literature and data readiness.
4. Preregistration Agent for confirmatory studies only; skip for exploratory.
5. Method / Compute Agent.
6. Parallel after Method: Code Audit Agent and Statistics Agent.
7. Spec Audit Agent after code audit and statistics.
8. Reviewer Agent.
9. If gate fails and cycles < 3: Repair Agent and loop back to the owning phase, usually Method/Statistics/Data.
10. If gate fails at cycle 3: `paper_locked`.
11. Paper-Code Verifier.
12. Writer Agent only if reviewer gate passed and verifier clean.

Critical path estimates:
- Exploratory descriptive: 12 to 25 minutes.
- Exploratory empirical: 25 to 45 minutes.
- Confirmatory public-data study: 35 to 70 minutes.
- Confirmatory uploaded/staged evidence: 45 to 90 minutes.
- Heavy simulations or unavailable external data: `[v2]` long-running job class.

## 16. Research Memory Artifact Store

Canonical Blob root: `sessions/{session_id}/` in Azure Blob Storage container `research-artifacts`.

Write contracts:
- `00_runspec/runspec.json`: Research Architect.
- `00_runspec/blueprint.json`: Research Architect.
- `01_integrity/truth_contract.json`: session API.
- `01_integrity/reviewer_gate.json`: Reviewer contract seed.
- `01_integrity/repair_contract_template.json`: Repair contract seed.
- `01_integrity/data_passport_preview.json`: Data Agent preview.
- `01_integrity/deviation_register.json`: Deviation Register generator.
- `01_integrity/deviation_register.pdf`: Deviation Register generator.
- `02_literature/papers.json`: Literature Agent.
- `02_literature/synthesis.json`: Literature Agent.
- `02_literature/gap_analysis.json`: Literature Agent.
- `03_data/data_passport.json`: Data Agent.
- `03_data/data_passport.pdf`: Data Agent/integrity generator.
- `03_data/schema_profile.json`: Data Agent.
- `03_data/data_quality_report.json`: Data Agent.
- `04_features/feature_manifest.json`: Feature / Mining Agent.
- `04_features/leakage_report.json`: Feature / Mining Agent.
- `05_preregistration/pap_lock_certificate.json`: Preregistration Agent.
- `05_preregistration/pap_lock_certificate.pdf`: Preregistration Agent.
- `06_compute/method_outputs/`: Method / Compute Agent, versioned on repair.
- `07_statistics/results_tables/`: Statistics Agent, versioned on repair.
- `07_statistics/economic_significance.json`: Statistics Agent.
- `08_audit/code_audit_report.md`: Code Audit Agent.
- `08_audit/spec_audit_report.md`: Spec Audit Agent.
- `09_review/reviewer_scorecard_v{n}.json`: Reviewer Agent.
- `09_review/repair_contracts/`: Repair Agent.
- `10_verification/paper_code_verification.json`: Paper-Code Verifier.
- `11_paper/draft_v{n}.tex`: Writer Agent.
- `11_paper/final.tex`: Writer Agent.
- `11_paper/final.pdf`: Writer Agent.

Versioning rule: repair reruns write `v{n}` paths through `storage.blob.write_artifact(..., version=n)`.

## 17. Monetization Architecture

V1 model: per-run credits.

Why: it aligns payment with value received and avoids charging a subscription before a researcher trusts long-running evidence work.

Credit events:
- Session creation: free.
- Blueprint generation: low credit or included free tier.
- Evidence preview: low credit.
- Full exploratory run: medium credit.
- Confirmatory run with integrity artifacts: higher credit.
- Paper package after gate pass: premium credit.
- Repair reruns: scoped incremental credits.

Free tier: one Blueprint plus one evidence preview.

Upgrade trigger: launching full pipeline, downloading integrity package, or unlocking paper workspace.

Schema support: `sessions.credits_spent` exists. `[v2]` account billing ledger, payment provider integration, institution seats.

## 18. Azure Infrastructure Map

### Azure Static Web Apps
Serves `frontend/app.html` and marketing/static pages. Uses `X-MS-CLIENT-PRINCIPAL` auth header for V1 authenticated identity.

### Azure Container App
Runs FastAPI (`main.py` or `api/main.py`) with two canonical API patterns:
- **Pipeline API** (`/runs/*`): research execution layer. Implemented in `api/runs.py` and `api/artifacts.py`.
- **Session API** (`/api/sessions/*`): session lifecycle and collaboration layer. Implemented in `api/sessions.py`.
- **Guide API** (`/guide/*` and `/api/guide/*`): research blueprint builder. Implemented in `api/guide.py`.
- **Data API** (`/data/*` and `/api/data/*`): evidence upload and preview. Implemented in `api/data.py`.

Both `/runs/*` and `/api/sessions/*` are canonical V1 paths. The Pipeline API handles research execution; the Session API handles session lifecycle, collaboration, and structured state management.

### Pipeline API Route Table (`/runs/*`)

| Method | Route | Response | Source |
|---|---|---|---|
| `POST` | `/runs/create` | `{"run_id": "pf-live-..."}` | `api/runs.py` |
| `GET` | `/runs` | `{"runs": [{run_object}, ...]}` | `api/runs.py` |
| `GET` | `/runs/{id}/status` | `{run_object}` | `api/runs.py` |
| `GET` | `/runs/{id}/truth_contract` | `{"truth_contract": {research_state, artifact_manifest, orchestration, failure_catalog, ...}}` | `api/runs.py` |
| `GET` | `/runs/{id}/stream` | `text/event-stream` — polls DB, emits `event: status\ndata: {run_object}`, terminates on done/failed/cancelled | `api/runs.py` |
| `GET` | `/runs/{id}/log` | `{"log_lines": [{"timestamp": "...", "message": "..."}]}` — last 500 lines from pipeline.log | `api/runs.py` |
| `POST` | `/runs/{id}/cancel` | `{"cancelled": true, "run_id": "..."}` — kills subprocess, sets DB status to cancelled | `api/runs.py` |
| `GET` | `/runs/{id}/findings` | `{"findings": {"validity": "SIGNIFICANT\|NULL\|INCONCLUSIVE", "p_value": 0.008, "key_numbers": {...}}}` | `api/artifacts.py` |
| `GET` | `/runs/{id}/reviewer_report` | `{"score": 7.5, "reviewer_narrative": "...", "strengths": [...], "weaknesses": [...]}` | `api/artifacts.py` |
| `GET` | `/runs/{id}/charts` | `{"charts": [{"title": "...", "url": "/runs/{id}/files/chart.png", "alt": "..."}]}` | `api/artifacts.py` |
| `GET` | `/runs/{id}/tables` | `{"tables": [{"caption": "...", "url": "/runs/{id}/files/stats_tables/file.csv"}]}` | `api/artifacts.py` |
| `GET` | `/runs/{id}/paper` | `{"paper": {"thrivarc": {"methodology": "...", "results": "..."}, "researcher": {intro/lit/conclusion prompts}}}` | `api/artifacts.py` |
| `GET` | `/runs/{id}/files/{path}` | Raw file response (PNG, CSV, etc.) — path-traversal protected | `api/artifacts.py` |

### Session API Route Table (`/api/sessions/*`)

| Method | Route | Response | Source |
|---|---|---|---|
| `POST` | `/api/sessions` | `{"session_id": "uuid", "status": "initializing", "upload_urls": [...]}` | `api/sessions.py` |
| `GET` | `/api/sessions` | `[{session_summary}, ...]` | `api/sessions.py` |
| `GET` | `/api/sessions/{id}` | `{session_summary, phases, blueprint}` | `api/sessions.py` |
| `GET` | `/api/sessions/{id}/resume` | `{next_action, route, stream, status}` | `api/sessions.py` |
| `GET` | `/api/sessions/{id}/compare/{other_id}` | `{diff: {field: {from, to}}}` | `api/sessions.py` |
| `PATCH` | `/api/sessions/{id}/scope` | `{"status": "scope_confirmed"}` | `api/sessions.py` |
| `GET` | `/api/sessions/{id}/blueprint` | `{blueprint_content, reviewer_gate, status}` | `api/sessions.py` |
| `POST` | `/api/sessions/{id}/blueprint/lock` | `{locked_at, blueprint_hash, pap_lock_id}` | `api/sessions.py` |
| `POST` | `/api/sessions/{id}/blueprint/deviation` | `{deviation_id, approval_required}` | `api/sessions.py` |
| `GET` | `/api/sessions/{id}/truth_contract` | `{session_id, state_map, blueprint, artifact_root, sse_stream, writer_rule, failure_contract}` | `api/sessions.py` |
| `GET` | `/api/sessions/{id}/stream` | `text/event-stream` — replays stored session events | `api/sessions.py` |
| `POST` | `/api/sessions/{id}/run` | `{"run_started": true, "estimated_minutes": 45}` | `api/sessions.py` |
| `POST` | `/api/sessions/{id}/repair/approve` | `{"repair_status": "approved\|rejected"}` | `api/sessions.py` |
| `GET` | `/api/sessions/{id}/artifacts` | `{"artifacts": [{name, path, url, size}]}` | `api/sessions.py` |
| `GET` | `/api/sessions/{id}/results` | `{reviewer_scores, paper_url, report_url, integrity_artifacts, deviation_count}` | `api/sessions.py` |
| `POST` | `/api/sessions/{id}/fork` | `{"new_session_id": "uuid"}` | `api/sessions.py` |

### Guide API Route Table

| Method | Route | Response | Source |
|---|---|---|---|
| `GET` | `/guide` or `/api/guide` | Reference contract: research_package, clarification_policy, reviewer_gate, repair_contract_template, integrity_artifacts, audit_boundary, paper_code_verifier, data_quality_policy, leakage_policy, statistical_battery, economic_significance, data_fallback_policy | `api/guide.py` |
| `POST` | `/guide/validate` or `/api/guide/validate` | Full blueprint validation with clarifications, completion contract, and agent_stack_preview | `api/guide.py` |
| `POST` | `/guide/build_runspec` or `/api/guide/build_runspec` | RunSpec with research, datapull, compute, statsrun, and blueprint sections | `api/guide.py` |

### Data API Route Table

| Method | Route | Response | Source |
|---|---|---|---|
| `POST` | `/data/upload` or `/api/data/upload` | `{upload_path, filename, bytes, sha256, storage_backend}` | `api/data.py` |
| `POST` | `/data/preview` or `/api/data/preview` | `{preview: {rows, columns, date_range, sha256, schema_profile, data_passport, blocking_issues, warnings}}` | `api/data.py` |

### Azure Container Registry
Stores deployable API image.

### Azure Database for PostgreSQL
Production state store. `get_db_connection()` requires PostgreSQL URL in production and refuses SQLite. Tables include sessions, blueprints, phases, papers, lock records, deviation register, reviewer scores, repair log, session events, coauthor invitations.

### Azure Key Vault
Connection secrets are expected to be injected as environment variables for the running Container App. `[v2]` direct Key Vault secret fetch through Managed Identity if environment injection is not used.

### Managed Identity
Used by Azure Blob client through `DefaultAzureCredential` and intended for PostgreSQL secret access via Azure configuration.

### Azure Blob Storage
Storage account: `paperforgeartifacts`. Container: `research-artifacts`. Stores all canonical session artifacts under `sessions/{session_id}/`.

### Azure OpenAI
Model string standardized to `gpt-4o`. Used by guide/research-architect paths where an API key is present, with deterministic fallback for tests and unavailable keys.

### Server-Sent Events
Two real-time stream endpoints:
- `GET /api/sessions/{id}/stream`: replays stored session events from `session_events` table. Used by the frontend for UI truth state updates.
- `GET /runs/{id}/stream`: polls `pipeline_runs` for phase state changes. Emits `event: status` with the full run object. Terminates on done/failed/cancelled.

Both return `Content-Type: text/event-stream`. Events include `phase_update`, `section_ready`, `gate_result`, `repair_triggered`, `repair_complete`, `writer_unlocked`, `run_complete`, `run_failed`, `deviation_logged`.

### Observability
`[v2]` Application Insights, distributed tracing, and per-agent latency/cost dashboards.
