from __future__ import annotations

import builtins
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.aria.aria import ARIAPipeline
from agents.aria.exceptions import ForgeGateError, IntegrityViolationError, PipelineHaltError
from agents.codec.codec import CodecAgent
from agents.hawk.hawk import HawkAgent
from agents.quill.quill import QuillAgent
from agents.sigma.sigma import SigmaAgent


def _make_pipeline(tmp_path: Path, run_id: str = "run-test") -> ARIAPipeline:
    db_path = tmp_path / "state.db"
    return ARIAPipeline(db_path=str(db_path), run_id=run_id, paper_md_path=str(tmp_path / "PAPER.md"))


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


def test_forge_gate_blocks_without_pap_lock(tmp_path: Path) -> None:
    pipeline = _make_pipeline(tmp_path)
    with pytest.raises(ForgeGateError):
        pipeline._check_forge_gate()


def test_forge_gate_passes_with_pap_lock(tmp_path: Path) -> None:
    pipeline = _make_pipeline(tmp_path)
    with sqlite3.connect(pipeline.db_path) as conn:
        conn.execute(
            """
            INSERT INTO pap_lock (run_id, locked_at, locked_by, pap_sha256, forge_started_at)
            VALUES (?, datetime('now'), 'SIGMA_JOB1', 'abc', NULL)
            """,
            (pipeline.run_id,),
        )
        conn.commit()

    pipeline._check_forge_gate()


def test_aria_never_reads_artifact_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = _make_pipeline(tmp_path)

    # Keep orchestration local and deterministic.
    monkeypatch.setattr(pipeline, "_dispatch", lambda *args, **kwargs: {"result_flag": "DONE"})
    monkeypatch.setattr(pipeline, "_run_hawk_loop", lambda max_cycles=3: pipeline._advance_phase("HAWK", "done"))
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


def test_sigma_job1_blocks_sim_results(tmp_path: Path) -> None:
    sigma = SigmaAgent(run_id="r1", job="JOB1", db_path=str(tmp_path / "state.db"), output_dir=str(tmp_path / "paper_memory"))
    sigma.context = {"sim_results": True}
    with pytest.raises(IntegrityViolationError):
        sigma._load_inputs()


def test_codec_passes_are_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    Path("agents").mkdir(parents=True, exist_ok=True)
    Path("agents/dummy.py").write_text("x=1\n", encoding="utf-8")

    out_dir = tmp_path / "paper_memory"
    run_id = "r-codec"
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_dir.joinpath("paper_draft_v1.tex").write_text("METHODS: PAPER_ONLY_CONTEXT", encoding="utf-8")

    db_path = tmp_path / "state.db"
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


def test_hawk_escalates_after_3_cycles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pipeline = _make_pipeline(tmp_path, run_id="r-hawk")

    def dispatch_revision_requested(*args, **kwargs):
        return {"result_flag": "REVISION_REQUESTED"}

    monkeypatch.setattr(pipeline, "_dispatch", dispatch_revision_requested)

    with pytest.raises(PipelineHaltError):
        pipeline._run_hawk_loop(max_cycles=3)

    with sqlite3.connect(pipeline.db_path) as conn:
        row = conn.execute(
            """
            SELECT result_flag
            FROM agent_results
            WHERE run_id=? AND agent='HAWK' AND job='REV3'
            ORDER BY id DESC
            LIMIT 1
            """,
            (pipeline.run_id,),
        ).fetchone()

    assert row is not None
    assert row[0] == "ESCALATE"


def test_quill_raises_on_forbidden_words(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    def bad_llm(_payload):
        return "This is a groundbreaking result."

    agent = QuillAgent(run_id="r-quill", output_dir=str(tmp_path / "paper_memory"), llm_client=bad_llm)
    with pytest.raises(ValueError):
        agent.run(revision_number=1)


def test_artifact_versioning_no_overwrite(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    out = tmp_path / "paper_memory"
    run_id = "r-ver"

    first = QuillAgent(run_id=run_id, output_dir=str(out), llm_client=lambda _p: "Version one body")
    first_result = first.run(revision_number=1)
    v1_path = Path(first_result["path"])
    v1_text_before = v1_path.read_text(encoding="utf-8")

    second = QuillAgent(run_id=run_id, output_dir=str(out), llm_client=lambda _p: "Version two body")
    second_result = second.run(revision_number=2)
    v2_path = Path(second_result["path"])

    assert v1_path.exists()
    assert v2_path.exists()
    assert v1_path.read_text(encoding="utf-8") == v1_text_before
    assert "Version one body" in v1_text_before


def test_full_pipeline_smoke_test(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    pipeline = _make_pipeline(tmp_path, run_id="r-smoke")

    with sqlite3.connect(pipeline.db_path) as conn:
        conn.execute(
            """
            INSERT INTO pap_lock (run_id, locked_at, locked_by, pap_sha256, forge_started_at)
            VALUES (?, datetime('now'), 'SIGMA_JOB1', 'abc', NULL)
            ON CONFLICT(run_id) DO UPDATE SET locked_at=excluded.locked_at, forge_started_at=NULL
            """,
            (pipeline.run_id,),
        )
        conn.commit()

    def fake_dispatch(agent_name, _server_name, _context):
        if agent_name == "HAWK":
            return {"result_flag": "APPROVED"}
        if agent_name == "QUILL":
            out = Path("paper_memory") / pipeline.run_id
            out.mkdir(parents=True, exist_ok=True)
            (out / "paper_draft_v1.tex").write_text("\\section*{Draft}", encoding="utf-8")
            return {"result_flag": "DONE"}
        return {"result_flag": "DONE"}

    monkeypatch.setattr(pipeline, "_dispatch", fake_dispatch)

    pipeline.run()

    with sqlite3.connect(pipeline.db_path) as conn:
        rows = conn.execute(
            "SELECT phase_name, status FROM phases WHERE run_id=? ORDER BY id", (pipeline.run_id,)
        ).fetchall()

    status_map = {name: status for name, status in rows}
    expected_phases = ["SCOUT", "MINER", "SIGMA_JOB1", "FORGE", "SIGMA_JOB2", "CODEC", "QUILL", "HAWK"]
    for phase in expected_phases:
        assert status_map.get(phase) == "done"

    assert (Path("paper_memory") / pipeline.run_id / "paper_draft_v1.tex").exists()
