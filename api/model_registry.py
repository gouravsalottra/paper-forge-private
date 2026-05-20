from __future__ import annotations

import json
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

from fastapi import APIRouter

router = APIRouter()

_MODEL_OVERRIDE: ContextVar[str | None] = ContextVar("thrivarc_model_override", default=None)
_DEFAULT_FALLBACK_MODEL = "gpt-4o"
_NON_CHAT_HINTS = ("embedding", "whisper", "tts", "dall", "image", "moderation", "transcribe", "audio")
_CODE_HINTS = ("gpt-5", "gpt-4", "o1", "o3", "o4")
_REASONING_HINTS = ("o1", "o3", "o4", "reason")


def _raw_configured_models() -> list[Any]:
    raw_json = os.getenv("THRIVARC_MODEL_REGISTRY_JSON", "").strip()
    if raw_json:
        try:
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
    configured = [item.strip() for item in os.getenv("THRIVARC_ALLOWED_MODELS", "").split(",") if item.strip()]
    if configured:
        return configured
    return [_DEFAULT_FALLBACK_MODEL]


def _normalize_entry(entry: Any) -> dict[str, Any] | None:
    if isinstance(entry, str):
        name = entry.strip()
        return {"name": name} if name else None
    if isinstance(entry, dict):
        name = str(entry.get("name") or entry.get("deployment_name") or entry.get("model") or "").strip()
        if not name:
            return None
        normalized = dict(entry)
        normalized["name"] = name
        return normalized
    return None


def _is_chat_capable(name: str) -> bool:
    lowered = name.lower()
    return not any(token in lowered for token in _NON_CHAT_HINTS)


def _family(name: str) -> str:
    lowered = name.lower()
    if lowered.startswith("gpt-5"):
        return "GPT-5"
    if lowered.startswith("gpt-4"):
        return "GPT-4"
    if lowered.startswith("o1"):
        return "o1"
    if lowered.startswith("o3"):
        return "o3"
    if lowered.startswith("o4"):
        return "o4"
    return "Other"


def _capabilities(name: str) -> dict[str, bool]:
    lowered = name.lower()
    return {
        "chat": _is_chat_capable(name),
        "json_safe": lowered.startswith(("gpt-", "o1", "o3", "o4")),
        "long_context": lowered.startswith(("gpt-", "o1", "o3", "o4")),
        "reasoning": any(token in lowered for token in _REASONING_HINTS),
        "code_friendly": any(token in lowered for token in _CODE_HINTS),
    }


def model_catalog() -> list[dict[str, Any]]:
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in _raw_configured_models():
        entry = _normalize_entry(raw)
        if not entry:
            continue
        name = entry["name"]
        if name in seen or not _is_chat_capable(name):
            continue
        seen.add(name)
        caps = _capabilities(name)
        models.append(
            {
                "name": name,
                "label": str(entry.get("label") or name),
                "family": str(entry.get("family") or _family(name)),
                "provider": str(entry.get("provider") or "azure_openai"),
                "deployment_name": str(entry.get("deployment_name") or name),
                "capabilities": caps,
                "healthy": bool(entry.get("healthy", True)),
                "available": bool(entry.get("available", True)),
            }
        )
    return models or [
        {
            "name": _DEFAULT_FALLBACK_MODEL,
            "label": _DEFAULT_FALLBACK_MODEL,
            "family": _family(_DEFAULT_FALLBACK_MODEL),
            "provider": "azure_openai",
            "deployment_name": _DEFAULT_FALLBACK_MODEL,
            "capabilities": _capabilities(_DEFAULT_FALLBACK_MODEL),
            "healthy": True,
            "available": True,
        }
    ]


def allowed_chat_models() -> list[str]:
    return [item["name"] for item in model_catalog() if item["capabilities"]["chat"] and item["healthy"] and item["available"]]


def default_model() -> str:
    configured_default = str(os.getenv("THRIVARC_DEFAULT_MODEL", "")).strip()
    allowed = allowed_chat_models()
    if configured_default and configured_default in allowed:
        return configured_default
    return allowed[0] if allowed else _DEFAULT_FALLBACK_MODEL


def fallback_model() -> str:
    configured = str(os.getenv("THRIVARC_FALLBACK_MODEL", "")).strip()
    allowed = allowed_chat_models()
    if configured and configured in allowed:
        return configured
    if _DEFAULT_FALLBACK_MODEL in allowed:
        return _DEFAULT_FALLBACK_MODEL
    return allowed[0] if allowed else _DEFAULT_FALLBACK_MODEL


def active_model_name(explicit: str | None = None) -> str:
    requested = str(explicit or "").strip()
    allowed = allowed_chat_models()
    if requested and requested in allowed:
        return requested
    override = _MODEL_OVERRIDE.get()
    if override and override in allowed:
        return override
    return default_model()


@contextmanager
def model_override(model_name: str | None):
    selected = active_model_name(model_name)
    token = _MODEL_OVERRIDE.set(selected)
    try:
        yield selected
    finally:
        _MODEL_OVERRIDE.reset(token)


@router.get("/api/models")
def list_models() -> dict[str, Any]:
    models = model_catalog()
    warning = None
    if len(models) == 1 and models[0]["name"] == _DEFAULT_FALLBACK_MODEL and not os.getenv("THRIVARC_ALLOWED_MODELS"):
        warning = "Model registry is using the fallback deployment only. Configure THRIVARC_ALLOWED_MODELS or THRIVARC_MODEL_REGISTRY_JSON to expose more deployments."
    return {
        "models": models,
        "default_model": default_model(),
        "fallback_model": fallback_model(),
        "warning": warning,
    }
