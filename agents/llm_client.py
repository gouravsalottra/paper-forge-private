from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
import json
from pathlib import Path

from dotenv import load_dotenv
from agents.aria.exceptions import TokenBudgetExceededError

load_dotenv()

GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
logger = logging.getLogger(__name__)


def _load_model_config() -> dict:
    cfg_path = Path("config/model_config.json")
    if not cfg_path.exists():
        return {}
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get_client(agent_name: str):
    """
    Returns (client, model_name) for the given agent.
    Reads from env vars: {AGENT}_LLM_PROVIDER, {AGENT}_MODEL
    Falls back to DEFAULT_LLM_PROVIDER, DEFAULT_MODEL
    Final fallback: GitHub Models + gpt-4o-mini
    """
    from openai import OpenAI

    agent_upper = agent_name.upper()

    provider = os.getenv(
        f"{agent_upper}_LLM_PROVIDER",
        os.getenv("DEFAULT_LLM_PROVIDER", "github"),
    )

    cfg = _load_model_config()
    model = os.getenv(
        f"{agent_upper}_MODEL",
        os.getenv("DEFAULT_MODEL", cfg.get("primary_model_alias", "gpt-4o-mini")),
    )

    if provider == "github":
        client = OpenAI(
            base_url=GITHUB_MODELS_BASE_URL,
            api_key=os.getenv("GITHUB_TOKEN"),
        )
        if cfg and model == cfg.get("primary_model_alias"):
            configured = cfg.get("primary_model")
            if configured and configured != model:
                logger.warning(
                    "Model %s may be deprecated. Falling back to %s. Update config/model_config.json.",
                    configured,
                    cfg.get("fallback_model", model),
                )
                model = cfg.get("fallback_model", model)
        return client, model

    if provider == "openai":
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        return client, model

    if provider == "azure":
        from openai import AzureOpenAI

        client = AzureOpenAI(
            api_key=os.getenv("AZURE_OPENAI_KEY"),
            azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
            api_version="2025-01-01-preview",
        )
        return client, model

    # Final fallback
    client = OpenAI(
        base_url=GITHUB_MODELS_BASE_URL,
        api_key=os.getenv("GITHUB_TOKEN"),
    )
    return client, model


def track_usage(
    response,
    run_id: str,
    phase_name: str,
    agent_name: str,
    model: str,
    db_path: str = "pipeline.db",
) -> dict:
    """Extract token usage from OpenAI response and record to DB."""
    usage = getattr(response, "usage", None)
    if usage is None:
        return {}

    token_pricing = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-5.4": {"input": 15.00, "output": 60.00},
        "default": {"input": 5.00, "output": 15.00},
    }
    pricing = token_pricing.get(model, token_pricing["default"])
    cost = (
        (usage.prompt_tokens / 1_000_000) * pricing["input"]
        + (usage.completion_tokens / 1_000_000) * pricing["output"]
    )
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_budget (
                budget_id TEXT PRIMARY KEY,
                run_id TEXT NOT NULL,
                phase_name TEXT NOT NULL,
                agent_name TEXT NOT NULL,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                total_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost_usd REAL,
                model TEXT,
                recorded_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_limits (
                run_id TEXT PRIMARY KEY,
                soft_limit_usd REAL NOT NULL DEFAULT 10.0,
                hard_limit_usd REAL NOT NULL DEFAULT 25.0,
                total_spent_usd REAL NOT NULL DEFAULT 0.0,
                last_updated TEXT
            )
            """
        )

        conn.execute(
            """
            INSERT INTO token_budget
            (budget_id, run_id, phase_name, agent_name, prompt_tokens, completion_tokens,
             total_tokens, estimated_cost_usd, model, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid.uuid4().hex,
                run_id,
                phase_name,
                agent_name,
                int(usage.prompt_tokens),
                int(usage.completion_tokens),
                int(usage.total_tokens),
                float(cost),
                model,
                now,
            ),
        )

        row = conn.execute(
            "SELECT soft_limit_usd, hard_limit_usd, total_spent_usd FROM token_limits WHERE run_id=?",
            (run_id,),
        ).fetchone()
        if row is None:
            soft_limit = float(os.getenv("PAPERFORGE_SOFT_LIMIT_USD", "10.0"))
            hard_limit = float(os.getenv("PAPERFORGE_HARD_LIMIT_USD", "25.0"))
            total_spent = 0.0
            conn.execute(
                """
                INSERT INTO token_limits (run_id, soft_limit_usd, hard_limit_usd, total_spent_usd, last_updated)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, soft_limit, hard_limit, total_spent, now),
            )
        else:
            soft_limit, hard_limit, total_spent = float(row[0]), float(row[1]), float(row[2])

        total_spent += float(cost)
        conn.execute(
            "UPDATE token_limits SET total_spent_usd=?, last_updated=? WHERE run_id=?",
            (total_spent, now, run_id),
        )
        conn.commit()

    if total_spent >= hard_limit:
        raise TokenBudgetExceededError(spent=total_spent, limit=hard_limit)

    if total_spent >= soft_limit:
        logger.warning(
            "Token budget soft limit exceeded: run_id=%s spent=%.4f limit=%.4f",
            run_id,
            total_spent,
            soft_limit,
        )

    return {
        "prompt_tokens": usage.prompt_tokens,
        "completion_tokens": usage.completion_tokens,
        "total_tokens": usage.total_tokens,
        "estimated_cost_usd": float(cost),
    }
