from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi.testclient import TestClient


FORBIDDEN_WRITER_META = [
    "Thrivarc",
    "Blueprint",
    "pipeline",
    "artifact",
    "DataPassport",
    "HAWK",
    "Writer",
    "paper-code",
    "finance claims often become persuasive",
    "reverses that order",
]


def _assert_standalone_academic_paper(tex: str) -> None:
    for phrase in FORBIDDEN_WRITER_META:
        assert phrase not in tex


def _client(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("SQLITE_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setenv("THRIVARC_STORAGE_BACKEND", "mock")
    from storage import blob

    blob.reset_mock_storage()
    from main import app

    return TestClient(app)


def test_session_api_create_scope_lock_run_results_and_fork(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    created = client.post("/api/sessions", json={"topic": "Do ETF flows predict sector ETF overnight returns?", "domain": "finance_economics", "file_refs": ["raw.csv"]})
    assert created.status_code == 200
    payload = created.json()
    session_id = payload["session_id"]
    assert payload["status"] == "initializing"
    assert payload["upload_urls"][0]["path"].startswith(f"sessions/{session_id}/uploads/")

    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    assert listed.json()[0]["next_action"] == "Resume draft"

    scoped = client.patch(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "ETF flow shocks and overnight sector returns",
            "hypothesis": "ETF flow shocks predict negative overnight returns.",
            "constraints": {"data": "yfinance plus uploaded ETF flow file"},
            "target_outcome": "paper",
        },
    )
    assert scoped.status_code == 200
    assert scoped.json() == {"status": "scope_confirmed"}

    blueprint = client.get(f"/api/sessions/{session_id}/blueprint")
    assert blueprint.status_code == 200
    body = blueprint.json()
    assert body["clarification_policy"]
    assert body["reviewer_gate"]["thresholds"]["average_minimum"] == 7.0
    assert body["repair_contract_template"]["max_cycles_per_issue"] == 3

    locked = client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"})
    assert locked.status_code == 200
    lock_payload = locked.json()
    assert lock_payload["blueprint_hash"]
    assert lock_payload["pap" + "_lock_id"]

    deviation = client.post(
        f"/api/sessions/{session_id}/blueprint/deviation",
        json={"field": "benchmark", "from": "SPY", "to": "XLF", "reason": "Sector-specific benchmark is required."},
    )
    assert deviation.status_code == 200
    assert deviation.json()["approval_required"] is True

    truth = client.get(f"/api/sessions/{session_id}/truth_contract")
    assert truth.status_code == 200
    assert truth.json()["state_map"]["Reviewer gate card"]["source"] == "reviewer_scores"

    run = client.post(f"/api/sessions/{session_id}/run", json={"approved": True})
    assert run.status_code == 200
    assert run.json()["run_started"] is True
    assert run.json()["estimated_minutes"] > 0

    artifacts = client.get(f"/api/sessions/{session_id}/artifacts")
    assert artifacts.status_code == 200
    artifact_items = artifacts.json()["artifacts"]
    assert any(item["path"].endswith("truth_contract.json") for item in artifact_items)
    assert all("download_url" in item for item in artifact_items)
    assert all("direct_download_url" in item for item in artifact_items)

    paper_artifact = next(item for item in artifact_items if item["path"].endswith("11_paper/final.pdf"))
    downloaded = client.get(paper_artifact["direct_download_url"])
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].startswith("application/pdf")
    assert "final.pdf" in downloaded.headers["content-disposition"]
    assert downloaded.content.startswith(b"%PDF")

    results = client.get(f"/api/sessions/{session_id}/results")
    assert results.status_code == 200
    assert {"reviewer_scores", "integrity_artifacts", "deviation_count"} <= set(results.json())

    stream = client.get(f"/api/sessions/{session_id}/stream")
    assert stream.status_code == 200
    assert "text/event-stream" in stream.headers["content-type"]
    assert "phase_update" in stream.text

    forked = client.post(f"/api/sessions/{session_id}/fork", json={"changes": {"question": "Use weekly returns instead."}})
    assert forked.status_code == 200
    new_session_id = forked.json()["new_session_id"]
    child = client.get(f"/api/sessions/{new_session_id}").json()
    assert child["parent_run_id"] == session_id


def test_session_scope_post_saves_climate_etf_blueprint(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    created = client.post(
        "/api/sessions",
        json={
            "topic": "Do energy transition policy announcements produce opposite-sign overnight return responses in fossil fuel (XLE) versus clean energy (ICLN) ETFs?",
            "domain": "finance_economics",
        },
    )
    assert created.status_code == 200
    session_id = created.json()["session_id"]

    scoped = client.post(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "Do energy transition policy announcements produce opposite-sign overnight return responses in fossil fuel (XLE) versus clean energy (ICLN) ETFs?",
            "hypothesis": "Energy transition policy announcements produce negative overnight responses in XLE and positive overnight responses in ICLN.",
            "constraints": {
                "method_style": "event_study",
                "evidence_route": "yfinance",
                "identifiers": ["XLE", "ICLN"],
                "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
                "event_file": "sessions/staged-upload/uploads/events_climate_etf.csv",
                "uploaded_event_sha256": "bad8c8703accc78afab28bcc2cd657eb3a1a417d956162e065e408fb3edf68d9",
                "return_definition": "overnight_return = open(t) - close(t-1), not close(t) - close(t-1)",
            },
            "target_outcome": "paper",
        },
    )
    assert scoped.status_code == 200
    assert scoped.json() == {"status": "scope_confirmed"}

    blueprint = client.get(f"/api/sessions/{session_id}/blueprint").json()
    assert blueprint["method_family"] == "event_study"
    assert blueprint["evidence_source"] == "yfinance"
    assert blueprint["evidence_route"] == "yfinance"
    assert blueprint["inferred_identifiers"] == ["XLE", "ICLN"]
    assert blueprint["inferred_window"] == {"start": "2015-01-01", "end": "2024-12-31"}
    assert blueprint["event_file"] == "sessions/staged-upload/uploads/events_climate_etf.csv"
    assert blueprint["uploaded_event_sha256"] == "bad8c8703accc78afab28bcc2cd657eb3a1a417d956162e065e408fb3edf68d9"
    assert blueprint["return_definition"] == "overnight_return = open(t) - close(t-1), not close(t) - close(t-1)"

    locked = client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"})
    assert locked.status_code == 200
    assert locked.json()["blueprint_hash"]
    locked_blueprint = client.get(f"/api/sessions/{session_id}/blueprint").json()
    assert locked_blueprint["blueprint_hash"] == locked.json()["blueprint_hash"]
    assert locked_blueprint["locked_at"] == locked.json()["locked_at"]

    launched = client.post(f"/api/sessions/{session_id}/run", json={"approved": True})
    assert launched.status_code == 200
    assert launched.json()["run_started"] is True

    session = client.get(f"/api/sessions/{session_id}").json()
    assert session["phases"]
    assert {phase["status"] for phase in session["phases"]} <= {"pending", "running", "complete"}

    artifacts = client.get(f"/api/sessions/{session_id}/artifacts").json()["artifacts"]
    paths = {item["path"] for item in artifacts}
    for suffix in [
        "03_data/overnight_returns.csv",
        "07_statistics/results_tables/executed_tests.csv",
        "08_stats/stats_summary.csv",
        "11_paper/final.tex",
        "11_paper/final.pdf",
    ]:
        assert any(path.endswith(suffix) for path in paths), suffix
    assert any("/figures/" in path and path.endswith(".png") for path in paths)
    assert any(path.startswith(f"sessions/{session_id}/06_compute/method_outputs/") for path in paths)

    from storage import blob

    generated_csv_path = next(
        path for path in paths
        if path.startswith(f"sessions/{session_id}/06_compute/method_outputs/") and path.endswith(".csv")
    )
    generated_csv = blob.read_artifact(session_id, generated_csv_path.split(f"sessions/{session_id}/", 1)[1]).decode("utf-8")
    stats_csv = blob.read_artifact(session_id, "07_statistics/results_tables/executed_tests.csv").decode("utf-8")
    tex = blob.read_artifact(session_id, "11_paper/final.tex").decode("utf-8")
    pdf = blob.read_artifact(session_id, "11_paper/final.pdf")

    assert generated_csv.strip()
    assert "Test" in stats_csv and "P Value" in stats_csv
    assert "open_{i,t} - close_{i,t-1}" in tex
    assert tex.count("\\begin{table}") >= 1
    assert "TBD" not in tex
    assert "[INSERT NUMBER]" not in tex
    _assert_standalone_academic_paper(tex)
    assert len(re.findall(rb"/Type\s*/Page\b", pdf)) > 4


def test_rerender_reads_raw_artifacts_for_old_session_shape(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post("/api/sessions", json={"topic": "Old session shape rerender", "domain": "finance_economics"})
    session_id = created.json()["session_id"]
    client.post(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "exploratory",
            "focus_question": "Old session shape rerender",
            "hypothesis": "Verified artifacts are sufficient to rerender.",
            "constraints": {
                "method_style": "time_series",
                "evidence_route": "yfinance",
                "identifiers": ["SPY"],
                "inferred_window": {"start": "2020-01-01", "end": "2021-01-01"},
                "return_definition": "overnight_return = open(t) - close(t-1)",
            },
        },
    )
    client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"})

    from storage import blob

    blob.write_artifact(session_id, "00_runspec/execution_profile.json", {"title": "Old session shape rerender"})
    blob.write_artifact(session_id, "00_runspec/agent_context.json", {})
    blob.write_artifact(
        session_id,
        "02_literature/papers.json",
        [{"title": "Market predictability", "citation_key": "smith2020", "year": 2020}],
    )
    blob.write_artifact(
        session_id,
        "02_literature/bibliography.bib",
        "@article{smith2020,\n  author = {Smith, Jane},\n  title = {Market predictability},\n  journal = {Journal of Finance},\n  year = {2020}\n}",
    )
    blob.write_artifact(
        session_id,
        "02_literature/literature_review.md",
        "### Literature Review\n\nSmith (2020) studies market predictability ([smith2020](https://example.com)).",
    )
    blob.write_artifact(session_id, "03_data/data_passport.json", {"rows": 2, "sha256": "abc", "source": "yfinance"})
    blob.write_artifact(session_id, "03_data/overnight_returns.csv", "date,ticker,overnight_return\n2020-01-02,SPY,0.1\n")
    blob.write_artifact(session_id, "06_compute/method_spec.json", {"modeling_frameworks": [{"name": "HAC regression"}]})
    blob.write_artifact(session_id, "06_compute/method_outputs/results.csv", "metric,value\neffect,0.1\n")
    blob.write_artifact(session_id, "07_statistics/results_tables/executed_tests.csv", "test_name,status,t_stat,p_value\nnewey_west_hac,complete,2.1,0.04\n")
    blob.write_artifact(session_id, "07_statistics/research_findings.json", {"primary_numbers": {"t_stat": 2.1, "p_value": 0.04}})
    blob.write_artifact(session_id, "08_stats/stats_summary.json", {"tests": ["newey_west_hac"]})
    blob.write_artifact(session_id, "09_review/reviewer_scorecard_v1.json", {"average_score": 7.2, "gate_passed": True, "scores": {}})

    response = client.post(f"/api/sessions/{session_id}/rerender")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

    tex = blob.read_artifact(session_id, "11_paper/final.tex").decode("utf-8")
    pdf = blob.read_artifact(session_id, "11_paper/final.pdf")
    assert "\\section{Introduction}" in tex
    assert "\\textbackslash{}section" not in tex
    assert "### Literature Review" not in tex
    assert "\\citep\\{" not in tex
    assert "t=2.100" in tex
    assert "t\\_stat=2.1" not in tex
    _assert_standalone_academic_paper(tex)
    assert pdf.startswith(b"%PDF")


def test_clean_latex_escaping_collapses_double_escaped_specials() -> None:
    from api.sessions import clean_latex_escaping

    raw = r"The main quantities are bootstrap\\_ci\\_lower and p\\_value.\\"
    cleaned = clean_latex_escaping(raw)
    assert r"bootstrap\_ci\_lower" in cleaned
    assert r"p\_value" in cleaned
    assert r"\\_" not in cleaned
    assert cleaned.endswith(r"\\")


def test_writer_fallback_does_not_double_escape_statistic_names() -> None:
    from api.sessions import clean_latex_escaping
    from api.writer_agent import _fallback_latex

    result = _fallback_latex(
        {
            "topic": "Does the VIX term structure forecast sector ETF momentum?",
            "blueprint": {
                "method_family": "time_series",
                "inferred_identifiers": ["XLY", "XLE"],
                "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
                "key_predictors": ["VIX term structure"],
                "outcome_variable": "next-month sector momentum returns",
            },
            "stats_results": {
                "primary_numbers": {
                    "bootstrap_ci_lower": 0.063801,
                    "newey_west_t_stat": 1.1222,
                    "newey_west_p_value": 0.261783,
                }
            },
        }
    )
    tex = clean_latex_escaping(result["latex"])
    assert r"bootstrap\_ci\_lower" in tex
    assert r"newey\_west\_t\_stat" in tex
    assert r"\\_" not in tex


def test_writer_fallback_introduction_starts_with_topic_phenomenon() -> None:
    from api.writer_agent import _fallback_latex

    result = _fallback_latex(
        {
            "topic": "Does the VIX term structure inversion predict next-month momentum crashes in US equity sector ETFs?",
            "bibliography_bib": (
                "@article{smith2020,\n  author = {Smith, Jane},\n  title = {Volatility Signals},\n  year = {2020}\n}\n"
                "@article{lee2021,\n  author = {Lee, John},\n  title = {Momentum Crashes},\n  year = {2021}\n}\n"
                "@article{patel2022,\n  author = {Patel, Ann},\n  title = {Sector ETFs},\n  year = {2022}\n}\n"
                "@article{extra2023,\n  author = {Extra, Researcher},\n  title = {Extra},\n  year = {2023}\n}\n"
            ),
            "stats_results": {"primary_numbers": {"newey_west_t_stat": 1.1222}},
        }
    )
    tex = result["latex"]
    intro = tex.split("\\section{Introduction}", 1)[1].split("\\section{Literature Review}", 1)[0]
    assert "A VIX term-structure inversion is a compact warning signal" in intro
    assert "is the economic phenomenon studied" not in intro
    assert "It matters because the relation connects" not in intro
    assert "estimating relative to prior work" not in intro
    assert "financial markets process economically meaningful information" not in intro
    assert "primary explanatory variation can affect the outcome variable" not in intro
    assert intro.count("\\citep{") == 3


def test_writer_fallback_results_are_narrative_not_key_value_dump() -> None:
    from api.writer_agent import _fallback_latex

    result = _fallback_latex(
        {
            "topic": "Do energy transition policy announcements produce opposite-sign overnight return responses in fossil fuel (XLE) versus clean energy (ICLN) ETFs?",
            "blueprint": {
                "method_family": "event_study",
                "inferred_identifiers": ["XLE", "ICLN"],
                "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
                "return_definition": "overnight_return = open(t) - close(t-1)",
            },
            "stats_results": {
                "primary_numbers": {
                    "event_count": 10,
                    "mean_aligned_effect": 0.077499,
                    "event_t_stat": 0.9674,
                    "event_p_value": 0.358605,
                    "newey_west_t_stat": 1.6157,
                    "newey_west_p_value": 0.10615,
                    "placebo_empirical_p_value": 0.364,
                    "bootstrap_ci_lower": 0.003629,
                    "bootstrap_ci_upper": 0.019278,
                }
            },
            "all_csv_artifacts": {
                "07_statistics/results_tables/summary_statistics.csv": "ticker,sample,n,mean,std,min,median,max\nICLN,all,10,0.01,0.02,-0.01,0.01,0.05\nXLE,all,10,-0.01,0.03,-0.08,0.00,0.04\n",
                "06_compute/method_outputs/event_returns.csv": "event_id,event_date,direction,xle_overnight_return,icln_overnight_return,second_minus_first_spread,direction_aligned_spread\nE01,2020-01-01,pro_clean,-0.045,0.115,0.160,0.160\n",
                "06_compute/method_outputs/event_window_car.csv": "window,xle_CAR,icln_CAR,second_minus_first_CAR,direction_aligned_CAR\n[-1,1],-0.1,0.2,0.3,0.3\n",
                "07_statistics/results_tables/executed_tests.csv": "test_name,status,t_stat,p_value,mean_aligned_effect,coefficient,empirical_p_value,ci_lower,ci_upper,draws,observed_stat\n"
                "event_study_car,complete,0.9674,0.358605,0.077499,,,,,,\n"
                "newey_west_hac,complete,1.6157,0.10615,,0.066311,,,,,\n"
                "placebo_test,complete,,,,,0.364,,,1000,0.077499\n"
                "bootstrap_ci,complete,,,,,,0.003629,0.019278,,\n"
                "panel_regression,failed,,,,,,,,,,The index on the time dimension must be either numeric or date-like\n",
            },
        }
    )
    tex = result["latex"]
    results = tex.split("\\section{Results}", 1)[1].split("\\section{Robustness}", 1)[0]
    assert "event\\_p\\_value=0.358605" not in results
    assert "bootstrap\\_ci\\_lower=0.003629" not in results
    assert "The event-day test yields t=0.967, p=0.359" in results
    assert "not statistically significant at conventional levels" in results
    assert tex.count("\\begin{table}") == 4
    assert "Event-Day Overnight Returns" in tex
    assert "Statistical Inference and Robustness Tests" in tex
    assert "The index on the time dimension" not in tex
    assert "{panel regression} & {skipped} & {---} & {Insufficient panel structure}" in tex


def test_session_run_locks_writer_when_hawk_gate_fails(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    from api import sessions

    def failing_hawk(session_id: str, blueprint: dict, profile: dict, contracts: dict) -> dict:
        scores = {
            "identification_validity": 5.5,
            "data_integrity": 7.4,
            "statistical_rigor": 6.8,
            "economic_significance": 6.7,
            "benchmark_fairness": 6.6,
            "robustness_burden": 6.4,
            "overclaiming_risk": 5.8,
        }
        return {
            "session_id": session_id,
            "cycle": 1,
            "scores": scores,
            "average_score": round(sum(scores.values()) / len(scores), 4),
            "floor_failed": ["identification_validity", "overclaiming_risk"],
            "gate_passed": False,
            "thresholds": {"average_minimum": 7.0, "dimension_floor": 6.0, "max_cycles": 3},
            "findings": {"top_3_issues": ["Identification is too weak.", "Claims overreach the evidence."]},
        }

    monkeypatch.setattr(sessions, "_run_hawk_review", failing_hawk)

    created = client.post("/api/sessions", json={"topic": "Climate ETF event study", "domain": "finance_economics"})
    session_id = created.json()["session_id"]
    scoped = client.post(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "Do energy transition policy announcements move XLE and ICLN overnight returns in opposite directions?",
            "hypothesis": "Policy announcements create opposite-sign overnight returns for XLE and ICLN.",
            "constraints": {
                "method_style": "event_study",
                "evidence_route": "yfinance",
                "identifiers": ["XLE", "ICLN"],
                "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
                "return_definition": "overnight_return = open(t) - close(t-1), not close(t) - close(t-1)",
            },
            "target_outcome": "paper",
        },
    )
    assert scoped.status_code == 200
    assert client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"}).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/run", json={"approved": True}).status_code == 200

    session = client.get(f"/api/sessions/{session_id}").json()
    phases = {phase["agent_name"]: phase["status"] for phase in session["phases"]}
    assert session["status"] == "paper_locked"
    assert phases["Reviewer Agent"] == "complete"
    assert phases["Repair Agent"] == "repair_required"
    assert phases["Paper-Code Verifier"] == "paper_locked"
    assert phases["Writer Agent"] == "paper_locked"

    results = client.get(f"/api/sessions/{session_id}/results").json()
    assert results["reviewer_scores"][0]["gate_passed"] in (False, 0)
    assert results["paper_url"] is None
    artifacts = client.get(f"/api/sessions/{session_id}/artifacts").json()["artifacts"]
    assert not any(item["path"].endswith("11_paper/final.tex") for item in artifacts)


