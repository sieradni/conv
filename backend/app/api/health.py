"""Health and LM Studio status endpoints."""

import logging
from fastapi import APIRouter

from app.services.lm_client import LMStudioClient

logger = logging.getLogger("api.health")
router = APIRouter(tags=["health"])


@router.get("/api/health")
async def health():
    return {"status": "ok"}


@router.get("/api/lm/status")
async def lm_status():
    client = LMStudioClient()
    try:
        # Try v2 first
        models = await client.get_models_v2()
        if models and "models" in models:
            for m in models["models"]:
                if m.get("type") == "llm" and m.get("loaded_instances"):
                    instance = m["loaded_instances"][0]
                    return {
                        "status": "connected",
                        "model": instance["id"],
                        "api_version": "v2",
                    }
        # Legacy fallback
        legacy = await client.get_models_legacy()
        if legacy and "data" in legacy and legacy["data"]:
            return {
                "status": "connected",
                "model": legacy["data"][0]["id"],
                "api_version": "legacy",
            }
        return {"status": "disconnected", "model": None, "api_version": None}
    except Exception as e:
        logger.warning(f"LM status check failed: {e}")
        return {"status": "disconnected", "model": None, "api_version": None}
