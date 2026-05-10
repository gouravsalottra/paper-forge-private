from __future__ import annotations

from pathlib import Path


def _check_master_context() -> bool:
    refs = []
    for py in Path(".").rglob("*.py"):
        if ".venv" in py.parts or "__pycache__" in py.parts:
            continue
        text = py.read_text(encoding="utf-8", errors="ignore")
        if "MASTER_CONTEXT" in text:
            refs.append(py)
    p = Path("MASTER_CONTEXT.md")
    if refs:
        return p.exists() and p.stat().st_size > 0
    return (not p.exists()) or ("deprecated" in p.read_text(encoding="utf-8", errors="ignore").lower())


def test_final_audit_checklist() -> None:
    checks = {
        "requirements.lock exists": Path("requirements.lock").exists(),
        ".github/workflows/ci.yml exists": Path(".github/workflows/ci.yml").exists(),
        "prompts/ directory has 5+ files": len(list(Path("prompts").glob("*.md"))) >= 5,
        "PROTOCOL.md exists": Path("PROTOCOL.md").exists(),
        "PROTOCOL_SCHEMA.md exists": Path("PROTOCOL_SCHEMA.md").exists(),
        "config/model_config.json exists": Path("config/model_config.json").exists(),
        "intake.py exists": Path("intake.py").exists(),
        "dashboard.py exists": Path("dashboard.py").exists(),
        "agents/miner/connectors/ exists": Path("agents/miner/connectors").is_dir(),
        "agents/sigma/tests/ exists": Path("agents/sigma/tests").is_dir(),
        "agents/forge/adapters/ exists": Path("agents/forge/adapters").is_dir(),
        "pipeline.db in .gitignore": "pipeline.db" in Path(".gitignore").read_text(encoding="utf-8"),
        "MASTER_CONTEXT.md not empty if referenced": _check_master_context(),
    }
    failures = [k for k, v in checks.items() if not v]
    assert not failures, "Audit checklist failures:\\n" + "\\n".join(f"  ✗ {f}" for f in failures)


def test_protocol_validator_accepts_protocol_md() -> None:
    from aria.validate_protocol import ProtocolValidator

    errors = ProtocolValidator().validate(Path("examples/gsci_momentum/PROTOCOL.md"))
    assert errors == []


def test_model_config_has_required_keys() -> None:
    import json

    cfg = json.loads(Path("config/model_config.json").read_text(encoding="utf-8"))
    for k in [
        "primary_model",
        "primary_model_alias",
        "fallback_model",
        "codec_pass2_model",
        "codec_pass2_temperature",
        "default_temperature",
        "last_verified",
        "deprecation_check_url",
    ]:
        assert k in cfg


def test_prompt_files_count() -> None:
    assert len(list(Path("prompts").glob("*.md"))) >= 6


def test_registry_directories_exist() -> None:
    assert Path("agents/miner/connectors").is_dir()
    assert Path("agents/sigma/tests").is_dir()
    assert Path("agents/forge/adapters").is_dir()


def test_ci_workflow_and_lockfile_exist() -> None:
    assert Path(".github/workflows/ci.yml").exists()
    assert Path("requirements.lock").exists()


def test_intake_and_dashboard_entrypoints_exist() -> None:
    assert Path("intake.py").exists()
    assert Path("dashboard.py").exists()


def test_gitignore_contains_state_db() -> None:
    text = Path(".gitignore").read_text(encoding="utf-8")
    assert "pipeline.db" in text


def test_master_context_present() -> None:
    p = Path("MASTER_CONTEXT.md")
    assert p.exists()
    assert p.stat().st_size > 0


def test_protocol_schema_and_template_present() -> None:
    assert Path("PROTOCOL_SCHEMA.md").exists()
    assert Path("PROTOCOL.md").exists()
