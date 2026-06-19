import logging
from typing import Any, Optional
from fastapi import WebSocket

logger = logging.getLogger("events")

# ── Event type constants ──────────────────────────────────────────

STEP_UPDATE = "step_update"
STEP_START = "step_start"
STATUS_UPDATE = "status_update"
TASK_COMPLETE = "task_complete"
LLM_CALL = "llm_call"
LLM_RESPONSE = "llm_response"

OVERSEER_REVIEW_START = "overseer_review_start"
OVERSEER_REVIEW_TOKEN = "overseer_review_token"
OVERSEER_REVIEW = "overseer_review"

AWAITING_USER_APPROVAL = "awaiting_user_approval"
ASK_USER = "ask_user"
USER_DECISION = "user_decision"

CHAT_START = "chat_start"
CHAT_TOKEN = "chat_token"
CHAT_REASONING_TOKEN = "chat_reasoning_token"
CHAT_STREAM_DIAG = "chat_stream_diag"
CHAT_TOOL = "chat_tool"
CHAT_TOOL_RESULT = "chat_tool_result"
CHAT_DONE = "chat_done"
CHAT_PAUSED = "chat_paused"
USER_MESSAGE = "user_message"
GOAL_SET = "goal_set"
ERROR = "error"
PING = "ping"


class ConnectionManager:
    """Manages WebSocket connections with global + session-scoped delivery."""

    def __init__(self):
        self._global: list[WebSocket] = []
        self._by_session: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: Optional[str] = None):
        await websocket.accept()
        self._global.append(websocket)
        if session_id:
            self._by_session.setdefault(session_id, []).append(websocket)
        logger.info(
            f"WS connected (session={session_id or 'global'}). "
            f"Global: {len(self._global)}, "
            f"Session-bound: {sum(len(v) for v in self._by_session.values())}"
        )

    def disconnect(self, websocket: WebSocket, session_id: Optional[str] = None):
        if websocket in self._global:
            self._global.remove(websocket)
        if session_id and session_id in self._by_session:
            try:
                self._by_session[session_id].remove(websocket)
            except ValueError:
                pass
        logger.info(f"WS disconnected. Global: {len(self._global)}")

    async def broadcast(self, message: dict, session_id: Optional[str] = None):
        dead: list[WebSocket] = []
        for ws in self._global:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

        if session_id and session_id in self._by_session:
            sdead: list[WebSocket] = []
            for ws in self._by_session[session_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    sdead.append(ws)
            for ws in sdead:
                self.disconnect(ws, session_id)

    async def broadcast_to_session(self, message: dict, session_id: str):
        if session_id not in self._by_session:
            return
        dead = []
        for ws in self._by_session[session_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws, session_id)


manager = ConnectionManager()
