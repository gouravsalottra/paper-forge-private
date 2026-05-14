# Thrivarc PRD V1 - Mentor Ready Product Specification

Status: product specification grounded by the current implementation.

Primary implementation references:

- `THRIVARC_PRODUCT_BLUEPRINT_PRD.md`
- `THRIVARC_MENTOR_ALIGNMENT_IMPLEMENTED.md`
- `frontend/app.html`
- `api/guide.py`
- `api/data.py`
- `api/runs.py`

This PRD defines the human experience, business logic, failure behavior, collaboration model, session model, document artifacts, agent execution graph, and artifact write contracts that sit on top of the implemented engineering contracts.

## 1. Product Contract

Thrivarc turns a serious finance or economics research intent into a defensible empirical research package.

It does this by:

1. Understanding the research question in natural language.
2. Asking only clarifications that materially change evidence, method, interpretation, or launch readiness.
3. Creating a Blueprint before evidence execution.
4. Previewing and fingerprinting the exact data before compute.
5. Running an agent pipeline that executes only the approved RunSpec.
6. Auditing code and specification alignment separately.
7. Applying reviewer pressure before writing.
8. Repairing only through issue-scoped contracts.
9. Unlocking paper writing only after evidence clears the gate.
10. Producing artifacts that a researcher can share with a mentor, co-author, editor, compliance reviewer, investment committee, or policy stakeholder.

Non-negotiable trust principle:

Writer is last and never invents numbers.

## 2. Primary Jobs To Be Done

### 2.1 Serious Researcher

When I have a research idea, I want Thrivarc to challenge, formalize, execute, and defend it so that I know whether I have a real finding before I spend weeks writing.

### 2.2 Quant Researcher Or PM

When I have a strategy or allocation idea, I want Thrivarc to enforce universe, benchmark, timing, costs, robustness, and audit discipline so that I can show an investment committee evidence instead of a backtest story.

### 2.3 Academic Researcher Or PhD Student

When I have an empirical finance question, I want Thrivarc to behave like a research architect, RA team, skeptical reviewer, and paper assistant so that I learn faster and avoid preventable reviewer rejection.

### 2.4 Policy Or Institutional Research User

When I need evidence for a policy, risk, or strategy decision, I want Thrivarc to turn an ambiguous question into an auditable evidence package without requiring me to manage the whole empirical pipeline.

## 3. Screen-By-Screen User Journey

This section is the canonical product journey. The API contracts support it, but the journey defines what the human experiences.

### Screen 0: Landing Page

What the researcher sees:

- A premium research operating-system promise, not an AI writing promise.
- The line: "Question to evidence to defense, before writing."
- A short diagram: Intent -> Blueprint -> Evidence Preview -> Agent Run -> Defense Gate -> Paper Package.
- Proof points: DataPassport, Reviewer Gate, Paper-Code Verification, Writer Last.
- CTA: "Start a Research Run."

What the researcher thinks:

- This is not a topic generator.
- This will not write fake results.
- This may save me weeks if it is honest.

What the researcher does:

- Starts a new research run.
- Optionally opens examples of prior artifact packages.

System behavior:

- No health banner is visible on first load.
- API status is visible as a small dot, not a disruptive warning.
- The product routes to the universal research intake.

Failure state:

- If API is offline after three failed checks, show a compact banner: "Research engine unavailable. Your draft is safe. Retry in a moment."

### Screen 1: Research Intent Intake

What the researcher sees:

- One large question field.
- A supporting context field.
- A data-access field with plain-language options: "Use public data if possible", "I will upload data", "I need to stage a source extract", "I am not sure yet."
- No method dropdown.
- No fixed rebalance-frequency dropdown.
- Prompt text: "Tell Thrivarc the market, period, strategy, risk lens, data preference, or anything you already know. If the design needs cadence, universe, benchmark, or timing, Thrivarc will ask."

What the researcher does:

- Writes the research question.
- Adds context and data notes if known.
- Clicks "Build Blueprint."

System behavior:

- Research Architect reads all text as the source of truth.
- The system infers research track, sub-domain, method family, evidence route, initial data needs, and reviewer attack surface.
- The system never starts compute from this screen.

Decision points:

- If the brief is specific enough, move to Blueprint screen.
- If a blocker exists, show the clarification workspace.

Failure state:

- If the brief is too vague, ask one high-value question instead of generating fake research directions.

### Screen 2: Live Architect Read

What the researcher sees:

- "Thrivarc reads this as..." with research track, domain, likely method family, evidence route, and first reviewer concern.
- A short explanation for each inference.
- The message: "This is not locked yet. You can correct the architect."

What the researcher does:

- Accepts the architect read.
- Edits the question/context.
- Answers clarifying questions.

System behavior:

- Every field is classified as infer, confirm, or block.
- Blocking fields prevent evidence preview.
- Confirmation fields appear on the Blueprint but do not stop progress unless the researcher edits them into blockers.

### Screen 3: Clarification Workspace

What the researcher sees:

