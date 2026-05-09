"""Tests for search backend implementations — mocked HTTP."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestSearchBackends:
    """Tests for search backends with mocked HTTP."""

    @pytest.mark.asyncio
    async def test_search_searxng_returns_results(self):
        """Test SearXNG backend with mocked JSON response."""
        from minerva.search.backends import search_searxng

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "results": [
                {"title": "Test Page", "url": "https://example.com", "content": "Test content"},
                {"title": "Another Page", "url": "https://example.org", "content": "More content"},
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            results = await search_searxng("test query")

        assert len(results) == 2
        assert results[0].title == "Test Page"
        assert results[0].source == "searxng"
        assert results[1].url == "https://example.org"

    @pytest.mark.asyncio
    async def test_search_searxng_handles_error(self):
        """Test SearXNG backend handles HTTP errors gracefully."""
        from minerva.search.backends import search_searxng

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = Exception("Connection refused")
            results = await search_searxng("test query")

        assert results == []  # Graceful degradation

    @pytest.mark.asyncio
    async def test_search_semantic_scholar_returns_results(self):
        """Test Semantic Scholar backend with mocked response."""
        from minerva.search.backends import search_semantic_scholar

        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "data": [
                {
                    "title": "Attention Is All You Need",
                    "url": "https://arxiv.org/abs/1706.03762",
                    "year": 2017,
                    "abstract": "The dominant sequence transduction models...",
                    "tldr": {"text": "Transformers introduced self-attention mechanism"},
                }
            ]
        }
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_resp
            results = await search_semantic_scholar("transformer")

        assert len(results) == 1
        assert results[0].title == "Attention Is All You Need"
        assert results[0].source == "scholar"
        assert "2017" in results[0].published_date
        assert results[0].snippet == "Transformers introduced self-attention mechanism"

    @pytest.mark.asyncio
    async def test_extract_jina_returns_content(self):
        """Test Jina Reader extraction with mocked response."""
        from minerva.search.backends import extract_jina

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_resp = MagicMock()
        mock_resp.text = "# Test Article\n\nThis content is long enough to pass minimum threshold." * 10
        mock_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            content = await extract_jina("https://example.com")

        assert len(content) > 200
        assert "Test Article" in content

    @pytest.mark.asyncio
    async def test_extract_bs4_with_readability(self):
        """Test BS4 extraction with readability-lxml."""
        from minerva.search.backends import extract_bs4

        mock_client = MagicMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        html = "<html><body><article><h1>Test</h1><p>Article text here that is long enough to pass.</p>" * 30 + "</article></body></html>"
        mock_resp = MagicMock()
        mock_resp.text = html
        mock_resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client):
            content = await extract_bs4("https://example.com")

        assert len(content) > 0
