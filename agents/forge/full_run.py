"""Run FORGE simulations across all concentration/seed combinations."""

from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor, as_completed
import json
import os
from pathlib import Path

from agents.forge.runner import ForgeRunner


def _run_scenario(concentration: float, seed: int, n_episodes: int) -> dict:
    pct = int(round(concentration * 100))
    print(f"▶ Running conc={pct}% seed={seed} ...")
    runner = ForgeRunner(passive_concentration=concentration, seed=seed, n_episodes=n_episodes)
    run_result = runner.run()
    result = {
        "concentration": concentration,
        "seed": seed,
        "sharpe": float(run_result.get("sharpe", 0.0)),
        "mean_reward": float(run_result.get("mean_reward", 0.0)),
        "n_episodes": int(run_result.get("n_episodes", n_episodes)),
    }
    return result


def run_full_sweep(n_episodes: int = 500_000) -> dict:
    concentrations = [0.10, 0.30, 0.60]
    seeds = [1337, 42, 9999]
    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = [(c, s) for c in concentrations for s in seeds]
    max_workers = min(len(scenarios), os.cpu_count() or 1)
    results = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        future_map = {
            executor.submit(_run_scenario, concentration, seed, n_episodes): (concentration, seed)
            for concentration, seed in scenarios
        }
        for future in as_completed(future_map):
            concentration, seed = future_map[future]
            result = future.result()
            results.append(result)
            pct = int(round(concentration * 100))
            print(f"✅ conc={pct}% seed={seed} Sharpe={result['sharpe']:.4f}")

    results.sort(key=lambda row: (row["concentration"], row["seed"]))

    output_path = output_dir / "sim_results.json"
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\nFinal Summary")
    print("concentration | seed | sharpe | mean_reward | n_episodes")
    for row in results:
        pct = int(round(row["concentration"] * 100))
        print(
            f"{pct:>12}% | {row['seed']:>4} | {row['sharpe']:>7.4f} | "
            f"{row['mean_reward']:>11.6f} | {row['n_episodes']:>10}"
        )
    return {"result_flag": "DONE", "output_path": str(output_path), "results": results}


def main() -> None:
    run_full_sweep(n_episodes=500_000)


if __name__ == "__main__":
    main()
