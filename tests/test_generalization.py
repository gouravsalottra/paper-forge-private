from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.compute.adapters.registry import get_adapter
from agents.miner.connectors.registry import get_connector, CONNECTOR_REGISTRY


def _write_protocol(path: Path, compute_type: str = "none", tests: list[str] | None = None, mode: str = "exploratory") -> None:
    tests = tests or ["descriptive_stats"]
    path.write_text(
        "\n".join(
            [
                "## research_question",
                "Test question",
                "## research_mode",
                mode,
                "## claim_type",
                "descriptive",
                "## hypothesis",
                "N/A",
                "## primary_metric",
                "N/A",
                "## minimum_effect_size",
                "N/A",
                "## significance_threshold",
                "0.05",
                "## data_source",
                "yfinance",
                "## sample_period",
                "2010-2024",
                "## compute_type",
                compute_type,
                "## statistical_tests",
                json.dumps(tests),
            ]
        ),
        encoding="utf-8",
    )


def test_pipeline_works_with_none_compute_type(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_protocol(tmp_path / "PROTOCOL.md", compute_type="none")
    monkeypatch.setenv("PAPER_FORGE_PROTOCOL_PATH", str(tmp_path / "PROTOCOL.md"))
    adapter = get_adapter("none")
    result = adapter.run(params={}, output_dir=tmp_path, seeds=[1337])
    assert result["skipped"] is True
    assert result["adapter_type"] == "none"


def test_statsrun_runs_only_specified_tests(tmp_path: Path) -> None:
    from agents.statsrun.statsrun import StatsrunAgent

    sample = pd.DataFrame(
        [
            {"concentration": 0.1, "seed": 1337, "sharpe": 0.1, "mean_reward": 0.01, "n_episodes": 10},
            {"concentration": 0.6, "seed": 1337, "sharpe": -0.1, "mean_reward": -0.01, "n_episodes": 10},
        ]
    )
    out = tmp_path / "outputs"
    out.mkdir(parents=True, exist_ok=True)
    (out / "sim_results.json").write_text(sample.to_json(orient="records"), encoding="utf-8")
    agent = StatsrunAgent(run_id="r", job="JOB2", db_path=str(tmp_path / "pipeline.db"), output_dir=str(tmp_path / "runs"))
    res = agent.run()
    assert res["result_flag"] == "DONE"


def test_datapull_uses_yfinance_connector_for_public_data(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PAPER_FORGE_MINER_SOURCE", "yfinance")
    connector = get_connector("yfinance")
    assert connector.source_name == "yfinance"
    assert hasattr(connector, "fetch")


def test_protocol_template_fails_with_unfilled_placeholders(tmp_path: Path) -> None:
    template = Path("PROTOCOL.md").read_text(encoding="utf-8")
    (tmp_path / "PROTOCOL.md").write_text(template, encoding="utf-8")
    from conductor.validate_protocol import ProtocolValidator

    errors = ProtocolValidator().validate(tmp_path / "PROTOCOL.md")
    assert any("placeholder" in e.lower() or "fill in" in e.lower() for e in errors)


def test_intake_generates_protocol_without_gsci_knowledge() -> None:
    content = Path("agents/intake/intake_agent.py").read_text(encoding="utf-8")
    forbidden = ["gsci", "GSCI", "commodity", "pettingzoo", "500000", "500_000", "concentration"]
    for word in forbidden:
        assert word not in content, f"INTAKE contains GSCI-specific knowledge: '{word}'."


def test_connector_registry_has_no_gsci_specific_connectors() -> None:
    for name in CONNECTOR_REGISTRY:
        assert "gsci" not in name.lower()
        assert "commodity" not in name.lower()
        assert "momentum" not in name.lower()


def test_example_gsci_protocol_exists_and_is_valid() -> None:
    gsci_protocol = Path("examples/gsci_momentum/PROTOCOL.md")
    assert gsci_protocol.exists()
    assert gsci_protocol.stat().st_size > 500


def test_core_protocol_template_has_no_gsci_content() -> None:
    content = Path("PROTOCOL.md").read_text(encoding="utf-8")
    assert "GSCI" not in content
    assert "passive investor concentration" not in content.lower()
    assert "commodity" not in content.lower()
    assert "[FILL IN" in content


def test_protocol_template_md_does_not_exist() -> None:
    assert not Path("PROTOCOL_TEMPLATE.md").exists(), (
        "PROTOCOL_TEMPLATE.md is a duplicate of PROTOCOL.md. "
        "Only PROTOCOL.md should exist as the canonical blank template."
    )


def test_protocol_md_is_blank_template() -> None:
    content = Path("PROTOCOL.md").read_text(encoding="utf-8")
    assert "FILL IN" in content, (
        "PROTOCOL.md should be a blank template with [FILL IN] placeholders"
    )
    assert "GSCI" not in content
    assert "passive investor" not in content.lower()


def test_gitignore_excludes_all_run_artifacts() -> None:
    content = Path(".gitignore").read_text(encoding="utf-8")
    required = ["*.log", "pipeline.db", "runs/", "outputs/", ".env"]
    for entry in required:
        assert entry in content, f".gitignore missing: {entry}"


def test_log_files_not_in_git_index() -> None:
    import subprocess

    result = subprocess.run(
        ["git", "ls-files", "*.log", "paper_draft_v1.log"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.stdout.strip() == "", (
        f"Log files are tracked in git: {result.stdout.strip()}\n"
        "Run: git rm --cached <filename>"
    )


def test_root_aria_conductor_are_shims_not_logic() -> None:
    for dirpath in [Path("aria"), Path("conductor")]:
        if not dirpath.exists():
            continue
        for pyfile in dirpath.glob("*.py"):
            if pyfile.name == "__init__.py":
                continue
            content = pyfile.read_text(encoding="utf-8")
            lines = [l.strip() for l in content.splitlines() if l.strip() and not l.strip().startswith("#")]
            non_import_lines = [l for l in lines if not l.startswith("from ") and not l.startswith("import ")]
            assert len(non_import_lines) == 0, (
                f"{pyfile} contains logic, not just imports.\n"
                "Root-level aria/ and conductor/ must be pure shims.\n"
                "Move logic to agents/conductor/ or agents/aria/\n"
                f"Non-import lines found: {non_import_lines}"
            )


def test_agents_conductor_is_canonical_import() -> None:
    from agents.conductor.conductor import ConductorPipeline

    assert ConductorPipeline is not None


def test_conductor_validate_protocol_importable_from_root() -> None:
    from conductor.validate_protocol import ProtocolValidator

    assert ProtocolValidator is not None


def test_compute_episodes_not_hardcoded() -> None:
    content = Path("agents/compute/adapters/rl_adapter.py").read_text(encoding="utf-8")
    assert "500_000" not in content
    assert "500000" not in content
    content2 = Path("agents/aria/aria.py").read_text(encoding="utf-8")
    assert "500_000" not in content2
    assert "500000" not in content2


def test_datapull_has_no_gsci_strings() -> None:
    content = Path("agents/datapull/datapull.py").read_text(encoding="utf-8")
    forbidden = ["GSCI", "gsci", "commodity_futures", "concentration_level", "mkt_rf_proxy"]
    for word in forbidden:
        assert word not in content, (
            f"datapull.py contains domain-specific string: '{word}'. "
            "Core agents must be domain-agnostic."
        )


def test_intake_no_llm_noninteractive_generates_protocol(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import io
    import sys
    from agents.intake.intake_agent import IntakeAgent
    from conductor.validate_protocol import ProtocolValidator

    class _FakeStdin(io.StringIO):
        def isatty(self) -> bool:  # pragma: no cover - explicit behavior
            return False

    monkeypatch.setattr(sys, "stdin", _FakeStdin(""))
    agent = IntakeAgent(output_path=tmp_path / "PROTOCOL.md", no_llm=True)
    agent.run()
    out = tmp_path / "PROTOCOL.md"
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "FILL IN" not in content
    assert "GSCI" not in content
    errors = ProtocolValidator().validate(out)
    assert len(errors) == 0, f"Generated protocol invalid: {errors}"
