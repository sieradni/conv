"""FastAPI application — slim entry point that includes all routers."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.core.config import FRONTEND_DIR
from app.core.events import manager, PING
from app.sleep_flow import sleep_loop

logger = logging.getLogger("main")
logging.basicConfig(level=logging.INFO, format="[%(name)s] %(levelname)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)

# Background task refs
_sleep_task: asyncio.Task | None = None
_reminder_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _sleep_task, _reminder_task
    _sleep_task = asyncio.create_task(sleep_loop(interval_seconds=3600))
    logger.info("Sleep flow loop started (every 3600s)")
    from app.services.reminder_service import get_reminder_service
    _reminder_task = asyncio.create_task(get_reminder_service().check_loop())
    logger.info("Reminder checker started (every 5s)")
    yield
    if _sleep_task and not _sleep_task.done():
        _sleep_task.cancel()
        logger.info("Sleep flow loop cancelled")
    if _reminder_task and not _reminder_task.done():
        _reminder_task.cancel()
        logger.info("Reminder checker cancelled")


app = FastAPI(title="conv agent framework", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Include routers ────────────────────────────────────────────────

from app.api.health import router as health_router
from app.api.session import router as session_router
from app.api.chat import router as chat_router
from app.api.models import router as models_router
from app.api.memory import router as memory_router
from app.api.notes import router as notes_router
from app.api.tools import router as tools_router
from app.api.self_dev import router as self_dev_router
from app.api.system import router as system_router
from app.api.reminders import router as reminders_router
from app.api.stopwatch import router as stopwatch_router

app.include_router(health_router)
app.include_router(session_router)
app.include_router(chat_router)
app.include_router(models_router)
app.include_router(memory_router)
app.include_router(notes_router)
app.include_router(tools_router)
app.include_router(self_dev_router)
app.include_router(system_router)
app.include_router(reminders_router)
app.include_router(stopwatch_router)


# ── WebSocket ──────────────────────────────────────────────────────


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
                    await websocket.send_json({"type": PING})
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
                    await websocket.send_json({"type": PING})
                except Exception:
                    break
                continue
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning(f"WS error ({session_id}): {e}")
    finally:
        manager.disconnect(websocket, session_id=session_id)


# ── Static files ───────────────────────────────────────────────────

frontend_path = str(FRONTEND_DIR.resolve())
if FRONTEND_DIR.is_dir():
    app.mount("/", StaticFiles(directory=frontend_path, html=True), name="static")
else:
    logger.warning(f"Frontend directory not found: {frontend_path}")
