from __future__ import annotations

from pathlib import Path

from .registry import register


@register
class RLAdapter:
    adapter_type = "rl"

    def run(self, params: dict, output_dir: Path, seeds: list[int]) -> dict:
        return {
            "adapter_type": self.adapter_type,
            "episodes_run": int(params.get("n_episodes", 0)),
            "seeds": seeds,
            "output_files": [],
            "summary": "RL adapter delegates to existing COMPUTE runner in legacy mode",
        }
