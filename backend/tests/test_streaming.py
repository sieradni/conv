import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.lm_client import (
    ChatStart, ChatEnd, MessageStart, MessageDelta, MessageEnd,
    ReasoningStart, ReasoningDelta, ReasoningEnd,
    ToolCallStart, ToolCallArguments, ToolCallSuccess, ToolCallFailure,
    StreamError, PromptProcessingStart, PromptProcessingEnd,
)


@pytest.fixture
def relay():
    from app.services.streaming import EventRelay
    return EventRelay(session_id="test-sess")


@pytest.mark.asyncio
class TestEventRelay:
    @pytest.fixture(autouse=True)
    def mock_manager(self):
        with patch("app.services.streaming.manager") as m:
            m.broadcast = AsyncMock()
            yield m

    async def test_chat_start(self, relay, mock_manager):
        ev = ChatStart(model_instance_id="m1")
        await relay.handle(ev)
        msg = mock_manager.broadcast.call_args[0][0]
        assert msg["type"] == "chat_start"
        assert msg["model_instance_id"] == "m1"

    async def test_message_stream(self, relay, mock_manager):
        await relay.handle(MessageStart())
        await relay.handle(MessageDelta(content="Hello"))
        await relay.handle(MessageDelta(content=" World"))
        await relay.handle(MessageEnd())
        calls = mock_manager.broadcast.call_args_list
        tokens = [c[0][0]["token"] for c in calls if c[0][0]["type"] == "chat_token"]
        assert tokens == ["Hello", " World"]

    async def test_reasoning_stream(self, relay, mock_manager):
        await relay.handle(ReasoningStart())
        await relay.handle(ReasoningDelta(content="thinking..."))
        await relay.handle(ReasoningEnd())
        calls = mock_manager.broadcast.call_args_list
        types = [c[0][0]["type"] for c in calls]
        assert "reasoning_start" in types
        assert "chat_reasoning_token" in types
        assert "reasoning_end" in types

    async def test_tool_call_flow(self, relay, mock_manager):
        await relay.handle(ToolCallStart(tool="read_file", provider_info={}))
        await relay.handle(ToolCallArguments(
            tool="read_file", arguments={"path": "x.txt"}, provider_info={}
        ))
        await relay.handle(ToolCallSuccess(
            tool="read_file", arguments={"path": "x.txt"}, output="content", provider_info={}
        ))
        calls = mock_manager.broadcast.call_args_list
        types = [c[0][0]["type"] for c in calls]
        assert "tool_call_start" in types
        assert "chat_tool" in types
        assert "chat_tool_result" in types

    async def test_tool_call_failure(self, relay, mock_manager):
        await relay.handle(ToolCallFailure(
            reason="permission denied", metadata={"code": 403}
        ))
        calls = mock_manager.broadcast.call_args_list
        types = [c[0][0]["type"] for c in calls]
        assert "error" in types
        messages = [c[0][0].get("message", "") for c in calls]
        assert any("permission denied" in m for m in messages)

    async def test_stream_error(self, relay, mock_manager):
        await relay.handle(StreamError(error={"type": "timeout", "message": "connection lost"}))
        calls = mock_manager.broadcast.call_args_list
        types = [c[0][0]["type"] for c in calls]
        assert "error" in types

    async def test_chat_end_sends_diagnostics(self, relay, mock_manager):
        ev = ChatEnd(
            model_instance_id="m1",
            output=[{"type": "message", "content": "done"}],
            stats={"tokens_per_second": 15.0, "token_count": 100, "generation_time_s": 6.67},
            response_id="r1",
        )
        await relay.handle(ev)
        calls = mock_manager.broadcast.call_args_list
        types = [c[0][0]["type"] for c in calls]
        assert "chat_stream_diag" in types
        assert "diagnostics" in calls[0][0][0]

    async def test_prompt_processing(self, relay, mock_manager):
        await relay.handle(PromptProcessingStart())
        await relay.handle(PromptProcessingEnd())
        calls = mock_manager.broadcast.call_args_list
        types = [c[0][0]["type"] for c in calls]
        assert "prompt_processing_start" in types
        assert "prompt_processing_end" in types
