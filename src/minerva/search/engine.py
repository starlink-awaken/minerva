"""
Minerva Search Engine — Unified search across multiple backends.

Backend priority (Tier 1 → Tier 2):
1. SearXNG (self-hosted, free, unlimited)
2. 秘塔AI搜索 (Chinese content, paid credits)
3. Exa API (semantic web search)
4. Semantic Scholar (academic, free)
5. arXiv API (preprints, free)
6. DuckDuckGo (fallback, free)

RRF (Reciprocal Rank Fusion) merges results from all backends.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str
    full_text: str | None = None
    published_date: str | None = None
    rank_score: float = 0.0


class SearchEngine:
    """Unified multi-backend search with RRF fusion."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self._result_cache: dict[str, list[SearchResult]] = {}

    # ============================================================
    # Public API
    # ============================================================

    async def search(
        self,
        query: str,
        backends: list[str] | None = None,
        max_results: int = 25,
    ) -> list[SearchResult]:
        """Search across multiple backends in parallel.

        Args:
            query: Search query
            backends: List of backends to use (default: all enabled)
            max_results: Maximum results after deduplication and fusion

        Returns:
            Deduplicated, RRF-ranked list of search results
        """
        backends = backends or self._default_backends()

        # Parallel search across all backends
        tasks = []
        for backend in backends:
            searcher = self._get_searcher(backend)
            if searcher:
                tasks.append(self._search_backend(backend, searcher, query))

        # Gather results
        results_per_backend = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten and deduplicate
        all_results: list[SearchResult] = []
        for i, results in enumerate(results_per_backend):
            if isinstance(results, Exception):
                logger.warning("backend_search_failed", backend=backends[i], error=str(results))
                continue
            all_results.extend(results)

        # Deduplicate by URL
        seen_urls = set()
        unique_results = []
        for r in all_results:
            if r.url not in seen_urls:
                seen_urls.add(r.url)
                unique_results.append(r)

        # RRF fusion ranking
        fused = self._rrf_fuse(unique_results, results_per_backend)

        return fused[:max_results]

    async def extract_content(self, url: str) -> str:
        """Extract clean text content from a URL.

        Tries in order: Jina Reader → BeautifulSoup+readability → raw HTML
        """
        # Try Jina Reader first
        try:
            content = await self._extract_jina(url)
            if content and len(content) > 200:
                return content
        except Exception:
            pass

        # Fallback: BeautifulSoup + readability-lxml
        try:
            content = await self._extract_bs4(url)
            if content and len(content) > 200:
                return content
        except Exception:
            pass

        return f"[Could not extract content from {url}]"

    # ============================================================
    # Backend Searchers
    # ============================================================

    def _default_backends(self) -> list[str]:
        """Return list of enabled backends."""
        return (
            self.config.get("backends")
            or ["searxng", "scholar", "arxiv"]
        )

    def _get_searcher(self, backend: str):
        """Get the search function for a backend."""
        searchers = {
            "searxng": self._search_searxng,
            "metaso": self._search_metaso,
            "exa": self._search_exa,
            "scholar": self._search_semantic_scholar,
            "arxiv": self._search_arxiv,
            "ddg": self._search_duckduckgo,
        }
        return searchers.get(backend)

    async def _search_backend(self, name: str, searcher, query: str) -> list[SearchResult]:
        """Execute search on a single backend with error handling."""
        try:
            return await searcher(query)
        except Exception as exc:
            logger.error("search_backend_error", backend=name, error=str(exc))
            return []

    # --- Individual backend implementations ---

    async def _search_searxng(self, query: str) -> list[SearchResult]:
        """
        Pseudocode:
        1. GET http://localhost:8080/search?q={query}&format=json
        2. Parse JSON response: {results: [{title, url, content, engine, score}]}
        3. Return [SearchResult(title, url, snippet=content, source="searxng") ...]
        """
        ...

    async def _search_metaso(self, query: str) -> list[SearchResult]:
        """
        Pseudocode:
        1. POST to 秘塔AI搜索 API with query
        2. Parse response (structured: title, url, snippet, source_type)
        3. Return [SearchResult(title, url, snippet, source="metaso") ...]
        """
        ...

    async def _search_exa(self, query: str) -> list[SearchResult]:
        """
        Pseudocode:
        1. POST https://api.exa.ai/search with {query, num_results: 10, use_autoprompt: true}
        2. Parse {results: [{title, url, text, published_date, score}]}
        3. Return [SearchResult(title, url, snippet=text, source="exa", published_date=date) ...]
        """
        ...

    async def _search_semantic_scholar(self, query: str) -> list[SearchResult]:
        """
        Pseudocode:
        1. GET https://api.semanticscholar.org/graph/v1/paper/search?query={query}&limit=10&fields=title,url,year,abstract,tldr
        2. Parse {data: [{title, url, year, abstract, tldr: {text}}]}
        3. Return [SearchResult(title, url, snippet=tldr["text"], source="scholar", published_date=str(year)) ...]
        """
        ...

    async def _search_arxiv(self, query: str) -> list[SearchResult]:
        """
        Pseudocode:
        1. GET http://export.arxiv.org/api/query?search_query=all:{query}&max_results=10
        2. Parse Atom XML → extract title, id, summary, published
        3. Return [SearchResult(title, url=id, snippet=summary, source="arxiv", published_date=published) ...]
        """
        ...

    async def _search_duckduckgo(self, query: str) -> list[SearchResult]:
        """
        Pseudocode:
        1. DuckDuckGo HTML search (no API key needed)
        2. Parse HTML → extract result titles, URLs, snippets
        3. Return [SearchResult(title, url, snippet, source="ddg") ...]
        """
        ...

    # --- Content extraction ---

    async def _extract_jina(self, url: str) -> str:
        """
        Pseudocode:
        1. GET https://r.jina.ai/{url}
        2. Return markdown content
        """
        ...

    async def _extract_bs4(self, url: str) -> str:
        """
        Pseudocode:
        1. GET url with httpx
        2. Parse HTML with BeautifulSoup
        3. Use readability-lxml to extract main content
        4. Return clean text
        """
        ...

    # ============================================================
    # RRF Fusion
    # ============================================================

    def _rrf_fuse(
        self,
        all_results: list[SearchResult],
        per_backend: list[list[SearchResult]],
        k: int = 60,
    ) -> list[SearchResult]:
        """Reciprocal Rank Fusion across multiple backend rankings.

        RRF score = Σ 1/(k + rank_in_backend_i)

        Args:
            all_results: All unique results (already deduplicated by URL)
            per_backend: Results per backend (maintains original ranking)
            k: RRF constant (default: 60, per literature)

        Returns:
            Results sorted by RRF score (descending)
        """
        # Build URL → per-backend rank lookup
        url_ranks: dict[str, list[int]] = {}
        for backend_results in per_backend:
            if isinstance(backend_results, Exception):
                continue
            for rank, result in enumerate(backend_results):
                if result.url not in url_ranks:
                    url_ranks[result.url] = []
                url_ranks[result.url].append(rank + 1)  # 1-indexed

        # Compute RRF scores
        rrf_scores: dict[str, float] = {}
        for url, ranks in url_ranks.items():
            rrf_scores[url] = sum(1.0 / (k + r) for r in ranks)

        # Assign scores and sort
        for result in all_results:
            result.rank_score = rrf_scores.get(result.url, 0.0)

        all_results.sort(key=lambda r: r.rank_score, reverse=True)
        return all_results

    # ============================================================
    # Content deduplication
    # ============================================================

    @staticmethod
    def content_hash(text: str) -> str:
        """SHA-256 hash for content deduplication."""
        return hashlib.sha256(text.encode()).hexdigest()[:16]
