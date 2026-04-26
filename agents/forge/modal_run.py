"""Modal entrypoint for running the full FORGE simulation sweep."""
# Run using detached mode:
# modal run --detach agents/forge/modal_run.py

import json
import os
import sys

import modal

app = modal.App("paper-forge-full-run")
runtime_secret = modal.Secret.from_name("paper-forge-runtime")
# SECURITY: Never use add_local_dir(".") — it uploads .env and secrets.
# Only add specific directories and files required for the FORGE run.
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "torch",
        "numpy",
        "pandas",
        "gymnasium",
        "pettingzoo",
        "stable-baselines3",
    )
    .add_local_dir("agents/forge", remote_path="/root/agents/forge")
    .add_local_file("PAPER.md", remote_path="/root/PAPER.md")
)


@app.function(
    image=image,
    timeout=7200,
    secrets=[runtime_secret],
    gpu="T4",
    retries=2,
)
@modal.concurrent(max_inputs=1)
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


@app.function(
    image=image,
    timeout=7200,
    secrets=[runtime_secret],
    gpu="T4",
    retries=2,
)
@modal.concurrent(max_inputs=1)
def run_all(n_episodes: int = 500_000) -> list[dict]:
    sys.path.insert(0, "/root")

    concentrations = [0.10, 0.30, 0.60]
    seeds = [
        1337, 42, 9999,          # pre-registered primary seeds (PAPER.md)
        123, 7, 99, 2024, 314,   # robustness seeds (PAP amendment)
        17, 888, 456, 1001       # robustness seeds (PAP amendment)
    ]
    scenarios = [(c, s, n_episodes) for c in concentrations for s in seeds]

    results = []
    batch_size = 8
    scenarios_list = list(scenarios)
    for i in range(0, len(scenarios_list), batch_size):
        batch = scenarios_list[i:i + batch_size]
        batch_results = list(run_scenario.starmap(batch))
        results.extend(batch_results)
    results.sort(key=lambda row: (row["concentration"], row["seed"]))
    return results


@app.local_entrypoint()
def main(n_episodes: int = 500_000) -> None:
    # Run in detached mode so local process exit does not terminate remote work:
    # modal run --detach agents/forge/modal_run.py
    concentrations = [0.10, 0.30, 0.60]
    seeds = [
        1337, 42, 9999,          # pre-registered primary seeds (PAPER.md)
        123, 7, 99, 2024, 314,   # robustness seeds (PAP amendment)
        17, 888, 456, 1001       # robustness seeds (PAP amendment)
    ]
    scenarios = [(c, s, n_episodes) for c in concentrations for s in seeds]

    os.makedirs("outputs", exist_ok=True)
    output_path = os.path.join("outputs", "sim_results.json")
    results = []
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("[]")

    batch_size = 8
    scenarios_list = list(scenarios)
    for i in range(0, len(scenarios_list), batch_size):
        batch = scenarios_list[i:i + batch_size]
        for result in run_scenario.starmap(batch):
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
