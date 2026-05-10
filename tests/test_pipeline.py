from __future__ import annotations

import builtins
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.aria.aria import ConductorPipeline
from agents.aria.exceptions import ComputeGateError, IntegrityViolationError, PipelineHaltError
from agents.codeaudit.codeaudit import CodecAgent
from agents.hawk.hawk import ReviewerAgent
from agents.quill.quill import WriterAgent
from agents.sigma.sigma import StatsrunAgent
from run_aria_pipeline import _reset_from_phase


def _make_pipeline(tmp_path: Path, run_id: str = "run-test") -> ConductorPipeline:
    db_path = tmp_path / "pipeline.db"
    return ConductorPipeline(db_path=str(db_path), run_id=run_id, paper_md_path=str(tmp_path / "PAPER.md"))


def _init_agent_results_table(db_path: Path) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS agent_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                agent TEXT NOT NULL,
                job TEXT,
                result_flag TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


def test_forge_gate_blocks_without_hypothesis_lock(tmp_path: Path) -> None:
    pipeline = _make_pipeline(tmp_path)
    with pytest.raises(ComputeGateError):
        pipeline._check_forge_gate()


def test_forge_gate_passes_with_hypothesis_lock(tmp_path: Path) -> None:
    pipeline = _make_pipeline(tmp_path)
    with sqlite3.connect(pipeline.db_path) as conn:
        conn.execute(
            """
            INSERT INTO hypothesis_lock (run_id, locked_at, locked_by, pap_sha256, forge_started_at)
            VALUES (?, datetime('now'), 'PREREGISTER', 'abc', NULL)
            """,
            (pipeline.run_id,),
        )
        conn.commit()

    pipeline._check_forge_gate()


def test_aria_never_reads_artifact_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = _make_pipeline(tmp_path)

    # Keep orchestration local and deterministic.
    monkeypatch.setattr(
        pipeline,
        "_dispatch",
        lambda agent_name, *args, **kwargs: {"result_flag": "PASS" if agent_name == "CODEAUDIT" else "DONE"},
    )
    monkeypatch.setattr(pipeline, "_run_hawk_loop", lambda max_cycles=3: pipeline._advance_phase("REVIEWER", "done"))
    monkeypatch.setattr(pipeline, "_check_forge_gate", lambda: None)

    forbidden = {".md", ".tex", ".json", ".pkl"}
    opened_forbidden: list[str] = []
    real_open = builtins.open

    def tracking_open(file, *args, **kwargs):  # type: ignore[no-untyped-def]
        name = str(file)
        suffix = Path(name).suffix.lower()
        if suffix in forbidden:
            opened_forbidden.append(name)
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", tracking_open)
    pipeline.run()
    assert opened_forbidden == []


def test_preregister_blocks_sim_results(tmp_path: Path) -> None:
    sigma = StatsrunAgent(run_id="r1", job="JOB1", db_path=str(tmp_path / "pipeline.db"), output_dir=str(tmp_path / "runs"))
    sigma.context = {"sim_results": True}
    with pytest.raises(IntegrityViolationError):
        sigma._load_inputs()


def test_codec_passes_are_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    Path("agents").mkdir(parents=True, exist_ok=True)
    Path("agents/dummy.py").write_text("x=1\n", encoding="utf-8")

    out_dir = tmp_path / "runs"
    run_id = "r-codec"
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_dir.joinpath("paper_draft_v1.tex").write_text("METHODS: PAPER_ONLY_CONTEXT", encoding="utf-8")

    db_path = tmp_path / "pipeline.db"
    _init_agent_results_table(db_path)

    calls: list[dict] = []

    def fake_llm(payload):
        calls.append(payload)
        return f"OUT:{payload['pass']}"

    agent = CodecAgent(run_id=run_id, db_path=str(db_path), output_dir=str(out_dir), llm_client=fake_llm)
    agent.run()

    assert len(calls) >= 2
    pass1 = calls[0]
    pass2 = calls[1]

    pass1_ctx = pass1.get("context", {})
    pass2_ctx = pass2.get("context", {})

    assert "codebase_text" in pass1_ctx
    assert "methods_text" not in pass1_ctx
    assert "PAPER_ONLY_CONTEXT" not in str(pass1)

    assert "methods_text" in pass2_ctx
    assert "codebase_text" not in pass2_ctx
    assert "dummy.py" not in str(pass2)


