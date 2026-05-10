"""Routing configuration for CONDUCTOR pipeline dispatch.

CONDUCTOR reads this dict — it never contains routing logic inline.
Adding a new agent = adding one entry here. Never modify aria.py for routing.
"""

from __future__ import annotations

AGENT_SERVER_MAP: dict[str, str] = {
    "LITERATURE": "semantic_scholar",
    "DATAPULL": "wrds",
    "PREREGISTER": "local_stats",
    "COMPUTE": "forge_cluster",
    "STATSRUN": "local_stats",
    "CODEAUDIT": "llm",
    "AUTOREPAIR": "local",
    "WRITER": "llm",
    "REVIEWER": "llm",
}

AGENT_TIMEOUTS_SECONDS: dict[str, int] = {
    "LITERATURE": 300,
    "DATAPULL": 600,
    "PREREGISTER": 120,
    "COMPUTE": 86400,
    "STATSRUN": 300,
    "CODEAUDIT": 600,
    "AUTOREPAIR": 600,
    "WRITER": 900,
    "REVIEWER": 600,
}

BLOCKED_ARTIFACTS: dict[str, set[str]] = {
    "PREREGISTER": {"sim_results", "paper_draft", "codec_spec"},
    "CODEAUDIT_PASS2": {"codebase", "codec_pass1_output"},
}

ALLOWED_ARTIFACTS: dict[str, set[str]] = {
    "WRITER": {"literature_map", "codec_spec", "stats_tables", "pap", "codec_mismatch"},
    "REVIEWER": {"paper_draft", "codec_spec", "stats_tables", "codec_mismatch"},
}

AGENT_DISPLAY_NAMES: dict[str, str] = {
    "LITERATURE": "LITERATURE",
    "DATAPULL": "DATAPULL",
    "PREREGISTER": "PREREGISTER",
    "COMPUTE": "COMPUTE",
    "STATSRUN": "STATSRUN",
    "CODEAUDIT": "CODEAUDIT / SPECAUDIT",
    "AUTOREPAIR": "AUTOREPAIR",
    "WRITER": "WRITER",
    "REVIEWER": "REVIEWER",
}

SYSTEM_DISPLAY_NAMES: dict[str, str] = {
    "ARIA": "CONDUCTOR",
    "INTAKE": "INTAKE",
    "PAPER.md": "PROTOCOL.md",
    "pipeline.db": "pipeline.db",
}
