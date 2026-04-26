"""Cross-Entropy Method optimizer for MetaRL policy weights."""

from __future__ import annotations

import numpy as np


class CEM:
    def __init__(self, obs_dim: int = 10, n_elite: int = 10, population: int = 50, noise: float = 0.1) -> None:
        self.obs_dim = int(obs_dim)
        self.n_elite = int(n_elite)
        self.population = int(population)
        self.noise = float(noise)

        self.mean = np.zeros((self.obs_dim, 3), dtype=np.float64)
        self.std = np.ones((self.obs_dim, 3), dtype=np.float64)

        self._candidates: list[np.ndarray] = []
        self._elite_set: list[np.ndarray] = []

    def ask(self) -> list[np.ndarray]:
        samples = np.random.normal(
            loc=self.mean,
            scale=self.std,
            size=(self.population, self.obs_dim, 3),
        )
        self._candidates = [samples[i] for i in range(self.population)]
        return self._candidates

    def tell(self, scores: list[float]) -> None:
        if not self._candidates:
            raise ValueError("ask() must be called before tell().")
        if len(scores) != len(self._candidates):
            raise ValueError("scores length must match population size from ask().")

        score_array = np.asarray(scores, dtype=np.float64)
        elite_idx = np.argsort(score_array)[-self.n_elite :]

        elite_weights = np.stack([self._candidates[i] for i in elite_idx], axis=0)
        self._elite_set = [elite_weights[i] for i in range(elite_weights.shape[0])]

        self.mean = elite_weights.mean(axis=0)
        self.std = elite_weights.std(axis=0) + self.noise

    def best(self) -> np.ndarray:
        return self.mean.copy()

    @staticmethod
    def act(obs: np.ndarray, weights: np.ndarray) -> int:
        logits = obs @ weights
        return int(np.argmax(logits))
