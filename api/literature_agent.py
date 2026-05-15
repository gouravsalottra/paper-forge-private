from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from difflib import SequenceMatcher
from typing import Any

from api.llm_caller import call_agent_llm

logger = logging.getLogger(__name__)

SEMANTIC_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"
ARXIV_QUERY_URL = "https://export.arxiv.org/api/query"


def _topic_text(topic: str, blueprint: dict[str, Any]) -> str:
    return str(topic or blueprint.get("focus_question") or blueprint.get("topic") or "empirical finance research question").strip()


def _fallback_queries(topic: str, method_style: str) -> dict[str, list[str]]:
    clean = re.sub(r"\s+", " ", topic).strip()
    method = str(method_style or "empirical finance").replace("_", " ")
    return {
        "queries": [
            f"{clean} empirical finance",
            f"{clean} {method} methodology",
            f"{clean} asset pricing evidence",
            f"{clean} econometric identification",
            f"{clean} market response literature",
            f"{clean} robustness tests",
            f"{clean} financial markets",
            f"{method} asset pricing empirical evidence",
        ]
    }


async def _generate_queries(topic: str, method_style: str, client) -> list[str]:
    prompt = f"""
Generate 6 precise academic search queries for this empirical finance research topic.
Each query must target a different angle: main hypothesis, methodology, data,
related empirical findings, theory, and policy or institutional implications.

Topic: {topic}
Method style: {method_style}

Return ONLY valid JSON: {{"queries": ["query 1", "query 2"]}}
"""
    if client is None:
        return _fallback_queries(topic, method_style)["queries"]
    result = await call_agent_llm(
        agent_name="LITERATURE_QUERY_AGENT",
        prompt=prompt,
        client=client,
        fallback_fn=_fallback_queries,
        fallback_args={"topic": topic, "method_style": method_style},
        max_tokens=1200,
    )
    queries = result.get("queries") if isinstance(result, dict) else []
    return [str(item).strip() for item in queries if str(item).strip()][:8] or _fallback_queries(topic, method_style)["queries"]


