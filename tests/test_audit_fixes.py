from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.statsrun_job import SigmaJob2


def test_top_level_agent_stubs_reexport_classes() -> None:
    hawk_mod = importlib.import_module("agents.hawk")
    miner_mod = importlib.import_module("agents.miner")
    quill_mod = importlib.import_module("agents.quill")
    scout_mod = importlib.import_module("agents.scout")

    assert hasattr(hawk_mod, "ReviewerAgent")
    assert hasattr(miner_mod, "build_returns_frame")
    assert hasattr(quill_mod, "WriterAgent")
    assert hasattr(scout_mod, "LiteratureAgent")


def test_seed_consistency_missing_seeds_is_invalid() -> None:
    df = pd.DataFrame(
        [
            {"concentration": 0.1, "seed": 42, "sharpe": -0.1},
            {"concentration": 0.6, "seed": 42, "sharpe": -0.2},
        ]
    )
    out = SigmaJob2._validate_seed_consistency(df)
    assert out["finding_valid"] is False
    assert out["conclusion"] == "Seed data missing — finding cannot be validated"


def test_concentration_sharpe_differential_method_exists() -> None:
    df = pd.DataFrame(
        [
            {"concentration": 0.1, "sharpe": 0.1},
            {"concentration": 0.6, "sharpe": -0.2},
        ]
    )
    out = SigmaJob2._concentration_sharpe_differential(df)
    assert "sharpe_differential" in out


def test_gitignore_contains_python_cache_rules() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")
    for token in ("__pycache__/", "*.pyc", "*.pyo", ".pytest_cache/"):
        assert token in text
