"""Model management endpoints — list, load, unload models from LM Studio."""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.lm_client import LMStudioClient
from app.core.session import get_conversation

logger = logging.getLogger("api.models")
router = APIRouter(tags=["models"])


class LoadModelPayload(BaseModel):
    model: str
    context_length: Optional[int] = None
    eval_batch_size: Optional[int] = None
    flash_attention: Optional[bool] = None
    num_experts: Optional[int] = None
    offload_kv_cache_to_gpu: Optional[bool] = None


@router.get("/api/models")
async def list_models():
    """List available models from LM Studio (both LLM and embedding)."""
    client = LMStudioClient()
    # Try v2 API first
    result = await client.get_models_v2()
    if result and "models" in result:
        return result
    # Legacy fallback
    legacy = await client.get_models_legacy()
    if legacy and "data" in legacy:
        return legacy
    return {"models": [], "detail": "No models available. Is LM Studio running?"}


@router.post("/api/models/load")
async def load_model(payload: LoadModelPayload):
    """Dynamically load a model in LM Studio."""
    client = LMStudioClient()
    kwargs = {}
    if payload.context_length is not None:
        kwargs["context_length"] = payload.context_length
    if payload.eval_batch_size is not None:
        kwargs["eval_batch_size"] = payload.eval_batch_size
    if payload.flash_attention is not None:
        kwargs["flash_attention"] = payload.flash_attention
    if payload.num_experts is not None:
        kwargs["num_experts"] = payload.num_experts
    if payload.offload_kv_cache_to_gpu is not None:
        kwargs["offload_kv_cache_to_gpu"] = payload.offload_kv_cache_to_gpu

    result = await client.load_model(payload.model, **kwargs)
    if result is None:
        raise HTTPException(status_code=502, detail="Failed to load model. Is LM Studio running?")

    # Update active model
    if result.get("status") == "loaded":
        conv = get_conversation()
        conv.model_instance_id = result.get("instance_id", payload.model)
        conv._save()

    return result


@router.get("/api/models/active")
async def get_active_model():
    """Get the currently active model."""
    conv = get_conversation()
    client = LMStudioClient()

    if conv.model_instance_id:
        return {"model_instance_id": conv.model_instance_id}

    # Auto-detect
    models = await client.get_models_v2()
    if models and "models" in models:
        for m in models["models"]:
            if m.get("type") == "llm" and m.get("loaded_instances"):
                instance = m["loaded_instances"][0]
                conv.model_instance_id = instance["id"]
                conv._save()
                return {"model_instance_id": instance["id"]}

    return {"model_instance_id": None}
