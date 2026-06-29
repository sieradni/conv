"""Self-development pipeline endpoints."""

import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.self_dev import get_shadow_sandbox

logger = logging.getLogger("api.self_dev")
router = APIRouter(tags=["self_dev"])

shadow_sandbox = get_shadow_sandbox()


class ProposePayload(BaseModel):
    file_path: str
    content: str


@router.post("/api/self-dev/init")
async def self_dev_init():
    try:
        msg = shadow_sandbox.create_shadow()
        return {"status": "ok", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/self-dev/propose")
async def self_dev_propose(payload: ProposePayload):
    try:
        if shadow_sandbox.status == "IDLE":
            shadow_sandbox.create_shadow()
        msg = shadow_sandbox.apply_change(payload.file_path, payload.content)
        return {"status": "ok", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/self-dev/test")
async def self_dev_test():
    try:
        if shadow_sandbox.status == "IDLE":
            return {"status": "error", "message": "No shadow initialized."}
        results = await asyncio.to_thread(shadow_sandbox.run_tests)
        return {"status": "ok", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/self-dev/deploy")
async def self_dev_deploy():
    try:
        if shadow_sandbox.status == "IDLE":
            return {"status": "error", "message": "No shadow initialized."}
        msg = shadow_sandbox.deploy_to_live()
        return {"status": "ok", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/self-dev/status")
async def self_dev_status():
    return shadow_sandbox.status_report()
