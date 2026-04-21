"""FORGE training runner using CEM for MetaRL."""

from __future__ import annotations

import random
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
    def __init__(self, passive_concentration: float, seed: int, n_episodes: int = 500_000) -> None:
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
                step_returns = self._run_episode_returns(self.cem.best())
                sharpe_value = self.sharpe(step_returns)
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
        env = self.env
        env.reset()

        meta_step_rewards: List[float] = []
        concentration = env.passive_concentration

        for _ in range(env.episode_length):
            p0 = env._price_history[0]
            p1 = env._price_history[1]
            p4 = env._price_history[4]

            trend_action = 1 if p0 > p4 else 2
            if p0 > p1 * 1.02:
                mean_action = 2
            elif p0 < p1 * 0.98:
                mean_action = 1
            else:
                mean_action = 0
            macro_action = 1 if concentration < 0.30 else 0
            liquidity_action = self.liquidity_agent.act(None)

            meta_obs = np.array(
                [
                    env._price_history[0],
                    env._price_history[1],
                    env._price_history[2],
                    env._price_history[3],
                    env._price_history[4],
                    env._current_volatility,
                    concentration,
                    env.portfolio_values["meta_rl"],
                    env.cash["meta_rl"],
                    float(env.current_step),
                ],
                dtype=np.float32,
            )
            meta_action = self.cem.act(meta_obs, weights)

            env._pending_actions = {
                "passive_gsci": 1,
                "trend_follower": trend_action,
                "mean_reversion": mean_action,
                "liquidity_provider": liquidity_action,
                "macro_allocator": macro_action,
                "meta_rl": meta_action,
            }
            env._clear_rewards()
            env._apply_market_step()
            env._pending_actions.clear()
            meta_step_rewards.append(float(env.rewards.get("meta_rl", 0.0)))

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
