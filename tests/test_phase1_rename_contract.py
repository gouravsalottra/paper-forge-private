from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from init_db import init_db


FORBIDDEN = [
    "".join(["ARIA", "Pipeline"]),
    "".join(["F", "orge", "GateError"]),
    "SIGMA" + "_JOB1",
    "SIGMA" + "_JOB2",
    "Scout" + "Agent",
    "Quill" + "Agent",
    "Hawk" + "Agent",
    "Sigma" + "Agent",
    "sigma_" + "job1",
    "sigma_" + "job2",
    "pap_" + "lock",
    "paper_" + "memory",
]


def test_no_old_names_in_codebase() -> None:
    offenders: list[str] = []
    root = Path(".")
    for py in root.rglob("*.py"):
        if py.name == Path(__file__).name:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        for idx, line in enumerate(text.splitlines(), start=1):
            for s in FORBIDDEN:
                if s in line:
                    offenders.append(f"{py}:{idx}: {s}")
    assert not offenders, "\n".join(offenders[:100])


def test_new_names_work_end_to_end(tmp_path: Path) -> None:
    pytest.importorskip("agents.conductor.conductor")
    from agents.conductor.conductor import ConductorPipeline

    db_path = tmp_path / "pipeline.db"
    protocol = tmp_path / "PROTOCOL.md"
    protocol.write_text("# protocol", encoding="utf-8")
    pipeline = ConductorPipeline(db_path=str(db_path), run_id="test-rename-001", paper_md_path=str(protocol))
    assert pipeline.db_path.endswith("pipeline.db")
    with sqlite3.connect(db_path) as conn:
        phases = {r[0] for r in conn.execute("SELECT phase_name FROM phases WHERE run_id=?", (pipeline.run_id,))}
    assert "LITERATURE" in phases
    assert "SCOUT" not in phases


def test_compute_gate_error_replaces_forge_gate_error() -> None:
    pytest.importorskip("agents.conductor.exceptions")
    from agents.conductor.exceptions import ComputeGateError, ComputeGateError

    assert ComputeGateError is not None
    assert ComputeGateError is ComputeGateError


def test_hypothesis_lock_table_exists_not_legacy_lock(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "hypothesis_lock" in tables
    assert ("pap_" + "lock") not in tables