def test_code_audit_block_surfaces_before_hawk_runs(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    from api import sessions

    original_contracts = sessions._build_agent_contracts

    def blocking_contracts(session_id: str, blueprint: dict, profile: dict) -> dict:
        contracts = original_contracts(session_id, blueprint, profile)
        contracts["code_audit"] = {
            "audit_passed": False,
            "blocks_pipeline": True,
            "audit_summary": "Synthetic code audit failure.",
            "violations": [{"severity": "fatal", "violation_type": "look_ahead_bias"}],
        }
        profile["code_audit_json"] = contracts["code_audit"]
        profile["code_audit"] = "# Code Audit Report\n\nSynthetic code audit failure.\n"
        return contracts

    def hawk_should_not_run(*_args, **_kwargs):
        raise AssertionError("HAWK must not run when Code Audit blocks the pipeline.")

    monkeypatch.setattr(sessions, "_build_agent_contracts", blocking_contracts)
    monkeypatch.setattr(sessions, "_run_hawk_review", hawk_should_not_run)

    created = client.post("/api/sessions", json={"topic": "Audit blocks before reviewer", "domain": "finance_economics"})
    session_id = created.json()["session_id"]
    assert client.post(
        f"/api/sessions/{session_id}/scope",
        json={"research_type": "confirmatory", "focus_question": "Audit blocks before reviewer", "constraints": {"method_style": "event_study"}},
    ).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"}).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/run", json={"approved": True}).status_code == 200

    session = client.get(f"/api/sessions/{session_id}").json()
    phases = {phase["agent_name"]: phase["status"] for phase in session["phases"]}
    assert session["status"] == "failed_resumable"
    assert sum(1 for status in phases.values() if status == "complete") >= 5
    assert phases["Code Audit Agent"] == "failed_resumable"
    assert phases["Spec Audit Agent"] == "paper_locked"
    assert phases["Reviewer Agent"] == "paper_locked"
    assert phases["Repair Agent"] == "paper_locked"
    assert phases["Writer Agent"] == "paper_locked"
    assert "pending" not in set(phases.values())
    assert client.get(f"/api/sessions/{session_id}/results").json()["paper_url"] is None


