import asyncio
import json
import os
import time
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from app.orchestrator import AgentOrchestrator
from app.state import AgentState
from app.session import registry, manager
from app.memory_graph import get_memory_graph
from app.sleep_flow import sleep_loop
from app.self_dev import get_shadow_sandbox

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")

app = FastAPI(title="Agentic Dev Framework")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ──────────────────────────────────────────────

class TaskPayload(BaseModel):
    goal: str
    approval_mode: str = "WAIT_FOR_USER"
    max_steps: int = 15
    session_id: Optional[str] = None


class UserApprovalPayload(BaseModel):
    approved: bool
    feedback: Optional[str] = None
    session_id: Optional[str] = None


class CreateSessionPayload(BaseModel):
    session_id: Optional[str] = None


class DirectTalkPayload(BaseModel):
    message: str
    session_id: Optional[str] = None


class BranchPayload(BaseModel):
    session_id: str


class SelfDevProposePayload(BaseModel):
    file_path: str
    content: str
    session_id: Optional[str] = None


class SelfDevDeployPayload(BaseModel):
    session_id: Optional[str] = None


class DiagnosticsPayload(BaseModel):
    generation_time_s: float = 0
    tokens_per_second: float = 0
    token_count: int = 0
    session_id: Optional[str] = None


# ── Background task runner ────────────────────────────────────────

async def run_agent_task(payload: TaskPayload, session_id: str):
    session = registry.get(session_id)
    if not session:
        logger.error(f"Session not found: {session_id}")
        return

    session.status = "RUNNING"
    session.goal = payload.goal
    session.approval_mode = payload.approval_mode
    session.max_steps = payload.max_steps

    logger.info(f"[{session_id}] Starting task: {payload.goal}")

    orch = AgentOrchestrator(
        task_goal=payload.goal,
        approval_mode=payload.approval_mode,
        max_steps=payload.max_steps,
        sandbox_dir=os.path.join(os.getcwd(), "sandbox_ui"),
        session_id=session_id,
    )

    orch.ui_manager = manager
    orch.user_queue = session.user_response_queue
    orch.session_id = session_id
    session.orchestrator = orch

    await orch.initialize()

    await manager.broadcast({
        "type": "status_update",
        "session_id": session_id,
        "status": "RUNNING",
        "goal": payload.goal,
        "approval_mode": payload.approval_mode,
        "max_steps": payload.max_steps,
    })

    try:
        final_state = await orch.run_loop()
        session.status = final_state.status
        await manager.broadcast({
            "type": "task_complete",
            "session_id": session_id,
            "status": final_state.status,
            "steps": len(final_state.history),
        })
    except Exception as e:
        logger.error(f"[{session_id}] Orchestrator error: {e}")
        session.status = "FAILED"
        await manager.broadcast({
            "type": "error",
            "session_id": session_id,
            "message": str(e),
        })


# ── Health ────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


# ── Session management ────────────────────────────────────────────

@app.post("/api/session/create")
async def create_session(payload: CreateSessionPayload = None):
    if payload and payload.session_id:
        existing = registry.get(payload.session_id)
        if existing:
            return {"session_id": payload.session_id, "created": False}
    session = registry.create()
    return {"session_id": session.session_id, "created": True}


@app.get("/api/sessions")
async def list_sessions():
    return {"sessions": registry.list()}


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    registry.delete(session_id)
    return {"status": "deleted"}


# ── Task endpoints ────────────────────────────────────────────────

@app.post("/api/task/start")
async def start_task(payload: TaskPayload, background_tasks: BackgroundTasks):
    if payload.max_steps < 1 or payload.max_steps > 100:
        raise HTTPException(status_code=400, detail="max_steps must be between 1 and 100")
    if payload.approval_mode not in ("AUTO_APPROVE", "CHECK_WITH_OVERSEER", "WAIT_FOR_USER"):
        raise HTTPException(status_code=400, detail="Invalid approval_mode")

    session_id = payload.session_id
    if not session_id or not registry.get(session_id):
        session = registry.create()
        session_id = session.session_id
    else:
        session = registry.get(session_id)

    background_tasks.add_task(run_agent_task, payload, session_id)
    return {"status": "started", "session_id": session_id, "goal": payload.goal}


@app.post("/api/task/approve")
async def submit_approval(payload: UserApprovalPayload):
    session_id = payload.session_id or "default"
    session = registry.get(session_id)

    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")

    logger.info(f"[{session_id}] User approval: approved={payload.approved}, feedback={payload.feedback}")
    await session.user_response_queue.put({
        "approved": payload.approved,
        "feedback": payload.feedback,
    })
    return {"status": "received", "session_id": session_id}


# ── Conversational Control ────────────────────────────────────────

