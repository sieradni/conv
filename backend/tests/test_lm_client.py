import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from app.services.lm_client import (
    LMStudioClient, ChatStart, MessageDelta, MessageEnd, ReasoningDelta,
    ReasoningEnd, ReasoningStart, StreamError, ChatEnd, ToolCallStart,
    ToolCallArguments, ToolCallSuccess, ToolCallFailure,
)


@pytest.fixture
def client():
    return LMStudioClient()


class TestConvertMessagesToV2Input:
    def test_user_only(self, client):
        sp, inp = LMStudioClient._convert_messages_to_v2_input(
            [{"role": "user", "content": "hello"}]
        )
        assert sp == ""
        assert inp == "[user]\nhello"

    def test_system_and_user(self, client):
        sp, inp = LMStudioClient._convert_messages_to_v2_input([
            {"role": "system", "content": "You are a bot"},
            {"role": "user", "content": "hello"},
        ])
        assert sp == "You are a bot"
        assert inp == "[user]\nhello"

    def test_multiple_messages(self, client):
        sp, inp = LMStudioClient._convert_messages_to_v2_input([
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello"},
            {"role": "user", "content": "what's up"},
        ])
        assert sp == "System prompt"
        assert "[user]\nhi" in inp
        assert "[assistant]\nhello" in inp
        assert "[user]\nwhat's up" in inp

    def test_last_takes_system(self, client):
        sp, inp = LMStudioClient._convert_messages_to_v2_input([
            {"role": "system", "content": "first"},
            {"role": "user", "content": "m1"},
            {"role": "system", "content": "second"},
        ])
        assert sp == "second"  # last system message wins

    def test_empty_messages(self, client):
        sp, inp = LMStudioClient._convert_messages_to_v2_input([])
        assert sp == ""
        assert inp == ""


class TestGetModelsLegacy:
    @pytest.mark.asyncio
    async def test_get_models_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": [{"id": "test-model"}]}
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_models_legacy()
            assert result == {"data": [{"id": "test-model"}]}

    @pytest.mark.asyncio
    async def test_get_models_request_error(self, client):
        import httpx
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_models_legacy()
            assert result is None

    @pytest.mark.asyncio
    async def test_get_models_http_error(self, client):
        import httpx
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_models_legacy()
            assert result is None


class TestGetModelsV2:
    @pytest.mark.asyncio
    async def test_get_models_v2_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"models": [{"key": "test-model", "type": "llm"}]}
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_models_v2()
            assert result["models"][0]["key"] == "test-model"

    @pytest.mark.asyncio
    async def test_get_models_v2_request_error(self, client):
        import httpx
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection refused"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_models_v2()
            assert result is None

    @pytest.mark.asyncio
    async def test_get_models_v2_http_error(self, client):
        import httpx
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.get_models_v2()
            assert result is None


class TestLoadUnloadModel:
    @pytest.mark.asyncio
    async def test_load_model_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "loaded", "instance_id": "m1"}
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.load_model("test-model", context_length=8192)
            assert result["status"] == "loaded"
            call_kwargs = mock_client.post.call_args.kwargs
            assert call_kwargs["json"]["model"] == "test-model"
            assert call_kwargs["json"]["context_length"] == 8192

    @pytest.mark.asyncio
    async def test_load_model_http_error(self, client):
        import httpx
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.load_model("x")
            assert result is None

    @pytest.mark.asyncio
    async def test_unload_model_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"status": "unloaded"}
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.unload_model("m1-instance")
            assert result["status"] == "unloaded"
            call_kwargs = mock_client.post.call_args.kwargs
            assert call_kwargs["json"]["instance_id"] == "m1-instance"

    @pytest.mark.asyncio
    async def test_unload_model_http_error(self, client):
        import httpx
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.unload_model("x")
            assert result is None


class TestChatCompletionLegacy:
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
            result = await client.chat_completion_legacy("model-x", [{"role": "user", "content": "Hi"}])
            assert result["choices"][0]["message"]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_chat_completion_request_error(self, client):
        import httpx
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat_completion_legacy("model-x", [])
            assert result is None

    @pytest.mark.asyncio
    async def test_chat_completion_http_error(self, client):
        import httpx
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat_completion_legacy("model-x", [])
            assert result is None