- One card per blocking issue.
- Each card states the question, why it matters, and what downstream phase depends on it.
- Example: "What exact universe, benchmark, or investable assets anchor this backtest? Backtests are not defensible until the investable universe and comparison set are explicit."

What the researcher does:

- Answers in plain English.
- Can include uncertainty: "Compare monthly and quarterly cadence if the data supports both."

System behavior:

- The answer is folded into the working brief.
- Research Architect rebuilds the Blueprint.
- The completion contract is recomputed after clarifications.

Failure state:

- If the answer remains ambiguous, the same issue stays blocked with a sharper reason.

### Screen 4: Blueprint Review

What the researcher sees:

- Research stance: exploratory or confirmatory.
- Evidence source and fallback plan.
- Method style.
- Cadence logic.
- Decision problem.
- Comparison set.
- Burden of proof.
- Reviewer attack surface.
- Agent stack.
- Research package.
- Conditional paper gate.
- Repair Contract.
- Integrity artifacts.
- Execution truth contract.

What the researcher does:

- Reviews the Blueprint.
- Answers remaining architect questions.
- Approves the Blueprint to open evidence preview.

System behavior:

- Approval does not start the run.
- Approval opens the evidence gate only.
- If confirmatory, Blueprint and PAP lock behavior becomes visible.
- If exploratory, the UI states that outputs are hypothesis-generating.

Failure state:

- If a blocker remains, the approval button is disabled and the UI states exactly which field blocks launch.

### Screen 5: Evidence Preview

What the researcher sees:

- Data route: upload, yfinance, EDGAR, FRED, staged extract, or manual connector request.
- Upload control when needed.
- Identifier, coverage, cadence, and schema fields.
- Data preview table.
- Schema profile.
- Missingness.
- SHA-256.
- DataPassport preview.
- Blocking issues and warnings.

What the researcher does:

- Uploads a file or confirms public data route.
- Edits symbols, date range, frequency, or evidence notes.
- Reviews sample rows and schema profile.
- Clicks "Confirm data and start research."

System behavior:

- Compute remains blocked until preview status is ready.
- Preview status is blocked if required data is missing, file is empty, schema cannot support the Blueprint, or missingness exceeds hard threshold.
- DataPassport preview is created before run launch.

Failure state:

- If data cannot be fetched, the researcher sees fallback options: upload data, revise source, narrow universe, or save Blueprint without launch.

### Screen 6: Run Launch

What the researcher sees:

- A final launch summary: Blueprint hash, DataPassport hash, expected agent path, estimated time, estimated credits, and paper gate rule.
- For confirmatory runs: pre-registration certificate preview.
- For exploratory runs: hypothesis-generating warning.

What the researcher does:

- Launches the run.

System behavior:

- RunSpec is persisted.
- Truth contract is written to `research_memory`.
- Deviation Register is initialized.
- Agent execution begins.

Failure state:

- If credit balance is insufficient, run does not launch. The Blueprint remains saved.

### Screen 7: Running Research

What the researcher sees:

- Phase timeline.
- Current agent.
- Current stage output summary.
- Live log lines, translated into researcher language by default.
- Technical logs in Expert mode.
- Estimated remaining time.
- Any agent-local repair attempts.

What the researcher does:

- Watches progress.
- Leaves and returns later.
- Opens the run detail from session history.

System behavior:

- Literature and Data phases can run in parallel where dependencies allow.
- Code Audit and Spec Audit can run in parallel after statistics outputs exist.
- Reviewer waits for audit and statistics artifacts.
- Writer waits for reviewer gate, audits, and Paper-Code Verifier.

Failure state:

- If an agent fails, the run enters a resumable failed state with owner, reason, affected artifacts, and available actions.

### Screen 8: Reviewer Gate Result

What the researcher sees:

- Seven-dimension scorecard.
- Overall score.
- Minimum-dimension floor status.
- Paper gate state: unlocked, conditional, repair required, or failed.
- Plain-English reviewer narrative.
- Specific repair suggestions, each with owner and scope.

What the researcher does:

- Accepts failure package.
- Approves researcher-gated repair.
- Lets safe automatic repairs continue.
- Forks into a new research run if the design needs major change.

System behavior:

- Reviewer score below threshold blocks Writer.
- Repair Contract controls every rerun.
- Blueprint changes require Deviation Register entries.
- After repair, affected downstream agents rerun and Reviewer reassesses.

Failure state:

- If three repair cycles are exhausted, the run produces a failure package instead of pretending success.

### Screen 9: Deviation Register

What the researcher sees:

- A timeline of post-lock changes.
- Each entry shows timestamp, trigger, changed field, old value, new value, reason, approver, affected artifacts, and whether it changes interpretation.
- Researcher annotation field.
- Co-author visibility status.

What the researcher does:

- Reviews deviations.
- Adds context.
- Approves or rejects proposed blueprint-changing repairs.
- Exports register as appendix.

System behavior:

- No post-lock Blueprint mutation can happen without a register entry.
- Confirmatory claims are downgraded or blocked when deviation invalidates PAP integrity.

### Screen 10: Paper-Code Verification

What the researcher sees:

- Claim-to-table checks.
- Table-to-code checks.
- Code-to-DataPassport checks.
- Mismatch status.

What the researcher does:

- Reviews mismatches if any.
- Approves repair if claim text or Blueprint needs to change.

System behavior:

- Writer remains blocked until verifier passes.
- Verifier reruns after repair cycles that change numbers.

### Screen 11: Paper Workspace

What the researcher sees:

- Paper sections generated only from verified artifacts.
- Numbers linked to tables.
- Limitations written explicitly.
- Researcher-owned sections clearly separated from system-written evidence sections.
- LaTeX export.

What the researcher does:

- Edits framing, introduction, related work, and conclusion.
- Cannot edit verified numeric claims without triggering verifier.

System behavior:

- Writer never invents numbers.
- Paper export includes DataPassport, Deviation Register, reviewer scorecard, audit summaries, and pre-registration certificate when applicable.

### Screen 12: Final Download Package

What the researcher sees:

- "Submission package ready."
- Download options:
  - paper PDF
  - LaTeX source
  - tables
  - charts
  - DataPassport
  - Deviation Register
  - pre-registration certificate
  - reviewer report
  - code audit report
  - spec audit report
  - RunSpec
  - research memory zip

What the researcher does:

- Downloads package.
- Shares with mentor/co-author/editor/committee.
- Forks into a new run.

System behavior:

- Package is immutable unless the researcher creates a new version.

### Screen 13: Session History

What the researcher sees:

- All research runs.
- Status: draft, needs clarification, evidence blocked, running, repair required, paper unlocked, failed package, complete.
- Cost/credits consumed.
- Last completed phase.
- Next action.
- Parent/fork lineage.

What the researcher does:

- Resumes a run.
- Forks a prior run.
- Compares two runs.
- Downloads artifacts.

System behavior:

- Long-running work is resumable from last durable phase.
- Failed runs preserve artifacts and reasons.

### Screen 14: Co-Author Workspace

What the researcher sees:

- Invite co-author.
- Permission role.
- Activity and approval history.
- Lock/repair approval status.

What the researcher does:

- Invites collaborator.
- Assigns role.
- Requests approval on Blueprint lock, data preview, repair cycle, or final export.

System behavior:

- Concurrent edits are controlled through versioned draft state.
- Locked state cannot be overwritten by another user without conflict resolution.

## 4. Buyer Segments And Willingness To Pay

### 4.1 Principal Investigator / World-Class Finance Economist

Workflow pain:

- Senior researchers have too many ideas and not enough trustworthy empirical scaffolding.
- They do not need generic AI prose.
- They need fast falsification, rigorous design, and pre-submission critique.

Thrivarc output that resolves it:

- Blueprint.
- Literature gap map.
- Reviewer scorecard.
- DataPassport.
- Deviation Register.
- Paper-Code verification.
- Evidence-backed paper sections.

Current alternative:

- Graduate RAs, manual notebooks, ad hoc scripts, ChatGPT drafts, and late-stage reviewer feedback.

Why alternative is worse:

- Slow, uneven quality, hard to audit, and often discovers weakness too late.

Dollar value:

- Saves 10-40 RA hours per serious idea.
- Avoids months spent on weak empirical claims.
- Improves submission readiness.

Willingness to pay:

- High per-run for complete confirmatory package.
- Institutional subscription later.

Primary must-buy hook:

- "Know if the finding can survive before you write the paper."

### 4.2 Academic Finance Researcher / Lab / PhD Student

Workflow pain:

- Moving from idea to credible empirical design is fragmented.
- Students overclaim exploratory work.
- Researchers lose time on data cleaning, method selection, and reviewer-style critique.

Thrivarc output that resolves it:

- Research Architect clarifications.
- Data preview and schema diagnosis.
- Method-specific statistical battery.
- Reviewer gate.
- Learning-visible but not dumbed-down flow.

Current alternative:

- Advisor meetings, RA scripts, course notes, manual Zotero search, notebooks, generic AI assistants.

Why alternative is worse:

- Guidance is not executable.
- Scripts are not integrated with the final paper.
- AI assistants hallucinate or overproduce text.

Dollar value:

- Saves days per iteration for students.
- Reduces preventable design mistakes.
- Helps labs triage more ideas.

Willingness to pay:

- Low-to-medium per exploratory run.
- Higher for confirmatory package and paper export.
- Department/lab credits later.

Primary must-buy hook:

- "Turn a research idea into a defensible empirical package without losing the integrity trail."

### 4.3 Quant Researcher / Portfolio Manager

Workflow pain:

- Backtests are easy to fake and hard to defend.
- Investment committees care about costs, drawdowns, regime dependence, benchmark fairness, capacity, and auditability.
- Strategy research needs repeatable evidence packages.

Thrivarc output that resolves it:

- Universe and benchmark lock.
- DataPassport.
- Backtest statistical battery.
- Deflated Sharpe and transaction-cost burden.
- Code Audit.
- Spec Audit.
- Reviewer attack surface.
- Investment-committee-ready artifact package.

Current alternative:

