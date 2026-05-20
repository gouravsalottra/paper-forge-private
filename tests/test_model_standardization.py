from __future__ import annotations

from pathlib import Path


def test_model_selection_is_registry_driven_not_single_model_locked() -> None:
    registry = Path("api/model_registry.py").read_text(encoding="utf-8")
    assert "THRIVARC_ALLOWED_MODELS" in registry
    assert "THRIVARC_MODEL_REGISTRY_JSON" in registry
    assert "fallback_model" in registry

    sessions = Path("api/sessions.py").read_text(encoding="utf-8")
    assert "/api/models" in Path("frontend/app.html").read_text(encoding="utf-8")
    assert "_allowed_models()" in sessions


def test_repo_does_not_hardcode_non_azure_model_providers() -> None:
    forbidden = ["cla" + "ude", "gem" + "ini"]
    suffixes = {".py", ".json", ".env", ".yaml", ".toml", ".md"}
    offenders: list[str] = []
    for path in Path(".").rglob("*"):
        if any(part in {".venv", "venv", "env", "node_modules", "__pycache__", ".git"} for part in path.parts):
            continue
        if not path.is_file() or path.suffix not in suffixes:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for token in forbidden:
            if token in text.lower():
                offenders.append(f"{path}: {token}")
    assert offenders == []