@app.post("/api/task/stop")
async def stop_task(payload: CreateSessionPayload = None):
    """Immediately abort the current task execution."""
    sid = payload.session_id if payload and payload.session_id else "default"
    session = registry.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {sid} not found")
    session.stop_requested = True
    session.status = "STOPPED"
    await manager.broadcast({
        "type": "status_update", "session_id": sid,
        "status": "STOPPED", "message": "User requested stop"
    })
    return {"status": "stopped", "session_id": sid}


@app.post("/api/task/stop-after-step")
async def stop_after_step(payload: CreateSessionPayload = None):
    """Pause execution after the current step completes."""
    sid = payload.session_id if payload and payload.session_id else "default"
    session = registry.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {sid} not found")
    session.stop_after_step = True
    await manager.broadcast({
        "type": "status_update", "session_id": sid,
        "status": "PAUSING", "message": "Will pause after current step"
    })
    return {"status": "will_pause_after_step", "session_id": sid}


@app.post("/api/task/talk")
async def direct_talk(payload: DirectTalkPayload):
    """Send a direct message to the agent, bypassing the task loop."""
    sid = payload.session_id or "default"
    session = registry.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {sid} not found")
    await session.direct_talk_queue.put(payload.message)
    logger.info(f"[{sid}] Direct talk: {payload.message[:80]}")
    return {"status": "sent", "session_id": sid}


@app.post("/api/task/override")
async def override_overseer(payload: DirectTalkPayload):
    """Force-approve the current action, overriding an Overseer rejection."""
    sid = payload.session_id or "default"
    session = registry.get(sid)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {sid} not found")
    # Put an override message into the user queue as an approved action
    await session.user_response_queue.put({
        "approved": True,
        "feedback": f"[USER OVERRIDE] {payload.message}"
    })
    await manager.broadcast({
        "type": "user_decision", "session_id": sid,
        "approved": True, "feedback": f"Overseer overridden: {payload.message}"
    })
    return {"status": "overridden", "session_id": sid}


# ── History / Branching ──────────────────────────────────────────

@app.delete("/api/task/history/{step_number}")
async def delete_history_step(step_number: int, session_id: str = Query("default")):
    """Delete a specific step from history without breaking sequence."""
    session = registry.get(session_id)
    if not session or not session.orchestrator:
        raise HTTPException(status_code=404, detail="No active session")
    state = session.orchestrator.state
    before = len(state.history)
    state.history = [s for s in state.history if s.step_number != step_number]
    removed = before - len(state.history)
    return {"status": "deleted" if removed else "not_found", "removed": removed, "session_id": session_id}


@app.post("/api/task/branch")
async def branch_task(payload: BranchPayload):
    """Branch from the current state: freeze history, reset step counter."""
    session = registry.get(payload.session_id)
    if not session or not session.orchestrator:
        raise HTTPException(status_code=404, detail="No active session")
    state = session.orchestrator.state
    # Create a branch point: archive current history and reset
    state.system_metrics["branch_point"] = {
        "step": state.current_step,
        "history_length": len(state.history),
    }
    state.current_step = 1
    # Remove the finish if it exists so agent continues
    state.history = [s for s in state.history if s.tool_name != "finish_task"]
    state.status = "RUNNING"
    await manager.broadcast({
        "type": "status_update", "session_id": payload.session_id,
        "status": "BRANCHED", "message": f"Branched at step {state.current_step}"
    })
    return {"status": "branched", "session_id": payload.session_id, "branch_point": state.system_metrics["branch_point"]}


@app.get("/api/task/status")
async def task_status(session_id: str = Query("default")):
    session = registry.get(session_id)
    if not session or not session.orchestrator:
        return {"session_id": session_id, "status": "IDLE"}

    s = session.orchestrator.state
    return {
        "session_id": session_id,
        "status": s.status,
        "current_step": s.current_step,
        "max_steps": s.max_steps,
        "approval_mode": s.approval_mode,
        "total_steps": len(s.history),
        "stop_requested": session.stop_requested,
        "stop_after_step": session.stop_after_step,
    }


@app.get("/api/state")
async def get_state(session_id: str = Query("default")):
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        memory_path = os.path.join(base, "working_memory.json")
        rules_path = os.path.join(base, "memory_rules.md")

        memory = {}
        if os.path.exists(memory_path):
            with open(memory_path) as f:
                memory = json.load(f)

        rules = ""
        if os.path.exists(rules_path):
            with open(rules_path) as f:
                rules = f.read()

        return {"memory": memory, "rules": rules, "session_id": session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── WebSocket ─────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_global(websocket: WebSocket):
    """Global WebSocket — receives broadcasts from all sessions."""
    await manager.connect(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error: {e}")
    finally:
        manager.disconnect(websocket)


@app.websocket("/ws/{session_id}")
async def websocket_session(websocket: WebSocket, session_id: str):
    """Session-scoped WebSocket — receives broadcasts only for one session."""
    await manager.connect(websocket, session_id=session_id)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "ping"})
                except Exception:
                    break
                continue
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error ({session_id}): {e}")
    finally:
        manager.disconnect(websocket, session_id=session_id)