- Internal notebooks, research platform fragments, Excel, Python scripts, portfolio analytics tools.

Why alternative is worse:

- Often strong on compute but weak on research narrative, audit trail, and reviewer-grade critique.

Dollar value:

- Saves quant/researcher days per strategy.
- Prevents false positives entering PM review.
- Creates reusable evidence package for internal governance.

Willingness to pay:

- Highest per-run segment for premium backtest/strategy defense packages.
- Likely enterprise buyer when permissions, storage, and compliance are mature.

Primary must-buy hook:

- "Do not take a backtest to committee until it survives the defense layer."

### 4.4 Policy / Corporate / Institutional Research User

Workflow pain:

- Business and policy questions are empirical but stakeholders do not want to manage research infrastructure.
- Teams need transparent limitations and decision-ready evidence.
- Internal data often has schema and provenance problems.

Thrivarc output that resolves it:

- Plain-English Blueprint.
- Upload schema validation.
- Evidence preview.
- Decision-oriented findings.
- DataPassport.
- Deviation Register.
- Limitation-forward report.

Current alternative:

- Analyst decks, consultant reports, spreadsheets, generic AI summaries.

Why alternative is worse:

- Weak reproducibility.
- Unclear data provenance.
- Claims are often stronger than evidence.

Dollar value:

- Saves analyst cycles.
- Reduces decision risk.
- Produces auditable artifacts for leadership or compliance.

Willingness to pay:

- Medium-to-high per decision package.
- Team credits once collaboration is available.

Primary must-buy hook:

- "Make the evidence defensible before it becomes a decision."

## 5. Monetization Architecture

V1 decision: per-run credits.

Reason:

- Aligns payment with research value.
- Easy to explain.
- Supports free first run.
- Supports higher pricing for confirmatory paper package.
- Can evolve into seats or institutional contracts later.

Credit events:

- Blueprint generation: low cost, may be free or bundled.
- Evidence preview: low credit event when public data or upload parsing is used.
- Exploratory run: base credit package.
- Confirmatory run with PAP and paper gate: premium credit package.
- Heavy compute, long simulations, or external data connectors: surcharge.
- Repair cycles: included up to a limit, then billed as additional credits when researcher approves.
- Paper export: included only when gate clears, or separately priced for institutional package.

Free tier:

- One Blueprint.
- One data preview.
- One small exploratory run with limited export.

Upgrade triggers:

- More rows or longer periods.
- Confirmatory lock.
- Full paper workspace.
- Advanced audit artifacts.
- Co-author access.
- Downloadable submission package.

Database implications:

- `accounts`
- `users`
- `credit_balances`
- `usage_events`
- `run_cost_estimates`
- `credit_transactions`
- `team_memberships`
- `artifact_entitlements`

UI implications:

- Every launch screen shows estimated credits before run.
- Repairs that cost extra require approval.
- Session history shows spend per run.

## 6. Co-Author Permission Model

V1 supports two-person collaboration on one research session.

Roles:

- Owner
- Co-author
- Reviewer-only

Owner can:

- edit draft Blueprint
- lock Blueprint
- approve data preview
- approve repair cycles
- invite/remove co-author
- export final package
- approve post-lock deviations

Co-author can:

- edit draft Blueprint before lock
- answer clarifications
- comment on evidence preview
- request repair
- annotate Deviation Register
- download artifacts if owner permits

Reviewer-only can:

- view Blueprint
- view reviewer report
- view artifacts
- comment
- cannot mutate state

Approval rules:

- Blueprint lock requires owner approval.
- Post-lock Blueprint change requires owner approval.
- If co-author made the change, owner approval still required.
- Data source change after preview requires owner approval.
- Final export can require both owner and co-author approval if enabled.

Concurrency rules:

- Draft Blueprint uses optimistic versioning.
- Every save includes `draft_version`.
- If two users edit same version, second save receives conflict screen.
- Conflict screen shows owner value, co-author value, and merged suggestion.
- Locked Blueprint is immutable except through Deviation Register.

Co-author metadata in artifacts:

- DataPassport lists owner and co-authors who approved data.
- Pre-registration certificate lists approver and timestamp.
- Deviation Register lists proposer and approver.
- Final paper metadata includes co-author names only if owner confirms.

## 7. Session History And Resumption

Session states:

- draft_intake
- needs_clarification
- blueprint_ready
- evidence_blocked
- evidence_ready
- queued
- running
- repair_required
- failed_resumable
- failed_terminal
- paper_unlocked
- complete

Session history screen shows:

- title
- research track
- sub-domain
- last phase
- next action
- created date
- last activity
- credits spent
- artifacts available
- co-author status
- parent run if forked

Resumption rules:

- Drafts resume at intake.
- Blueprints resume at last unresolved clarification or approval screen.
- Evidence-blocked sessions resume at data preview.
- Running sessions resume at run page with current phase.
- Failed-resumable sessions resume at failure card with retry/fork options.
- Failed-terminal sessions can be downloaded or forked, not resumed in place.
- Paper-unlocked sessions resume at paper workspace.

Forking:

