"""Agent service — the ReAct loop orchestrator."""

import asyncio
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Optional

from app.core.config import (
    MAX_CHAT_ROUNDS, MAX_TOOL_OBSERVATION_LENGTH, MAX_DETAIL_OBSERVATION_LENGTH,
    REVIEW_TOOLS, SANDBOX_DIR,
)
from app.core.events import manager
from app.core.session import get_conversation
from app.memory_graph import get_memory_graph
from app.prompts import CHAT_SYSTEM_PROMPT, SLEEP_SYSTEM_PROMPT
from app.services.lm_client import LMStudioClient, ChatEnd, ChatStart, MessageDelta, ReasoningDelta, StreamError
from app.services.streaming import EventRelay
from app.services.tool_executor import get_executor
from app.services.overseer import OverseerAgent


logger = logging.getLogger("agent")


# Track active tasks for cancellation
_chat_tasks: dict[str, asyncio.Task] = {}


def get_active_chat_tasks() -> dict[str, asyncio.Task]:
    return _chat_tasks


# ── Tool call parsing ──────────────────────────────────────────────


def extract_tool_call(content: str) -> Optional[dict[str, Any]]:
    """Extract a tool call from LLM response text.

    Supports all known formats:
      - ```json {"tool":"name","args":{...}} ```
      - <|tool_call|>call:name{...}</tool_call|> (flexible pipe variants)
      - {"tool":"name","args":{...}}  (bare JSON)
      - {"tool_name":"name","tool_args":{...}}  (task system JSON)
    """
    tag_pattern = r'<\|?tool_call\|?>'
    m = re.search(tag_pattern, content)
    if m:
        start_idx = m.start()
        brace_start = content.find('{', m.end())
        if brace_start != -1:
            between = content[m.end():brace_start]
            func_match = re.search(r'call:\s*(\w+)', between)
            tool_name = func_match.group(1) if func_match else ''
            if not tool_name:
                word_m = re.search(r'(\w+)\s*\{', between)
                if word_m:
                    tool_name = word_m.group(1)
            depth = 0
            args_end = brace_start
            for i in range(brace_start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        args_end = i + 1
                        break
            raw_args = content[brace_start:args_end]
            if tool_name:
                parsed_args = _parse_js_object(raw_args)
                if parsed_args is not None:
                    return {"tool": tool_name, "args": parsed_args}

    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict) and "tool" in data:
                return data
        except (json.JSONDecodeError, KeyError):
            pass

    for key_pattern in [r'"tool"\s*:', r'"tool_name"\s*:']:
        m = re.search(r'\{\s*' + key_pattern, content, re.DOTALL)
        if m:
            try:
                start = m.start()
                depth = 0
                end = start
                for i in range(start, len(content)):
                    if content[i] == '{':
                        depth += 1
                    elif content[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                data = json.loads(content[start:end])
                if isinstance(data, dict):
                    tool = data.get("tool") or data.get("tool_name", "")
                    args = data.get("args") or data.get("tool_args", {})
                    if tool:
                        return {"tool": tool, "args": args}
            except (json.JSONDecodeError, KeyError):
                pass

    return None


def find_tool_call_start(content: str) -> int:
    """Find where the first tool call JSON block starts. Returns -1 if not found."""
    tag_m = re.search(r'<\|?tool_call\|?>', content)
    if tag_m:
        return tag_m.start()
    fence_m = re.search(r'```(?:json)?\s*\{.*?(?:"tool"|"tool_name").*?\}', content, re.DOTALL)
    if fence_m:
        return fence_m.start()
    for key_pattern in [r'"tool"\s*:', r'"tool_name"\s*:']:
        m = re.search(r'\{\s*' + key_pattern, content)
        if m:
            return m.start()
    return -1


def find_tool_call_end(content: str) -> int:
    tag_pattern = r'<\|?tool_call\|?>'
    m = re.search(tag_pattern, content)
    if m:
        brace_start = content.find('{', m.end())
        if brace_start != -1:
            depth = 0
            for i in range(brace_start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        close_tag = re.search(tag_pattern, content[i + 1:])
                        return i + 1 + (close_tag.end() if close_tag else 0)
    m = re.search(r'```(?:json)?\s*\{', content)
    if m:
        close = content.find('```', m.end())
        if close != -1:
            return close + 3
    for key_pattern in [r'"tool"\s*:', r'"tool_name"\s*:']:
        m = re.search(r'\{\s*' + key_pattern, content)
        if m:
            depth = 0
            for i in range(m.start(), len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        return i + 1
    return len(content)


def _parse_js_object(text: str) -> Optional[dict[str, Any]]:
    text = text.strip()
    if text.startswith('{') and text.endswith('}'):
        text = text[1:-1].strip()
    if not text:
        return {}

    try:
        return json.loads('{' + text + '}')
    except json.JSONDecodeError:
        pass

    normalized = _normalize_js_to_json(text)
    try:
        return json.loads('{' + normalized + '}')
    except json.JSONDecodeError:
        pass

    result = {}
    parts = _split_js_values(text)
    for part in parts:
        sep = None
        for s in ('=', ':'):
            if s in part:
                idx = part.index(s)
                if sep is None or idx < part.index(sep):
                    sep = (s, idx)
        if sep is None:
            continue
        sep_char, sep_idx = sep
        key = part[:sep_idx].strip().strip('"').strip("'")
        value = part[sep_idx + 1:].strip()
        result[key] = _parse_js_value(value)
    return result


def _parse_js_value(value: str) -> Any:
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value == 'true':
        return True
    if value == 'false':
        return False
    if value == 'null' or value == 'None':
        return None
    if value.startswith('[') and value.endswith(']'):
        inner = value[1:-1].strip()
        if not inner:
            return []
        items = _split_js_values(inner)
        return [_parse_js_value(item.strip()) for item in items]
    if value.startswith('{') and value.endswith('}'):
        return _parse_js_object(value)
    try:
        return int(value) if '.' not in value else float(value)
    except (ValueError, TypeError):
        return value


def _split_js_values(text: str) -> list:
    parts = []
    current = ""
    depth = 0
    in_str = False
    str_char = None
    for ch in text:
        if in_str:
            current += ch
            if ch == str_char:
                in_str = False
        elif ch in ('"', "'"):
            in_str = True
            str_char = ch
            current += ch
        elif ch in ('{', '['):
            depth += 1
            current += ch
        elif ch in ('}', ']'):
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    return parts


def _normalize_js_to_json(text: str) -> str:
    result = []
    parts = _split_js_values(text)
    for part in parts:
        sep_idx = -1
        depth = 0
        in_str = False
        str_char = None
        for i, ch in enumerate(part):
            if in_str:
                if ch == str_char:
                    in_str = False
            elif ch in ('"', "'"):
                in_str = True
                str_char = ch
            elif ch in ('{', '['):
                depth += 1
            elif ch in ('}', ']'):
                depth -= 1
            elif ch in ('=', ':') and depth == 0 and not in_str:
                sep_idx = i
                break
        if sep_idx == -1:
            result.append(part)
            continue
        key = part[:sep_idx].strip().strip('"').strip("'")
        val = part[sep_idx + 1:].strip()
        result.append(f'"{key}": {val}')
    return ', '.join(result)


def count_tokens(text: str) -> int:
    return max(1, len(text) // 4)


# ── ReAct Loop ─────────────────────────────────────────────────────


async def build_context_messages(
    user_message: str,
    sleep_mode: bool = False,
) -> tuple[list[dict], str]:
    """Build the messages array for the LLM call.

    Returns (messages, memory_context).
    """
    conv = get_conversation()
    system_prompt = SLEEP_SYSTEM_PROMPT if sleep_mode else CHAT_SYSTEM_PROMPT

    # Memory context
    graph = get_memory_graph()
    if sleep_mode:
        now_ts = time.time()
        earliest = min((n.created_at for n in graph._nodes.values()), default=now_ts)
        memory_context = graph.generate_sleep_context(earliest, now_ts)
    else:
        memory_context = graph.current_context()

    # Todo context
    todo_context = ""
    from app.core.config import TODO_FILE
    if TODO_FILE.exists():
        try:
            todo_data = json.loads(TODO_FILE.read_text(encoding="utf-8"))
            todo_items = todo_data.get("todo_items", [])
            completed_items = todo_data.get("completed_items", [])
            parts = []
            if todo_items:
                parts.append("Pending: " + json.dumps(todo_items))
            if completed_items:
                parts.append("Completed: " + json.dumps(completed_items))
            if parts:
                todo_context = "\n\n## Current Todo List\n" + "\n".join(parts)
        except Exception:
            pass

    full_system = (
        system_prompt
        + "\n\n## Memory Context (always accessible; use read_detail for full details)\n"
        + memory_context
        + todo_context
    )

    messages = [{"role": "system", "content": full_system}]

    # Add history (skip for sleep mode)
    if not sleep_mode:
        history = conv.get_context_messages()
        messages.extend(history)

    # Add user message
    if user_message == "__CONTINUE__":
        if history and history[-1]["role"] == "user":
            pass  # Let agent respond to existing user message
        else:
            messages.append({"role": "user", "content": "Please continue."})
    else:
        messages.append({"role": "user", "content": user_message})

    return messages, memory_context


async def run_agent_loop(
    session_id: str,
    user_message: str,
    sleep_mode: bool = False,
):
    """Run the ReAct agent loop.

    Calls LM Studio via v2 API, streams events to frontend,
    detects and executes tool calls, and loops until done.
    """
    lm_client = LMStudioClient()
    overseer = OverseerAgent()
    executor = get_executor()
    conv = get_conversation()
    relay = EventRelay(session_id)

    # Ensure we have a model
    model_id = await _resolve_model(lm_client)
    if not model_id:
        await manager.broadcast({
            "type": "chat_done", "session_id": session_id,
            "response": "[Error: No model available. Load a model first.]",
        })
        return

    conv.reset_flow_control()

    logger.info(f"[{session_id}] Starting agent loop (sleep={sleep_mode}, model={model_id})")

    # Save user message to history
    if user_message != "__CONTINUE__":
        display_msg = "Please continue." if user_message == "__CONTINUE__" else user_message
        conv.add_message("user", display_msg)

    await manager.broadcast({
        "type": "chat_start", "session_id": session_id, "message": user_message,
    })

    for rnd in range(MAX_CHAT_ROUNDS):
        if conv.stop_requested:
            await manager.broadcast({
                "type": "chat_done", "session_id": session_id,
                "response": "[Stopped]",
            })
            return

        # Build messages
        messages, memory_context = await build_context_messages(user_message, sleep_mode)
        # For subsequent rounds, all history is already in messages
        if rnd > 0:
            messages, _ = await build_context_messages("__CONTINUE__", sleep_mode)

        await manager.broadcast({"type": "llm_call", "session_id": session_id})

        content_buffer = ""
        output_items = []

        # ── Streaming LLM call (v2 API) ──────────────────────────
        try:
            async for event in lm_client.chat_completion_stream_v2(
                model=model_id,
                messages=messages,
                temperature=0.7,
            ):
                if conv.stop_requested and not sleep_mode:
                    raise asyncio.CancelledError()

                await relay.handle(event)

                # Accumulate content
                if isinstance(event, ChatStart):
                    conv.model_instance_id = event.model_instance_id
                elif isinstance(event, ReasoningDelta):
                    pass
                elif isinstance(event, MessageDelta):
                    content_buffer += event.content
                elif isinstance(event, ChatEnd):
                    output_items = event.output
                    # Update conversation stats
                    stats = event.stats
                    await manager.broadcast({
                        "type": "chat_stream_diag",
                        "session_id": session_id,
                        "diagnostics": {
                            "generation_time_s": stats.get("generation_time_s", 0),
                            "tokens_per_second": stats.get("tokens_per_second", 0),
                            "token_count": stats.get("total_output_tokens", 0),
                            "input_tokens": stats.get("input_tokens", 0),
                            "reasoning_tokens": stats.get("reasoning_output_tokens", 0),
                            "time_to_first_token": stats.get("time_to_first_token_seconds", 0),
                        },
                    })

        except asyncio.CancelledError:
            if content_buffer.strip():
                conv.add_message("assistant", content_buffer)
            return

        # If chat.end never arrived (e.g. stream error), use accumulated content
        stats = {}
        for item in output_items:
            if item.get("type") == "message":
                txt = item.get("content", "")
                if txt and not content_buffer:
                    content_buffer = txt

        # ── Pause check ──────────────────────────────────────────
        if conv.pause_requested:
            await manager.broadcast({"type": "chat_paused", "session_id": session_id})
            await conv.resume_event.wait()
            conv.resume_event.clear()
            if conv.stop_requested and not sleep_mode:
                await manager.broadcast({
                    "type": "chat_done", "session_id": session_id,
                    "response": "[Stopped]",
                })
                return

        # ── Detect tool call ─────────────────────────────────────
        tool_call = extract_tool_call(content_buffer)

        if not tool_call:
            # No tool call — conversation is done
            await manager.broadcast({
                "type": "chat_done", "session_id": session_id,
                "response": content_buffer,
            })
            if content_buffer.strip():
                conv.add_message("assistant", content_buffer)
            return

        # ── Extract text before tool ─────────────────────────────
        tool_start = find_tool_call_start(content_buffer)
        clean_text = content_buffer[:tool_start].strip() if tool_start > 0 else ""

        tool_name = tool_call.get("tool", "")
        tool_args = tool_call.get("args", {})

        # Broadcast tool card
        await manager.broadcast({
            "type": "chat_tool", "session_id": session_id,
            "tool_name": tool_name, "tool_args": tool_args,
            "clean_text": clean_text,
        })

        # ── Approval gate ────────────────────────────────────────
        approved = True
        if sleep_mode and tool_name == "finish_task":
            pass
        elif tool_name in REVIEW_TOOLS and tool_name not in ("ask_user",):
            mode = conv.approval_mode

            if mode == "CHECK_WITH_OVERSEER":
                previous_block = ""
                if len(messages) >= 2:
                    for m in messages[-2:]:
                        role = m.get("role", "unknown")
                        c = m.get("content", "")
                        previous_block += f"[{role}]: {c}\n"

                await manager.broadcast({
                    "type": "overseer_review_start", "session_id": session_id,
                })

                review = await overseer.review_action(
                    tool_name=tool_name, tool_args=tool_args,
                    thought=content_buffer, previous_block=previous_block,
                    sandbox_dir=str(SANDBOX_DIR),
                )
                review_status = review.get("status", "REJECTED").upper()
                review_reasoning = review.get("reasoning", "")
                review_feedback = review.get("feedback", "")
                approved = review_status == "APPROVED"

                if review_reasoning:
                    # Stream overseer reasoning
                    await manager.broadcast({
                        "type": "overseer_review_token",
                        "session_id": session_id,
                        "token": review_reasoning,
                    })

                await manager.broadcast({
                    "type": "overseer_review", "session_id": session_id,
                    "status": review_status, "reasoning": review_reasoning,
                    "feedback": review_feedback, "approved": approved,
                })

                if not approved:
                    observation = f"[Overseer rejected: {review_feedback}]"
                    await manager.broadcast({
                        "type": "chat_tool_result", "session_id": session_id,
                        "observation": observation,
                    })
                    messages.append({"role": "assistant", "content": content_buffer})
                    messages.append({
                        "role": "user",
                        "content": f"Overseer rejected your {tool_name} action. Feedback: {review_feedback}. Try a different approach.",
                    })
                    continue

            elif mode == "WAIT_FOR_USER":
                await manager.broadcast({
                    "type": "awaiting_user_approval", "session_id": session_id,
                    "tool_name": tool_name, "tool_args": tool_args,
                    "thought": f"The agent wants to run: {tool_name}",
                })
                try:
                    approval = await asyncio.wait_for(
                        conv.user_response_queue.get(), timeout=300.0
                    )
                except asyncio.TimeoutError:
                    await manager.broadcast({
                        "type": "chat_tool_result", "session_id": session_id,
                        "observation": "[Approval timed out]",
                    })
                    await manager.broadcast({
                        "type": "chat_done", "session_id": session_id,
                        "response": "[Approval timed out]",
                    })
                    return

                if not approval.get("approved", False):
                    feedback = approval.get("feedback", "User rejected")
                    observation = f"[Rejected: {feedback}]"
                    await manager.broadcast({
                        "type": "chat_tool_result", "session_id": session_id,
                        "observation": observation,
                    })
                    messages.append({"role": "assistant", "content": content_buffer})
                    messages.append({
                        "role": "user",
                        "content": f"Your {tool_name} action was rejected. Feedback: {feedback}. Try a different approach.",
                    })
                    continue

        # ── Execute tool ─────────────────────────────────────────
        if approved:
            observation = await asyncio.to_thread(executor.execute, tool_name, **tool_args)
        else:
            observation = "[Rejected]"

        await manager.broadcast({
            "type": "chat_tool_result", "session_id": session_id,
            "tool_name": tool_name, "observation": observation,
        })

        # ── Handle special tools ─────────────────────────────────
        if tool_name == "finish_task":
            summary = tool_args.get("summary", observation.replace("[FINISH_TASK:", "").rstrip("]"))
            await manager.broadcast({
                "type": "task_complete", "session_id": session_id,
                "status": "COMPLETED", "summary": summary,
            })

            if sleep_mode:
                last_user_msg = messages[-1]["content"] if messages else ""
                if "reflect on your work" in last_user_msg.lower():
                    conv.sleep_mode = False
                    await manager.broadcast({
                        "type": "chat_done", "session_id": session_id,
                        "response": f"[Sleep complete] {summary}",
                    })
                    return
                messages.append({"role": "assistant", "content": content_buffer})
                messages.append({
                    "role": "user",
                    "content": "Now reflect on your work. Consider calling refine_memory_methodology to update your memory management rules. When you are truly finished, call finish_task again.",
                })
                continue
            else:
                conv.add_message("assistant", content_buffer)
                await manager.broadcast({
                    "type": "chat_done", "session_id": session_id,
                    "response": summary,
                })
                return

        if tool_name == "ask_user":
            question = tool_args.get("question", tool_args.get("message", "I have a question."))
            await manager.broadcast({
                "type": "ask_user", "session_id": session_id, "question": question,
            })
            try:
                answer = await asyncio.wait_for(conv.user_response_queue.get(), timeout=600.0)
            except asyncio.TimeoutError:
                answer = "[User did not respond]"
            answer_text = answer.get("feedback", answer) if isinstance(answer, dict) else str(answer)
            messages.append({"role": "assistant", "content": content_buffer})
            messages.append({
                "role": "user",
                "content": f"User answered your question: {answer_text}",
            })
            continue

        if tool_name == "set_goal":
            new_goal = tool_args.get("goal", "")
            conv.current_goal = new_goal
            conv._save()
            await manager.broadcast({
                "type": "goal_set", "session_id": session_id, "goal": new_goal,
            })

        # ── Feed back to LLM ────────────────────────────────────
        obs_trunc = MAX_DETAIL_OBSERVATION_LENGTH if tool_name == "read_detail" else MAX_TOOL_OBSERVATION_LENGTH
        messages.append({"role": "assistant", "content": content_buffer})
        continuation = "Continue your memory consolidation work." if sleep_mode else "Continue your response naturally."
        messages.append({
            "role": "user",
            "content": f"Tool {tool_name} returned:\n{observation[:obs_trunc]}\n\n{continuation}",
        })

        # Reset user_message so loop continues
        user_message = "__CONTINUE__"

    await manager.broadcast({
        "type": "chat_done", "session_id": session_id,
        "response": "[I've completed what I can do. Feel free to ask for more.]",
    })


async def _resolve_model(lm_client: LMStudioClient) -> Optional[str]:
    """Get the current model ID from LM Studio."""
    conv = get_conversation()
    if conv.model_instance_id:
        return conv.model_instance_id

    # Try v2 API first
    models = await lm_client.get_models_v2()
    if models and "models" in models:
        for m in models["models"]:
            if m.get("type") == "llm" and m.get("loaded_instances"):
                instance = m["loaded_instances"][0]
                conv.model_instance_id = instance["id"]
                conv._save()
                return instance["id"]

    # Legacy fallback
    legacy = await lm_client.get_models_legacy()
    if legacy and "data" in legacy and legacy["data"]:
        model_id = legacy["data"][0]["id"]
        conv.model_instance_id = model_id
        conv._save()
        return model_id

    return None
