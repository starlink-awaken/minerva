"""Tests for OpenAICompatibleClient."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


class TestOpenAICompatibleClient:
    """Tests for the LLM client."""

    @pytest.mark.asyncio
    async def test_generate_mock(self):
        """Test generate() with mocked HTTP response."""
        from minerva.llm.client import OpenAICompatibleClient

        client = OpenAICompatibleClient(
            base_url="http://localhost:11434/v1",
            model="qwen3:30b-a3b",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Hello, world!"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.generate(
                system="You are helpful.",
                prompt="Say hello",
                temperature=0.1,
            )

        assert result == "Hello, world!"
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert call_args[0][0].endswith("/chat/completions")
        payload = call_args[1]["json"]
        assert payload["model"] == "qwen3:30b-a3b"
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["role"] == "user"
        assert payload["temperature"] == 0.1

    @pytest.mark.asyncio
    async def test_generate_no_system(self):
        """Test generate() without system prompt."""
        from minerva.llm.client import OpenAICompatibleClient

        client = OpenAICompatibleClient(
            base_url="http://localhost:11434/v1",
            model="qwen3:30b-a3b",
        )

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "OK"}}]
        }
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response
            result = await client.generate(system=None, prompt="test")

        assert result == "OK"
        payload = mock_post.call_args[1]["json"]
        # When system is None, only user message should be present
        assert len(payload["messages"]) == 1
        assert payload["messages"][0]["role"] == "user"