- Fork creates a new run with parent_run_id.
- Fork can change question, data, method, or research track.
- Fork does not mutate parent artifacts.

Comparison:

- Compare two runs by Blueprint, data source, method, reviewer score, and key outputs.

## 8. Failure State Catalogue

Each failure card must show:

- what failed
- why it matters
- current system state
- affected artifacts
- available actions
- whether credits were consumed
- whether the run can resume

### 8.1 Research Architect Failure

Failure modes:

- question too vague
- research track ambiguous
- method family cannot be inferred
- evidence route impossible

Researcher sees:

- one blocking question at a time
- reason linked to downstream risk

System state:

- needs_clarification

Options:

- answer clarification
- revise question
- save draft

### 8.2 Literature Agent Failure

Failure modes:

- zero relevant papers
- too few high-quality papers
- source unavailable
- topic appears already answered

Researcher sees:

- relevance summary
- what was searched
- what failed
- recommended search expansion or narrowing

System state:

- failed_resumable unless literature is not required for exploratory data mapping

Options:

- broaden query
- narrow domain
- continue with literature gap warning
- stop run

### 8.3 Data Agent Failure

Failure modes:

- yfinance unavailable
- EDGAR unavailable
- uploaded file empty
- schema missing required fields
- date range mismatch
- frequency mismatch
- missingness above threshold

Researcher sees:

- data issue card
- schema profile
- missing fields
- fallback options

System state:

- evidence_blocked

Options:

- upload data
- revise source route
- change universe
- change date range
- save Blueprint without launch

### 8.4 Feature / Mining Agent Failure

Failure modes:

- leakage detected
- feature cannot be constructed
- text extraction fails
- graph construction invalid

Researcher sees:

- feature issue
- leakage explanation
- affected variables

System state:

- repair_required or failed_resumable

Options:

- approve safe repair
- revise feature definition
- route back to Blueprint

### 8.5 Preregistration Agent Failure

Failure modes:

- hypothesis not testable
- primary test missing
- outcome variable missing
- alpha/significance threshold missing

Researcher sees:

- PAP readiness checklist
- missing locked fields

System state:

- needs_clarification

Options:

- answer PAP fields
- downgrade to exploratory
- save draft

### 8.6 Method / Compute Agent Failure

Failure modes:

- adapter unavailable
- compute timeout
- method incompatible with data
- parameter set invalid

Researcher sees:

- failed method
- runtime
- input artifact
- retry/fork options

System state:

- failed_resumable if method can rerun
- failed_terminal if design is invalid

Options:

- rerun
- choose simpler method if Blueprint allows
- approve Blueprint revision
- stop and download partial package

### 8.7 Statistics Agent Failure

Failure modes:

- test assumptions fail
- all p-values null
- insufficient sample size
- multiple-testing burden overwhelms finding

Researcher sees:

- result strength card
- null result is not hidden
- statistical reason

System state:

- repair_required if robustness can be run
- paper_locked if evidence is weak

Options:

- accept null-result package
- approve robustness repair
- fork new design

### 8.8 Code Audit Failure

Failure modes:

- code did not execute
- output schema mismatch
- unapproved library
- edge case failure

Researcher sees:

- technical audit failure
- affected file
- whether automatic repair is safe

System state:

- repair_required

Options:

- allow automatic repair
- inspect technical log
- stop run

### 8.9 Spec Audit Failure

Failure modes:

- output does not match Blueprint
- reported test not in RunSpec
- benchmark changed without approval
- exploratory result written as confirmatory

Researcher sees:

- integrity mismatch
- locked plan vs actual output

System state:

- repair_required

Options:

- rerun affected phase
- approve deviation
- downgrade claim
- stop run

### 8.10 Reviewer Agent Failure

Failure modes:

- average score below 7
- any dimension below 6
- overclaiming risk too high
- repair cycles exhausted

Researcher sees:

- scorecard
- weakest dimensions
- repair contracts
- paper gate state

System state:

- repair_required or failed_terminal

Options:

- approve repair
- accept failure package
- fork new run

### 8.11 Paper-Code Verifier Failure

Failure modes:

- paper number not found in table
- table number not traceable to code output
- code output hash not traceable to DataPassport

Researcher sees:

- mismatch table
- claim text
- source artifact

System state:

- writer_blocked

Options:

- correct claim text
- rerun verifier
- create deviation if Blueprint changes

### 8.12 Credit Failure

Failure modes:

- insufficient credits before launch
- repair cycle exceeds included quota
- external compute surcharge required

Researcher sees:

- credit estimate
- consumed credits
- additional credits required

System state:

- blocked_before_costly_action

Options:

- add credits
- reduce scope
- save without launch

## 9. Pre-Registration Certificate Document

Purpose:

- Prove what was locked before evidence execution.
- Make confirmatory claims credible to mentors, co-authors, editors, and reviewers.

Format:

- HTML and PDF for humans.
- JSON for machine verification.

Plain-English opening:

"This certificate records the research claim, primary test, data preview fingerprint, and analysis plan that were locked before confirmatory evidence execution. Any post-lock changes are recorded separately in the Deviation Register."

