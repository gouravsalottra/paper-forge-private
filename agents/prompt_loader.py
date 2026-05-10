from __future__ import annotations

import hashlib
from pathlib import Path


def _prompt_root() -> Path:
    return Path(__file__).resolve().parents[1] / "prompts"


def _load_prompt(name: str) -> str:
    path = _prompt_root() / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file missing: {path}")
    return path.read_text(encoding="utf-8")


def load_prompt(name: str) -> tuple[str, str]:
    """Returns (prompt_text, sha256_hex)."""
    text = _load_prompt(name)
    sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return text, sha256
