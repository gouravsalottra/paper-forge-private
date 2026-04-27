"""
agents/forge/gpu_run.py
=======================
GPU-vectorized FORGE runner.

Runs all 36 scenarios simultaneously as batched tensor operations.
Exact match to runner.py: same CEM (population=50, n_elite=10, noise=0.1),
same linear policy (obs @ weights, shape 10x3), same reward formula,
same output schema.

Usage:
    python agents/forge/gpu_run.py --n-episodes 500000
    python agents/forge/gpu_run.py --n-episodes 500000 --output outputs/sim_results.json

Architecture:
    - 36 scenarios × 50 CEM candidates = 1800 parallel env instances per step
    - All state tensors on GPU: (n_scenarios, population, ...)
    - One GPU kernel per episode step across all 1800 instances
    - CEM update vectorized across all 36 scenarios simultaneously
    - Checkpoints every 50k episodes to output path
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F


# ── constants matching runner.py exactly ──────────────────────────────────────
OBS_DIM = 10
ACTION_DIM = 3
POPULATION = 50        # CEM population — matches cem.py
N_ELITE = 10           # CEM elite count — matches cem.py
CEM_NOISE = 0.1        # CEM noise — matches cem.py
EPISODE_LENGTH = 252   # matches runner.py self.episode_length
N_AGENTS = 6           # passive_gsci, trend_follower, mean_reversion,
                       # liquidity_provider, macro_rlocator, meta_rl
META_IDX = 5           # index of meta_rl agent — matches runner.py

# Scenario definitions — matches full_run.py exactly
CONCENTRATIONS = [0.10, 0.30, 0.60]
SEEDS = [1337, 42, 9999, 123, 7, 99, 2024, 314, 17, 888, 456, 1001]
# 3 × 12 = 36 scenarios


def build_scenarios() -> list[tuple[float, int]]:
    return [(c, s) for c in CONCENTRATIONS for s in SEEDS]


# ── vectorized environment step ───────────────────────────────────────────────

class BatchedForgeEnv:
    """
    Batched version of CommodityFuturesEnv.
    State tensors shape: (N,) where N = n_scenarios × population.
    Each instance has its own concentration, price, positions, cash.
    Reward formula: exact match to env.py _apply_market_step.
    """

    def __init__(
        self,
        concentrations: torch.Tensor,  # shape (N,)
        device: torch.device,
    ) -> None:
        self.device = device
        self.N = int(concentrations.shape[0])
        self.concentrations = concentrations.to(device)  # (N,)

        # Precompute concentration-dependent constants (same as runner.py)
        c = self.concentrations
        self.flow_impact = 0.0003 * (1.0 + 5.0 * c ** 2)        # (N,)
        self.concentration_drag = 0.0002 * c ** 2                 # (N,)
        self.noise_std = 0.006 * (1.0 + 6.0 * c ** 2)            # (N,)
        self.crowding_cost_factor = 0.00005 * c ** 2              # (N,)
        self.volatility_penalty_factor = 0.15 * c ** 2            # (N,)
        self.rf_daily = torch.tensor(0.05 / 252, device=device)
        self.max_position = torch.tensor(50.0, device=device)

        self.reset()

    def reset(self) -> None:
        N, dev = self.N, self.device

        self.price = torch.full((N,), 100.0, dtype=torch.float32, device=dev)
        # price_history: last 5 prices, all start at 100
        self.price_history = torch.full((N, 5), 100.0, dtype=torch.float32, device=dev)
        self.current_vol = torch.zeros(N, dtype=torch.float32, device=dev)

        # positions and cash: shape (N, n_agents)
        self.positions = torch.zeros((N, N_AGENTS), dtype=torch.float32, device=dev)
        self.cash = torch.full((N, N_AGENTS), 10_000.0, dtype=torch.float32, device=dev)
        self.portfolio_values = self.cash.clone()

        # rolling returns buffer (window=20) for volatility, matches env.py
        self.returns_buffer = torch.zeros((N, 20), dtype=torch.float32, device=dev)
        self.step_count = 0

    def step(self, actions: torch.Tensor) -> torch.Tensor:
        """
        actions: (N, n_agents) int tensor {0=hold, 1=long, 2=short}
        Returns meta_rl rewards: (N,)

        Exact reward formula from env.py _apply_market_step:
            flow = action_to_flow(action)
            net_order_flow = sum(flows)
            price *= (1 + flow_impact * net_order_flow + noise - drag)
            step_return = (price / old_price) - 1
            volatility = rolling_std(returns, window=20)
            pct = (new_value - old_value) / max(|old_value|, 10000)
            reward = pct - rf_daily - crowding_cost - volatility_penalty
        """
        # ── action to flow: 1→+1, 2→-1, 0→0 (matches env.py _action_to_flow)
        flows = torch.where(actions == 1, 1.0,
                torch.where(actions == 2, -1.0, 0.0))  # (N, n_agents)

        # passive_gsci always goes long (action=1 → flow=+1)
        flows[:, 0] = 1.0

        net_order_flow = flows.sum(dim=1)  # (N,)

        # ── price update (exact match to env.py)
        old_price = self.price.clone()
        noise = torch.randn(self.N, device=self.device) * self.noise_std
        self.price = self.price * (
            1.0 + self.flow_impact * net_order_flow + noise - self.concentration_drag
        )
        self.price = torch.clamp(self.price, min=1e-6)

        # ── rolling volatility (window=20, matches env.py)
        step_return = (self.price / old_price) - 1.0
        buf_idx = self.step_count % 20
        self.returns_buffer[:, buf_idx] = step_return
        n_obs = min(self.step_count + 1, 20)
        if n_obs < 2:
            self.current_vol = torch.zeros(self.N, device=self.device)
        else:
            self.current_vol = self.returns_buffer[:, :n_obs].std(dim=1, unbiased=True)

        # ── price history (last 5)
        self.price_history = torch.cat(
            [self.price_history[:, 1:], self.price.unsqueeze(1)], dim=1
        )

        # ── position update with clamping
        old_values = self.portfolio_values.clone()
        next_positions = self.positions + flows
        next_positions = torch.clamp(next_positions, -self.max_position, self.max_position)
        executed_flow = next_positions - self.positions
        self.positions = next_positions
        self.cash = self.cash - executed_flow * self.price.unsqueeze(1)

        # ── portfolio values and rewards
        self.portfolio_values = self.cash + self.positions * self.price.unsqueeze(1)

        denom = torch.maximum(old_values.abs(), torch.full_like(old_values, 10_000.0))
        pct = (self.portfolio_values - old_values) / denom

        crowding_cost = (
            self.crowding_cost_factor.unsqueeze(1)
            * self.positions.abs()
            / self.max_position
        )
        volatility_penalty = (
            self.volatility_penalty_factor.unsqueeze(1)
            * self.current_vol.unsqueeze(1)
        )
        rewards = pct - self.rf_daily - crowding_cost - volatility_penalty  # (N, n_agents)

        self.step_count += 1
        return rewards[:, META_IDX]  # return meta_rl rewards only

    def observe(self) -> torch.Tensor:
        """
        Returns obs for meta_rl agent: (N, obs_dim=10)
        Matches env.py observe():
            [price_hist×5, current_vol, concentration, portfolio_value, cash, step]
        """
        obs = torch.stack([
            self.price_history[:, 0],
            self.price_history[:, 1],
            self.price_history[:, 2],
            self.price_history[:, 3],
            self.price_history[:, 4],
            self.current_vol,
            self.concentrations,
            self.portfolio_values[:, META_IDX],
            self.cash[:, META_IDX],
            torch.full((self.N,), float(self.step_count), device=self.device),
        ], dim=1)  # (N, 10)
        return obs


# ── rule-based agents (exact match to runner.py _simulate_batch) ──────────────

def get_rule_actions(
    price_history: torch.Tensor,  # (N, 5)
    step: int,
    N: int,
    device: torch.device,
) -> torch.Tensor:
    """
    Returns actions for 5 rule-based agents: (N, 5)
    Columns: [passive_gsci, trend_follower, mean_reversion,
              liquidity_provider, macro_allocator]

    Exact match to runner.py _simulate_batch training_mode=False:
    - passive_gsci:     always 1 (long)
    - trend_follower:   1 if price_hist[0] > price_hist[4] else 2
    - mean_reversion:   2 if price > 1.02*prev, 1 if price < 0.98*prev, else 0
    - liquidity_provider: alternates 1/2 by step parity
    - macro_allocator:  0 (hold) — matches runner.py macro_action init
    """
    h0 = price_history[:, 0]  # most recent (after shift)
    h1 = price_history[:, 1]
    h4 = price_history[:, 4]  # oldest

    passive = torch.ones(N, dtype=torch.long, device=device)

    # trend: 1 if recent > old else 2
    trend = torch.where(h0 > h4,
                        torch.ones(N, dtype=torch.long, device=device),
                        torch.full((N,), 2, dtype=torch.long, device=device))

    # mean reversion
    mean_rev = torch.zeros(N, dtype=torch.long, device=device)
    mean_rev = torch.where(h0 > h1 * 1.02,
                           torch.full((N,), 2, dtype=torch.long, device=device),
                           mean_rev)
    mean_rev = torch.where(h0 < h1 * 0.98,
                           torch.ones(N, dtype=torch.long, device=device),
                           mean_rev)

    # liquidity: alternates each step
    liq_val = 1 if step % 2 == 0 else 2
    liquidity = torch.full((N,), liq_val, dtype=torch.long, device=device)

    # macro: hold (0) — matches runner.py
    macro = torch.zeros(N, dtype=torch.long, device=device)

    return torch.stack([passive, trend, mean_rev, liquidity, macro], dim=1)  # (N, 5)


# ── vectorized CEM across all scenarios ──────────────────────────────────────

class BatchedCEM:
    """
    CEM state for all n_scenarios simultaneously.
    Exact match to cem.py: population=50, n_elite=10, noise=0.1
    Linear policy: obs @ weights, weights shape (obs_dim=10, action_dim=3)
    """

    def __init__(self, n_scenarios: int, device: torch.device) -> None:
        self.n_scenarios = n_scenarios
        self.device = device
        self.n_params = OBS_DIM * ACTION_DIM  # 30 params per policy

        # CEM distribution: mean and std per scenario
        # shape: (n_scenarios, obs_dim, action_dim)
        self.mean = torch.zeros(
            (n_scenarios, OBS_DIM, ACTION_DIM), dtype=torch.float32, device=device
        )
        self.std = torch.ones(
            (n_scenarios, OBS_DIM, ACTION_DIM), dtype=torch.float32, device=device
        )

    def ask(self) -> torch.Tensor:
        """
        Sample population candidates for all scenarios.
        Returns: (n_scenarios, population, obs_dim, action_dim)
        """
        eps = torch.randn(
            (self.n_scenarios, POPULATION, OBS_DIM, ACTION_DIM),
            device=self.device
        )
        # broadcast mean/std: (n_scenarios, 1, obs_dim, action_dim)
        candidates = self.mean.unsqueeze(1) + self.std.unsqueeze(1) * eps
        return candidates

    def tell(self, scores: torch.Tensor, candidates: torch.Tensor) -> None:
        """
        scores: (n_scenarios, population) — episode mean rewards
        candidates: (n_scenarios, population, obs_dim, action_dim)
        Updates mean and std using top n_elite candidates per scenario.
        Exact match to cem.py tell(): elite mean + std + noise.
        """
        # argsort descending per scenario
        elite_idx = scores.argsort(dim=1, descending=True)[:, :N_ELITE]
        # (n_scenarios, n_elite, obs_dim, action_dim)
        elite_weights = candidates[
            torch.arange(self.n_scenarios, device=self.device).unsqueeze(1),
            elite_idx
        ]
        self.mean = elite_weights.mean(dim=1)
        self.std = elite_weights.std(dim=1) + CEM_NOISE

    def best(self) -> torch.Tensor:
        """Returns current best weights: (n_scenarios, obs_dim, action_dim)"""
        return self.mean.clone()


# ── episode runner ────────────────────────────────────────────────────────────

def run_episode_batch(
    env: BatchedForgeEnv,
    weights: torch.Tensor,   # (N, obs_dim, action_dim) where N = n_scenarios × population
    rule_actions_cache: dict,
    training_mode: bool = True,
) -> torch.Tensor:
    """
    Run one full episode (252 steps) for N parallel instances.
    Returns: mean meta_rl reward per instance, shape (N,)

    weights: linear policy weights, applied as obs @ weights → logits → argmax
    """
    env.reset()
    accumulated = torch.zeros(env.N, device=env.device)

    for step in range(EPISODE_LENGTH):
        obs = env.observe()  # (N, 10)

        # meta_rl action: obs @ weights → (N, action_dim) → argmax
        logits = torch.bmm(obs.unsqueeze(1), weights).squeeze(1)  # (N, action_dim)
        meta_action = logits.argmax(dim=1)  # (N,)

        # rule-based agents (same for all instances at same step)
        rule_acts = get_rule_actions(
            env.price_history, step, env.N, env.device
        )  # (N, 5)

        # combine: [passive, trend, mean_rev, liquidity, macro, meta_rl]
        all_actions = torch.cat([rule_acts, meta_action.unsqueeze(1)], dim=1)  # (N, 6)

        rewards = env.step(all_actions)  # (N,)
        accumulated += rewards

    return accumulated / EPISODE_LENGTH


# ── main simulation loop ──────────────────────────────────────────────────────

def run_all_gpu(
    n_episodes: int = 500_000,
    output_path: str = "outputs/sim_results.json",
    checkpoint_every: int = 50_000,
) -> list[dict]:
    """
    Run all 36 scenarios for n_episodes each using GPU batching.

    Strategy:
    - All 36 scenarios × 50 CEM candidates = 1800 parallel env instances
    - Each iteration = one episode across all 1800 instances
    - CEM update every episode using all 50 candidate scores per scenario
    - Progress printed every 10k episodes
    - Checkpoint written every 50k episodes
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if device.type == "cuda":
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1e9:.1f}GB")

    scenarios = build_scenarios()
    n_scenarios = len(scenarios)
    print(f"Scenarios: {n_scenarios} ({len(CONCENTRATIONS)} concentrations × {len(SEEDS)} seeds)")
    print(f"Batch size: {n_scenarios * POPULATION} env instances per episode step")
    print(f"Target: {n_episodes:,} episodes per scenario")

    # Build concentration tensor: repeat each scenario's concentration POPULATION times
    # Shape: (n_scenarios × population,) = (1800,)
    conc_per_scenario = torch.tensor(
        [c for c, s in scenarios], dtype=torch.float32
    )  # (36,)
    conc_expanded = conc_per_scenario.repeat_interleave(POPULATION)  # (1800,)

    N_total = n_scenarios * POPULATION  # 1800

    # Initialize batched env and CEM
    env = BatchedForgeEnv(concentrations=conc_expanded, device=device)
    cem = BatchedCEM(n_scenarios=n_scenarios, device=device)
    for i, (c, s) in enumerate(scenarios):
        gen = torch.Generator()
        gen.manual_seed(s)
        cem.mean[i] = torch.randn(OBS_DIM, ACTION_DIM, generator=gen) * 0.1

    # Per-scenario tracking
    rewards_history = [[] for _ in range(n_scenarios)]
    episodes_done = 0

    # For Sharpe computation (matches runner.py sharpe())
    def compute_sharpe(returns_list: list[float]) -> float:
        if len(returns_list) < 2:
            return 0.0
        arr = torch.tensor(returns_list, dtype=torch.float32)
        mean = arr.mean()
        std = arr.std(unbiased=False)
        if float(std.item()) < 1e-8:
            return 0.0
        return float((mean / std * (252.0 ** 0.5)).item())

    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    t_start = time.time()
    t_last_print = t_start

    print(f"\nStarting simulation...")

    try:
        for episode in range(1, n_episodes + 1):
            # Sample CEM candidates for all scenarios
            # candidates: (n_scenarios, population, obs_dim, action_dim)
            candidates = cem.ask()

            # Expand candidates to match env batch:
            # Each scenario has POPULATION candidates, env has n_scenarios×POPULATION instances
            # weights for env: (N_total, obs_dim, action_dim)
            weights = candidates.view(N_total, OBS_DIM, ACTION_DIM)

            # Run one episode across all 1800 instances
            ep_rewards = run_episode_batch(env, weights, {})  # (N_total,)

            # Reshape to (n_scenarios, population) for CEM update
            scores = ep_rewards.view(n_scenarios, POPULATION)

            # CEM update
            cem.tell(scores, candidates)

            # Track rewards history per scenario (use max score per episode)
            max_scores = scores.max(dim=1).values  # (n_scenarios,)
            for i in range(n_scenarios):
                rewards_history[i].append(float(max_scores[i].item()))

            episodes_done = episode

            # Progress print every 10k episodes
            if episode % 10_000 == 0 or episode == n_episodes:
                elapsed = time.time() - t_start
                eps_per_sec = episode / elapsed
                remaining = (n_episodes - episode) / eps_per_sec if eps_per_sec > 0 else 0
                print(
                    f"[{episode:>7,}/{n_episodes:,}] "
                    f"elapsed={elapsed/60:.1f}min "
                    f"ETA={remaining/60:.1f}min "
                    f"eps/sec={eps_per_sec:.0f}",
                    flush=True,
                )

            # Checkpoint every 50k episodes
            if episode % checkpoint_every == 0:
                partial = _build_results(
                    scenarios, rewards_history, episode, cem, env, device
                )
                output_path_obj.write_text(json.dumps(partial, indent=2), encoding="utf-8")
                print(f"  Checkpoint saved: {output_path_obj} ({len(partial)} scenarios)")

    except KeyboardInterrupt:
        print(f"\nInterrupted at episode {episodes_done}. Saving partial results...")

    # Final results
    results = _build_results(scenarios, rewards_history, episodes_done, cem, env, device)

    # Compute Bonferroni p-value
    from scipy import stats as scipy_stats
    low_sharpes = [r["sharpe"] for r in results if round(r["concentration"], 2) == 0.10]
    high_sharpes = [r["sharpe"] for r in results if round(r["concentration"], 2) == 0.60]
    if len(low_sharpes) > 1 and len(high_sharpes) > 1:
        _, p = scipy_stats.ttest_ind(high_sharpes, low_sharpes, equal_var=False)
        p = float(p) if np.isfinite(p) else 1.0
    else:
        p = 1.0
    corrected_p = min(p * 6.0, 1.0)
    passes_bonferroni = corrected_p < 0.008333

    for r in results:
        r["primary_p_value"] = corrected_p
        r["passes_bonferroni"] = passes_bonferroni

    output_path_obj.write_text(json.dumps(results, indent=2), encoding="utf-8")

    # Summary
    total_elapsed = time.time() - t_start
    print(f"\n=== COMPLETE ===")
    print(f"Total time: {total_elapsed/60:.1f} min")
    print(f"Scenarios: {len(results)}")
    print(f"\nSummary: concentration vs mean Sharpe")
    for c in CONCENTRATIONS:
        sharpes = [r["sharpe"] for r in results if round(r["concentration"], 2) == c]
        if sharpes:
            print(f"  c={c:.2f}: mean_sharpe={sum(sharpes)/len(sharpes):.4f}")
    print(f"\nprimary_p_value(corrected): {corrected_p:.6f}")
    print(f"passes_bonferroni(p < 0.008333): {passes_bonferroni}")
    print(f"Saved: {output_path_obj}")

    return results