def test_codec_mismatch_report_contains_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    Path("agents").mkdir(parents=True, exist_ok=True)
    Path("agents/dummy.py").write_text("momentum_signal = returns.rolling(252).mean()\n", encoding="utf-8")
    Path("PAPER.md").write_text(
        "## Methodology\nGARCH(1,1) volatility. Sharpe ratio momentum signal. Bonferroni correction.\n",
        encoding="utf-8",
    )

    out_dir = tmp_path / "runs"
    run_id = "r-codec-meta"
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    db_path = tmp_path / "pipeline.db"
    _init_agent_results_table(db_path)

    agent = CodecAgent(
        run_id=run_id,
        db_path=str(db_path),
        output_dir=str(out_dir),
        llm_client=lambda p: f"CODEAUDIT output for pass {p.get('pass', '?')}: sharpe garch bonferroni momentum",
    )
    agent.run()

    mismatch_path = run_dir / "codec_mismatch.md"
    assert mismatch_path.exists()
    content = mismatch_path.read_text()
    assert "model:" in content
    assert "temperature:" in content
    assert "timestamp_utc:" in content


def test_hawk_loop_accepts_after_max_cycles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """REVIEWER loop must halt at max_cycles with deterministic cap."""
    pipeline = _make_pipeline(tmp_path, run_id="r-hawk-accept")

    # REVIEWER always returns REVISION_REQUESTED
    call_count = {"hawk": 0}

    def always_revision(agent, *args, **kwargs):
        if agent == "REVIEWER":
            call_count["hawk"] += 1
        return {
            "result_flag": "REVISION_REQUESTED",
            "recommendation": "MAJOR_REVISION",
            "routing": {
                "mandatory_items": [],
                "routes_to_forge": False,
                "routes_to_sigma": False,
                "routes_to_miner": False,
                "routes_to_codec": False,
            },
        }

    monkeypatch.setattr(pipeline, "_dispatch", always_revision)

    with pytest.raises(PipelineHaltError):
        pipeline._run_hawk_loop(max_cycles=3)

    # Verify REVIEWER did not exceed cycle cap
    with sqlite3.connect(pipeline.db_path) as conn:
        row = conn.execute(
            "SELECT status FROM phases WHERE run_id=? AND phase_name='REVIEWER'",
            (pipeline.run_id,),
        ).fetchone()
    assert row[0] == "failed"
    assert call_count["hawk"] <= 3


def test_hawk_loop_terminates_despite_fixer_escalate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = _make_pipeline(tmp_path, run_id="r-fixer-escalate")

    call_count = {"hawk": 0, "fixer": 0}

    def fake_dispatch(agent, *args, **kwargs):
        if agent == "WRITER":
            return {"result_flag": "DONE"}
        if agent == "AUTOREPAIR":
            call_count["fixer"] += 1
            return {"result_flag": "ESCALATE"}
        if agent == "REVIEWER":
            call_count["hawk"] += 1
            return {
                "result_flag": "REVISION_REQUESTED",
                "recommendation": "MAJOR_REVISION",
                "routing": {
                    "mandatory_items": [],
                    "routes_to_forge": False,
                    "routes_to_sigma": False,
                    "routes_to_miner": False,
                    "routes_to_codec": False,
                },
            }
        return {"result_flag": "DONE"}

    monkeypatch.setattr(pipeline, "_dispatch", fake_dispatch)
    with pytest.raises(PipelineHaltError):
        pipeline._run_hawk_loop(max_cycles=3)

    with sqlite3.connect(pipeline.db_path) as conn:
        row = conn.execute(
            "SELECT status FROM phases WHERE run_id=? AND phase_name='REVIEWER'",
            (pipeline.run_id,),
        ).fetchone()

    assert row[0] == "failed"
    assert call_count["hawk"] <= 3
    # AUTOREPAIR should run in non-final cycles, and never reset REVIEWER cycle counting.
    assert 1 <= call_count["fixer"] <= 3


