import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.lm_client import LMStudioClient


@pytest.fixture
def client():
    return LMStudioClient(base_url="http://test:1234/v1", timeout=10.0)


class TestGetModels:
    @pytest.mark.asyncio
    async def test_get_models_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"id": "test-model"}]}
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_models()
            assert result == {"data": [{"id": "test-model"}]}

    @pytest.mark.asyncio
    async def test_get_models_request_error(self, client):
        import httpx
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_models()
            assert result is None

    @pytest.mark.asyncio
    async def test_get_models_connect_error(self, client):
        import httpx
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused", request=MagicMock()))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_models()
            assert result is None


class TestChatCompletion:
    @pytest.mark.asyncio
    async def test_chat_completion_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"role": "assistant", "content": "Hello"}}]
        }
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat_completion("model-x", [{"role": "user", "content": "Hi"}])
            assert result["choices"][0]["message"]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_chat_completion_request_error(self, client):
        import httpx
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat_completion("model-x", [])
            assert result is None

    @pytest.mark.asyncio
    async def test_chat_completion_sends_correct_payload(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"choices": [{"message": {"content": "ok"}}]}
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            messages = [{"role": "user", "content": "test"}]
            await client.chat_completion("m1", messages, temperature=0.5)
            call_kwargs = mock_client.post.call_args.kwargs
            assert call_kwargs["json"]["model"] == "m1"
            assert call_kwargs["json"]["messages"] == messages
            assert call_kwargs["json"]["temperature"] == 0.5


class TestChatCompletionStream:
    @pytest.mark.asyncio
    async def test_stream_content_tokens(self, client):
        chunks = [
            b"data: " + json.dumps({"choices": [{"delta": {"content": "Hello"}}]}).encode() + b"\n",
            b"data: " + json.dumps({"choices": [{"delta": {"content": " World"}}]}).encode() + b"\n",
            b"data: [DONE]\n",
        ]

        mock_response = MagicMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.aiter_lines.return_value = AsyncIterator(chunks)
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = []
            async for ttype, token in client.chat_completion_stream("m1", []):
                tokens.append((ttype, token))
            assert tokens == [("content", "Hello"), ("content", " World")]

    @pytest.mark.asyncio
    async def test_stream_reasoning_tokens(self, client):
        chunks = [
            b"data: " + json.dumps({"choices": [{"delta": {"reasoning_content": "thinking..."}}]}).encode() + b"\n",
            b"data: " + json.dumps({"choices": [{"delta": {"content": "Answer"}}]}).encode() + b"\n",
            b"data: [DONE]\n",
        ]

        mock_response = MagicMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.aiter_lines.return_value = AsyncIterator(chunks)
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = []
            async for ttype, token in client.chat_completion_stream("m1", []):
                tokens.append((ttype, token))
            assert tokens == [("reasoning", "thinking..."), ("content", "Answer")]

    @pytest.mark.asyncio
    async def test_stream_skips_non_data_lines(self, client):
        chunks = [
            b": heartbeat\n",
            b"data: " + json.dumps({"choices": [{"delta": {"content": "A"}}]}).encode() + b"\n",
            b"data: [DONE]\n",
        ]

        mock_response = MagicMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.aiter_lines.return_value = AsyncIterator(chunks)
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = []
            async for ttype, token in client.chat_completion_stream("m1", []):
                tokens.append((ttype, token))
            assert tokens == [("content", "A")]

    @pytest.mark.asyncio
    async def test_stream_request_error(self, client):
        import httpx
        mock_response = MagicMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.aiter_lines.side_effect = httpx.RequestError("Network error")

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = []
            async for ttype, token in client.chat_completion_stream("m1", []):
                tokens.append((ttype, token))
            assert len(tokens) == 1
            assert tokens[0][0] == "content"
            assert "Error" in tokens[0][1]

    @pytest.mark.asyncio
    async def test_stream_skips_bad_json(self, client):
        chunks = [
            b"data: {invalid json}\n",
            b"data: " + json.dumps({"choices": [{"delta": {"content": "OK"}}]}).encode() + b"\n",
            b"data: [DONE]\n",
        ]

        mock_response = MagicMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.aiter_lines.return_value = AsyncIterator(chunks)
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = []
            async for ttype, token in client.chat_completion_stream("m1", []):
                tokens.append((ttype, token))
            assert tokens == [("content", "OK")]


class AsyncIterator:
    def __init__(self, items):
        self.items = items

    def __aiter__(self):
        self.idx = 0
        return self

    async def __anext__(self):
        if self.idx >= len(self.items):
            raise StopAsyncIteration
        val = self.items[self.idx]
        if callable(val):
            val = val()
        self.idx += 1
        if isinstance(val, Exception):
            raise val
        return val if isinstance(val, str) else val.decode() if isinstance(val, bytes) else str(val)
