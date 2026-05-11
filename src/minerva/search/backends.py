"""Search backend implementations — SearXNG, Semantic Scholar, DuckDuckGo, Jina, BS4."""

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
# Exa API Backend
# ============================================================

async def search_exa(query: str, api_key: str, max_results: int = 10) -> list[SearchResult]:
    """Search via Exa API — semantic web search with content extraction.

    Requires API key from https://exa.ai. Free tier: 1000 queries/month.
    """
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://api.exa.ai/search",
                headers={
                    "x-api-key": api_key,
                    "Content-Type": "application/json",
                },
                json={"query": query, "numResults": max_results, "useAutoprompt": True},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    results = []
    for item in data.get("results", []):
        snippet = item.get("text", "")[:500] if item.get("text") else ""
        published = item.get("publishedDate", "")
        results.append(SearchResult(
            title=item.get("title", ""),
            url=item.get("url", ""),
            snippet=snippet,
            source="exa",
            published_date=published[:10] if published else "",
        ))
    return results


# ============================================================
# arXiv Backend
# ============================================================

async def search_arxiv(query: str, max_results: int = 10) -> list[SearchResult]:
    """Search preprints via arXiv API (free, no key required).

    Returns paper titles, abstracts, authors, and arXiv URLs.
    """
    import urllib.parse
    try:
        encoded = urllib.parse.quote(query)
        url = f"http://export.arxiv.org/api/query?search_query=all:{encoded}&start=0&max_results={max_results}&sortBy=relevance&sortOrder=descending"
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            raw = resp.text
    except Exception:
        return []

    results = []
    try:
        import xml.etree.ElementTree as ET
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        root = ET.fromstring(raw)
        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            link_el = entry.find("atom:id", ns)
            if link_el is None:
                link_el = entry.find("atom:link", ns)
            published_el = entry.find("atom:published", ns)
            authors = [a.find("atom:name", ns).text for a in entry.findall("atom:author", ns) if a.find("atom:name", ns) is not None]

            title = title_el.text.strip() if title_el is not None and title_el.text else ""
            snippet = summary_el.text.strip()[:500] if summary_el is not None and summary_el.text else ""
            url = link_el.text.strip() if link_el is not None and link_el.text else ""
            published = published_el.text[:10] if published_el is not None and published_el.text else ""

            if title:
                results.append(SearchResult(
                    title=title,
                    url=url,
                    snippet=f"{', '.join(authors[:3])}. {snippet}" if authors else snippet,
                    source="arxiv",
                    published_date=published,
                ))
    except Exception:
        pass
    return results


# ============================================================
# 秘塔AI搜索 Backend
# ============================================================

async def search_metaso(query: str, api_key: str | None = None, max_results: int = 10) -> list[SearchResult]:
    """Search via 秘塔AI搜索 (Metaso) — Chinese-optimized AI search.

    Requires API key from https://metaso.cn/search-api/api-keys
    Credits: ~3 per search, free 5000 on signup.
    """
    if not api_key:
        api_key = __import__("os").environ.get("METASO_API_KEY", "")
    if not api_key:
        return []

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                "https://metaso.cn/api/v1/search",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json={
                    "q": query,
                    "scope": "webpage",
                    "size": str(max_results),
                    "includeSummary": False,
                    "includeRawContent": False,
                    "conciseSnippet": False,
                },
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        return []

    results = []
    for item in data.get("webpages", []):
        results.append(SearchResult(
            title=item.get("title", ""),
            url=item.get("link", ""),
            snippet=item.get("snippet", "")[:500],
            source="metaso",
            published_date=item.get("date", ""),
        ))
    return results


# ============================================================
# DuckDuckGo Backend
# ============================================================

async def search_duckduckgo(query: str, max_results: int = 10) -> list[SearchResult]:
    """Search web via DuckDuckGo (free, no API key required).

    Uses duckduckgo-search library as SearXNG alternative when Docker unavailable.
    """
    try:
        from ddgs import DDGS
        loop = __import__("asyncio").get_event_loop()
        results_raw = await loop.run_in_executor(
            None, lambda: list(DDGS().text(query, max_results=max_results))
        )
    except Exception:
        return []

    results = []
    for item in results_raw:
        results.append(SearchResult(
            title=item.get("title", ""),
            url=item.get("href", ""),
            snippet=item.get("body", "")[:500],
            source="ddg",
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
