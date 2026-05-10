from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_latex_mcp_server_has_required_tools() -> None:
    from mcp_servers.latex_server import mcp

    tool_names = [t.name for t in mcp.tools]
    assert "compile_latex" in tool_names
    assert "validate_latex_syntax" in tool_names


def test_latex_syntax_validator_catches_mismatched_envs() -> None:
    from mcp_servers.latex_server import validate_latex_syntax

    result = validate_latex_syntax(r"\begin{document}\begin{table}\end{document}")
    assert result["valid"] is False
    assert any("Mismatched" in i for i in result["issues"])


def test_latex_syntax_validator_passes_valid_document() -> None:
    from mcp_servers.latex_server import validate_latex_syntax

    result = validate_latex_syntax(r"\begin{document}Hello\end{document}")
    assert result["valid"] is True


def test_modal_mcp_server_has_required_tools() -> None:
    from mcp_servers.modal_server import mcp

    tool_names = [t.name for t in mcp.tools]
    assert "dispatch_compute_job" in tool_names
    assert "check_compute_status" in tool_names


def test_modal_dispatch_fails_gracefully_without_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MODAL_TOKEN_ID", raising=False)
    monkeypatch.delenv("MODAL_TOKEN_SECRET", raising=False)
    from mcp_servers.modal_server import dispatch_compute_job

    result = dispatch_compute_job(
        n_episodes=500,
        seeds=[1337],
        concentration_levels=[0.1],
        output_dir="/tmp/test",
    )
    assert result["success"] is False
    assert "MODAL_TOKEN_ID" in result["error"]


def test_check_compute_status_returns_incomplete_when_no_results(tmp_path: Path) -> None:
    from mcp_servers.modal_server import check_compute_status

    result = check_compute_status(str(tmp_path))
    assert result["complete"] is False
