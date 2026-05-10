from __future__ import annotations

import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_codeaudit_and_specaudit_files_have_different_sha() -> None:
    p1 = Path("agents/codeaudit_pass1.py").read_bytes()
    p2 = Path("agents/specaudit_pass2.py").read_bytes()
    sha1 = hashlib.sha256(p1).hexdigest()
    sha2 = hashlib.sha256(p2).hexdigest()
    assert sha1 != sha2, (
        "codeaudit_pass1.py and specaudit_pass2.py are identical — "
        "CODEAUDIT integrity is broken. Pass 1 must read code only. "
        "Pass 2 must read PROTOCOL.md only. They must be different files."
    )


def test_codeaudit_loads_codeaudit_prompt() -> None:
    content = Path("agents/codeaudit/codeaudit_pass1.py").read_text(encoding="utf-8")
    assert "codeaudit" in content.lower()
    assert "specaudit" not in content.lower()


def test_specaudit_loads_specaudit_prompt() -> None:
    content = Path("agents/codeaudit/specaudit_pass2.py").read_text(encoding="utf-8")
    assert "specaudit" in content.lower()
    assert "codeaudit" not in content.lower()


def test_specaudit_uses_different_api_key() -> None:
    content = Path("agents/codeaudit/specaudit_pass2.py").read_text(encoding="utf-8")
    assert "OPENAI_API_KEY_PASS2" in content


def test_no_orphan_codec_files_exist() -> None:
    assert not Path("agents/codec_pass1.py").exists(), (
        "agents/codec_pass1.py is an orphan from the rename. Delete it."
    )
    assert not Path("agents/codec_pass2.py").exists(), (
        "agents/codec_pass2.py is an orphan from the rename. Delete it."
    )
