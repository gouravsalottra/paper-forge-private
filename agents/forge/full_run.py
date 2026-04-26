"""Run FORGE simulations across all concentration/seed combinations."""

from __future__ import annotations

import json
import os
from multiprocessing import Manager, Pool, cpu_count
from pathlib import Path
from typing import Any

from agents.forge.runner import ForgeRunner

_LOCK = None
_OUTPUT_PATH = None
_COUNTER = None
_TOTAL = 0


def _worker_init(lock, output_path: str, counter, total: int) -> None:
    global _LOCK, _OUTPUT_PATH, _COUNTER, _TOTAL
    _LOCK = lock
    _OUTPUT_PATH = output_path
    _COUNTER = counter
    _TOTAL = total


def _safe_read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def _run_scenario_worker(concentration: float, seed: int, n_episodes: int) -> dict[str, Any]:
    runner = ForgeRunner(passive_concentration=concentration, seed=seed, n_episodes=n_episodes)
    run_result = runner.run()
    result = {
        "concentration": float(concentration),
        "seed": int(seed),
        "sharpe": float(run_result.get("sharpe", 0.0)),
        "mean_reward": float(run_result.get("mean_reward", 0.0)),
        "n_episodes": int(run_result.get("n_episodes", n_episodes)),
    }

    if _LOCK is not None and _OUTPUT_PATH is not None:
        with _LOCK:
            p = Path(_OUTPUT_PATH)
            existing = _safe_read_json(p)
            seen = {(float(r.get("concentration", -1.0)), int(r.get("seed", -1))) for r in existing}
            key = (float(concentration), int(seed))
            if key not in seen:
                existing.append(result)
                existing.sort(key=lambda row: (float(row["concentration"]), int(row["seed"])))
                p.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            if _COUNTER is not None:
                _COUNTER.value += 1
                i = int(_COUNTER.value)
                total = int(_TOTAL)
            else:
                i = 0
                total = 0

        p_val = float(result.get("primary_p_value", float("nan")))
        print(
            f"Scenario {i}/{total}: concentration={concentration:.2f}, "
            f"seed={seed} → Sharpe={result['sharpe']:.4f}, p={p_val:.6f}"
        )

    return result


def run_full_sweep(n_episodes: int | None = None) -> dict[str, Any]:
    n_episodes = int(n_episodes if n_episodes is not None else os.getenv("PAPER_FORGE_FORGE_EPISODES", "500000"))

    concentrations = [0.10, 0.30, 0.60]
    seeds = [
        1337,
        42,
        9999,  # pre-registered primary seeds (PAPER.md)
        123,
        7,
        99,
        2024,
        314,  # robustness seeds (PAP amendment)
        17,
        888,
        456,
        1001,  # robustness seeds (PAP amendment)
    ]

    output_dir = Path("outputs")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "sim_results.json"

    existing = _safe_read_json(output_path)
    completed = {(float(r.get("concentration", -1.0)), int(r.get("seed", -1))) for r in existing}

    scenarios = [(c, s, n_episodes) for c in concentrations for s in seeds]
    pending: list[tuple[float, int, int]] = []
    for c, s, ne in scenarios:
        if (float(c), int(s)) in completed:
            print(f"Skipping already-completed scenario c={c} s={s}")
            continue
        pending.append((c, s, ne))

    if not pending:
        existing.sort(key=lambda row: (float(row["concentration"]), int(row["seed"])))
        output_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return {"result_flag": "DONE", "output_path": str(output_path), "results": existing}

    workers = min(cpu_count() or 1, len(pending))
    total_scenarios = len(scenarios)

    with Manager() as manager:
        lock = manager.Lock()
        counter = manager.Value("i", len(completed))

        with Pool(
            processes=workers,
            initializer=_worker_init,
            initargs=(lock, str(output_path), counter, total_scenarios),
        ) as pool:
            pool.starmap(_run_scenario_worker, pending)

    results = _safe_read_json(output_path)
    results.sort(key=lambda row: (float(row["concentration"]), int(row["seed"])))
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\nFinal Summary")
    print("concentration | seed | sharpe | mean_reward | n_episodes")
    for row in results:
        pct = int(round(float(row["concentration"]) * 100))
        print(
            f"{pct:>12}% | {int(row['seed']):>4} | {float(row['sharpe']):>7.4f} | "
            f"{float(row['mean_reward']):>11.6f} | {int(row['n_episodes']):>10}"
        )

    return {"result_flag": "DONE", "output_path": str(output_path), "results": results}


def main() -> None:
    run_full_sweep(n_episodes=int(os.getenv("PAPER_FORGE_FORGE_EPISODES", "500000")))


if __name__ == "__main__":
    main()
