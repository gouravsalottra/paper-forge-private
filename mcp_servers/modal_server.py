from __future__ import annotations

import json
import os
from pathlib import Path

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover
    class _Tool:
        def __init__(self, fn):
            self.fn = fn
            self.name = fn.__name__

    class FastMCP:
        def __init__(self, _name: str):
            self.tools: list[_Tool] = []

        def tool(self):
            def deco(fn):
                self.tools.append(_Tool(fn))
                return fn
            return deco

        def run(self):
            return None


mcp = FastMCP("modal-compute")


@mcp.tool()
def dispatch_compute_job(
    n_episodes: int,
    seeds: list,
    concentration_levels: list,
    output_dir: str,
) -> dict:
    """Dispatch a COMPUTE job to Modal GPU infrastructure."""
    modal_token_id = os.getenv("MODAL_TOKEN_ID")
    modal_token_secret = os.getenv("MODAL_TOKEN_SECRET")
    if not modal_token_id or not modal_token_secret:
        return {
            "success": False,
            "error": (
                "Modal credentials not configured. Set "
                "MODAL_TOKEN_ID and MODAL_TOKEN_SECRET in .env"
            ),
        }
    try:
        import modal  # noqa: F401

        job_config = {
            "n_episodes": n_episodes,
            "seeds": seeds,
            "concentration_levels": concentration_levels,
            "output_dir": output_dir,
        }
        config_path = Path(output_dir) / "modal_job_config.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text(json.dumps(job_config, indent=2), encoding="utf-8")
        estimated_minutes = max(15, n_episodes // 33333)
        return {
            "success": True,
            "config_path": str(config_path),
            "estimated_minutes": estimated_minutes,
            "command": f"modal run --detach agents/compute/modal_run.py --n-episodes {n_episodes}",
            "note": "Job config written. Run the command above to dispatch to Modal GPU.",
        }
    except ImportError:
        return {"success": False, "error": "modal package not installed. Run: pip install modal"}


@mcp.tool()
def check_compute_status(output_dir: str) -> dict:
    """Check if a compute job has completed by looking for sim_results.json."""
    results_path = Path(output_dir) / "sim_results.json"
    if results_path.exists():
        results = json.loads(results_path.read_text(encoding="utf-8"))
        episodes_done = results.get("episodes_done", 0) if isinstance(results, dict) else 0
        return {"complete": True, "episodes_done": episodes_done, "results_path": str(results_path)}
    return {"complete": False, "waiting_for": str(results_path)}


if __name__ == "__main__":
    mcp.run()
