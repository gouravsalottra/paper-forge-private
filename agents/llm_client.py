from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"


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

    model = os.getenv(
        f"{agent_upper}_MODEL",
        os.getenv("DEFAULT_MODEL", "gpt-4o-mini"),
    )

    if provider == "github":
        client = OpenAI(
            base_url=GITHUB_MODELS_BASE_URL,
            api_key=os.getenv("GITHUB_TOKEN"),
        )
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
