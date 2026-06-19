import asyncio
import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from app.core.config import SESSION_FILE

logger = logging.getLogger("session")


class Conversation:
    """Single persistent conversation session.

    All state is kept in memory and written to data/session.json
    on every mutation.  Multiple frontends connecting to the same
    backend see the same state automatically via WebSocket broadcast.
    """

    def __init__(self):
        self.session_id: str = ""
        self.chat_history: list[dict] = []
        self.current_goal: str = ""
        self.approval_mode: str = "WAIT_FOR_USER"
        self.model_instance_id: str = ""
        self.created_at: float = 0.0
        self.updated_at: float = 0.0

        self.stop_requested: bool = False
        self.pause_requested: bool = False
        self.sleep_mode: bool = False
        self.thinking_level: str = ""  # "" = model default, or "off"/"low"/"medium"/"high"
        self._resume_event: Any = None
        self.user_response_queue: asyncio.Queue = asyncio.Queue()

        self._load_or_init()

    # ── Persistence ────────────────────────────────────────────────

    def _load_or_init(self):
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        if SESSION_FILE.exists() and SESSION_FILE.stat().st_size > 0:
            try:
                data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
                self.session_id = data.get("session_id", "")
                self.chat_history = data.get("chat_history", [])
                self.current_goal = data.get("current_goal", "")
                self.approval_mode = data.get("approval_mode", "WAIT_FOR_USER")
                self.model_instance_id = data.get("model_instance_id", "")
                self.thinking_level = data.get("thinking_level", "")
                self.created_at = data.get("created_at", 0.0)
                self.updated_at = data.get("updated_at", 0.0)
                logger.info(f"Loaded session {self.session_id} ({len(self.chat_history)} messages)")
                return
            except Exception as e:
                logger.warning(f"Failed to load session file: {e}")
        self._init_fresh()

    def _init_fresh(self):
        self.session_id = uuid.uuid4().hex[:8]
        self.chat_history = []
        self.current_goal = ""
        self.approval_mode = "WAIT_FOR_USER"
        self.model_instance_id = ""
        self.created_at = time.time()
        self.updated_at = time.time()
        self._save()
        logger.info(f"Created new session {self.session_id}")

    def _save(self):
        self.updated_at = time.time()
        data = {
            "session_id": self.session_id,
            "chat_history": self.chat_history,
            "current_goal": self.current_goal,
            "approval_mode": self.approval_mode,
            "model_instance_id": self.model_instance_id,
            "thinking_level": self.thinking_level,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": 2,
        }
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = SESSION_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(SESSION_FILE)

    # ── History helpers ────────────────────────────────────────────

    def add_message(self, role: str, content: str, **extra):
        entry = {"role": role, "content": content, "timestamp": time.time()}
        entry.update(extra)
        self.chat_history.append(entry)
        self._save()

    def get_context_messages(self, max_messages: int = 0) -> list[dict]:
        """Return chat_history entries formatted for the LLM context.

        If max_messages > 0, returns only the last N messages.
        """
        if max_messages and len(self.chat_history) > max_messages:
            return self.chat_history[-max_messages:]
        return list(self.chat_history)

    # ── Flow control ───────────────────────────────────────────────

    @property
    def resume_event(self):
        if self._resume_event is None:
            import asyncio
            self._resume_event = asyncio.Event()
        return self._resume_event

    def reset_flow_control(self):
        self.stop_requested = False
        self.pause_requested = False
        self._resume_event = None

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "current_goal": self.current_goal,
            "approval_mode": self.approval_mode,
            "model_instance_id": self.model_instance_id,
            "thinking_level": self.thinking_level,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "message_count": len(self.chat_history),
        }

    def set_thinking_level(self, level: str):
        valid = ("", "off", "low", "medium", "high")
        if level not in valid:
            raise ValueError(f"Invalid thinking level: {level}. Valid: {valid}")
        self.thinking_level = level
        self._save()


# Singleton
conversation: Optional[Conversation] = None


def get_conversation() -> Conversation:
    global conversation
    if conversation is None:
        conversation = Conversation()
    return conversation


def reset_conversation():
    global conversation
    conversation = Conversation()
