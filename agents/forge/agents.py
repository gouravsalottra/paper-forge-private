"""Rule-based and placeholder agent policies for the FORGE environment."""

from __future__ import annotations

import random

import numpy as np


class PassiveGSCI:
    def act(self, obs: np.ndarray) -> int:
        del obs
        return 1


class TrendFollower:
    def act(self, obs: np.ndarray) -> int:
        return 1 if obs[0] > obs[4] else 2


class MeanReversion:
    def act(self, obs: np.ndarray) -> int:
        if obs[0] > obs[1] * 1.02:
            return 2
        if obs[0] < obs[1] * 0.98:
            return 1
        return 0


class LiquidityProvider:
    def __init__(self) -> None:
        self._counter = 0

    def act(self, obs: np.ndarray) -> int:
        del obs
        action = 1 if self._counter % 2 == 0 else 2
        self._counter += 1
        return action


class MacroAllocator:
    def act(self, obs: np.ndarray) -> int:
        return 1 if obs[6] < 0.30 else 0


class MetaRL:
    def act(self, obs: np.ndarray) -> int:
        del obs
        return random.randint(0, 2)
