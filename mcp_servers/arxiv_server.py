"""ArXiv MCP server stub.

Provides SCOUT agent with structured literature search via the ArXiv API.

Status: PLANNED — not yet implemented.
When implemented, this server will expose:
  - search(query: str, max_results: int) -> list[Paper]
  - fetch_abstract(arxiv_id: str) -> str
  - fetch_full_text(arxiv_id: str) -> str

ARIA health check: GET /health returns {"status": "ok"}
"""