Required fields:

- certificate id
- run id
- project title
- owner
- co-authors and approvers
- timestamp UTC
- research question verbatim
- primary hypothesis verbatim
- outcome variable
- treatment/signal/event variable
- primary test
- significance threshold
- sample period
- data source route
- DataPassport hash
- Blueprint hash
- RunSpec hash
- allowed robustness checks
- prohibited post-hoc changes
- verification instruction

Verification instruction:

"To verify this certificate, hash the submitted Blueprint JSON and DataPassport JSON using SHA-256 and compare the values to the hashes listed here. Any mismatch means the submitted artifacts differ from the locked plan."

OSF/AEA compatibility:

- Export includes plain research question, hypotheses, design plan, data source, outcome, statistical tests, and analysis plan.
- V1 is compatible as an attachment packet, not a direct registry API integration.
- Future version can push to OSF or AEA registry API if credentials and registry schema mapping are available.

Visual structure:

1. Certificate summary.
2. Locked claim.
3. Locked data preview.
4. Locked analysis plan.
5. Hash verification.
6. Deviation Register pointer.
7. Co-author approvals.

## 10. DataPassport Document

Purpose:

- Certify what data was previewed, accepted, and used.
- Make data provenance understandable to non-technical readers.

Format:

- HTML and PDF for humans.
- JSON for machine verification.

Plain-English opening:

"This DataPassport records the evidence used in this research run. It explains where the data came from, what period and fields it covered, how much data was available, what quality issues were found, and the fingerprint that ties the analysis back to this exact preview."

Required sections:

1. Summary for non-technical reader.
2. Source route and provider.
3. Upload or connector details.
4. Sample period and coverage.
5. Row and column counts.
6. Identifier fields.
7. Date/time fields.
8. Numeric measurement fields.
9. Missingness profile.
10. Schema warnings and blocking issues.
11. Transformations approved before compute.
12. SHA-256 evidence fingerprint.
13. Verification instruction.
14. Limitations.

Risk-manager/editor language:

- "This document does not certify that the research conclusion is correct."
- "It certifies that the reported analysis was tied to the data preview described here."
- "Any later data replacement must appear in the Deviation Register."

Visual structure:

- top status badge: accepted, warning, or blocked
- summary card
- coverage chart
- schema table
- quality issues table
- hash verification block
- appendix JSON

## 11. Deviation Register UI

Purpose:

- Make post-lock changes visible, reviewable, and exportable.

Location:

- Blueprint screen after lock.
- Run page when any deviation exists.
- Paper workspace before final export.
- Final artifact package.

Entry fields:

- deviation id
- timestamp UTC
- proposer
- approver
- trigger source
- affected Blueprint field
- old value
- new value
- reason
- affected agents
- affected artifacts
- claim impact
- approval state
- researcher annotation

UI states:

- empty: "No post-lock deviations."
- pending approval: owner action required
- approved: included in final package
- rejected: proposed change not applied
- material: claim language or confirmatory status affected

Researcher actions:

- approve
- reject
- annotate
- export
- fork run instead of mutating locked plan

Paper treatment:

- If any approved deviation exists, final paper includes an appendix note.
- If deviation materially changes a confirmatory claim, the paper must either downgrade claim language or show the deviation explicitly.

## 12. Finance Sub-Domains And Agent Behavior

Supported V1 sub-domains:

1. Asset pricing and factor research.
2. Portfolio strategy and backtesting.
3. Event studies and corporate finance.
4. Text/NLP finance.
5. Macro-finance and time-series econometrics.
6. Network/systemic risk mapping.

### 12.1 Asset Pricing And Factor Research

Literature Agent:

- prioritize Journal of Finance, Review of Financial Studies, Journal of Financial Economics, SSRN/NBER where appropriate
- weight methodological similarity higher than keyword overlap

Data Agent:

- focus on returns, factors, identifiers, survivorship, sample period

Statistics Agent:

- Fama-MacBeth
- factor regression
- Newey-West
- spanning tests
- out-of-sample R2

Reviewer Agent:

- attacks factor redundancy, data snooping, transaction costs, subperiod stability, multiple testing

Economic significance:

- annualized alpha, basis points, t-stat reliability, turnover-adjusted returns

### 12.2 Portfolio Strategy And Backtesting

Literature Agent:

- search strategy class, allocation literature, transaction-cost and capacity evidence

Data Agent:

- enforce investable universe, benchmark, rebalance calendar, delisting/survivorship warnings

Statistics Agent:

- net return
- Sharpe
- drawdown
- turnover
- deflated Sharpe
- bootstrap

Reviewer Agent:

- attacks look-ahead bias, benchmark choice, capacity, costs, overfit, regime fragility

Economic significance:

- net-of-cost performance, drawdown, hit rate, capacity, implementation burden

### 12.3 Event Studies And Corporate Finance

Literature Agent:

- search event definition, identification strategy, confound controls, nearest corporate finance literature

Data Agent:

- enforce event timestamp, estimation window, event window, firm identifiers, trading calendar

Statistics Agent:

