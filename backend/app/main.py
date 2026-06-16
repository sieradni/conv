import asyncio
import json
import os
import logging
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from app.orchestrator import AgentOrchestrator
from app.state import AgentState

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

orchestrator_instance: Optional[AgentOrchestrator] = None
user_response_queue = asyncio.Queue()

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"WS connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"WS disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                dead.append(connection)
        for conn in dead:
            self.disconnect(conn)

manager = ConnectionManager()

class TaskPayload(BaseModel):
    goal: str
    approval_mode: str = "WAIT_FOR_USER"
    max_steps: int = 15

class UserApprovalPayload(BaseModel):
    approved: bool
    feedback: Optional[str] = None

async def run_agent_task(payload: TaskPayload):
    global orchestrator_instance

    logger.info(f"Starting background task: {payload.goal}")

    orchestrator_instance = AgentOrchestrator(
        task_goal=payload.goal,
        approval_mode=payload.approval_mode,
        max_steps=payload.max_steps,
        sandbox_dir=os.path.join(os.getcwd(), "sandbox_ui")
    )

    orchestrator_instance.ui_manager = manager
    orchestrator_instance.user_queue = user_response_queue

    await orchestrator_instance.initialize()

    await manager.broadcast({
        "type": "status_update",
        "status": "RUNNING",
        "goal": payload.goal,
        "approval_mode": payload.approval_mode,
        "max_steps": payload.max_steps
    })

    try:
        final_state = await orchestrator_instance.run_loop()
        await manager.broadcast({
            "type": "task_complete",
            "status": final_state.status,
            "steps": len(final_state.history)
        })
    except Exception as e:
        logger.error(f"Orchestrator error: {e}")
        await manager.broadcast({
            "type": "error",
            "message": str(e)
        })

@app.get("/api/health")
async def health():
    return {"status": "ok"}

@app.post("/api/task/start")
async def start_task(payload: TaskPayload, background_tasks: BackgroundTasks):
    if payload.max_steps < 1 or payload.max_steps > 100:
        raise HTTPException(status_code=400, detail="max_steps must be between 1 and 100")
    if payload.approval_mode not in ("AUTO_APPROVE", "CHECK_WITH_OVERSEER", "WAIT_FOR_USER"):
        raise HTTPException(status_code=400, detail="Invalid approval_mode")
    background_tasks.add_task(run_agent_task, payload)
    return {"status": "started", "goal": payload.goal}

@app.post("/api/task/approve")
async def submit_approval(payload: UserApprovalPayload):
    logger.info(f"User approval: approved={payload.approved}, feedback={payload.feedback}")
    await user_response_queue.put({
        "approved": payload.approved,
        "feedback": payload.feedback
    })
    return {"status": "received"}

@app.get("/api/state")
async def get_state():
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

        return {"memory": memory, "rules": rules}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/task/status")
async def task_status():
    global orchestrator_instance
    if orchestrator_instance is None:
        return {"status": "IDLE"}
    s = orchestrator_instance.state
    return {
        "status": s.status,
        "current_step": s.current_step,
        "max_steps": s.max_steps,
        "approval_mode": s.approval_mode,
        "total_steps": len(s.history)
    }

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
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
            if data == "ping" or data == '{"type":"ping"}':
                continue
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error: {e}")
    finally:
        manager.disconnect(websocket)

frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "frontend")
frontend_dir = os.path.abspath(frontend_dir)
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")
else:
    logger.warning(f"Frontend directory not found: {frontend_dir}")
