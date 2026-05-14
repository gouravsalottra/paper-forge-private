# Thrivarc Mentor Alignment - Implemented Contract

This file records the implementation pass made after mentor feedback. It is not the final PRD. It is the working truth ledger that ties product promises to backend/API/UI behavior so future PRD work starts from the same plane.

## Product Direction

Thrivarc is an evidence-first research engine for empirical finance and economics.

The user does not choose from narrow persona or method dropdowns. The user gives a research intent in natural language. Thrivarc turns it into a Blueprint, asks only blocking or high-value clarifications, previews the exact evidence, launches a RunSpec-backed agent pipeline, defends the result through reviewer/audit gates, and only then unlocks writing.

The strongest product promise remains:

Writer is last and never invents numbers.

## Implemented Now

### 1. User Journey Is Now Represented In Product Contracts

The guide API now returns the complete research path needed by the UI:

- research package: exploratory vs confirmatory
- clarification policy: infer, confirm, or block
- evidence route and fallback logic
- reviewer gate
- repair contract template
- integrity artifacts
- audit boundary
- paper-code verifier policy
- data quality policy
- leakage policy
- statistical battery
- economic significance policy

Files:

- `api/guide.py`
- `frontend/app.html`
- `tests/test_api_guide_contract.py`
- `tests/test_frontend_truth_contract.py`

### 2. Conditional Paper Gate Is Now A Backend Contract

The guide response includes a `reviewer_gate` object.

Gate dimensions:

- identification validity
- data integrity
- statistical rigor
- economic significance
- benchmark fairness
- robustness burden
- overclaiming risk

Unlock threshold:

- average score must be at least 7.0
- no dimension can be below 6.0
- max repair cycles per issue: 3

UI status:

- visible on the Blueprint screen as "Conditional paper gate"
- score bands explain what the researcher receives at each level
- Writer remains blocked until reviewer/audit/verifier gates pass

### 3. Repair Agent Is Now Bounded By A Repair Contract

The guide response includes `repair_contract_template`.

Every repair must have:

- trigger
- scope
- pass criterion
- approval requirement
- Deviation Register entry when the Blueprint changes

Automatic repairs are limited to safe operations:

- rerun failed parser
- regenerate chart from existing outputs
- run robustness already named in the Blueprint
- fix output formatting that does not change the claim

Researcher approval is required for:

- Blueprint change
- data source change
- benchmark or universe change
- method-family change
- exploratory-to-confirmatory claim upgrade

### 4. Exploratory vs Confirmatory Is Now A Structural Fork

The guide response includes `research_package`.

Exploratory package:

- EDA findings
- literature gap map
- research opportunity map
- data quality profile
- preliminary evidence table
- reviewer warnings against overclaiming
- no pre-registration certificate
- no confirmatory proof language

Confirmatory package:

- locked Blueprint and PAP
- pre-registration certificate
- DataPassport
- Deviation Register
- Code Audit report
- Spec Audit report
- Reviewer scorecard
- Paper-Code verification
- paper-ready sections only after gate pass

### 5. Clarification Policy Has Teeth

The guide response includes `clarification_policy`.

Each Blueprint field is marked as:

- infer: Thrivarc can safely infer from the brief
- confirm: Thrivarc shows the inferred value and asks for confirmation
- block: evidence preview cannot open until answered

Backtest-specific blockers now include:

- missing universe/benchmark/assets
- missing historical window
- missing cadence logic when cadence affects the design

### 6. Data Preview Now Handles Uploads As First-Class Evidence

`/data/upload` now returns:

- upload path
- filename
- byte size
- SHA-256

`/data/preview` now handles uploaded CSV/XLSX/Parquet evidence and returns:

- rows
- columns
- date range
- SHA-256
- schema profile
- date columns
- identifier columns
- numeric columns
- missingness
- blocking issues
- warnings
- DataPassport preview

The UI blocks launch when preview status is blocked.

Files:

- `api/data.py`
- `frontend/app.html`
- `tests/test_api_data_preview.py`

### 7. Leakage And Data Quality Are Now Explicit

The guide response includes:

