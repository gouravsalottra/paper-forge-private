from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class ComputeAdapter(ABC):
    adapter_type: str

    @abstractmethod
    def run(self, params: dict, output_dir: Path, seeds: list[int]) -> dict:
        ...
