"""Modal entrypoint for running the full FORGE simulation sweep."""
# Run using detached mode:
# modal run --detach agents/forge/modal_run.py

import json
import os
import sys

import modal

app = modal.App("paper-forge-full-run")
runtime_secret = modal.Secret.from_name("paper-forge-runtime")
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "numpy==2.1.3",
        "pandas==2.2.3",
        "gymnasium==1.2.3",
        "pettingzoo==1.24.3",
    )
    .add_local_dir(".", remote_path="/root")
)


@app.function(image=image, timeout=1800, secrets=[runtime_secret])
def run_scenario(concentration: float, seed: int, n_episodes: int = 500_000) -> dict:
    sys.path.insert(0, "/root")
    from agents.forge.runner import ForgeRunner

    runner = ForgeRunner(passive_concentration=concentration, seed=seed, n_episodes=n_episodes)
    result = runner.run()
    return {
        "concentration": concentration,
        "seed": seed,
        "sharpe": float(result.get("sharpe", 0.0)),
        "mean_reward": float(result.get("mean_reward", 0.0)),
        "n_episodes": int(result.get("n_episodes", n_episodes)),
    }


@app.function(image=image, timeout=3600, secrets=[runtime_secret])
def run_all(n_episodes: int = 500_000) -> list[dict]:
    sys.path.insert(0, "/root")

    concentrations = [0.10, 0.30, 0.60]
    seeds = [1337, 42, 9999]
    scenarios = [(c, s, n_episodes) for c in concentrations for s in seeds]

    results = list(run_scenario.starmap(scenarios))
    results.sort(key=lambda row: (row["concentration"], row["seed"]))
    return results


@app.local_entrypoint()
def main(n_episodes: int = 500_000) -> None:
    # Run in detached mode so local process exit does not terminate remote work:
    # modal run --detach agents/forge/modal_run.py
    concentrations = [0.10, 0.30, 0.60]
    seeds = [1337, 42, 9999]
    scenarios = [(c, s, n_episodes) for c in concentrations for s in seeds]

    os.makedirs("outputs", exist_ok=True)
    output_path = os.path.join("outputs", "sim_results.json")
    results = []
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("[]")

    for result in run_scenario.starmap(scenarios):
        results.append(result)
        results.sort(key=lambda row: (row["concentration"], row["seed"]))
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(results, indent=2))
        pct = int(round(result["concentration"] * 100))
        print(f"✅ conc={pct}% seed={result['seed']} Sharpe={result['sharpe']:.4f}")

    print("Final Summary")
    print("concentration | seed | sharpe | mean_reward | n_episodes")
    for row in results:
        pct = int(round(row["concentration"] * 100))
        print(
            f"{pct:>12}% | {row['seed']:>4} | {row['sharpe']:>7.4f} | "
            f"{row['mean_reward']:>11.6f} | {row['n_episodes']:>10}"
        )

    print(f"\nSaved: {output_path}")
