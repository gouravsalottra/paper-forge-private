from __future__ import annotations

from pathlib import Path

from .registry import register


@register
class RLAdapter:
    adapter_type = "rl"

    def run(self, params: dict, output_dir: Path, seeds: list[int]) -> dict:
        raise NotImplementedError(
            "The RL adapter requires a custom compute environment. "
            "See examples/gsci_momentum/ for a reference implementation "
            "using PettingZoo + CEM optimizer on commodity futures. "
            "To use RL for your research: copy examples/gsci_momentum/compute/ "
            "into your project, adapt env.py for your domain, and point "
            "rl_adapter.py to your environment class."
        )
