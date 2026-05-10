from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class StatTest(ABC):
    test_name: str
    requires_seeds: bool = True

    @abstractmethod
    def run(self, data: pd.DataFrame, seed: int, params: dict) -> dict:
        ...
