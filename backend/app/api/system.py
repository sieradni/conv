"""System resource monitoring API endpoint."""

import logging
from fastapi import APIRouter

from app.services.system_monitor import get_system_resources

logger = logging.getLogger("api.system")
router = APIRouter(tags=["system"])


@router.get("/api/system/resources")
async def system_resources():
    """Return current CPU, memory, GPU, and battery usage."""
    return get_system_resources()