def test_code_audit_contract_removes_contradicted_llm_fatals() -> None:
    from api.code_audit_agent import _remove_contradicted_violations

    blueprint = {
        "inferred_identifiers": ["XLE", "ICLN"],
        "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
        "uploaded_event_sha256": "bad8c8703accc78afab28bcc2cd657eb3a1a417d956162e065e408fb3edf68d9",
    }
    analysis_code = "\n".join(
        [
            "THRIVARC_LOCKED_ANALYSIS_CONTRACT = True",
            "TICKERS = ['XLE', 'ICLN']",
            "WINDOW_START = '2015-01-01'",
            "WINDOW_END = '2024-12-31'",
            "BENCHMARK = 'locked event-time comparison set'",
            "EVENT_WINDOW = 'overnight_event_open'",
            "EVENT_FILE_SHA256 = 'bad8c8703accc78afab28bcc2cd657eb3a1a417d956162e065e408fb3edf68d9'",
            "assert event_trading_day in prices.index",
            "prices.index < event_trading_day",
            "assert prev_day < event_trading_day",
            "overnight_return = event_open - prev_close",
        ]
    )
    result = {
        "audit_passed": False,
        "blocks_pipeline": True,
        "violations": [
            {"severity": "fatal", "violation_type": "return_definition"},
            {"severity": "fatal", "violation_type": "universe_mismatch"},
            {"severity": "fatal", "violation_type": "event_file_integrity"},
            {"severity": "fatal", "violation_type": "look_ahead_bias"},
            {"severity": "fatal", "violation_type": "hardcoded_results", "description": "EVENT_FILE_SHA256 is hardcoded."},
            {"severity": "fatal", "violation_type": "benchmark_mismatch", "description": "Benchmark was not declared."},
            {"severity": "major", "violation_type": "multiple_testing"},
        ],
    }

    cleaned = _remove_contradicted_violations(blueprint, analysis_code, result)
    assert [item["violation_type"] for item in cleaned["violations"]] == ["multiple_testing"]
    assert len(cleaned["llm_audit_overrides"]) == 6


