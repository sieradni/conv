"""Stopwatch API endpoints."""

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


@router.post("/api/stopwatch/reset")
async def reset_stopwatch():
    svc = get_stopwatch_service()
    return svc.reset()
