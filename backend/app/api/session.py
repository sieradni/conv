"""Session endpoints."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from app.core.session import get_conversation, reset_conversation

router = APIRouter(tags=["session"])


class ApprovalModePayload(BaseModel):
    mode: str = "WAIT_FOR_USER"


@router.get("/api/session")
async def get_session():
    conv = get_conversation()
    return conv.to_dict()


@router.get("/api/session/history")
async def get_session_history():
    conv = get_conversation()
    return {"history": conv.chat_history}


@router.delete("/api/session")
async def reset_session():
    from app.core.config import SESSION_FILE
    import os
    try:
        if os.path.exists(SESSION_FILE):
            os.unlink(SESSION_FILE)
    except Exception:
        pass
    reset_conversation()
    return {"status": "reset"}


@router.delete("/api/session/message")
async def delete_message(index: int = Query(...)):
    """Delete a single message from chat_history by index."""
    conv = get_conversation()
    if index < 0 or index >= len(conv.chat_history):
        raise HTTPException(status_code=404, detail="Message not found")
    del conv.chat_history[index]
    conv._save()
    return {"status": "ok"}


@router.post("/api/session/approval-mode")
async def set_approval_mode(payload: ApprovalModePayload):
    conv = get_conversation()
    from app.core.config import APPROVAL_MODES
    if payload.mode not in APPROVAL_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {payload.mode}")
    conv.approval_mode = payload.mode
    conv._save()
    return {"status": "ok", "approval_mode": payload.mode}
