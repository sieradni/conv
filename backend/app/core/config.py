import os
from pathlib import Path

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent.parent.parent
BACKEND_DIR = FRAMEWORK_ROOT / "backend"
APP_DIR = BACKEND_DIR / "app"
DATA_DIR = BACKEND_DIR / "data"
FRONTEND_DIR = FRAMEWORK_ROOT / "frontend"
SANDBOX_DIR = FRAMEWORK_ROOT / "sandbox"
VENV_DIR = BACKEND_DIR / "venv"

SESSION_FILE = DATA_DIR / "session.json"
TODO_FILE = APP_DIR / "todo.json"
NOTES_FILE = APP_DIR / "user_notes.md"
DIAG_FILE = APP_DIR / "diagnostics.json"
MEMORY_FILE = APP_DIR / "memory.json"
MEMORY_RULES_FILE = APP_DIR / "memory_rules.md"
REMINDERS_FILE = APP_DIR / "reminders.json"
META_PROMPT_HISTORY_LOG = APP_DIR / "meta_prompt_history.log"

LM_STUDIO_BASE_URL = os.environ.get("LM_STUDIO_URL", "http://localhost:1234")
LM_STUDIO_LEGACY_URL = f"{LM_STUDIO_BASE_URL}/v1"
LM_STUDIO_V2_URL = f"{LM_STUDIO_BASE_URL}/api/v1"
LM_STUDIO_TIMEOUT = 120.0

MAX_CHAT_ROUNDS = 50
MAX_TOOL_OBSERVATION_LENGTH = 1500
MAX_DETAIL_OBSERVATION_LENGTH = 100000

REVIEW_TOOLS = {
    "read_file", "write_file", "run_command", "set_goal",
    "finish_task", "propose_change", "run_self_test",
    "deploy_change", "write_user_notes", "replace_lines",
    "insert_lines", "append_to_file",
}

APPROVAL_MODES = ("AUTO_APPROVE", "CHECK_WITH_OVERSEER", "WAIT_FOR_USER")

WS_HEARTBEAT_INTERVAL = 30
WS_HEARTBEAT_TIMEOUT = 30
