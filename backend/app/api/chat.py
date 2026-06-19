"""Chat endpoints — the main interaction with the agent."""

import asyncio
import logging
from pydantic import BaseModel
from typing import Optional

from fastapi import APIRouter, BackgroundTasks

from app.core.session import get_conversation
from app.core.events import manager
from app.services.agent_service import run_agent_loop, get_active_chat_tasks

logger = logging.getLogger("api.chat")
router = APIRouter(tags=["chat"])


class ChatPayload(BaseModel):
    message: str
    session_id: Optional[str] = None


class SleepStartPayload(BaseModel):
    message: str = ""


# ── Main chat — triggers agent loop ────────────────────────────────


@router.post("/api/chat")
async def chat(payload: ChatPayload, background_tasks: BackgroundTasks):
    """Send a message and trigger the agent ReAct loop."""
    conv = get_conversation()
    session_id = conv.session_id

    # Cancel any existing task
    tasks = get_active_chat_tasks()
    existing = tasks.get(session_id)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(
        run_agent_loop(session_id, payload.message, sleep_mode=False)
    )
    task.add_done_callback(lambda _: tasks.pop(session_id, None))
    tasks[session_id] = task

    return {"status": "ok", "session_id": session_id}


# ── Send message without triggering agent ─────────────────────────


@router.post("/api/chat/send")
async def chat_send(payload: ChatPayload):
    """Post a user message to history without triggering the agent."""
    conv = get_conversation()
    if payload.message:
        conv.add_message("user", payload.message)
        await manager.broadcast({
            "type": "user_message",
            "session_id": conv.session_id,
            "message": payload.message,
        })
    return {"status": "ok", "session_id": conv.session_id}


# ── Stop / Pause / Resume ──────────────────────────────────────────


@router.post("/api/chat/stop")
async def stop_chat():
    """Stop the current chat response."""
    conv = get_conversation()
    conv.stop_requested = True

    tasks = get_active_chat_tasks()
    existing = tasks.get(conv.session_id)
    if existing and not existing.done():
        existing.cancel()
        await manager.broadcast({
            "type": "chat_done",
            "session_id": conv.session_id,
            "response": "[Stopped]",
        })

    return {"status": "stopped"}


@router.post("/api/chat/pause")
async def pause_chat():
    """Pause after current LLM response finishes."""
    conv = get_conversation()
    conv.pause_requested = True
    return {"status": "pausing"}


@router.post("/api/chat/resume")
async def resume_chat():
    """Resume a paused chat."""
    conv = get_conversation()
    conv.pause_requested = False
    conv.resume_event.set()
    return {"status": "resumed"}


# ── Approval responses ─────────────────────────────────────────────


class UserApprovalPayload(BaseModel):
    approved: bool
    feedback: Optional[str] = None


@router.post("/api/approve")
async def submit_approval(payload: UserApprovalPayload):
    """Submit user approval/response for pending agent request."""
    conv = get_conversation()
    await conv.user_response_queue.put({
        "approved": payload.approved,
        "feedback": payload.feedback,
    })
    return {"status": "received"}


# ── Sleep mode ─────────────────────────────────────────────────────


@router.post("/api/chat/sleep-start")
async def sleep_start(payload: SleepStartPayload):
    """Start sleep-flow optimization via the chat ReAct loop."""
    conv = get_conversation()
    conv.sleep_mode = True

    tasks = get_active_chat_tasks()
    existing = tasks.get(conv.session_id)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(
        run_agent_loop(conv.session_id, payload.message, sleep_mode=True)
    )
    task.add_done_callback(lambda _: tasks.pop(conv.session_id, None))
    tasks[conv.session_id] = task

    return {"status": "sleep_started"}


@router.post("/api/chat/sleep-wake")
async def sleep_wake():
    """End sleep mode."""
    conv = get_conversation()
    conv.sleep_mode = False
    conv.stop_requested = True

    tasks = get_active_chat_tasks()
    existing = tasks.get(conv.session_id)
    if existing and not existing.done():
        existing.cancel()
        await manager.broadcast({
            "type": "chat_done",
            "session_id": conv.session_id,
            "response": "[Sleep ended]",
        })

    return {"status": "sleep_ended"}