# ── Memory ─────────────────────────────────────────────────────────

@app.get("/api/memory")
async def get_memory_graph_api():
    """Return the full HSWM graph state."""
    graph = get_memory_graph()
    return {
        "current_node_id": graph.current_node_id,
        "neighborhood": graph.get_neighborhood(),
        "root": graph.get_node(graph.root().id) if graph.root() else None,
    }


@app.post("/api/memory/optimize")
async def optimize_memory():
    """Trigger a sleep-flow optimization cycle."""
    from app.sleep_flow import run_sleep_cycle
    await run_sleep_cycle()
    return {"status": "optimized"}


# ── Self-Development Pipeline ──────────────────────────────────────

shadow_sandbox = get_shadow_sandbox()


@app.post("/api/self-dev/init")
async def self_dev_init():
    """Create a shadow copy of the framework for safe self-modification."""
    try:
        msg = shadow_sandbox.create_shadow()
        return {"status": "ok", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/self-dev/propose")
async def self_dev_propose(payload: SelfDevProposePayload):
    """Apply a proposed change to the shadow copy."""
    try:
        if shadow_sandbox.status == "IDLE":
            shadow_sandbox.create_shadow()
        msg = shadow_sandbox.apply_change(payload.file_path, payload.content)
        return {"status": "ok", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/self-dev/test")
async def self_dev_test():
    """Run the test suite inside the shadow sandbox."""
    try:
        if shadow_sandbox.status == "IDLE":
            return {"status": "error", "message": "No shadow initialized. Call /api/self-dev/init first."}
        results = await asyncio.to_thread(shadow_sandbox.run_tests)
        return {"status": "ok", "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/self-dev/deploy")
async def self_dev_deploy():
    """Deploy approved shadow changes to the live codebase."""
    try:
        if shadow_sandbox.status == "IDLE":
            return {"status": "error", "message": "No shadow initialized."}
        msg = shadow_sandbox.deploy_to_live()
        return {"status": "ok", "message": msg}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/self-dev/status")
async def self_dev_status():
    """Get the status of the self-development pipeline."""
    return shadow_sandbox.status_report()


# ── Notes (User Scratchpad) ────────────────────────────────────────

NOTES_PATH = Path(__file__).parent / "user_notes.md"


@app.get("/api/notes")
async def get_notes():
    """Return the user's persistent notes."""
    if NOTES_PATH.exists():
        content = NOTES_PATH.read_text(encoding="utf-8")
    else:
        content = "# User Notes\n\nWrite your notes here..."
        NOTES_PATH.write_text(content, encoding="utf-8")
    return {"content": content, "path": str(NOTES_PATH)}


@app.put("/api/notes")
async def update_notes(payload: DirectTalkPayload):
    """Update the user's persistent notes."""
    NOTES_PATH.write_text(payload.message, encoding="utf-8")
    return {"status": "updated"}


# ── Diagnostics Metrics ───────────────────────────────────────────

DIAG_PATH = Path(__file__).parent / "diagnostics.json"


@app.get("/api/diagnostics")
async def get_diagnostics():
    """Return recent diagnostics metrics."""
    if DIAG_PATH.exists():
        data = json.loads(DIAG_PATH.read_text(encoding="utf-8"))
    else:
        data = {"history": []}
    return data


@app.post("/api/diagnostics/record")
async def record_diagnostics(payload: DiagnosticsPayload):
    """Record a diagnostics data point."""
    data = {"generation_time_s": 0, "tokens_per_second": 0, "token_count": 0}
    if DIAG_PATH.exists():
        data = json.loads(DIAG_PATH.read_text(encoding="utf-8"))
    entry = {
        "timestamp": time.time(),
        "generation_time_s": payload.generation_time_s,
        "tokens_per_second": payload.tokens_per_second,
        "token_count": payload.token_count,
    }
    data.setdefault("history", []).append(entry)
    data["history"] = data["history"][-100:]
    DIAG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return {"status": "recorded"}


# ── Startup / Shutdown ────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    asyncio.create_task(sleep_loop(interval_seconds=3600))
    logger.info("Sleep flow loop started (every 3600s)")


# ── Static files ──────────────────────────────────────────────────

frontend_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "..",
    "frontend",
)
frontend_dir = os.path.abspath(frontend_dir)
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")
else:
    logger.warning(f"Frontend directory not found: {frontend_dir}")