def test_codec_retry_exhaustion_halts_without_skip_spam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    pipeline = _make_pipeline(tmp_path, run_id="r-codec-halt")
    pipeline.MAX_MAIN_LOOPS = 50

    # Force planner to keep selecting CODEAUDIT to reproduce historical skip-spam behavior.
    monkeypatch.setattr(pipeline, "_next_tool_call", lambda: "CODEAUDIT")
    monkeypatch.setattr(pipeline, "_paper_is_publishable", lambda *a, **k: False)

    def fail_codec(agent_name, *_args, **_kwargs):
        if agent_name == "CODEAUDIT":
            raise RuntimeError("DeploymentNotFound")
        return {"result_flag": "DONE"}

    monkeypatch.setattr(pipeline, "_dispatch", fail_codec)
    pipeline.run()

    with sqlite3.connect(pipeline.db_path) as conn:
        run = conn.execute(
            "SELECT status FROM pipeline_runs WHERE run_id=?",
            (pipeline.run_id,),
        ).fetchone()
    assert run is not None
    assert run[0] == "failed"

    log_path = Path("runs") / pipeline.run_id / "audit_log.txt"
    text = log_path.read_text(encoding="utf-8")
    # Should stop after first retry-exhaustion event; no repeated skip lines.
    assert text.count("Skipping after") <= 1


def test_quill_raises_on_forbidden_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    def bad_llm(_payload):
        return "This is a groundbreaking result."

    agent = WriterAgent(run_id="r-quill", output_dir=str(tmp_path / "runs"), llm_client=bad_llm)
    out = agent.run(revision_number=1)
    assert out["result_flag"] == "REVISION_REQUESTED"


def test_artifact_versioning_no_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    out = tmp_path / "runs"
    run_id = "r-ver"
    run_dir = out / run_id
    (run_dir / "stats_tables").mkdir(parents=True, exist_ok=True)
    (run_dir / "pap.md").write_text("hypothesis: test", encoding="utf-8")
    (run_dir / "stats_tables" / "primary_metric.csv").write_text(
        "sharpe_differential,meets_minimum_effect\n-0.2,True\n",
        encoding="utf-8",
    )
    (run_dir / "stats_tables" / "ttest_results.csv").write_text(
        "p_value,bonferroni_threshold\n0.01,0.0083\n",
        encoding="utf-8",
    )
    (run_dir / "hawk_routing_v1.json").write_text(
        '{"approved_for_quill": true, "research_summary": {"hypothesis":"h","primary_result":"Sharpe differential = -0.2","p_value":"0.01","bonferroni_threshold":"0.0083","passes_bonferroni":false,"seed_consistent":true,"codec_clean":true,"n_episodes":2000,"production_ready":false}}',
        encoding="utf-8",
    )

    first = WriterAgent(run_id=run_id, output_dir=str(out), llm_client=lambda _p: "Version one body")
    first_result = first.run(revision_number=1)
    v1_path = Path(first_result["path"])
    v1_text_before = v1_path.read_text(encoding="utf-8")

    second = WriterAgent(run_id=run_id, output_dir=str(out), llm_client=lambda _p: "Version two body")
    second_result = second.run(revision_number=2)
    v2_path = Path(second_result["path"])

    assert v1_path.exists()
    assert v2_path.exists()
    assert v1_path.read_text(encoding="utf-8") == v1_text_before
    assert "\\begin{document}" in v1_text_before


