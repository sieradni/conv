"""LM Studio API Client - Asynchronous communication with local LM Studio server"""

import json
import httpx
from typing import Optional, Dict, Any, AsyncGenerator


class LMStudioClient:
    """Asynchronous client for LM Studio API."""

    def __init__(self, base_url: str = "http://localhost:1234/v1", timeout: float = 120.0):
        """Initialize the LM Studio client.

        Args:
            base_url: Base URL for LM Studio server (default: http://localhost:1234/v1)
            timeout: Request timeout in seconds (default: 120.0)
        """
        self.base_url = base_url
        self.timeout = timeout

    async def get_models(self) -> Optional[Dict[str, Any]]:
        """Fetch available models from LM Studio.

        Returns:
            Dictionary with models data, or None if request fails.
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(f"{self.base_url}/models")
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            print(f"Error fetching models: {e}")
            return None

    async def chat_completion(self, model: str, messages: list, temperature: float = 0.7) -> Optional[Dict[str, Any]]:
        """Send a chat completion request to LM Studio.

        Args:
            model: Model ID to use for completion
            messages: List of message dictionaries with 'role' and 'content'
            temperature: Sampling temperature (default: 0.7)

        Returns:
            Response JSON, or None if request fails.
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/chat/completions", json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.RequestError as e:
            print(f"Error in chat completion: {e}")
            return None

    async def chat_completion_stream(
        self, model: str, messages: list, temperature: float = 0.7
    ) -> AsyncGenerator[tuple, None]:
        """Stream a chat completion response from LM Studio token by token.

        Yields:
            (type, token) tuples where type is 'reasoning' or 'content'.
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        data_str = line[6:].strip()
                        if data_str == "[DONE]":
                            return
                        try:
                            chunk = json.loads(data_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content")
                            reasoning = delta.get("reasoning_content")
                            if reasoning:
                                yield ("reasoning", reasoning)
                            if content:
                                yield ("content", content)
                        except json.JSONDecodeError:
                            continue
        except httpx.RequestError as e:
            print(f"Error in streaming chat completion: {e}")
            yield ("content", f"\n[Error: {e}]")
