from __future__ import annotations

from pathlib import Path


def test_step0_model_strings_are_standardized_to_gpt_4o() -> None:
    forbidden = [
        "gpt" + "-5",
        "gpt" + "-4o-mini",
        "gpt" + "-4-",
        "gpt" + "-3",
        "cla" + "ude",
    ]
    suffixes = {".py", ".json", ".env", ".yaml", ".toml", ".md"}
    ignored_parts = {".git", "__pycache__", ".pytest_cache", "paper" + "_memory", "runs", "outputs"}

    offenders: list[str] = []
    for path in Path(".").rglob("*"):
        if any(part in {
            ".venv", "venv", "env",
            "node_modules", "__pycache__", ".git"
        } for part in path.parts):
            continue
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part in ignored_parts for part in path.parts):
            continue
        try:
            if path.suffix == ".py":
                lines = path.read_text(
                    encoding="utf-8", errors="ignore"
                ).splitlines()
                text = "\n".join(
                    l for l in lines 
                    if not l.strip().startswith("#")
                )
            else:
                text = path.read_text(
                    encoding="utf-8", errors="ignore"
                )
        except Exception:
            continue
        for token in forbidden:
            if token in text:
                offenders.append(f"{path}: {token}")

    assert offenders == []
