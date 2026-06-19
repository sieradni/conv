"""Tool-related endpoints — todo, diagnostics, sleep context."""

import json
import logging
import time
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.core.config import TODO_FILE, DIAG_FILE, MEMORY_FILE, MEMORY_RULES_FILE

logger = logging.getLogger("api.tools")
router = APIRouter(tags=["tools"])


# ── Todo ───────────────────────────────────────────────────────────


@router.get("/api/todos")
async def get_todos():
    default = {"todo_items": [], "completed_items": []}
    if TODO_FILE.exists():
        try:
            return json.loads(TODO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


class TodoPayload(BaseModel):
    message: str


@router.put("/api/todos")
async def update_todos(payload: TodoPayload):
    try:
        data = json.loads(TODO_FILE.read_text(encoding="utf-8")) if TODO_FILE.exists() else {"todo_items": [], "completed_items": []}
        updated = json.loads(payload.message)
        for k, v in updated.items():
            data[k] = v
        TODO_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Sleep Context ──────────────────────────────────────────────────


class SleepContextPayload(BaseModel):
    start_time: float = 0.0
    end_time: float = 0.0


@router.post("/api/sleep-context")
async def generate_sleep_context(payload: SleepContextPayload):
    from app.memory_graph import get_memory_graph
    graph = get_memory_graph()
    start = payload.start_time or 0.0
    end = payload.end_time or time.time()
    context = graph.generate_sleep_context(start, end)
    return {"status": "generated", "context": context}


@router.post("/api/sleep-flow")
async def trigger_sleep_flow(payload: SleepContextPayload):
    from app.sleep_flow import run_sleep_cycle
    start = payload.start_time or 0.0
    end = payload.end_time or time.time()
    import asyncio
    asyncio.create_task(run_sleep_cycle(start_time=start, end_time=end))
    return {"status": "started"}


# ── Diagnostics ────────────────────────────────────────────────────


class DiagnosticsPayload(BaseModel):
    generation_time_s: float = 0
    tokens_per_second: float = 0
    token_count: int = 0


@router.get("/api/diagnostics")
async def get_diagnostics():
    if DIAG_FILE.exists():
        data = json.loads(DIAG_FILE.read_text(encoding="utf-8"))
    else:
        data = {"history": []}
    return data


@router.post("/api/diagnostics/record")
async def record_diagnostics(payload: DiagnosticsPayload):
    data = {"history": []}
    if DIAG_FILE.exists():
        data = json.loads(DIAG_FILE.read_text(encoding="utf-8"))
    entry = {
        "timestamp": time.time(),
        "generation_time_s": payload.generation_time_s,
        "tokens_per_second": payload.tokens_per_second,
        "token_count": payload.token_count,
    }
    data.setdefault("history", []).append(entry)
    data["history"] = data["history"][-100:]
    DIAG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"status": "recorded"}


# ── State (memory + rules for frontend) ───────────────────────────


@router.get("/api/state")
async def get_state():
    memory = {}
    if MEMORY_FILE.exists():
        try:
            memory = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    rules = ""
    if MEMORY_RULES_FILE.exists():
        rules = MEMORY_RULES_FILE.read_text(encoding="utf-8")
    return {"memory": memory, "rules": rules}
