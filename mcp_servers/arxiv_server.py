"""ArXiv query helper used by SCOUT."""

from __future__ import annotations

from typing import Any

import arxiv


def query(terms: list[str], date_after: str = "2018-01-01", max_results: int = 50) -> list[dict[str, Any]]:
    del date_after  # arxiv package query API currently handled by search relevance filter only.
    search_query = " AND ".join(terms)
    client = arxiv.Client()
    search = arxiv.Search(
        query=search_query,
        max_results=max_results,
        sort_by=arxiv.SortCriterion.Relevance,
    )
    results: list[dict[str, Any]] = []
    for paper in client.results(search):
        results.append(
            {
                "title": paper.title,
                "abstract": paper.summary,
                "authors": [str(a) for a in paper.authors],
                "published": str(paper.published),
                "pdf_url": paper.pdf_url,
                "entry_id": paper.entry_id,
            }
        )
    return results

