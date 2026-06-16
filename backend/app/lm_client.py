"""LM Studio API Client - Asynchronous communication with local LM Studio server"""

import httpx
from typing import Optional, Dict, Any


class LMStudioClient:
    """Asynchronous client for LM Studio API."""
    
    def __init__(self, base_url: str = "http://localhost:1234/v1", timeout: float = 30.0):
        """Initialize the LM Studio client.
        
        Args:
            base_url: Base URL for LM Studio server (default: http://localhost:1234/v1)
            timeout: Request timeout in seconds (default: 30.0)
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