def _build_results(
    scenarios: list[tuple[float, int]],
    rewards_history: list[list[float]],
    n_episodes: int,
    cem: BatchedCEM,
    env: BatchedForgeEnv,
    device: torch.device,
) -> list[dict]:
    """
    Build sim_results.json schema from current state.
    Matches runner.py results() output exactly:
    {concentration, seed, sharpe, mean_reward, n_episodes, ...}
    """
    best_weights = cem.best()  # (n_scenarios, obs_dim, action_dim)
    results = []

    for i, (concentration, seed) in enumerate(scenarios):
        rh = rewards_history[i]

        # Compute Sharpe from trailing rewards (matches runner.py sharpe())
        if len(rh) >= 2:
            arr = torch.tensor(rh[-252:], dtype=torch.float32)
            mean = arr.mean()
            std = arr.std(unbiased=False)
            sharpe = float((mean / std * (252.0 ** 0.5)).item()) if float(std.item()) > 1e-8 else 0.0
        else:
            sharpe = 0.0

        mean_reward = float(np.mean(rh)) if rh else 0.0

        results.append({
            "concentration": concentration,
            "passive_concentration": concentration,
            "seed": seed,
            "sharpe": sharpe,
            "mean_reward": mean_reward,
            "n_episodes": n_episodes,
            "fitness_function": "trailing_252_episode_sharpe",
            "momentum_lookback_steps": 252,
        })

    return results


