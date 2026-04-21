"""Routing configuration for ARIA pipeline dispatch.

ARIA reads this dict — it never contains routing logic inline.
Adding a new agent = adding one entry here. Never modify aria.py for routing.
"""

from __future__ import annotations

AGENT_SERVER_MAP: dict[str, str] = {
    "SCOUT": "semantic_scholar",
    "MINER": "wrds",
    "SIGMA_JOB1": "local_stats",
    "FORGE": "forge_cluster",
    "SIGMA_JOB2": "local_stats",
    "CODEC": "llm",
    "FIXER": "local",
    "QUILL": "llm",
    "HAWK": "llm",
}

AGENT_TIMEOUTS_SECONDS: dict[str, int] = {
    "SCOUT": 300,
    "MINER": 600,
    "SIGMA_JOB1": 120,
    "FORGE": 86400,
    "SIGMA_JOB2": 300,
    "CODEC": 600,
    "FIXER": 600,
    "QUILL": 900,
    "HAWK": 600,
}

BLOCKED_ARTIFACTS: dict[str, set[str]] = {
    "SIGMA_JOB1": {"sim_results", "paper_draft", "codec_spec"},
    "CODEC_PASS2": {"codebase", "codec_pass1_output"},
}

ALLOWED_ARTIFACTS: dict[str, set[str]] = {
    "QUILL": {"literature_map", "codec_spec", "stats_tables", "pap", "codec_mismatch"},
    "HAWK": {"paper_draft", "codec_spec", "stats_tables", "codec_mismatch"},
}
