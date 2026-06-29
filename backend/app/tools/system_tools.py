"""System tools — todo, notes, goal, ask_user, finish_task."""

import json
from pathlib import Path

from app.core.config import TODO_FILE, NOTES_FILE


# ── Todo ────────────────────────────────────────────────────────────


def update_todo(key: str, value: list) -> str:
    data = {"todo_items": [], "completed_items": []}
    if TODO_FILE.exists():
        try:
            data = json.loads(TODO_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    data[key] = value
    TODO_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"Updated {key}"


# ── User Notes ─────────────────────────────────────────────────────


def read_user_notes() -> str:
    if NOTES_FILE.exists():
        return NOTES_FILE.read_text(encoding="utf-8")
    return "# User Notes\n\nNo notes yet."


def write_user_notes(content: str) -> str:
    NOTES_FILE.write_text(content, encoding="utf-8")
    return "Notes updated"


# ── Goal ────────────────────────────────────────────────────────────


def set_goal(goal: str) -> str:
    return f"Goal set: {goal}" if goal else "No goal provided"


# ── Communication ──────────────────────────────────────────────────


def ask_user(question: str) -> str:
    return f"[ASK_USER:{question}]"


# ── Time ────────────────────────────────────────────────────────────


def get_current_time() -> str:
    import time, datetime
    now = time.time()
    local = datetime.datetime.fromtimestamp(now)
    utc = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
    return f"Current time:\n  Local: {local.strftime('%Y-%m-%d %H:%M:%S %Z')}\n  UTC:   {utc.strftime('%Y-%m-%d %H:%M:%S UTC')}\n  Unix:  {int(now)}"


# ── Task completion ────────────────────────────────────────────────


def finish_task(summary: str) -> str:
    return f"[FINISH_TASK:{summary}]"
