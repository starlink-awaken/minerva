"""OpenAI-compatible LLM client — single interface for Ollama (local) and DeepSeek (cloud)."""

from __future__ import annotations

import httpx


class OpenAICompatibleClient:
    """Thin wrapper around OpenAI-compatible /v1/chat/completions endpoint.

    Works with: Ollama (localhost:11434/v1), DeepSeek (api.deepseek.com/v1),
    LM Studio (localhost:1234/v1), and any OpenAI-compatible provider.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str = "ollama",
        model: str = "qwen3.6:35b-a3b-coding-nvfp4",
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    async def generate(
        self,
        system: str | None,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Send chat completion request. Returns raw text response.

        Args:
            system: System prompt (optional, None to omit)
            prompt: User prompt
            temperature: Sampling temperature (0.0-2.0)
            max_tokens: Maximum tokens in response

        Returns:
            Raw text from the model's response

        Raises:
            httpx.HTTPError: On network or HTTP failures
        """
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
