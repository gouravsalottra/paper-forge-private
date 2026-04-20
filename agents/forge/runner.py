"""FORGE training runner using CEM for MetaRL."""

from __future__ import annotations

import random
from math import sqrt
from typing import Dict, List

import numpy as np

from agents.forge.agents import (
    LiquidityProvider,
    MacroAllocator,
    MeanReversion,
    MetaRL,
    PassiveGSCI,
    TrendFollower,
)
from agents.forge.cem import CEM
from agents.forge.env import CommodityFuturesEnv


class ForgeRunner:
    def __init__(self, passive_concentration: float, seed: int, n_episodes: int = 500) -> None:
        self.passive_concentration = float(passive_concentration)
        self.seed = int(seed)
        self.n_episodes = int(n_episodes)

        np.random.seed(self.seed)
        random.seed(self.seed)

        self.env = CommodityFuturesEnv(passive_concentration=self.passive_concentration)
        self.passive_agent = PassiveGSCI()
        self.trend_agent = TrendFollower()
        self.mean_agent = MeanReversion()
        self.liquidity_agent = LiquidityProvider()
        self.macro_agent = MacroAllocator()
        self.meta_rl = MetaRL()

        self.cem = CEM(obs_dim=10, n_elite=10, population=50, noise=0.1)
        self.rewards_history: List[float] = []

    def run(self) -> Dict[str, object]:
        for episode in range(1, self.n_episodes + 1):
            candidates = self.cem.ask()
            scores: List[float] = []

            for weights in candidates:
                total_reward = self._run_single_episode(weights)
                scores.append(float(total_reward))

            self.cem.tell(scores)
            self.rewards_history.append(float(np.max(scores)))

            if episode % 100 == 0:
                sharpe_value = self.sharpe(self.rewards_history)
                print(f"Episode {episode}, best Sharpe: {sharpe_value:.4f}")

        return self.results()

    @staticmethod
    def sharpe(step_returns: list) -> float:
        """Compute Sharpe from per-step returns within a single episode."""
        if len(step_returns) < 2:
            return 0.0
        arr = np.asarray(step_returns, dtype=np.float64)
        mean = arr.mean()
        std = arr.std()
        if std < 1e-8:
            return 0.0
        return float((mean / std) * np.sqrt(252))

    def results(self) -> dict:
        best_weights = self.cem.best()
        step_returns = self._run_episode_returns(best_weights)
        sharpe_val = self.sharpe(step_returns)
        return {
            'concentration': self.passive_concentration,
            'seed': self.seed,
            'mean_reward': float(np.mean(step_returns)) if step_returns else 0.0,
            'sharpe': sharpe_val,
            'n_episodes': self.n_episodes,
            'rewards_history': self.rewards_history,
        }

    def _run_episode_returns(self, weights) -> list:
        """Run one episode, return list of meta_rl per-step rewards."""
        self.env.reset()
        step_returns = []
        for agent in self.env.agent_iter():
            obs, reward, term, trunc, info = self.env.last()
            if term or trunc:
                self.env.step(None)
                continue
            if agent == 'meta_rl':
                step_returns.append(float(reward))
                action = self.cem.act(obs, weights)
            else:
                action = self._rule_policy(agent, obs)
            self.env.step(action)
        return step_returns

    def _run_single_episode(self, weights: np.ndarray) -> float:
        # Reset stateful policy so each candidate sees a fresh episode policy state.
        self.liquidity_agent = LiquidityProvider()
        self.env.reset()

        meta_step_rewards: List[float] = []

        while self.env.current_step < self.env.episode_length:
            agent = self.env.agent_selection
            obs = self.env.observe(agent)

            if agent == "passive_gsci":
                action = self.passive_agent.act(obs)
            elif agent == "trend_follower":
                action = self.trend_agent.act(obs)
            elif agent == "mean_reversion":
                action = self.mean_agent.act(obs)
            elif agent == "liquidity_provider":
                action = self.liquidity_agent.act(obs)
            elif agent == "macro_allocator":
                action = self.macro_agent.act(obs)
            elif agent == "meta_rl":
                action = self.cem.act(obs, weights)
            else:
                action = 0

            prev_step = self.env.current_step
            self.env.step(action)

            if self.env.current_step > prev_step:
                meta_step_rewards.append(float(self.env.rewards.get("meta_rl", 0.0)))

        episode_rewards_sum = float(np.sum(meta_step_rewards))
        step_count = len(meta_step_rewards)
        return float(episode_rewards_sum / max(step_count, 1))

    def _rule_policy(self, agent: str, obs) -> int:
        if agent == 'passive_gsci':
            return self.passive_agent.act(obs)
        elif agent == 'trend_follower':
            return self.trend_agent.act(obs)
        elif agent == 'mean_reversion':
            return self.mean_agent.act(obs)
        elif agent == 'liquidity_provider':
            return self.liquidity_agent.act(obs)
        elif agent == 'macro_allocator':
            return self.macro_agent.act(obs)
        return 0