def test_full_pipeline_smoke_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    pipeline = _make_pipeline(tmp_path, run_id="r-smoke")

    with sqlite3.connect(pipeline.db_path) as conn:
        conn.execute(
            """
            INSERT INTO hypothesis_lock (run_id, locked_at, locked_by, pap_sha256, forge_started_at)
            VALUES (?, datetime('now'), 'PREREGISTER', 'abc', NULL)
            ON CONFLICT(run_id) DO UPDATE SET locked_at=excluded.locked_at, forge_started_at=NULL
            """,
            (pipeline.run_id,),
        )
        conn.commit()

    def fake_dispatch(agent_name, _server_name, _context):
        if agent_name == "REVIEWER":
            out = Path("runs") / pipeline.run_id
            out.mkdir(parents=True, exist_ok=True)
            (out / "hawk_routing_v1.json").write_text(
                '{"result_flag":"APPROVED","approved_for_quill":true,"mandatory_items":[],"research_summary":{"hypothesis":"h"}}',
                encoding="utf-8",
            )
            return {"result_flag": "APPROVED", "approved_for_quill": True, "mandatory_items": []}
        if agent_name == "WRITER":
            out = Path("runs") / pipeline.run_id
            out.mkdir(parents=True, exist_ok=True)
            (out / "paper_draft_v1.tex").write_text("\\section*{Draft}", encoding="utf-8")
            return {"result_flag": "DONE"}
        if agent_name == "CODEAUDIT":
            return {"result_flag": "PASS"}
        return {"result_flag": "DONE"}

    monkeypatch.setattr(pipeline, "_dispatch", fake_dispatch)

    pipeline.run()

    with sqlite3.connect(pipeline.db_path) as conn:
        rows = conn.execute(
            "SELECT phase_name, status FROM phases WHERE run_id=? ORDER BY id", (pipeline.run_id,)
        ).fetchall()

    status_map = {name: status for name, status in rows}
    expected_phases = ["LITERATURE", "DATAPULL", "PREREGISTER", "COMPUTE", "STATSRUN", "CODEAUDIT", "WRITER", "REVIEWER"]
    for phase in expected_phases:
        assert status_map.get(phase) == "done"

    assert (Path("runs") / pipeline.run_id / "paper_draft_v1.tex").exists()


def test_resume_blocks_on_paper_md_tamper(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from agents.aria.exceptions import PAPTamperError
    import hashlib

    monkeypatch.chdir(tmp_path)
    paper = Path("PAPER.md")
    paper.write_text("initial protocol\n", encoding="utf-8")

    pipeline = ConductorPipeline(db_path="pipeline.db", run_id="r-tamper", paper_md_path="PAPER.md")
    locked_hash = hashlib.sha256(paper.read_bytes()).hexdigest()

    with sqlite3.connect("pipeline.db") as conn:
        conn.execute(
            """
            INSERT INTO hypothesis_lock (run_id, locked_at, locked_by, pap_sha256, forge_started_at)
            VALUES (?, datetime('now'), 'PREREGISTER', ?, NULL)
            ON CONFLICT(run_id) DO UPDATE SET pap_sha256=excluded.pap_sha256
            """,
            (pipeline.run_id, locked_hash),
        )
        conn.execute(
            "UPDATE phases SET status='done' WHERE run_id=? AND phase_name IN ('LITERATURE','DATAPULL')",
            (pipeline.run_id,),
        )
        conn.commit()

    paper.write_text("tampered protocol\n", encoding="utf-8")

    with pytest.raises(PAPTamperError) as exc:
        _reset_from_phase(pipeline.run_id, "COMPUTE")

    msg = str(exc.value)
    assert "Locked hash:" in msg
    assert "Current hash:" in msg


def test_resume_allows_tamper_with_override_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import hashlib

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PAPERCOMPUTE_OVERRIDE_PAP_TAMPER", "1")

    paper = Path("PAPER.md")
    paper.write_text("initial protocol\n", encoding="utf-8")
    pipeline = ConductorPipeline(db_path="pipeline.db", run_id="r-tamper-override", paper_md_path="PAPER.md")
    locked_hash = hashlib.sha256(paper.read_bytes()).hexdigest()

    with sqlite3.connect("pipeline.db") as conn:
        conn.execute(
            """
            INSERT INTO hypothesis_lock (run_id, locked_at, locked_by, pap_sha256, forge_started_at)
            VALUES (?, datetime('now'), 'PREREGISTER', ?, NULL)
            ON CONFLICT(run_id) DO UPDATE SET pap_sha256=excluded.pap_sha256
            """,
            (pipeline.run_id, locked_hash),
        )
        conn.commit()

    paper.write_text("tampered protocol\n", encoding="utf-8")
    _reset_from_phase(pipeline.run_id, "COMPUTE")

    with sqlite3.connect("pipeline.db") as conn:
        row = conn.execute(
            """
            SELECT status, detail
            FROM server_health_log
            WHERE run_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (pipeline.run_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "CRITICAL"
    assert "PAPER.md has been modified since PAP was locked" in row[1]
