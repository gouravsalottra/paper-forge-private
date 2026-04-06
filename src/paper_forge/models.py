from __future__ import annotations

from enum import Enum


class Phase(str, Enum):
    """Ordered workflow phases (restart-safe via run_state.phase)."""

    INIT = "init"
    SCOUT = "scout"
    MINER = "miner"
    SIGMA = "sigma"
    PAP_COMMIT = "pap_commit"
    PAP_SEAL = "pap_seal"
    FORGE = "forge"
    CODEC = "codec"
    QUILL = "quill"
    HAWK = "hawk"
    DONE = "done"


class Agent(str, Enum):
    """Named actors with disjoint SQLite write lanes."""

    ARIA = "ARIA"
    SCOUT = "SCOUT"
    MINER = "MINER"
    SIGMA = "SIGMA"
    FORGE = "FORGE"
    CODEC = "CODEC"
    QUILL = "QUILL"
    HAWK = "HAWK"
