#!/usr/bin/env python3
# pip install tqdm numpy pettingzoo gymnasium
# On ThunderCompute: set --workers to vCPU count
# On Colab Pro: set --workers 2 (Colab has 2 real CPU cores for multiprocessing)

from __future__ import annotations

import argparse
import json
import math
import os
from multiprocessing import Manager, Pool, cpu_count
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

from agents.forge.full_run import _run_scenario_worker, _safe_read_json, _worker_init


def _run_tuple(scenario: tuple[float, int, int]) -> dict[str, Any]:
    return _run_scenario_worker(*scenario)


def _eta_minutes(remaining: int, workers: int, mins_per_scenario: float = 8.0) -> int:
    batches = math.ceil(max(remaining, 0) / max(workers, 1))
    return int(round(batches * mins_per_scenario))


def _summary_table(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not results:
        return []
    rows = []
    for c in sorted({float(r["concentration"]) for r in results}):
        vals = [float(r["sharpe"]) for r in results if float(r["concentration"]) == c]
        rows.append({"concentration": c, "mean_sharpe": float(np.mean(vals)) if vals else float("nan")})
    return rows


def _bonferroni_from_results(results: list[dict[str, Any]]) -> tuple[float, bool]:
    high = [float(r["sharpe"]) for r in results if np.isclose(float(r["concentration"]), 0.60)]
    low = [float(r["sharpe"]) for r in results if np.isclose(float(r["concentration"]), 0.10)]
    if len(high) > 1 and len(low) > 1:
        _, p = stats.ttest_ind(high, low, equal_var=False)
        p = float(p) if np.isfinite(p) else 1.0
    else:
        p = 1.0
    corrected = min(p * 6.0, 1.0)
    return corrected, corrected < 0.008333


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-episodes", type=int, default=500000)
    ap.add_argument("--workers", type=int, default=max(1, min(cpu_count() or 1, 8)))
    ap.add_argument("--output", type=str, default="outputs/sim_results.json")
    args = ap.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    concentrations = [0.10, 0.30, 0.60]
    seeds = [1337, 42, 9999, 123, 7, 99, 2024, 314, 17, 888, 456, 1001]
    scenarios = [(c, s, args.n_episodes) for c in concentrations for s in seeds]

    existing = _safe_read_json(output_path)
    completed = {(float(r.get("concentration", -1.0)), int(r.get("seed", -1))) for r in existing}
    pending = [s for s in scenarios if (float(s[0]), int(s[1])) not in completed]

    print(f"Already completed scenarios: {len(completed)}")
    eta_min = _eta_minutes(len(pending), args.workers)
    print(f"Estimated time: ~{eta_min} min ({len(pending)} scenarios remaining on {args.workers} workers)")
    confirm = input(f"Run {len(scenarios)} scenarios × {args.n_episodes} episodes on {args.workers} workers? [y/n] ").strip().lower()
    if confirm not in {"y", "yes"}:
        print("Cancelled.")
        return

    partial_path = output_path.with_name("sim_results_partial.json")

    manager = Manager()
    lock = manager.Lock()
    counter = manager.Value("i", len(completed))

    use_tqdm = False
    try:
        from tqdm import tqdm  # type: ignore

        use_tqdm = True
    except Exception:
        tqdm = None  # type: ignore

    try:
        with Pool(
            processes=max(1, min(args.workers, len(pending) or 1)),
            initializer=_worker_init,
            initargs=(lock, str(output_path), counter, len(scenarios)),
        ) as pool:
            iterator = pool.imap_unordered(_run_tuple, pending)
            if use_tqdm:
                iterator = tqdm(iterator, total=len(pending), desc="FORGE scenarios")

            processed = 0
            for _ in iterator:
                processed += 1
                if not use_tqdm:
                    done = int(counter.value)
                    remaining = len(scenarios) - done
                    print(f"[{done}/{len(scenarios)}] ETA: ~{_eta_minutes(remaining, args.workers)} min")
    except KeyboardInterrupt:
        results_now = _safe_read_json(output_path)
        partial_path.write_text(json.dumps(results_now, indent=2), encoding="utf-8")
        print("Partial results saved. Re-run to resume (completed scenarios will be skipped).")
        return
    except Exception:
        results_now = _safe_read_json(output_path)
        partial_path.write_text(json.dumps(results_now, indent=2), encoding="utf-8")
        print("Partial results saved. Re-run to resume (completed scenarios will be skipped).")
        raise
    finally:
        manager.shutdown()

    results = _safe_read_json(output_path)
    results.sort(key=lambda r: (float(r["concentration"]), int(r["seed"])))
    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print("\nSummary: concentration vs mean Sharpe")
    for row in _summary_table(results):
        print(f"c={row['concentration']:.2f} mean_sharpe={row['mean_sharpe']:.6f}")

    corrected_p, passes = _bonferroni_from_results(results)
    print(f"primary_p_value(corrected): {corrected_p:.6f}")
    print(f"passes_bonferroni(p < 0.008333): {passes}")
    print(f"Saved final: {output_path}")


if __name__ == "__main__":
    main()