- CAR
- BHAR
- market model
- cross-sectional CAR regression
- bootstrap inference

Reviewer Agent:

- attacks confounds, clustering, event contamination, selection bias, endogeneity

Economic significance:

- abnormal return magnitude relative to bid-ask spread and event-window volatility

### 12.4 Text/NLP Finance

Literature Agent:

- search finance text methods, dictionary baselines, LLM/embedding validity, SEC/earnings-call literature

Data Agent:

- enforce document timestamp, release timing, entity mapping, text coverage

Feature Agent:

- document embedding or sentiment extraction
- leakage check on document availability

Statistics Agent:

- predictive regression
- out-of-sample tests
- placebo text windows
- multiple-testing correction

Reviewer Agent:

- attacks text validity, prompt drift, look-ahead text timing, benchmark against simpler dictionary methods

Economic significance:

- return predictability in basis points and incremental value beyond existing controls

### 12.5 Macro-Finance And Time-Series

Literature Agent:

- search macro-finance journals, NBER, FRED series documentation, structural-break literature

Data Agent:

- enforce release calendars, revisions, real-time data when available

Statistics Agent:

- ADF
- VAR
- Granger causality
- cointegration
- structural break tests
- HAC errors

Reviewer Agent:

- attacks nonstationarity, look-ahead macro revisions, sample sensitivity, identification

Economic significance:

- forecast improvement, policy relevance, magnitude under regimes

### 12.6 Network/Systemic Risk

Literature Agent:

- search systemic risk, holdings networks, contagion, graph econometrics

Data Agent:

- enforce node/edge schema, timestamped holdings, entity mapping

Feature Agent:

- graph construction, centrality, exposure, network snapshots

Statistics Agent:

- network descriptive stats
- predictive regression
- stress simulation if Blueprint permits

Reviewer Agent:

- attacks network construction validity, target validity, survivorship, interpretability

Economic significance:

- early-warning lead time, risk concentration, systemic exposure magnitude

## 13. Agent Execution Graph

Default critical path:

1. Research Architect.
2. Blueprint approval.
3. Evidence preview.
4. RunSpec launch.
5. Data Agent.
6. Feature Agent if required.
7. Preregistration Agent if confirmatory.
8. Method/Compute Agent if required.
9. Statistics Agent.
10. Code Audit Agent and Spec Audit Agent.
11. Reviewer Agent.
12. Repair loop if required.
13. Paper-Code Verifier.
14. Writer Agent.
15. Final Package Agent.

Parallelism:

- Literature Agent can run in parallel with Data Agent after Blueprint approval if literature output is not needed to define the data query.
- Data quality profiling can run in parallel with literature synthesis.
- Feature Agent waits for Data Agent.
- Preregistration Agent waits for Blueprint and evidence preview but must finish before confirmatory compute.
- Method/Compute waits for DataPassport acceptance and PAP when confirmatory.
- Statistics waits for compute outputs or descriptive evidence outputs.
- Code Audit and Spec Audit run in parallel after statistics outputs exist.
- Reviewer waits for Statistics, Code Audit, and Spec Audit.
- Repair Agent blocks the downstream path until affected upstream and downstream outputs are regenerated.
- Paper-Code Verifier waits for final reviewer/audit pass.
- Writer waits for Paper-Code Verifier.

Minimum run-time product expectations:

- Blueprint only: under 2 minutes.
- Evidence preview: under 1 minute for small upload or small public query.
- Exploratory descriptive run: 5-15 minutes.
- Standard regression/event run: 15-35 minutes.
- Backtest/strategy run: 20-60 minutes depending on universe and robustness.
- Heavy simulation or external compute: explicit estimate before launch.

State machine rule:

- No agent writes to a downstream artifact if its required upstream artifact is missing or failed.

## 14. research_memory Write Contracts

Versioning rule:

- First successful artifact uses `_v1`.
- Repair reruns create `_v2`, `_v3`, etc.
- Latest pointer files may exist, but old versions are never overwritten.
- Every repair version references the Repair Contract id.

Directory layout:

- `00_runspec/`
- `01_integrity/`
- `02_literature/`
- `03_datapull/`
- `04_features/`
- `05_preregistration/`
- `06_compute/`
- `07_statsrun/`
- `08_audits/`
- `09_reviewer/`
- `10_verifier/`
- `11_writer/`
- `12_package/`

### 14.1 Research Architect

Writes:

- `00_runspec/blueprint_v1.json`
- `00_runspec/runspec_v1.json`
- `00_runspec/clarification_policy_v1.json`

Repair/version behavior:

- If Blueprint changes before lock, create new draft version.
- If Blueprint changes after lock, create Deviation Register entry and new locked version only after approval.

### 14.2 Literature Agent

Writes:

- `02_literature/literature_map_v1.md`
- `02_literature/paper_screen_v1.json`
- `02_literature/search_log_v1.json`

Version behavior:

- Rerun writes `_v2` and keeps prior search log.

### 14.3 Data Agent

Writes:

