from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.codec_pass1 import CodecPass1
from agents.aria.exceptions import TokenBudgetExceededError
from agents.llm_client import track_usage
from init_db import init_db


class _MockUsage:
    def __init__(self, prompt_tokens: int, completion_tokens: int, total_tokens: int) -> None:
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class _MockResponse:
    def __init__(self, usage: _MockUsage | None) -> None:
        self.usage = usage


def test_token_budget_table_exists_after_init_db(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        token_budget_cols = [r[1] for r in conn.execute("PRAGMA table_info(token_budget)")]
        token_limits_cols = [r[1] for r in conn.execute("PRAGMA table_info(token_limits)")]

    for c in [
        "budget_id",
        "run_id",
        "phase_name",
        "agent_name",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "estimated_cost_usd",
        "model",
        "recorded_at",
    ]:
        assert c in token_budget_cols

    for c in ["run_id", "soft_limit_usd", "hard_limit_usd", "total_spent_usd", "last_updated"]:
        assert c in token_limits_cols


def test_track_usage_records_to_db(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    usage = _MockUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    response = _MockResponse(usage=usage)

    out = track_usage(
        response,
        run_id="test-001",
        phase_name="REVIEWER",
        agent_name="REVIEWER",
        model="gpt-4o",
        db_path=str(db),
    )
    assert out["total_tokens"] == 150
    assert out["estimated_cost_usd"] > 0

    with sqlite3.connect(db) as conn:
        row = conn.execute(
            "SELECT total_tokens, estimated_cost_usd FROM token_budget WHERE run_id=? ORDER BY rowid DESC LIMIT 1",
            ("test-001",),
        ).fetchone()
    assert row is not None
    assert row[0] == 150
    assert float(row[1]) > 0


def test_hard_limit_raises_token_budget_exceeded(tmp_path: Path) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO token_limits (run_id, soft_limit_usd, hard_limit_usd, total_spent_usd, last_updated)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            ("tiny-limit", 0.0, 0.0001, 0.0),
        )
        conn.commit()

    response = _MockResponse(_MockUsage(prompt_tokens=10_000, completion_tokens=10_000, total_tokens=20_000))
    with pytest.raises(TokenBudgetExceededError):
        track_usage(
            response,
            run_id="tiny-limit",
            phase_name="CODEAUDIT",
            agent_name="CODEAUDIT",
            model="gpt-4o",
            db_path=str(db),
        )


def test_soft_limit_logs_warning_not_raises(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    with sqlite3.connect(db) as conn:
        conn.execute(
            """
            INSERT INTO token_limits (run_id, soft_limit_usd, hard_limit_usd, total_spent_usd, last_updated)
            VALUES (?, ?, ?, ?, datetime('now'))
            """,
            ("soft-limit", 0.0001, 100.0, 0.0),
        )
        conn.commit()

    response = _MockResponse(_MockUsage(prompt_tokens=10_000, completion_tokens=10_000, total_tokens=20_000))
    out = track_usage(
        response,
        run_id="soft-limit",
        phase_name="WRITER",
        agent_name="WRITER",
        model="gpt-4o",
        db_path=str(db),
    )
    assert out["estimated_cost_usd"] > 0
    assert "budget" in caplog.text.lower() or "warning" in caplog.text.lower()


def test_real_agent_result_has_prompt_hash_and_usage_row(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = tmp_path / "pipeline.db"
    init_db(db)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "agents").mkdir(exist_ok=True)
    (tmp_path / "agents" / "dummy.py").write_text("x=1\n", encoding="utf-8")

    class _FakeClient:
        class _Chat:
            class _Completions:
                @staticmethod
                def create(**_kwargs):
                    usage = SimpleNamespace(prompt_tokens=120, completion_tokens=80, total_tokens=200)
                    msg = SimpleNamespace(content="spec ok")
                    choice = SimpleNamespace(message=msg)
                    return SimpleNamespace(choices=[choice], usage=usage)

            completions = _Completions()

        chat = _Chat()

    monkeypatch.setattr("agents.codec_pass1.get_client", lambda _agent: (_FakeClient(), "gpt-4o-mini"))
    agent = CodecPass1(run_id="r-usage", db_path=str(db), output_dir=str(tmp_path / "runs"))
    result = agent.run()
    assert result["result_flag"] == "DONE"

    with sqlite3.connect(db) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(agent_results)")]
        if {"run_id", "agent", "job", "prompt_sha256"}.issubset(cols):
            prompt_sha_row = conn.execute(
                """
                SELECT prompt_sha256
                FROM agent_results
                WHERE run_id=? AND agent=? AND job=?
                ORDER BY id DESC LIMIT 1
                """,
                ("r-usage", "CODEAUDIT", "PASS1"),
            ).fetchone()
        else:
            prompt_sha_row = conn.execute(
                """
                SELECT prompt_sha256
                FROM agent_results
                WHERE run_id=? AND phase_name=? AND agent_name=?
                ORDER BY created_at DESC LIMIT 1
                """,
                ("r-usage", "CODEAUDIT", "CODEAUDIT_PASS1"),
            ).fetchone()
        usage_row = conn.execute(
            """
            SELECT total_tokens
            FROM token_budget
            WHERE run_id=? AND phase_name=?
            ORDER BY rowid DESC LIMIT 1
            """,
            ("r-usage", "CODEAUDIT"),
        ).fetchone()

    assert prompt_sha_row is not None
    assert prompt_sha_row[0]
    assert usage_row is not None
    assert int(usage_row[0]) > 0
