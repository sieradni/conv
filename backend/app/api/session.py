"""Session endpoints."""

from fastapi import APIRouter, HTTPException
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
    reset_conversation()
    return {"status": "reset"}


@router.post("/api/session/approval-mode")
async def set_approval_mode(payload: ApprovalModePayload):
    conv = get_conversation()
    from app.core.config import APPROVAL_MODES
    if payload.mode not in APPROVAL_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode: {payload.mode}")
    conv.approval_mode = payload.mode
    conv._save()
    return {"status": "ok", "approval_mode": payload.mode}