- `03_datapull/data_preview_v1.json`
- `03_datapull/schema_profile_v1.json`
- `03_datapull/source_query_v1.json`
- `01_integrity/data_passport_v1.json`
- `01_integrity/data_passport_v1.html`

Version behavior:

- Data replacement after acceptance requires Deviation Register entry.
- New preview version creates new DataPassport hash.

### 14.4 Feature / Mining Agent

Writes:

- `04_features/feature_plan_v1.json`
- `04_features/features_v1.parquet` or `features_v1.csv`
- `04_features/leakage_report_v1.json`

Version behavior:

- Leakage repair creates new feature version and downstream compute/stat reruns.

### 14.5 Preregistration Agent

Writes:

- `05_preregistration/pap_v1.md`
- `01_integrity/preregistration_certificate_v1.json`
- `01_integrity/preregistration_certificate_v1.html`

Version behavior:

- Confirmatory PAP cannot be silently overwritten.
- Material change requires Deviation Register and may downgrade claim.

### 14.6 Method / Compute Agent

Writes:

- `06_compute/compute_config_v1.json`
- `06_compute/results_v1.json`
- `06_compute/charts_v1/`
- `06_compute/execution_log_v1.txt`

Version behavior:

- Rerun creates `results_v2.json` and updates latest pointer.

### 14.7 Statistics Agent

Writes:

- `07_statsrun/statistical_tests_v1.json`
- `07_statsrun/tables_v1/`
- `07_statsrun/economic_significance_v1.json`
- `07_statsrun/robustness_v1.json`

Version behavior:

- Repair reruns never overwrite previous statistical tables.

### 14.8 Code Audit Agent

Writes:

- `08_audits/code_audit_v1.json`
- `08_audits/code_audit_v1.md`

Version behavior:

- Code repair creates `code_audit_v2`.

### 14.9 Spec Audit Agent

Writes:

- `08_audits/spec_audit_v1.json`
- `08_audits/spec_audit_v1.md`

Version behavior:

- Spec mismatch repair creates new audit version and links affected Blueprint/output versions.

### 14.10 Reviewer Agent

Writes:

- `09_reviewer/reviewer_scorecard_v1.json`
- `09_reviewer/reviewer_report_v1.md`
- `09_reviewer/repair_recommendations_v1.json`

Version behavior:

- Each repair cycle creates new reviewer scorecard.

### 14.11 Repair Agent

Writes:

- `01_integrity/repair_contract_{id}.json`
- `01_integrity/deviation_register.json` when needed
- `09_reviewer/repair_cycle_{n}_summary.md`

Version behavior:

- Each repair has a stable id and references affected artifact versions.

### 14.12 Paper-Code Verifier

Writes:

- `10_verifier/paper_code_verification_v1.json`
- `10_verifier/claim_trace_v1.json`

Version behavior:

- Reruns after any evidence or numeric change.

### 14.13 Writer Agent

Writes:

- `11_writer/paper_draft_v1.tex`
- `11_writer/paper_draft_v1.md`
- `11_writer/claim_sources_v1.json`

Version behavior:

- Text revisions create new draft version.
- Numeric claim edits require verifier rerun.

### 14.14 Final Package

Writes:

- `12_package/submission_package_v1.zip`
- `12_package/manifest_v1.json`

Zip organization:

- `/paper`
- `/tables`
- `/charts`
- `/data_passport`
- `/deviation_register`
- `/preregistration`
- `/audits`
- `/reviewer`
- `/runspec`
- `/logs`
- `/code_trace`

## 15. Release Definition For V1

V1 is ready when:

1. A researcher can start from natural language, not a method dropdown.
2. The Blueprint explains the research design before evidence execution.
3. Blocking clarifications prevent unsafe evidence preview.
4. Upload and public-data preview produce DataPassport preview.
5. Confirmatory and exploratory outputs are visibly different.
6. RunSpec is persisted before launch.
7. research_memory artifact skeleton is created at launch.
8. Agent run state is resumable from session history.
9. Reviewer gate blocks Writer below threshold.
10. Repair cycles are bounded and visible.
11. DataPassport, Deviation Register, reviewer report, audit reports, and paper package are downloadable.
12. Every visible UI promise has a backend writer, reader, and test.

## 16. Product Risks And Decisions

Decision:

- Per-run credits for v1.

Decision:

- WRDS is not default until access is stable.

Decision:

- Exploratory runs cannot generate confirmatory paper language.

Decision:

- Co-author v1 supports two-person collaboration with owner-controlled locks.

Risk:

- Overbuilding technical artifacts without making them understandable.

Mitigation:

- DataPassport, Deviation Register, and pre-registration certificate must be designed as human documents, not raw JSON.

Risk:

- Long-running runs feel like a black box.

Mitigation:

- Session history, phase timeline, translated logs, and resumable states.

Risk:

- Reviewer gate feels punitive.

Mitigation:

- Scorecard explains what failed, why it matters, and what repair can realistically improve.

## 17. North Star

Thrivarc should become the default integrity layer for empirical finance research.

The product wins when a serious researcher says:

"I trust this because it made the evidence, weaknesses, deviations, and claims visible before it wrote anything."