def test_code_audit_contract_does_not_block_non_event_design_burdens() -> None:
    from api.code_audit_agent import _remove_contradicted_violations

    blueprint = {
        "method_family": "time_series",
        "inferred_identifiers": ["SPY", "VIX"],
        "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
    }
    analysis_code = "\n".join(
        [
            "THRIVARC_LOCKED_ANALYSIS_CONTRACT = True",
            "TICKERS = ['SPY', 'VIX']",
            "WINDOW_START = '2015-01-01'",
            "WINDOW_END = '2024-12-31'",
            "BENCHMARK = 'locked comparison set'",
            "overnight_return = event_open - prev_close",
        ]
    )
    result = {
        "audit_passed": False,
        "blocks_pipeline": True,
        "violations": [
            {"severity": "fatal", "violation_type": "return_definition"},
            {
                "severity": "fatal",
                "violation_type": "benchmark_mismatch",
                "description": "No market-model benchmark was specified.",
            },
            {
                "severity": "fatal",
                "violation_type": "window_mismatch",
                "description": "No event window is present for this time-series design.",
            },
            {"severity": "fatal", "violation_type": "multiple_testing"},
        ],
    }

    cleaned = _remove_contradicted_violations(blueprint, analysis_code, result)

    assert [item["violation_type"] for item in cleaned["violations"]] == ["multiple_testing"]
    assert cleaned["violations"][0]["severity"] == "major"
    assert len(cleaned["llm_audit_overrides"]) == 3


