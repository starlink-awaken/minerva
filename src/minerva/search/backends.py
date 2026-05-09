"""Search backend implementations — SearXNG, Semantic Scholar, Jina, BS4."""

from __future__ import annotations

import httpx
from bs4 import BeautifulSoup

from minerva.search.engine import SearchResult


# ============================================================
# SearXNG Backend
# ============================================================

async def search_searxng(query: str, base_url: str = "http://localhost:8080", max_results: int = 10) -> list[SearchResult]:
    """Search via self-hosted SearXNG meta-search engine.

    SearXNG aggregates results from 70+ engines (Google, Bing, DuckDuckGo, Wikipedia, etc.)
    and returns structured JSON.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{base_url}/search",
                params={"q": query, "format": "json", "categories": "general"},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    results = []
    for item in data.get("results", [])[:max_results]:
        results.append(SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=item.get("content", "")[:500],
            source="searxng",
            published_date=item.get("publishedDate"),
        ))
    return results


# ============================================================
# Semantic Scholar Backend
# ============================================================

async def search_semantic_scholar(query: str, max_results: int = 10) -> list[SearchResult]:
    """Search academic papers via Semantic Scholar API (free, no key required).

    Returns paper titles, abstracts, TLDR summaries, and URLs.
    """
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                params={
                    "query": query,
                    "limit": max_results,
                    "fields": "title,url,year,abstract,tldr",
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    results = []
    for paper in data.get("data", []):
        tldr = paper.get("tldr", {})
        snippet = (tldr.get("text") or paper.get("abstract") or "")[:500]
        results.append(SearchResult(
            title=paper.get("title", ""),
            url=paper.get("url", f"https://api.semanticscholar.org/paper/{paper.get('paperId', '')}"),
            snippet=snippet,
            source="scholar",
            published_date=str(paper.get("year", "")),
        ))
    return results


# ============================================================
# Jina Reader — Content Extraction
# ============================================================

async def extract_jina(url: str, api_key: str | None = None) -> str:
    """Extract clean markdown content from URL using Jina Reader API.

    Free tier: 10M tokens/month without API key.
    With API key: 500-5000 RPM.
    """
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"https://r.jina.ai/{url}",
                headers=headers,
            )
            resp.raise_for_status()
            content = resp.text
            if len(content) > 200:
                return content
    except Exception:
        pass

    return ""


# ============================================================
# BS4 + readability — Content Extraction Fallback
# ============================================================

async def extract_bs4(url: str) -> str:
    """Extract main content from URL using BeautifulSoup + readability-lxml.

    Fallback when Jina Reader is unavailable or rate-limited.
    """
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url, headers={"User-Agent": "Minerva/0.1 Research Bot"})
            resp.raise_for_status()
            html = resp.text
    except Exception:
        return ""

    try:
        from readability import Document
        doc = Document(html)
        content_html = doc.summary()
        soup = BeautifulSoup(content_html, "html.parser")
        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:10000] if len(text) > 200 else ""
    except ImportError:
        # Fallback: basic BeautifulSoup extraction
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        return text[:10000] if len(text) > 200 else ""
