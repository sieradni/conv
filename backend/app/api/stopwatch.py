"""Stopwatch API endpoints — start, stop, check, and set."""

import logging

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Optional

from app.services.stopwatch_service import get_stopwatch_service

logger = logging.getLogger("api.stopwatch")
router = APIRouter(tags=["stopwatch"])


@router.get("/api/stopwatch")
async def get_stopwatch():
    svc = get_stopwatch_service()
    return svc.state()


@router.post("/api/stopwatch/start")
async def start_stopwatch():
    svc = get_stopwatch_service()
    return svc.start()


@router.post("/api/stopwatch/stop")
async def stop_stopwatch():
    svc = get_stopwatch_service()
    return svc.stop()


class SetStopwatchRequest(BaseModel):
    seconds: float = 0.0


@router.post("/api/stopwatch/set")
async def set_stopwatch(body: SetStopwatchRequest):
    svc = get_stopwatch_service()
    return svc.set(body.seconds)
