"""Data MCP server stub.

Provides DATAPULL agent with WRDS and alternative data source access.

Status: PLANNED — not yet implemented.
When implemented, this server will expose:
  - fetch_futures(tickers, start, end, roll_convention) -> DataFrame
  - fetch_ff_factors(start, end) -> DataFrame
  - health() -> dict

CONDUCTOR health check: verifies WRDS connection on startup.
"""
