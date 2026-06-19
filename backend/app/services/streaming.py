"""Streaming service — relays LM Studio SSE events to frontend WebSocket."""

import logging
import time
from typing import Optional

from app.core.events import manager
from app.services.lm_client import (
    LMStudioEvent, ChatStart, ReasoningDelta, MessageDelta, ChatEnd,
    StreamError, ToolCallStart, ToolCallArguments, ToolCallSuccess,
    ToolCallFailure, ModelLoadStart, ModelLoadProgress, ModelLoadEnd,
    PromptProcessingStart, PromptProcessingProgress, PromptProcessingEnd,
    ReasoningStart, ReasoningEnd, MessageStart, MessageEnd,
)

logger = logging.getLogger("streaming")


class EventRelay:
    """Converts LM Studio SSE events into frontend WebSocket messages.

    Tracks diagnostics and builds per-round state.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.t0: float = 0.0
        self.token_count: int = 0

    async def handle(self, event: LMStudioEvent):
        """Route an LM Studio event to the correct WS broadcast."""
        t = type(event).__name__

        if isinstance(event, ChatStart):
            self.t0 = time.time()
            self.token_count = 0
            await manager.broadcast({
                "type": "chat_start",
                "session_id": self.session_id,
                "model_instance_id": event.model_instance_id,
            })

        elif isinstance(event, ModelLoadStart):
            await manager.broadcast({
                "type": "model_load_start",
                "session_id": self.session_id,
                "model_instance_id": event.model_instance_id,
            })

        elif isinstance(event, ModelLoadProgress):
            await manager.broadcast({
                "type": "model_load_progress",
                "session_id": self.session_id,
                "progress": event.progress,
            })

        elif isinstance(event, ModelLoadEnd):
            await manager.broadcast({
                "type": "model_load_end",
                "session_id": self.session_id,
                "load_time_seconds": event.load_time_seconds,
            })

        elif isinstance(event, PromptProcessingStart):
            await manager.broadcast({
                "type": "prompt_processing_start",
                "session_id": self.session_id,
            })

        elif isinstance(event, PromptProcessingProgress):
            await manager.broadcast({
                "type": "prompt_processing_progress",
                "session_id": self.session_id,
                "progress": event.progress,
            })

        elif isinstance(event, PromptProcessingEnd):
            await manager.broadcast({
                "type": "prompt_processing_end",
                "session_id": self.session_id,
            })

        elif isinstance(event, ReasoningStart):
            await manager.broadcast({
                "type": "reasoning_start",
                "session_id": self.session_id,
            })

        elif isinstance(event, ReasoningDelta):
            await manager.broadcast({
                "type": "chat_reasoning_token",
                "session_id": self.session_id,
                "token": event.content,
            })

        elif isinstance(event, ReasoningEnd):
            await manager.broadcast({
                "type": "reasoning_end",
                "session_id": self.session_id,
            })

        elif isinstance(event, ToolCallStart):
            await manager.broadcast({
                "type": "tool_call_start",
                "session_id": self.session_id,
                "tool": event.tool,
                "provider_info": event.provider_info,
            })

        elif isinstance(event, ToolCallArguments):
            await manager.broadcast({
                "type": "chat_tool",
                "session_id": self.session_id,
                "tool_name": event.tool,
                "tool_args": event.arguments,
                "provider_info": event.provider_info,
            })

        elif isinstance(event, ToolCallSuccess):
            await manager.broadcast({
                "type": "chat_tool_result",
                "session_id": self.session_id,
                "tool_name": event.tool,
                "observation": event.output,
            })

        elif isinstance(event, ToolCallFailure):
            await manager.broadcast({
                "type": "error",
                "session_id": self.session_id,
                "message": f"Tool call failed: {event.reason}",
                "metadata": event.metadata,
            })

        elif isinstance(event, MessageStart):
            pass

        elif isinstance(event, MessageDelta):
            self.token_count += 1
            now = time.time()
            elapsed = now - self.t0 if self.t0 else 0
            tps = self.token_count / elapsed if elapsed > 0 else 0

            await manager.broadcast({
                "type": "chat_token",
                "session_id": self.session_id,
                "token": event.content,
            })

            # Periodic diagnostics every 200ms
            if elapsed > 0 and (int(elapsed * 5) > int((elapsed - 0.01) * 5)):
                await manager.broadcast({
                    "type": "chat_stream_diag",
                    "session_id": self.session_id,
                    "diagnostics": {
                        "generation_time_s": round(elapsed, 2),
                        "tokens_per_second": round(tps, 1),
                        "token_count": self.token_count,
                    },
                })

        elif isinstance(event, MessageEnd):
            pass

        elif isinstance(event, StreamError):
            await manager.broadcast({
                "type": "error",
                "session_id": self.session_id,
                "message": event.error.get("message", "Unknown streaming error"),
                "error_type": event.error.get("type", "unknown"),
            })

        elif isinstance(event, ChatEnd):
            await manager.broadcast({
                "type": "chat_stream_diag",
                "session_id": self.session_id,
                "diagnostics": {
                    "generation_time_s": round(event.stats.get("generation_time_s", time.time() - self.t0), 2),
                    "tokens_per_second": round(event.stats.get("tokens_per_second", 0), 1),
                    "token_count": event.stats.get("total_output_tokens", self.token_count),
                    "input_tokens": event.stats.get("input_tokens", 0),
                    "reasoning_tokens": event.stats.get("reasoning_output_tokens", 0),
                    "time_to_first_token": event.stats.get("time_to_first_token_seconds", 0),
                },
            })

        else:
            logger.debug(f"Unhandled LM Studio event: {t}")
