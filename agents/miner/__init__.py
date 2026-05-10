"""Legacy miner package shim.

Canonical DATAPULL implementation lives in ``agents.datapull.datapull``.
"""

from .miner import build_returns_frame, run_miner_pipeline, select_data_source  # noqa: F401