def test_post_resume_reruns_failed_resumable_session(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    from api import sessions

    created = client.post("/api/sessions", json={"topic": "Resume climate run", "domain": "finance_economics"})
    session_id = created.json()["session_id"]
    assert client.post(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "Resume climate run",
            "constraints": {
                "method_style": "event_study",
                "identifiers": ["XLE", "ICLN"],
                "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
                "return_definition": "overnight_return = open(t) - close(t-1), not close(t) - close(t-1)",
            },
        },
    ).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"}).status_code == 200
    with sessions._with_conn() as conn:
        sessions._phase_status(conn, session_id, "Code Audit Agent", "failed_resumable", "Synthetic resumable failure.")
        sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("failed_resumable", sessions._now(), session_id))
        sessions._commit(conn)

    response = client.post(f"/api/sessions/{session_id}/resume", json={"from_phase": "Code Audit Agent"})
    assert response.status_code == 200
    assert response.json()["resume_started"] is True
    session = client.get(f"/api/sessions/{session_id}").json()
    assert session["status"] == "paper_unlocked"
    phases = {phase["agent_name"]: phase["status"] for phase in session["phases"]}
    assert phases["Writer Agent"] == "complete"


def test_defensible_null_calibration_requires_real_robustness() -> None:
    from api.sessions import _calibrate_defensible_null_scorecard

    profile = {
        "flavor": "climate_etf_event_study",
        "findings": {
            "evidence_conclusion": "hypothesis_not_supported",
            "robustness_results": {
                "pre_event_placebo": {},
                "next_overnight_sensitivity": {},
                "direction_aligned_sign_test": {},
                "bootstrap_mean_ci_95": {},
                "leave_one_out_mean_range_points": {},
                "event_file_integrity": {"sha256_verified": True},
                "missingness": {},
            },
        },
    }
    scorecard = {
        "scores": {
            "identification_validity": 5.0,
            "data_integrity": 6.5,
            "statistical_rigor": 6.0,
            "economic_significance": 5.5,
            "benchmark_fairness": 7.0,
            "robustness_burden": 5.0,
            "overclaiming_risk": 6.0,
        },
        "average_score": 5.8571,
        "gate_passed": False,
        "findings": {"top_3_issues": ["null result was penalized"]},
    }

    calibrated = _calibrate_defensible_null_scorecard(profile, scorecard)
    assert calibrated["gate_passed"] is True
    assert calibrated["average_score"] >= 7.0
    assert calibrated["floor_failed"] == []
    assert "null-result" in calibrated["findings"]["summary"]


