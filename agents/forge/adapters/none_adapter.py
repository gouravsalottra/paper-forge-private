from __future__ import annotations

from pathlib import Path

from .registry import register


@register
class NoneAdapter:
    adapter_type = "none"

    def run(self, params: dict, output_dir: Path, seeds: list[int]) -> dict:
        return {
            "adapter_type": self.adapter_type,
            "skipped": True,
            "episodes_run": 0,
            "seeds": seeds,
            "output_files": [],
            "summary": "No compute requested",
        }