- `data_quality_policy`
- `leakage_policy`

Rules by method:

- backtest: no feature can use information released after the rebalance decision timestamp
- event study: feature windows cannot overlap event windows unless locked in Blueprint
- regression: right-hand-side timing must be prior or explicitly contemporaneous
- descriptive: descriptive results cannot be reframed as predictive or causal

### 8. Audit Agent Boundaries Are Now Explicit

The guide response includes `audit_boundary`.

Code Audit Agent:

- technical correctness
- code executed
- approved libraries used
- edge cases handled
- output files match schema
- errors are resumable

Spec Audit Agent:

- research integrity
- outputs match Blueprint
- tests match locked plan
- reported tables exist
- claim stays inside research track

### 9. Paper-Code Verifier Trigger Is Now Defined

The guide response includes `paper_code_verifier`.

It runs:

- after review and audit gates pass
- after every repair cycle that changes evidence or reported numbers
- immediately before Writer export

On mismatch:

- block Writer
- create Repair Contract
- write Deviation Register entry if Blueprint changes

### 10. Run Creation Now Persists A Truth Contract

When `/runs/create` receives a RunSpec, the backend writes a structured research memory skeleton:

- `research_memory/{run_id}/00_runspec/runspec.json`
- `research_memory/{run_id}/00_runspec/blueprint.json`
- `research_memory/{run_id}/01_integrity/truth_contract.json`
- `research_memory/{run_id}/01_integrity/reviewer_gate.json`
- `research_memory/{run_id}/01_integrity/repair_contract_template.json`
- `research_memory/{run_id}/01_integrity/data_passport_preview.json`
- `research_memory/{run_id}/01_integrity/deviation_register.json`

New endpoint:

- `GET /runs/{run_id}/truth_contract`

Files:

- `api/runs.py`
- `tests/test_api_runs_truth_contract.py`

### 11. Finance Method Batteries Are Now Declared

The guide response includes `statistical_battery`.

Backtest:

- net return
- annualized Sharpe
- max drawdown
- turnover cost
- deflated Sharpe
- block bootstrap

Event study:

- CAR
- BHAR
- market-model abnormal return
- cross-sectional CAR regression
- bootstrap inference

Regression:

- Newey-West
- Fama-MacBeth
- factor regression
- out-of-sample R2
- multiple-testing control

Descriptive:

- coverage profile
- summary statistics
- correlation map
- sample stability

### 12. Economic Significance Is Now Declared

The guide response includes `economic_significance`.

Backtest:

- net-of-cost returns
- Sharpe
- max drawdown
- turnover
- capacity caveats

Event study:

- abnormal return magnitude relative to bid-ask spread and event-window noise

Regression:

- annualized alpha or basis-point effect size, not just p-values

Descriptive:

- magnitude and limits without proof language

### 13. WRDS Is No Longer Treated As A Default Dependency

The data fallback policy says WRDS is not default in v1 because access is paused.

Preferred sequence:

- researcher upload
- yfinance
- EDGAR
- FRED
- manual connector request

### 14. Product Truth Is Now Tested

New and updated tests verify:

- launch readiness cannot contradict blocking clarifications
- guide responses include reviewer gate, repair contract, integrity artifacts, audit boundary, verifier policy, data fallback policy
- backtest designs block missing universe/window/cadence
- RunSpecs persist the truth contracts
- upload data preview returns schema profile and DataPassport preview
- frontend exposes the backend truth contracts

Targeted test command:

`python -m pytest tests/test_api_guide_contract.py tests/test_frontend_truth_contract.py tests/test_api_data_preview.py tests/test_api_runs_truth_contract.py -q`

## Final PRD Sections Grounded By This Implementation

The code now carries the mentor's critical product contracts. The final mentor-facing PRD can be written from these implemented sections:

- full screen-by-screen journey prose
- buyer pain and monetization model
- co-author permission model
- session history and resumption UX
- journal/export format for pre-registration certificates
- complete failure-state catalogue wording
- final premium website narrative and visual direction

These are no longer loose philosophical gaps; they now map to concrete API, UI, artifact, and test contracts.