def _get_json(url: str, params: dict[str, Any], timeout: int = 15) -> dict[str, Any]:
    query = urllib.parse.urlencode({key: value for key, value in params.items() if value is not None})
    request = urllib.request.Request(f"{url}?{query}", headers={"User-Agent": "Thrivarc literature agent"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - fixed scholarly APIs only
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.warning("Literature API request failed for %s: %s", url, exc)
        return {}


def _authors_from_semantic(authors: list[dict[str, Any]] | None) -> list[str]:
    return [str(author.get("name") or "").strip() for author in authors or [] if str(author.get("name") or "").strip()]


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(title).lower()).strip()


def _paper_key(paper: dict[str, Any]) -> str:
    doi = str(paper.get("doi") or "").lower().strip()
    if doi:
        return f"doi:{doi}"
    return f"title:{_normalize_title(str(paper.get('title') or ''))}"


def _title_similar(a: str, b: str) -> bool:
    na, nb = _normalize_title(a), _normalize_title(b)
    return bool(na and nb and SequenceMatcher(None, na, nb).ratio() >= 0.92)


def _dedupe(papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    keys: set[str] = set()
    for paper in papers:
        title = str(paper.get("title") or "").strip()
        if not title:
            continue
        key = _paper_key(paper)
        if key in keys or any(_title_similar(title, str(existing.get("title") or "")) for existing in out):
            continue
        keys.add(key)
        out.append(paper)
    return out


def _semantic_papers(query: str, limit: int = 20) -> list[dict[str, Any]]:
    payload = _get_json(
        SEMANTIC_SEARCH_URL,
        {
            "query": query,
            "fields": "paperId,title,abstract,year,authors,citationCount,externalIds,venue,referenceCount,citationStyles",
            "limit": limit,
        },
    )
    papers = []
    for item in payload.get("data", []) or []:
        external = item.get("externalIds") or {}
        papers.append(
            {
                "source": "Semantic Scholar",
                "paper_id": item.get("paperId"),
                "title": item.get("title"),
                "abstract": item.get("abstract") or "",
                "year": item.get("year"),
                "authors": _authors_from_semantic(item.get("authors")),
                "citation_count": item.get("citationCount") or 0,
                "doi": external.get("DOI") or external.get("doi"),
                "venue": item.get("venue") or "",
                "url": f"https://www.semanticscholar.org/paper/{item.get('paperId')}" if item.get("paperId") else "",
                "query": query,
            }
        )
    return papers


def _openalex_papers(query: str, per_page: int = 10) -> list[dict[str, Any]]:
    payload = _get_json(
        OPENALEX_WORKS_URL,
        {
            "search": query,
            "filter": "type:article",
            "per-page": per_page,
        },
    )
    papers = []
    for item in payload.get("results", []) or []:
        authors = []
        for authorship in item.get("authorships", []) or []:
            author = authorship.get("author") or {}
            name = str(author.get("display_name") or "").strip()
            if name:
                authors.append(name)
        abstract_index = item.get("abstract_inverted_index") or {}
        abstract_words: list[tuple[int, str]] = []
        for word, positions in abstract_index.items():
            for pos in positions:
                abstract_words.append((int(pos), word))
        abstract = " ".join(word for _, word in sorted(abstract_words)) if abstract_words else ""
        papers.append(
            {
                "source": "OpenAlex",
                "paper_id": item.get("id"),
                "title": item.get("display_name"),
                "abstract": abstract,
                "year": item.get("publication_year"),
                "authors": authors,
                "citation_count": item.get("cited_by_count") or 0,
                "doi": str(item.get("doi") or "").replace("https://doi.org/", ""),
                "venue": ((item.get("primary_location") or {}).get("source") or {}).get("display_name") or "",
                "url": item.get("id") or "",
                "query": query,
            }
        )
    return papers


def _arxiv_papers(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "search_query": f'all:"{query}"',
            "start": 0,
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }
    )
    request = urllib.request.Request(f"{ARXIV_QUERY_URL}?{params}", headers={"User-Agent": "Thrivarc literature agent"})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - fixed scholarly API only
            root = ET.fromstring(response.read())
    except Exception as exc:
        logger.warning("arXiv request failed: %s", exc)
        return []
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    papers = []
    for entry in root.findall("atom:entry", ns):
        title = " ".join((entry.findtext("atom:title", default="", namespaces=ns) or "").split())
        abstract = " ".join((entry.findtext("atom:summary", default="", namespaces=ns) or "").split())
        year = (entry.findtext("atom:published", default="", namespaces=ns) or "")[:4]
        authors = [
            (author.findtext("atom:name", default="", namespaces=ns) or "").strip()
            for author in entry.findall("atom:author", ns)
        ]
        url = entry.findtext("atom:id", default="", namespaces=ns)
        if title:
            papers.append(
                {
                    "source": "arXiv",
                    "paper_id": url,
                    "title": title,
                    "abstract": abstract,
                    "year": int(year) if year.isdigit() else year,
                    "authors": [author for author in authors if author],
                    "citation_count": 0,
                    "doi": "",
                    "venue": "arXiv",
                    "url": url,
                    "query": query,
                }
            )
    return papers


def _supplemental_queries(topic: str, method_style: str) -> list[str]:
    clean = re.sub(r"\s+", " ", topic).strip()
    method = str(method_style or "empirical finance").replace("_", " ")
    acronyms = re.findall(r"\b[A-Z][A-Z0-9^]{1,}\b", clean)
    topic_terms_list = re.findall(r"[A-Za-z][A-Za-z0-9-]{2,}", clean)
    topic_terms = " ".join(topic_terms_list[:8])
    acronym_queries: list[str] = []
    for acronym in acronyms[:3]:
        nearby = " ".join(term for term in topic_terms_list[:8] if term.upper() != acronym)
        acronym_queries.extend([f"{acronym} {nearby}".strip(), f"{acronym} asset pricing", f"{acronym} predictability"])
    candidates = [
        clean,
        *acronym_queries,
        f"{topic_terms} empirical asset pricing",
        f"{topic_terms} empirical finance",
        f"{topic_terms} corporate finance",
        f"{topic_terms} financial econometrics",
        f"{topic_terms} market microstructure",
        f"{method} finance econometrics",
        f"{method} robustness empirical finance",
    ]
    out: list[str] = []
    seen: set[str] = set()
    for query in candidates:
        normalized = query.lower().strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            out.append(query)
    return out


def _semantic_references(paper_id: str) -> list[dict[str, Any]]:
    if not paper_id:
        return []
    url = f"https://api.semanticscholar.org/graph/v1/paper/{urllib.parse.quote(paper_id)}/references"
    payload = _get_json(
        url,
        {"fields": "citedPaper.paperId,citedPaper.title,citedPaper.abstract,citedPaper.year,citedPaper.authors,citedPaper.citationCount,citedPaper.externalIds,citedPaper.venue", "limit": 20},
    )
    refs = []
    for item in payload.get("data", []) or []:
        cited = item.get("citedPaper") or {}
        external = cited.get("externalIds") or {}
        refs.append(
            {
                "source": "Semantic Scholar references",
                "paper_id": cited.get("paperId"),
                "title": cited.get("title"),
                "abstract": cited.get("abstract") or "",
                "year": cited.get("year"),
                "authors": _authors_from_semantic(cited.get("authors")),
                "citation_count": cited.get("citationCount") or 0,
                "doi": external.get("DOI") or external.get("doi"),
                "venue": cited.get("venue") or "",
                "url": f"https://www.semanticscholar.org/paper/{cited.get('paperId')}" if cited.get("paperId") else "",
                "query": "citation_chase_depth_1",
            }
        )
    return refs


def _fallback_rank(topic: str, papers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stopwords = {
        "does",
        "with",
        "from",
        "this",
        "that",
        "next",
        "month",
        "study",
        "research",
        "empirical",
        "finance",
        "financial",
        "market",
        "markets",
    }
    topic_terms = {term for term in re.findall(r"[a-z][a-z0-9-]{2,}", topic.lower()) if term not in stopwords}
    ranked = []
    for paper in papers:
        title = str(paper.get("title") or "").lower()
        title_abs = f"{title} {paper.get('abstract', '')}".lower()
        overlap = sum(1 for term in topic_terms if term in title_abs)
        title_overlap = sum(1 for term in topic_terms if term in title)
        citation = min(float(paper.get("citation_count") or 0) / 500.0, 1.0)
        score = max(1.0, min(10.0, 2.0 + overlap * 1.2 + title_overlap * 1.6 + citation))
        ranked.append({**paper, "relevance_score": round(score, 2), "_lexical_overlap": overlap})
    relevant = [paper for paper in ranked if paper.get("_lexical_overlap", 0) > 0]
    if len(relevant) >= 10:
        ranked = relevant
    return sorted(ranked, key=lambda item: (item.get("relevance_score", 0), item.get("citation_count", 0)), reverse=True)


async def _rank_papers(topic: str, papers: list[dict[str, Any]], client) -> list[dict[str, Any]]:
    if not papers:
        return []
    if client is None:
        return _fallback_rank(topic, papers)[:20]
    compact = [
        {
            "index": idx,
            "title": paper.get("title"),
            "abstract": str(paper.get("abstract") or "")[:1200],
            "year": paper.get("year"),
            "venue": paper.get("venue"),
            "citation_count": paper.get("citation_count"),
        }
        for idx, paper in enumerate(papers[:80])
    ]
    prompt = f"""
Score each paper for relevance to this empirical finance topic on a 1-10 scale.
Use only the provided title and abstract. Return ONLY valid JSON:
{{"scores": [{{"index": 0, "score": 8.5, "reason": "..."}}]}}

Topic: {topic}
Papers:
{json.dumps(compact, ensure_ascii=True)}
"""
    result = await call_agent_llm(
        agent_name="LITERATURE_RANKING_AGENT",
        prompt=prompt,
        client=client,
        fallback_fn=lambda topic, papers: {"scores": [{"index": i, "score": p.get("relevance_score", 5)} for i, p in enumerate(_fallback_rank(topic, papers))]},
        fallback_args={"topic": topic, "papers": papers[:80]},
        max_tokens=3000,
    )
    score_map = {int(item.get("index")): float(item.get("score") or 0.0) for item in result.get("scores", []) if str(item.get("index", "")).isdigit()}
    ranked = []
    for idx, paper in enumerate(papers[:80]):
        ranked.append({**paper, "relevance_score": round(score_map.get(idx, 0.0) or _fallback_rank(topic, [paper])[0].get("relevance_score", 5), 2)})
    return sorted(ranked, key=lambda item: (item.get("relevance_score", 0), item.get("citation_count", 0)), reverse=True)[:20]


def _citation_key(paper: dict[str, Any], used: set[str]) -> str:
    author = "study"
    if paper.get("authors"):
        author = re.sub(r"[^A-Za-z]", "", str(paper["authors"][0]).split()[-1]).lower() or "study"
    year = str(paper.get("year") or "nd")
    base = f"{author}{year}"
    key = base
    suffix = 2
    while key in used:
        key = f"{base}{suffix}"
        suffix += 1
    used.add(key)
    return key


def _bibtex_entry(paper: dict[str, Any]) -> str:
    authors = " and ".join(paper.get("authors") or ["Unknown"])
    fields = {
        "author": authors,
        "title": paper.get("title") or "Untitled",
        "journal": paper.get("venue") or "Working paper",
        "year": paper.get("year") or "n.d.",
        "doi": paper.get("doi") or "",
        "url": paper.get("url") or "",
    }
    body = ",\n".join(f"  {key} = {{{str(value)}}}" for key, value in fields.items() if value)
    return f"@article{{{paper['citation_key']},\n{body}\n}}"


def _fallback_synthesis(topic: str, papers: list[dict[str, Any]]) -> dict[str, str]:
    lines = [f"# Literature Review\n\nThe literature base for `{topic}` was built from verified scholarly metadata. The discussion below uses only retrieved papers and avoids uncited claims.\n"]
    for idx, paper in enumerate(papers[:20], start=1):
        authors = ", ".join((paper.get("authors") or ["Unknown"] )[:3])
        year = paper.get("year") or "n.d."
        abstract = str(paper.get("abstract") or "No abstract was available from the source metadata.").strip()
        lines.append(f"## Theme {idx}: {paper.get('title')}\n\n{authors} ({year}) [@{paper.get('citation_key')}] is relevant because its abstract indicates: {abstract[:900]}\n")
    review = "\n".join(lines)
    gap = (
        "# Literature Map\n\n"
        "The study should position itself against the retrieved empirical and methodological papers above. "
        "The remaining contribution must be stated as a narrow incremental test whose data, method, and inference are locked before compute.\n"
    )
    return {"literature_review_md": review, "literature_map_md": gap}


async def _synthesize(topic: str, papers: list[dict[str, Any]], bibliography_bib: str, client) -> dict[str, str]:
    if client is None or not papers:
        return _fallback_synthesis(topic, papers)
    compact = [
        {
            "citation_key": paper.get("citation_key"),
            "title": paper.get("title"),
            "authors": paper.get("authors"),
            "year": paper.get("year"),
            "venue": paper.get("venue"),
            "abstract": str(paper.get("abstract") or "")[:1600],
        }
        for paper in papers[:20]
    ]
    prompt = f"""
You are writing the literature review section of an empirical finance paper.
Topic: {topic}
Using ONLY the papers provided below, write a 3-4 page literature review in Markdown.
Organize by theme. For each paper you cite, use the citation key from the BibTeX list.
Every claim must be attributed to a specific paper. Do not invent papers or facts.
Also write a concise literature map / gap analysis.

Return ONLY valid JSON:
{{"literature_review_md": "...", "literature_map_md": "..."}}

Papers:
{json.dumps(compact, ensure_ascii=True)}

BibTeX keys:
{bibliography_bib}
"""
    return await call_agent_llm(
        agent_name="LITERATURE_SYNTHESIS_AGENT",
        prompt=prompt,
        client=client,
        fallback_fn=_fallback_synthesis,
        fallback_args={"topic": topic, "papers": papers},
        max_tokens=8000,
    )



def _fixture_literature(topic: str, method_style: str) -> dict[str, Any]:
    papers = []
    for idx in range(1, 21):
        key = f"fixture{idx}2020"
        papers.append({
            "source": "test_fixture",
            "paper_id": f"fixture-{idx}",
            "title": f"Fixture empirical finance paper {idx} for {topic[:48]}",
            "abstract": f"This fixture abstract discusses empirical finance methodology, evidence quality, and robustness for {topic}.",
            "year": 2000 + (idx % 24),
            "authors": [f"Author {idx}"],
            "citation_count": 100 - idx,
            "doi": f"10.0000/thrivarc.fixture.{idx}",
            "venue": "Test Journal",
            "url": "https://example.test/paper",
            "query": method_style,
            "relevance_score": 7.0,
            "citation_key": key,
            "verified": True,
        })
    bib = "\n\n".join(_bibtex_entry(paper) for paper in papers)
    synth = _fallback_synthesis(topic, papers)
    return {
        "queries": _fallback_queries(topic, method_style)["queries"],
        "papers": papers,
        "bibliography_bib": bib,
        "literature_review_md": synth["literature_review_md"],
        "literature_map_md": synth["literature_map_md"],
        "source_counts": {"test_fixture": len(papers)},
    }


async def run_literature_agent(topic: str, method_style: str, blueprint: dict[str, Any], client=None) -> dict[str, Any]:
    """Retrieve, rank, synthesize, and format literature for any research topic."""
    topic = _topic_text(topic, blueprint)
    method_style = str(method_style or blueprint.get("method_family") or "empirical finance")
    import os
    if os.getenv("ENVIRONMENT") == "test" or os.getenv("THRIVARC_STORAGE_BACKEND") == "mock":
        return _fixture_literature(topic, method_style)
    queries = await _generate_queries(topic, method_style, client)
    papers: list[dict[str, Any]] = []
    for query in queries:
        papers.extend(_semantic_papers(query))
        time.sleep(0.1)
        papers.extend(_openalex_papers(query))
        time.sleep(0.1)
        papers.extend(_arxiv_papers(query))
        time.sleep(0.1)
    papers = _dedupe(papers)
    for query in _supplemental_queries(topic, method_style):
        papers.extend(_semantic_papers(query, limit=20))
        time.sleep(0.1)
        papers.extend(_openalex_papers(query, per_page=10))
        time.sleep(0.1)
        papers.extend(_arxiv_papers(query, max_results=10))
        time.sleep(0.1)
        papers = _dedupe(papers)
        if len(papers) >= 60:
            break
    for paper in sorted(papers, key=lambda item: item.get("citation_count", 0), reverse=True)[:5]:
        if paper.get("source") == "Semantic Scholar" and paper.get("paper_id"):
            papers.extend(_semantic_references(str(paper["paper_id"])))
            time.sleep(0.1)
    papers = _dedupe(papers)
    if len(papers) < 20:
        for query in _supplemental_queries(topic, method_style):
            papers.extend(_arxiv_papers(query, max_results=10))
            papers = _dedupe(papers)
            if len(papers) >= 20:
                break
    ranked = await _rank_papers(topic, papers, client)
    used: set[str] = set()
    enriched = []
    for paper in ranked[:20]:
        enriched.append({**paper, "citation_key": _citation_key(paper, used), "verified": bool(paper.get("title") and (paper.get("doi") or paper.get("paper_id") or paper.get("url")))})
    bibliography_bib = "\n\n".join(_bibtex_entry(paper) for paper in enriched)
    synthesis = await _synthesize(topic, enriched, bibliography_bib, client)
    return {
        "queries": queries,
        "papers": enriched,
        "bibliography_bib": bibliography_bib,
        "literature_review_md": synthesis.get("literature_review_md") or _fallback_synthesis(topic, enriched)["literature_review_md"],
        "literature_map_md": synthesis.get("literature_map_md") or _fallback_synthesis(topic, enriched)["literature_map_md"],
        "source_counts": {
            "semantic_scholar_or_references": sum(1 for paper in enriched if "Semantic" in str(paper.get("source"))),
            "openalex": sum(1 for paper in enriched if paper.get("source") == "OpenAlex"),
        },
    }