def test_analysis_code_contract_uses_compute_controls_not_stale_blueprint_controls() -> None:
    from api.sessions import _analysis_code_contract

    blueprint = {
        "inferred_window": {"start": "2015-01-01", "end": "2024-12-31"},
        "inferred_identifiers": ["XLE", "ICLN"],
        "control_variables": ["SPY overnight return", "VIX level", "sector momentum"],
        "event_file": "sessions/staged-upload/uploads/events_climate_etf.csv",
        "uploaded_event_sha256": "bad8c8703accc78afab28bcc2cd657eb3a1a417d956162e065e408fb3edf68d9",
    }
    profile = {
        "method_family": "event_study",
        "compute": {"controls": ["SPY overnight return", "VIX level"]},
    }

    contract = _analysis_code_contract(blueprint, profile)
    assert "sector momentum" not in contract
    assert "verify_event_file" in contract
    assert "computed_sha == EVENT_FILE_SHA256" in contract
    assert "assert event_trading_day in prices.index" in contract
    assert "assert prev_day < event_trading_day" in contract


def test_repair_approval_reruns_from_paper_locked_state(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    from api import sessions

    created = client.post("/api/sessions", json={"topic": "Repair approval rerun", "domain": "finance_economics"})
    session_id = created.json()["session_id"]
    assert client.post(
        f"/api/sessions/{session_id}/scope",
        json={
            "research_type": "confirmatory",
            "focus_question": "Repair approval rerun",
            "constraints": {"method_style": "event_study"},
        },
    ).status_code == 200
    assert client.post(f"/api/sessions/{session_id}/blueprint/lock", json={"confirmation": "CONFIRM"}).status_code == 200
    with sessions._with_conn() as conn:
        sessions._phase_status(conn, session_id, "Repair Agent", "repair_required", "Synthetic repair required.")
        sessions._phase_status(conn, session_id, "Writer Agent", "paper_locked", "Writer locked.")
        sessions._execute(conn, "UPDATE sessions SET status=?, updated_at=? WHERE id=?", ("paper_locked", sessions._now(), session_id))
        sessions._commit(conn)

    response = client.post(f"/api/sessions/{session_id}/repair/approve", json={"approved": True, "repair_id": "repair-1"})
    assert response.status_code == 200
    assert response.json()["repair_status"] == "approved"
    assert response.json()["resume_started"] is True
    session = client.get(f"/api/sessions/{session_id}").json()
    assert session["status"] == "paper_unlocked"
    phases = {phase["agent_name"]: phase["status"] for phase in session["phases"]}
    assert phases["Writer Agent"] == "complete"


def test_background_failure_records_traceback_in_phase(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    from api import sessions

    created = client.post("/api/sessions", json={"topic": "Failure visibility test", "domain": "finance_economics"})
    session_id = created.json()["session_id"]

    try:
        raise RuntimeError("synthetic background boom")
    except RuntimeError as exc:
        sessions._mark_pipeline_failed(session_id, exc)

    with sessions._with_conn() as conn:
        phase = sessions._fetchone(conn, "SELECT status, failure_reason, failure_mode FROM phases WHERE session_id=? AND agent_name=?", (session_id, "Pipeline orchestrator"))
        session = sessions._session_row(conn, session_id)

    assert phase["status"] == "failed_resumable"
    assert phase["failure_mode"] == "background_exception"
    assert "RuntimeError: synthetic background boom" in phase["failure_reason"]
    assert "Traceback:" in phase["failure_reason"]
    assert session["status"] == "failed_resumable"


def test_api_guide_and_data_aliases_exist(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    guide = client.get("/api/guide")
    assert guide.status_code == 200
    assert "research_package" in json.dumps(guide.json())

    preview = client.post("/api/data/preview", json={"data_mode": "upload"})
    assert preview.status_code == 200
    assert "preview" in preview.json()


def test_session_api_returns_structured_errors(tmp_path: Path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    missing = client.get("/api/sessions/not-a-real-session")
    assert missing.status_code == 404
    body = missing.json()
    assert body["error_code"] == "SESSION_NOT_FOUND"
    assert body["system_state"] == "not_found"
    assert body["available_actions"] == ["return_to_sessions"]
