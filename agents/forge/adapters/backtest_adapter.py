from __future__ import annotations

from pathlib import Path

from .registry import register


@register
class BacktestAdapter:
    adapter_type = "backtest"

    def run(self, params: dict, output_dir: Path, seeds: list[int]) -> dict:
        raise NotImplementedError(
            "Backtester not yet implemented. Contributions welcome: agents/forge/adapters/backtest_adapter.py"
        )