# ── benchmark ─────────────────────────────────────────────────────────────────

def benchmark(device: torch.device) -> float:
    """Run 100 episodes and return seconds per episode."""
    scenarios = build_scenarios()
    n_scenarios = len(scenarios)
    conc_expanded = torch.tensor(
        [c for c, s in scenarios], dtype=torch.float32
    ).repeat_interleave(POPULATION)

    env = BatchedForgeEnv(concentrations=conc_expanded, device=device)
    cem = BatchedCEM(n_scenarios=n_scenarios, device=device)

    t0 = time.time()
    for _ in range(100):
        candidates = cem.ask()
        weights = candidates.view(n_scenarios * POPULATION, OBS_DIM, ACTION_DIM)
        scores_raw = run_episode_batch(env, weights, {})
        scores = scores_raw.view(n_scenarios, POPULATION)
        cem.tell(scores, candidates)
    elapsed = time.time() - t0
    return elapsed / 100.0


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="GPU-vectorized FORGE runner")
    parser.add_argument("--n-episodes", type=int, default=500_000)
    parser.add_argument("--output", type=str, default="outputs/sim_results.json")
    parser.add_argument("--checkpoint-every", type=int, default=50_000)
    args = parser.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    print("=" * 55)
    print("PAPER-FORGE GPU RUNNER")
    print("=" * 55)
    import os
    print(f"CPU cores: {os.cpu_count()}")
    if device.type == "cuda":
        props = torch.cuda.get_device_properties(0)
        print(f"GPU: {props.name}")
        print(f"VRAM: {props.total_memory / 1e9:.1f}GB")
        print(f"SMs: {props.multi_processor_count}")
    else:
        print("GPU: none (CPU fallback)")

    print(f"\nRunning benchmark (100 episodes)...")
    secs_per_ep = benchmark(device)
    total_est = secs_per_ep * args.n_episodes
    print(f"Seconds per episode: {secs_per_ep:.3f}s")
    print(f"Estimated total time: {total_est/60:.0f} min ({total_est/3600:.1f} hr)")
    print(f"Target episodes: {args.n_episodes:,}")
    print(f"Output: {args.output}")
    print()

    run_all_gpu(
        n_episodes=args.n_episodes,
        output_path=args.output,
        checkpoint_every=args.checkpoint_every,
    )


if __name__ == "__main__":
    main()
