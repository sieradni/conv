"""User notes endpoints."""

import logging
from pathlib import Path
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import NOTES_FILE

logger = logging.getLogger("api.notes")
router = APIRouter(tags=["notes"])


class NotePayload(BaseModel):
    message: str


@router.get("/api/notes")
async def get_notes():
    if NOTES_FILE.exists():
        content = NOTES_FILE.read_text(encoding="utf-8")
    else:
        content = "# User Notes\n\nWrite your notes here..."
        NOTES_FILE.write_text(content, encoding="utf-8")
    return {"content": content, "path": str(NOTES_FILE)}


@router.put("/api/notes")
async def update_notes(payload: NotePayload):
    NOTES_FILE.write_text(payload.message, encoding="utf-8")
    return {"status": "updated"}
