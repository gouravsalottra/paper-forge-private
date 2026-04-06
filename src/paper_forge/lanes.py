from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from sqlite3 import Connection, Cursor

from paper_forge.errors import LaneViolationError
from paper_forge.models import Agent

# Table names each agent may INSERT/UPDATE/DELETE. ARIA may read all.
LANES: Mapping[Agent, frozenset[str]] = {
    Agent.ARIA: frozenset(
        {
            "aria_meta",
            "routing_log",
            "checkpoints",
            "run_state",
            "pap_commit",
            "pap_lock",
        }
    ),
    Agent.SCOUT: frozenset({"scout_literature"}),
    Agent.MINER: frozenset({"miner_dataset_manifest", "miner_data_blob"}),
    Agent.SIGMA: frozenset({"pap_row", "sigma_stats", "sigma_figure"}),
    Agent.FORGE: frozenset({"forge_simulation", "forge_simulation_output"}),
    Agent.CODEC: frozenset({"codec_spec", "codec_audit", "codec_fix_request"}),
    Agent.QUILL: frozenset({"quill_latex"}),
    Agent.HAWK: frozenset({"hawk_review"}),
}


def assert_lane(agent: Agent, tables: Iterable[str]) -> None:
    allowed = LANES[agent]
    bad = [t for t in tables if t not in allowed]
    if bad:
        raise LaneViolationError(f"{agent.value} cannot write tables: {bad}")


def with_lane(
    conn: Connection,
    agent: Agent,
    tables: Iterable[str],
    work: Callable[[Cursor], None],
) -> None:
    """Run a write callback inside the current transaction after lane checks."""

    assert_lane(agent, tables)
    cur = conn.cursor()
    work(cur)
