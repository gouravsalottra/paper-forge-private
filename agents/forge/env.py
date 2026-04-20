"""PettingZoo AEC commodity futures market environment for Paper Forge."""

from __future__ import annotations

from functools import reduce
from typing import Dict, List

import numpy as np
from gymnasium.spaces import Box, Discrete
from pettingzoo import AECEnv


class CommodityFuturesEnv(AECEnv):
    """Six-agent commodity futures market simulator using the AEC pattern."""

    metadata = {"name": "commodity_futures_aec_v0", "render_modes": ["human"]}

    def __init__(self, passive_concentration: float = 0.30, episode_length: int = 252) -> None:
        super().__init__()

        if passive_concentration not in (0.10, 0.30, 0.60):
            raise ValueError("passive_concentration must be one of: 0.10, 0.30, 0.60")

        self.possible_agents: List[str] = [
            "passive_gsci",
            "trend_follower",
            "mean_reversion",
            "liquidity_provider",
            "macro_allocator",
            "meta_rl",
        ]
        self.passive_concentration = float(passive_concentration)
        self.episode_length = int(episode_length)

        self._observation_spaces = {
            agent: Box(low=-np.inf, high=np.inf, shape=(10,), dtype=np.float32)
            for agent in self.possible_agents
        }
        self._action_spaces = {
            agent: Discrete(3)  # 0=hold, 1=long, 2=short
            for agent in self.possible_agents
        }

        self._agent_cycle = self._build_agent_cycle(self.possible_agents)
        self._pending_actions: Dict[str, int] = {}

        self.reset()

    def observation_space(self, agent: str) -> Box:
        return self._observation_spaces[agent]

    def action_space(self, agent: str) -> Discrete:
        return self._action_spaces[agent]

    def reset(self, seed: int | None = None, options: dict | None = None) -> None:
        if seed is not None:
            np.random.seed(seed)

        del options

        self.agents = self.possible_agents[:]
        self.rewards = {agent: 0.0 for agent in self.agents}
        self._cumulative_rewards = {agent: 0.0 for agent in self.agents}
        self.terminations = {agent: False for agent in self.agents}
        self.truncations = {agent: False for agent in self.agents}
        self.infos = {agent: {} for agent in self.agents}

        self.current_step = 0
        self.price = 100.0
        self._returns_window: List[float] = []
        self._price_history = [self.price] * 5

        self.positions = {agent: 0.0 for agent in self.agents}
        self.cash = {agent: 10_000.0 for agent in self.agents}
        self.portfolio_values = {
            agent: self.cash[agent] + self.positions[agent] * self.price
            for agent in self.agents
        }

        self._pending_actions.clear()
        self.agent_selection = self.agents[0]

    def observe(self, agent: str) -> np.ndarray:
        vol = self._rolling_volatility()
        obs = np.array(
            [
                self._price_history[0],
                self._price_history[1],
                self._price_history[2],
                self._price_history[3],
                self._price_history[4],
                vol,
                self.passive_concentration,
                self.portfolio_values[agent],
                self.cash[agent],
                float(self.current_step),
            ],
            dtype=np.float32,
        )
        return obs

    def step(self, action: int) -> None:
        if not self.agents:
            return

        agent = self.agent_selection
        if self.terminations[agent] or self.truncations[agent]:
            self._was_dead_step(action)
            return

        action_int = int(action)
        if agent == "passive_gsci":
            action_int = 1

        self._pending_actions[agent] = action_int

        if len(self._pending_actions) == len(self.agents):
            self._clear_rewards()
            self._apply_market_step()
            self._pending_actions.clear()

            if self.current_step >= self.episode_length:
                for name in self.agents:
                    self.truncations[name] = True

        self.agent_selection = self._agent_cycle[self.agent_selection]

    def render(self) -> None:
        print(f"step={self.current_step} price={self.price:.4f}")
        for agent in self.possible_agents:
            value = self.portfolio_values.get(agent, 0.0)
            print(f"{agent}: portfolio_value={value:.2f}")

    def close(self) -> None:
        return

    def _apply_market_step(self) -> None:
        prev_values = self.portfolio_values.copy()
        old_price = self.price

        net_order_flow = float(sum(self._action_to_flow(a) for a in self._pending_actions.values()))
        noise = np.random.normal(0.0, 0.01)
        self.price = self.price * (1.0 + 0.0005 * net_order_flow + noise)

        step_return = (self.price / old_price) - 1.0
        self._returns_window.append(step_return)
        if len(self._returns_window) > 20:
            self._returns_window = self._returns_window[-20:]

        self._price_history.append(self.price)
        self._price_history = self._price_history[-5:]

        for agent, action in self._pending_actions.items():
            flow = self._action_to_flow(action)
            self.positions[agent] += flow

        for agent in self.agents:
            old_value = prev_values[agent]
            new_value = self.cash[agent] + self.positions[agent] * self.price
            self.portfolio_values[agent] = new_value
            pct = (new_value - old_value) / (old_value + 1e-8)
            rf_daily = 0.05 / 252
            self.rewards[agent] = float(pct - rf_daily)
            self._cumulative_rewards[agent] = self.rewards[agent]

        self.current_step += 1

    @staticmethod
    def _action_to_flow(action: int) -> int:
        if action == 1:
            return 1
        if action == 2:
            return -1
        return 0

    def _rolling_volatility(self) -> float:
        if len(self._returns_window) < 2:
            return 0.0
        return float(np.std(self._returns_window, ddof=1))

    @staticmethod
    def _build_agent_cycle(agents: List[str]) -> Dict[str, str]:
        """Build next-agent mapping using functools.reduce."""

        def reducer(mapping: Dict[str, str], item: tuple[int, str]) -> Dict[str, str]:
            idx, agent = item
            mapping[agent] = agents[(idx + 1) % len(agents)]
            return mapping

        return reduce(reducer, enumerate(agents), {})
