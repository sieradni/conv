"""Reminders API endpoints — CRUD for reminders/timers."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.reminder_service import get_reminder_service

logger = logging.getLogger("api.reminders")
router = APIRouter(tags=["reminders"])


# ── Schemas ─────────────────────────────────────────────────────────


class CreateReminderPayload(BaseModel):
    title: str
    message: str
    trigger_at: Optional[float] = None
    trigger_in: Optional[float] = None


class UpdateReminderPayload(BaseModel):
    title: Optional[str] = None
    message: Optional[str] = None
    trigger_at: Optional[float] = None
    active: Optional[bool] = None


class ReminderResponse(BaseModel):
    id: str
    title: str
    message: str
    trigger_at: float
    created_at: float
    active: bool
    fired: bool


# ── Endpoints ───────────────────────────────────────────────────────


@router.get("/api/reminders")
async def list_reminders():
    svc = get_reminder_service()
    return {"reminders": svc.list_all()}


@router.post("/api/reminders", status_code=201)
async def create_reminder(payload: CreateReminderPayload):
    import time
    if payload.trigger_at is None and payload.trigger_in is not None:
        trigger_at = time.time() + payload.trigger_in
    elif payload.trigger_at is not None:
        trigger_at = payload.trigger_at
    else:
        raise HTTPException(status_code=422, detail="Provide trigger_at or trigger_in")
    svc = get_reminder_service()
    reminder = svc.create(title=payload.title, message=payload.message, trigger_at=trigger_at)
    return reminder


@router.get("/api/reminders/{reminder_id}")
async def get_reminder(reminder_id: str):
    svc = get_reminder_service()
    reminder = svc.get(reminder_id)
    if reminder is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return reminder


@router.put("/api/reminders/{reminder_id}")
async def update_reminder(reminder_id: str, payload: UpdateReminderPayload):
    svc = get_reminder_service()
    kwargs = {}
    for key in ("title", "message", "trigger_at", "active"):
        val = getattr(payload, key, None)
        if val is not None:
            kwargs[key] = val
    if not kwargs:
        raise HTTPException(status_code=422, detail="Nothing to update")
    result = svc.update(reminder_id, **kwargs)
    if result is None:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return result


@router.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: str):
    svc = get_reminder_service()
    if not svc.delete(reminder_id):
        raise HTTPException(status_code=404, detail="Reminder not found")
    return {"status": "deleted"}
