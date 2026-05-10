from __future__ import annotations

import json

try:
    import arxiv  # type: ignore
except Exception:  # pragma: no cover
    class _ArxivMissing:
        class SortCriterion:
            Relevance = "relevance"

        class Search:
            def __init__(self, *args, **kwargs):
                self.args = args
                self.kwargs = kwargs

        class Client:
            def results(self, _search):
                raise RuntimeError("arxiv package not installed")

    arxiv = _ArxivMissing()  # type: ignore

try:
    from fastmcp import FastMCP
except Exception:  # pragma: no cover
    class _Tool:
        def __init__(self, fn):
            self.fn = fn
            self.name = fn.__name__

    class FastMCP:  # minimal fallback for local tests
        def __init__(self, _name: str):
            self.tools: list[_Tool] = []

        def tool(self):
            def deco(fn):
                self.tools.append(_Tool(fn))
                return fn
            return deco

        def run(self):
            return None


mcp = FastMCP("arxiv-search")


@mcp.tool()
def search_arxiv(query: str, max_results: int = 40, categories: list[str] | None = None) -> str:
    client = arxiv.Client()
    search = arxiv.Search(query=query, max_results=max_results, sort_by=arxiv.SortCriterion.Relevance)
    results = []
    for paper in client.results(search):
        if categories and not any(c in getattr(paper, "categories", []) for c in categories):
            continue
        results.append(
            {
                "title": paper.title,
                "authors": [a.name for a in paper.authors],
                "abstract": paper.summary,
                "arxiv_id": paper.entry_id,
                "published": paper.published.isoformat() if hasattr(paper.published, "isoformat") else str(paper.published),
                "doi": getattr(paper, "doi", None),
                "pdf_url": paper.pdf_url,
                "categories": getattr(paper, "categories", []),
                "peer_reviewed": bool(getattr(paper, "doi", None)),
            }
        )
    return json.dumps(results)


@mcp.tool()
def fetch_arxiv_paper(arxiv_id: str) -> str:
    client = arxiv.Client()
    search = arxiv.Search(id_list=[arxiv_id])
    paper = next(client.results(search))
    return json.dumps(
        {
            "title": paper.title,
            "authors": [a.name for a in paper.authors],
            "abstract": paper.summary,
            "arxiv_id": paper.entry_id,
            "published": paper.published.isoformat() if hasattr(paper.published, "isoformat") else str(paper.published),
            "doi": getattr(paper, "doi", None),
            "categories": getattr(paper, "categories", []),
            "peer_reviewed": bool(getattr(paper, "doi", None)),
        }
    )


if __name__ == "__main__":
    mcp.run()
