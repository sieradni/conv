"""Session-based state management for concurrent agent sessions."""

import asyncio
import time
import uuid
import logging
from typing import Dict, Any, Optional, List, Tuple
from fastapi import WebSocket

logger = logging.getLogger("session")


class ConnectionManager:
    """Manages WebSocket connections with optional session scoping.

    - Global broadcast: sent to ALL connected clients.
    - Session-scoped broadcast: sent only to clients subscribed to that session.
    - Every message is tagged with session_id so clients can filter.
    """

    def __init__(self):
        self._global: List[WebSocket] = []
        self._by_session: Dict[str, List[WebSocket]] = {}

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
        """Broadcast to global + optional session-scoped connections."""
        dead: List[WebSocket] = []

        # Global
        for ws in self._global:
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

        # Session-scoped
        if session_id and session_id in self._by_session:
            dead = []
            for ws in self._by_session[session_id]:
                try:
                    await ws.send_json(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                self.disconnect(ws, session_id)

    async def broadcast_to_session(
        self, message: dict, session_id: str
    ):
        """Broadcast only to connections bound to a specific session."""
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


# Singleton
manager = ConnectionManager()


class Session:
    """A single agent conversation session with its own state and queue."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.user_response_queue: asyncio.Queue = asyncio.Queue()
        self.direct_talk_queue: asyncio.Queue = asyncio.Queue()
        self.stop_requested: bool = False
        self.pause_requested: bool = False
        self.resume_event: asyncio.Event = asyncio.Event()
        self.approval_mode: str = "WAIT_FOR_USER"
        self.chat_history: List[dict] = []
        self.created_at: float = time.time()
        self.last_active_at: float = time.time()
        self.sleep_mode: bool = False
        self.current_goal: str = ""

    def touch(self):
        self.last_active_at = time.time()

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "stop_requested": self.stop_requested,
            "approval_mode": self.approval_mode,
            "created_at": self.created_at,
            "last_active_at": self.last_active_at,
        }


class SessionRegistry:
    """Global registry of active sessions."""

    def __init__(self):
        self._sessions: Dict[str, Session] = {}

    def create(self) -> Session:
        session_id = uuid.uuid4().hex[:12]
        session = Session(session_id)
        self._sessions[session_id] = session
        logger.info(f"Session created: {session_id}")
        return session

    def get_or_create(self, session_id: Optional[str] = None) -> Session:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]
        return self.create()

    def get(self, session_id: str) -> Optional[Session]:
        return self._sessions.get(session_id)

    def delete(self, session_id: str):
        session = self._sessions.pop(session_id, None)
        if session:
            logger.info(f"Session deleted: {session_id}")

    def list(self) -> List[dict]:
        return [s.to_dict() for s in self._sessions.values()]


# Singleton
registry = SessionRegistry()
