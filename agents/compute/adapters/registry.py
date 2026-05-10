from __future__ import annotations

from .base import ComputeAdapter

ADAPTER_REGISTRY: dict[str, type[ComputeAdapter]] = {}


def register(cls):
    ADAPTER_REGISTRY[cls.adapter_type] = cls
    return cls


def get_adapter(adapter_type: str) -> ComputeAdapter:
    _bootstrap_registry()
    if adapter_type not in ADAPTER_REGISTRY:
        raise ValueError(
            f"Unknown compute adapter: '{adapter_type}'. "
            f"Available: {sorted(ADAPTER_REGISTRY.keys())}"
        )
    return ADAPTER_REGISTRY[adapter_type]()


def _bootstrap_registry() -> None:
    if ADAPTER_REGISTRY:
        return
    from . import rl_adapter, none_adapter, backtest_adapter, event_study_adapter  # noqa: F401


_bootstrap_registry()