class TestChatCompletionV2:
    @pytest.mark.asyncio
    async def test_chat_completion_v2_success(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "output": [{"type": "message", "content": "Hello"}],
            "stats": {"tokens": 5},
        }
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat_completion_v2("m1", [{"role": "user", "content": "Hi"}])
            assert result["output"][0]["content"] == "Hello"

    @pytest.mark.asyncio
    async def test_chat_completion_v2_request_error(self, client):
        import httpx
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=httpx.RequestError("Timeout"))

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat_completion_v2("model-x", [])
            assert result is None

    @pytest.mark.asyncio
    async def test_chat_completion_v2_sends_correct_payload(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"output": [{"type": "message", "content": "ok"}]}
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            messages = [{"role": "user", "content": "test"}]
            await client.chat_completion_v2("m1", messages, temperature=0.5)
            call_kwargs = mock_client.post.call_args.kwargs
            assert call_kwargs["json"]["model"] == "m1"
            assert call_kwargs["json"]["input"] == "[user]\ntest"
            assert call_kwargs["json"]["temperature"] == 0.5
            assert call_kwargs["json"]["store"] is False
            assert call_kwargs["json"]["stream"] is False

    @pytest.mark.asyncio
    async def test_chat_completion_v2_sends_system_prompt(self, client):
        mock_response = MagicMock()
        mock_response.json.return_value = {"output": []}
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            messages = [{"role": "system", "content": "You are helpful"}, {"role": "user", "content": "hi"}]
            await client.chat_completion_v2("m1", messages)
            call_kwargs = mock_client.post.call_args.kwargs
            assert call_kwargs["json"]["system_prompt"] == "You are helpful"
            assert call_kwargs["json"]["input"] == "[user]\nhi"

    @pytest.mark.asyncio
    async def test_chat_completion_v2_http_error(self, client):
        import httpx
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            result = await client.chat_completion_v2("m1", [])
            assert result is None


class TestChatCompletionStreamLegacy:
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
            async for ttype, token in client.chat_completion_stream_legacy("m1", []):
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
            async for ttype, token in client.chat_completion_stream_legacy("m1", []):
                tokens.append((ttype, token))
            assert tokens == [("reasoning", "thinking..."), ("content", "Answer")]

    @pytest.mark.asyncio
    async def test_stream_legacy_http_error(self, client):
        import httpx
        mock_response = MagicMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "500", request=MagicMock(), response=MagicMock()
        )
        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            tokens = []
            async for ttype, token in client.chat_completion_stream_legacy("m1", []):
                tokens.append((ttype, token))
            assert len(tokens) == 1
            assert "error" in tokens[0][1].lower()


class TestChatCompletionStreamV2:
    @pytest.mark.asyncio
    async def test_stream_typed_events(self, client):
        import json
        events_sent = [
            ("event", "message.start"),
            ("data", json.dumps({"type": "message.start"})),
            ("", ""),
            ("event", "message.delta"),
            ("data", json.dumps({"content": "Hello"})),
            ("", ""),
            ("event", "message.delta"),
            ("data", json.dumps({"content": " World"})),
            ("", ""),
            ("event", "message.end"),
            ("data", json.dumps({"type": "message.end"})),
            ("", ""),
            ("event", "chat.end"),
            ("data", json.dumps({
                "result": {
                    "model_instance_id": "m1",
                    "output": [],
                    "stats": {"tokens": 5},
                }
            })),
            ("", ""),
        ]

        lines = []
        for etype, data in events_sent:
            if etype == "event":
                lines.append(f"event: {data}")
            elif etype == "data":
                lines.append(f"data: {data}")
            else:
                lines.append("")

        mock_response = MagicMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.aiter_lines.return_value = AsyncIterator([l.encode() for l in lines])
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            events = []
            async for ev in client.chat_completion_stream_v2("m1", []):
                events.append(type(ev).__name__)
            assert events == ["MessageStart", "MessageDelta", "MessageDelta", "MessageEnd", "ChatEnd"]

    @pytest.mark.asyncio
    async def test_stream_connection_error(self, client):
        import httpx
        mock_response = MagicMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.aiter_lines.side_effect = httpx.RequestError("Connection refused")

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            events = []
            async for ev in client.chat_completion_stream_v2("m1", []):
                events.append(type(ev).__name__)
            assert events == ["StreamError"]

    @pytest.mark.asyncio
    async def test_stream_http_error(self, client):
        import httpx
        mock_response = MagicMock()
        mock_response.__aenter__.return_value = mock_response
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "400", request=MagicMock(), response=MagicMock()
        )

        mock_client = MagicMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.stream.return_value = mock_response

        with patch("httpx.AsyncClient", return_value=mock_client):
            events = []
            async for ev in client.chat_completion_stream_v2("m1", []):
                events.append(type(ev).__name__)
            assert events == ["StreamError"]


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
