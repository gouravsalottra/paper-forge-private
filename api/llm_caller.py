# api/llm_caller.py
# Canonical LLM caller for all Thrivarc agents.
# All agents call call_agent_llm() -- never call the LLM directly.
# Handles: retries, JSON extraction, fallback logging, engine enforcement.

import inspect
import json
import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Canonical deployment name. Keep model selection centralized here and in api/guide.py.
AZURE_DEPLOYMENT = "gpt-4o"
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2
REQUEST_TIMEOUT_SECONDS = 45


def _extract_json(text: str) -> Optional[dict]:
    """
    Extract JSON from LLM response.
    Handles: raw JSON, JSON wrapped in ```json blocks, JSON with preamble.
    """
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


def _sanitize_engine_fields(obj):
    """
    Recursively enforce gpt-4o on any engine field.
    Mirrors the sanitizer already in api/guide.py.
    """
    if isinstance(obj, dict):
        if "engine" in obj:
            obj["engine"] = AZURE_DEPLOYMENT
        return {k: _sanitize_engine_fields(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_engine_fields(item) for item in obj]
    return obj


async def call_agent_llm(
    agent_name: str,
    prompt: str,
    client,
    fallback_fn=None,
    fallback_args=None,
    max_tokens: int = 4000,
) -> dict:
    """
    Call the LLM for a specific agent.

    Args:
        agent_name: Name of the calling agent (for logging)
        prompt: Fully formatted prompt string
        client: Azure OpenAI client instance
        fallback_fn: Function to call if all LLM attempts fail
        fallback_args: Args for fallback_fn
        max_tokens: Max tokens for response

    Returns:
        Parsed JSON dict from LLM, or fallback result

    Raises:
        RuntimeError if LLM fails and no fallback provided
    """
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response_or_coro = client.chat.completions.create(
                model=AZURE_DEPLOYMENT,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=0.1,
                response_format={"type": "json_object"},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response = await response_or_coro if inspect.isawaitable(response_or_coro) else response_or_coro

            raw = response.choices[0].message.content or ""
            parsed = _extract_json(raw)

            if parsed is None:
                logger.warning(
                    "%s attempt %s: LLM returned non-JSON response. Retrying.",
                    agent_name,
                    attempt,
                )
                last_error = "non-JSON response"
                time.sleep(RETRY_DELAY_SECONDS)
                continue

            parsed = _sanitize_engine_fields(parsed)

            logger.info("%s: LLM call succeeded on attempt %s", agent_name, attempt)
            return parsed

        except Exception as e:
            logger.warning("%s attempt %s: LLM error: %s", agent_name, attempt, e)
            last_error = str(e)
            time.sleep(RETRY_DELAY_SECONDS)

    logger.error(
        "%s: all %s LLM attempts failed. Last error: %s",
        agent_name,
        MAX_RETRIES,
        last_error,
    )

    if fallback_fn is not None:
        logger.warning("%s: using fallback function", agent_name)
        return fallback_fn(**(fallback_args or {}))

    raise RuntimeError(f"{agent_name} LLM call failed after {MAX_RETRIES} attempts: {last_error}")
