"""LM Studio API Client — Dual protocol support.

Legacy path:  /v1/chat/completions  (OpenAI-compatible, for fallback)
New path:     /api/v1/chat          (native LM Studio SSE typed events)
              /api/v1/models        (model listing)
              /api/v1/models/load   (dynamic model loading)
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

import httpx

from app.core.config import LM_STUDIO_LEGACY_URL, LM_STUDIO_V2_URL, LM_STUDIO_TIMEOUT

logger = logging.getLogger("lm_client")


# ── Typed SSE event classes ────────────────────────────────────────


@dataclass
class ChatStart:
    model_instance_id: str


@dataclass
class ModelLoadStart:
    model_instance_id: str


@dataclass
class ModelLoadProgress:
    model_instance_id: str
    progress: float


@dataclass
class ModelLoadEnd:
    model_instance_id: str
    load_time_seconds: float


@dataclass
class PromptProcessingStart:
    pass


@dataclass
class PromptProcessingProgress:
    progress: float


@dataclass
class PromptProcessingEnd:
    pass


@dataclass
class ReasoningStart:
    pass


@dataclass
class ReasoningDelta:
    content: str


@dataclass
class ReasoningEnd:
    pass


@dataclass
class ToolCallStart:
    tool: str
    provider_info: dict


@dataclass
class ToolCallArguments:
    tool: str
    arguments: dict
    provider_info: dict


@dataclass
class ToolCallSuccess:
    tool: str
    arguments: dict
    output: str
    provider_info: dict


@dataclass
class ToolCallFailure:
    reason: str
    metadata: dict


@dataclass
class MessageStart:
    pass


@dataclass
class MessageDelta:
    content: str


@dataclass
class MessageEnd:
    pass


@dataclass
class StreamError:
    error: dict


@dataclass
class ChatEnd:
    model_instance_id: str
    output: list[dict]
    stats: dict
    response_id: Optional[str] = None


LMStudioEvent = (
    ChatStart | ModelLoadStart | ModelLoadProgress | ModelLoadEnd
    | PromptProcessingStart | PromptProcessingProgress | PromptProcessingEnd
    | ReasoningStart | ReasoningDelta | ReasoningEnd
    | ToolCallStart | ToolCallArguments | ToolCallSuccess | ToolCallFailure
    | MessageStart | MessageDelta | MessageEnd
    | StreamError | ChatEnd
)


_EVENT_CLASSES = {
    "chat.start": ChatStart,
    "model_load.start": ModelLoadStart,
    "model_load.progress": ModelLoadProgress,
    "model_load.end": ModelLoadEnd,
    "prompt_processing.start": PromptProcessingStart,
    "prompt_processing.progress": PromptProcessingProgress,
    "prompt_processing.end": PromptProcessingEnd,
    "reasoning.start": ReasoningStart,
    "reasoning.delta": ReasoningDelta,
    "reasoning.end": ReasoningEnd,
    "tool_call.start": ToolCallStart,
    "tool_call.arguments": ToolCallArguments,
    "tool_call.success": ToolCallSuccess,
    "tool_call.failure": ToolCallFailure,
    "message.start": MessageStart,
    "message.delta": MessageDelta,
    "message.end": MessageEnd,
    "error": StreamError,
    "chat.end": ChatEnd,
}


# ── Client ─────────────────────────────────────────────────────────


class LMStudioClient:
    """Async client for LM Studio API — supports both legacy and v2 protocols."""

    def __init__(self):
        self.timeout = LM_STUDIO_TIMEOUT

    # ── Helpers ────────────────────────────────────────────────────

    def _legacy_url(self, path: str) -> str:
        return f"{LM_STUDIO_LEGACY_URL}{path}"

    def _v2_url(self, path: str) -> str:
        return f"{LM_STUDIO_V2_URL}{path}"

    # ── Model info (shared between legacy and v2) ──────────────────

    async def get_models_legacy(self) -> Optional[dict]:
        """Legacy /v1/models — OpenAI-compatible format."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(self._legacy_url("/models"))
                r.raise_for_status()
                return r.json()
        except httpx.RequestError as e:
            logger.warning(f"Legacy models request failed: {e}")
            return None

    async def get_models_v2(self) -> Optional[dict]:
        """New /api/v1/models — returns available + loaded instances."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(self._v2_url("/models"))
                r.raise_for_status()
                return r.json()
        except httpx.RequestError as e:
            logger.warning(f"V2 models request failed: {e}")
            return None

    async def load_model(self, model: str, **kwargs) -> Optional[dict]:
        """POST /api/v1/models/load — dynamically load a model.

        Kwargs: context_length, eval_batch_size, flash_attention,
                num_experts, offload_kv_cache_to_gpu, echo_load_config
        """
        payload = {"model": model, **kwargs}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(self._v2_url("/models/load"), json=payload)
                r.raise_for_status()
                return r.json()
        except httpx.RequestError as e:
            logger.warning(f"Model load request failed: {e}")
            return None

    # ── Legacy streaming (OpenAI-compatible) ──────────────────────

    async def chat_completion_stream_legacy(
        self, model: str, messages: list, temperature: float = 0.7, **kwargs
    ) -> AsyncGenerator[tuple[str, str], None]:
        """Stream tokens from legacy /v1/chat/completions.

        Yields (type, token) where type is 'reasoning' or 'content'.
        """
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
            **kwargs,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", self._legacy_url("/chat/completions"), json=payload
                ) as response:
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
                            if delta.get("reasoning_content"):
                                yield ("reasoning", delta["reasoning_content"])
                            if delta.get("content"):
                                yield ("content", delta["content"])
                        except json.JSONDecodeError:
                            continue
        except httpx.RequestError as e:
            logger.error(f"Legacy stream error: {e}")
            yield ("content", f"\n[Stream error: {e}]")

    async def chat_completion_legacy(
        self, model: str, messages: list, temperature: float = 0.7, **kwargs
    ) -> Optional[dict]:
        """Non-streaming completion via legacy /v1/chat/completions."""
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            **kwargs,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(
                    self._legacy_url("/chat/completions"), json=payload
                )
                r.raise_for_status()
                return r.json()
        except httpx.RequestError as e:
            logger.error(f"Legacy completion error: {e}")
            return None

    # ── V2 streaming (native LM Studio SSE events) ────────────────

    async def chat_completion_stream_v2(
        self,
        model: str,
        messages: list,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> AsyncGenerator[LMStudioEvent, None]:
        """Stream typed events from /api/v1/chat (native LM Studio SSE).

        Yields LMStudioEvent dataclass instances.
        Kwargs: top_p, top_k, min_p, repeat_penalty, max_output_tokens,
                reasoning, context_length, store, previous_response_id
        """
        payload = {
            "model": model,
            "input": messages,
            "stream": True,
            "temperature": temperature,
            "store": kwargs.pop("store", False),
            **kwargs,
        }
        if system_prompt:
            payload["system_prompt"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream(
                    "POST", self._v2_url("/chat"), json=payload
                ) as response:
                    response.raise_for_status()
                    current_event = ""
                    current_data_lines: list[str] = []

                    async for line in response.aiter_lines():
                        line = line.strip()
                        if line.startswith("event: "):
                            # Flush previous event
                            if current_event and current_data_lines:
                                yield self._parse_event(
                                    current_event, "".join(current_data_lines)
                                )
                            current_event = line[7:]
                            current_data_lines = []
                        elif line.startswith("data: "):
                            current_data_lines.append(line[6:])
                        elif line == "":
                            if current_event and current_data_lines:
                                yield self._parse_event(
                                    current_event, "".join(current_data_lines)
                                )
                            current_event = ""
                            current_data_lines = []

                    # Flush remaining
                    if current_event and current_data_lines:
                        yield self._parse_event(
                            current_event, "".join(current_data_lines)
                        )

        except httpx.RequestError as e:
            logger.error(f"V2 stream error: {e}")
            yield StreamError(
                error={"type": "connection_error", "message": str(e)}
            )

    def _parse_event(self, event_type: str, data_str: str) -> LMStudioEvent:
        """Parse an SSE event line into a typed LMStudioEvent."""
        cls = _EVENT_CLASSES.get(event_type)
        if cls is None:
            logger.warning(f"Unknown event type: {event_type}")
            return StreamError(
                error={"type": "unknown_event", "message": f"Unknown event: {event_type}"}
            )

        try:
            data = json.loads(data_str)
        except json.JSONDecodeError:
            logger.warning(f"Failed to parse event data: {data_str[:200]}")
            return StreamError(
                error={"type": "parse_error", "message": "Failed to parse event data"}
            )

        try:
            if cls is ChatStart:
                return ChatStart(model_instance_id=data["model_instance_id"])
            elif cls is ModelLoadStart:
                return ModelLoadStart(model_instance_id=data["model_instance_id"])
            elif cls is ModelLoadProgress:
                return ModelLoadProgress(
                    model_instance_id=data["model_instance_id"],
                    progress=data["progress"],
                )
            elif cls is ModelLoadEnd:
                return ModelLoadEnd(
                    model_instance_id=data["model_instance_id"],
                    load_time_seconds=data["load_time_seconds"],
                )
            elif cls is PromptProcessingStart:
                return PromptProcessingStart()
            elif cls is PromptProcessingProgress:
                return PromptProcessingProgress(progress=data["progress"])
            elif cls is PromptProcessingEnd:
                return PromptProcessingEnd()
            elif cls is ReasoningStart:
                return ReasoningStart()
            elif cls is ReasoningDelta:
                return ReasoningDelta(content=data["content"])
            elif cls is ReasoningEnd:
                return ReasoningEnd()
            elif cls is ToolCallStart:
                return ToolCallStart(
                    tool=data["tool"],
                    provider_info=data.get("provider_info", {}),
                )
            elif cls is ToolCallArguments:
                return ToolCallArguments(
                    tool=data["tool"],
                    arguments=data.get("arguments", {}),
                    provider_info=data.get("provider_info", {}),
                )
            elif cls is ToolCallSuccess:
                return ToolCallSuccess(
                    tool=data["tool"],
                    arguments=data.get("arguments", {}),
                    output=data.get("output", ""),
                    provider_info=data.get("provider_info", {}),
                )
            elif cls is ToolCallFailure:
                return ToolCallFailure(
                    reason=data.get("reason", ""),
                    metadata=data.get("metadata", {}),
                )
            elif cls is MessageStart:
                return MessageStart()
            elif cls is MessageDelta:
                return MessageDelta(content=data["content"])
            elif cls is MessageEnd:
                return MessageEnd()
            elif cls is StreamError:
                return StreamError(error=data.get("error", {}))
            elif cls is ChatEnd:
                result = data.get("result", {})
                return ChatEnd(
                    model_instance_id=result.get("model_instance_id", ""),
                    output=result.get("output", []),
                    stats=result.get("stats", {}),
                    response_id=result.get("response_id"),
                )
        except (KeyError, TypeError) as e:
            logger.warning(f"Failed to construct event {event_type}: {e}")
            return StreamError(
                error={"type": "parse_error", "message": f"Failed to parse {event_type}: {e}"}
            )

        return StreamError(
            error={"type": "unhandled", "message": f"Unhandled event: {event_type}"}
        )

    # ── V2 non-streaming ──────────────────────────────────────────

    async def chat_completion_v2(
        self,
        model: str,
        messages: list,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        **kwargs,
    ) -> Optional[dict]:
        """Non-streaming completion via /api/v1/chat.

        Returns the full response dict with output, stats, etc.
        """
        payload = {
            "model": model,
            "input": messages,
            "stream": False,
            "temperature": temperature,
            "store": kwargs.pop("store", False),
            **kwargs,
        }
        if system_prompt:
            payload["system_prompt"] = system_prompt

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(self._v2_url("/chat"), json=payload)
                r.raise_for_status()
                return r.json()
        except httpx.RequestError as e:
            logger.error(f"V2 completion error: {e}")
            return None
