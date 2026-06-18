import asyncio
import json
import re
import os
import time
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, BackgroundTasks, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from app.session import registry, manager
from app.memory_graph import get_memory_graph
from app.sleep_flow import sleep_loop
from app.self_dev import get_shadow_sandbox
from app.lm_client import LMStudioClient
from app.prompts import CHAT_SYSTEM_PROMPT
from app.tools import ToolExecutor
from app.sandbox import LocalSandbox
from app.overseer import OverseerAgent

# Active chat tasks for cancellation
_chat_tasks: Dict[str, asyncio.Task] = {}

logging.basicConfig(level=logging.INFO, format="[%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")
logging.getLogger("httpx").setLevel(logging.WARNING)

@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(sleep_loop(interval_seconds=3600))
    logger.info("Sleep flow loop started (every 3600s)")
    yield

app = FastAPI(title="conv dev framework", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Pydantic models ──────────────────────────────────────────────

class UserApprovalPayload(BaseModel):
    approved: bool
    feedback: Optional[str] = None
    session_id: Optional[str] = None


class CreateSessionPayload(BaseModel):
    session_id: Optional[str] = None
    approval_mode: Optional[str] = None


class DirectTalkPayload(BaseModel):
    message: str
    session_id: Optional[str] = None


class SelfDevProposePayload(BaseModel):
    file_path: str
    content: str
    session_id: Optional[str] = None


class SelfDevDeployPayload(BaseModel):
    session_id: Optional[str] = None


class ChatPayload(BaseModel):
    message: str
    session_id: Optional[str] = None


class DiagnosticsPayload(BaseModel):
    generation_time_s: float = 0
    tokens_per_second: float = 0
    token_count: int = 0
    session_id: Optional[str] = None


class SleepContextPayload(BaseModel):
    start_time: float = 0.0
    end_time: float = 0.0
    session_id: Optional[str] = None


class SleepStartPayload(BaseModel):
    message: str = ""
    session_id: Optional[str] = None


# ── Health ────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/lm/status")
async def lm_status():
    """Check LM Studio connection status."""
    from app.lm_client import LMStudioClient
    client = LMStudioClient()
    try:
        models = await client.get_models()
        if models and 'data' in models and models['data']:
            return {"status": "connected", "model": models['data'][0]['id']}
        return {"status": "disconnected", "model": None}
    except Exception:
        return {"status": "disconnected", "model": None}


# ── Session management ────────────────────────────────────────────

@app.post("/api/session/create")
async def create_session(payload: CreateSessionPayload = None):
    if payload and payload.session_id:
        existing = registry.get(payload.session_id)
        if existing:
            return {"session_id": payload.session_id, "created": False}
    session = registry.create()
    if payload and payload.approval_mode:
        if payload.approval_mode in ("AUTO_APPROVE", "CHECK_WITH_OVERSEER", "WAIT_FOR_USER"):
            session.approval_mode = payload.approval_mode
    return {"session_id": session.session_id, "created": True, "approval_mode": session.approval_mode}


@app.get("/api/sessions")
async def list_sessions():
    return {"sessions": registry.list()}


@app.delete("/api/session/{session_id}")
async def delete_session(session_id: str):
    registry.delete(session_id)
    return {"status": "deleted"}


@app.get("/api/session/info")
async def session_info(session_id: str = Query("default")):
    session = registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return session.to_dict()


@app.get("/api/session/{session_id}/history")
async def session_history(session_id: str):
    session = registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"history": getattr(session, 'chat_history', [])}


# ── Approval mode ────────────────────────────────────────────────

class ApprovalModePayload(BaseModel):
    mode: str = "WAIT_FOR_USER"
    session_id: Optional[str] = None


@app.post("/api/session/approval-mode")
async def set_approval_mode(payload: ApprovalModePayload):
    """Set the approval mode for a session.
    Modes: AUTO_APPROVE, CHECK_WITH_OVERSEER, WAIT_FOR_USER"""
    session_id = payload.session_id or "default"
    session = registry.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    if payload.mode not in ("AUTO_APPROVE", "CHECK_WITH_OVERSEER", "WAIT_FOR_USER"):
        raise HTTPException(status_code=400, detail=f"Invalid mode: {payload.mode}")
    session.approval_mode = payload.mode
    logger.info(f"[{session_id}] Approval mode set to {payload.mode}")
    return {"status": "ok", "session_id": session_id, "approval_mode": payload.mode}


# ── Approval endpoint (for chat ReAct loop) ─────────────────────

@app.post("/api/approve")
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


# ── Chat (ReAct Loop) ────────────────────────────────────────────

REVIEW_TOOLS = {"read_file", 
                "write_file", 
                "run_command", 
                "set_goal", 
                "finish_task", 
                "propose_change", 
                "run_self_test", 
                "deploy_change", 
                "write_user_notes", 
                "replace_lines", 
                "insert_lines", 
                "append_to_file"}
MAX_CHAT_ROUNDS = 50


def extract_tool_call(content: str) -> Optional[Dict[str, Any]]:
    """Extract a tool call from LLM response text.

    Supports all known formats:
      - ```json {"tool":"name","args":{...}} ```
      - <|tool_call|>call:name{...}</tool_call|> (flexible pipe variants)
      - {"tool":"name","args":{...}}  (bare JSON)
      - {"tool_name":"name","tool_args":{...}}  (task system JSON)
    """
    # 1. Flexible <|tool_call|> / <|tool_call> matching with brace-tracking
    tag_pattern = r'<\|?tool_call\|?>'
    m = re.search(tag_pattern, content)
    if m:
        start_idx = m.start()
        # Find opening brace after the tag
        brace_start = content.find('{', m.end())
        if brace_start != -1:
            # Extract function name (after "call:" if present)
            between = content[m.end():brace_start]
            func_match = re.search(r'call:\s*(\w+)', between)
            tool_name = func_match.group(1) if func_match else ''
            if not tool_name:
                # Try finding a word before the brace
                word_m = re.search(r'(\w+)\s*\{', between)
                if word_m:
                    tool_name = word_m.group(1)
            # Find matching close brace
            depth = 0
            args_end = brace_start
            for i in range(brace_start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        args_end = i + 1
                        break
            raw_args = content[brace_start:args_end]
            if tool_name:
                parsed_args = _parse_js_object(raw_args)
                if parsed_args is not None:
                    return {"tool": tool_name, "args": parsed_args}

    # 2. Standard JSON in code fences
    m = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict) and "tool" in data:
                return data
        except (json.JSONDecodeError, KeyError):
            pass

    # 3. Bare JSON {"tool":..., "args":{...}} with brace-tracking for nesting
    for key_pattern in [r'"tool"\s*:', r'"tool_name"\s*:']:
        m = re.search(r'\{\s*' + key_pattern, content, re.DOTALL)
        if m:
            try:
                start = m.start()
                depth = 0
                end = start
                for i in range(start, len(content)):
                    if content[i] == '{':
                        depth += 1
                    elif content[i] == '}':
                        depth -= 1
                        if depth == 0:
                            end = i + 1
                            break
                data = json.loads(content[start:end])
                if isinstance(data, dict):
                    tool = data.get("tool") or data.get("tool_name", "")
                    args = data.get("args") or data.get("tool_args", {})
                    if tool:
                        return {"tool": tool, "args": args}
            except (json.JSONDecodeError, KeyError):
                pass

    return None


def find_tool_call_end(content: str) -> int:
    """Find where the first tool call block ends in content. Returns end index (exclusive)."""
    # 1. <|tool_call|>... block
    tag_pattern = r'<\|?tool_call\|?>'
    m = re.search(tag_pattern, content)
    if m:
        brace_start = content.find('{', m.end())
        if brace_start != -1:
            depth = 0
            for i in range(brace_start, len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        close_tag = re.search(tag_pattern, content[i+1:])
                        return i + 1 + (close_tag.end() if close_tag else 0)
    # 2. ```json block
    m = re.search(r'```(?:json)?\s*\{', content)
    if m:
        close = content.find('```', m.end())
        if close != -1:
            return close + 3
    # 3. Bare JSON
    for key_pattern in [r'"tool"\s*:', r'"tool_name"\s*:']:
        m = re.search(r'\{\s*' + key_pattern, content)
        if m:
            depth = 0
            for i in range(m.start(), len(content)):
                if content[i] == '{':
                    depth += 1
                elif content[i] == '}':
                    depth -= 1
                    if depth == 0:
                        return i + 1
    return len(content)


async def stream_text(session_id: str, text: str, chunk_size: int = 3, delay: float = 0.015):
    """Stream text as chat_token events, respecting stop_requested."""
    session = registry.get(session_id)
    for i in range(0, len(text), chunk_size):
        if session and session.stop_requested:
            return
        token = text[i:i+chunk_size]
        await manager.broadcast({"type": "chat_token", "session_id": session_id, "token": token})
        await asyncio.sleep(delay)


def count_tokens(text: str) -> int:
    """Rough token count estimate."""
    return max(1, len(text) // 4)


def _parse_js_object(text: str) -> Optional[Dict[str, Any]]:
    """Try to parse a JavaScript/JSON-like object string into a dict.

    Handles:
      - true JSON: {"key": "val"}
      - JS-like: {key="val", num=42}
      - mixed: {key: "val", other="val2"}
    """
    text = text.strip()

    # Strip outer braces if present
    if text.startswith('{') and text.endswith('}'):
        text = text[1:-1].strip()

    if not text:
        return {}

    # Try JSON first
    try:
        return json.loads('{' + text + '}')
    except json.JSONDecodeError:
        pass

    # Normalize: convert JS syntax (key=val) to JSON-like ("key": val)
    # by replacing = after keys with : and quoting keys
    normalized = _normalize_js_to_json(text)
    try:
        return json.loads('{' + normalized + '}')
    except json.JSONDecodeError:
        pass

    # Fallback: basic key-value split
    result = {}
    parts = []
    current = ""
    depth = 0
    in_str = False
    str_char = None
    for ch in text:
        if in_str:
            current += ch
            if ch == str_char:
                in_str = False
        elif ch in ('"', "'"):
            in_str = True
            str_char = ch
            current += ch
        elif ch in ('{', '['):
            depth += 1
            current += ch
        elif ch in (']', '}'):
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())

    for part in parts:
        sep = None
        for s in ('=', ':'):
            if s in part:
                idx = part.index(s)
                if sep is None or idx < part.index(sep):
                    sep = (s, idx)
        if sep is None:
            continue
        sep_char, sep_idx = sep
        key = part[:sep_idx].strip().strip('"').strip("'")
        value = part[sep_idx + 1:].strip()
        result[key] = _parse_js_value(value)
    return result


def _parse_js_value(value: str) -> Any:
    """Parse a JS-like value from a tool call argument."""
    value = value.strip()
    if value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value == 'true':
        return True
    if value == 'false':
        return False
    if value == 'null' or value == 'None':
        return None
    if value.startswith('[') and value.endswith(']'):
        # Parse array: [a, b, c] or ["a", "b", "c"]
        inner = value[1:-1].strip()
        if not inner:
            return []
        items = _split_js_values(inner)
        return [_parse_js_value(item.strip()) for item in items]
    if value.startswith('{') and value.endswith('}'):
        return _parse_js_object(value)
    # Try number
    try:
        return int(value) if '.' not in value else float(value)
    except (ValueError, TypeError):
        return value


def _split_js_values(text: str) -> list:
    """Split comma-separated values respecting nesting and quotes."""
    parts = []
    current = ""
    depth = 0
    in_str = False
    str_char = None
    for ch in text:
        if in_str:
            current += ch
            if ch == str_char:
                in_str = False
        elif ch in ('"', "'"):
            in_str = True
            str_char = ch
            current += ch
        elif ch in ('{', '['):
            depth += 1
            current += ch
        elif ch in ('}', ']'):
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())
    return parts


def _normalize_js_to_json(text: str) -> str:
    """Normalize JS-like key=value pairs to JSON-like "key": value.

    Turns:  key="val", num=42, items=[1,2]
    Into:   "key": "val", "num": 42, "items": [1,2]
    """
    result = []
    parts = _split_js_values(text)
    for part in parts:
        # Find separator (= or :)
        sep_idx = -1
        depth = 0
        in_str = False
        str_char = None
        for i, ch in enumerate(part):
            if in_str:
                if ch == str_char:
                    in_str = False
            elif ch in ('"', "'"):
                in_str = True
                str_char = ch
            elif ch in ('{', '['):
                depth += 1
            elif ch in ('}', ']'):
                depth -= 1
            elif ch in ('=', ':') and depth == 0 and not in_str:
                sep_idx = i
                break
        if sep_idx == -1:
            result.append(part)
            continue
        key = part[:sep_idx].strip().strip('"').strip("'")
        val = part[sep_idx + 1:].strip()
        result.append(f'"{key}": {val}')
    return ', '.join(result)


def _resolve_framework_root() -> Path:
    """Resolve the framework root (agent-framework/ dir)."""
    return Path(__file__).resolve().parent.parent.parent


def _sandbox_root() -> Path:
    """Resolve the sandbox workspace directory (project-root sandbox/)."""
    return _resolve_framework_root() / "sandbox"


def _make_sandbox() -> LocalSandbox:
    """Create a LocalSandbox with all scopes registered."""
    sb = LocalSandbox(workspace_dir=str(_sandbox_root()))
    sb.add_scope("framework", _resolve_framework_root())
    shadow = get_shadow_sandbox()
    if shadow.shadow_dir:
        sb.add_scope("shadow", shadow.shadow_dir)
    return sb


def _build_sandbox() -> tuple[LocalSandbox, ToolExecutor]:
    """Build a sandbox with all scopes and a tool executor."""
    sandbox = _make_sandbox()
    executor = ToolExecutor(sandbox)
    return sandbox, executor


def _framework_write_via_shadow(tool_name: str, tool_args: Dict[str, Any]) -> str:
    """Route a framework-scoped write through the shadow sandbox.
    
    Reads the current framework file, applies the edit, writes to shadow.
    """
    shadow = get_shadow_sandbox()
    if shadow.status == "IDLE":
        shadow.create_shadow()
    sandbox_for_read = _make_sandbox()

    file_path = tool_args.get("file_path", "")
    scope = tool_args.get("scope", "framework")

    if tool_name in ("replace_lines", "insert_lines", "append_to_file"):
        # Read current framework file raw
        try:
            raw = sandbox_for_read.read_file(file_path, scope="framework")
        except FileNotFoundError:
            return f"Error: file '{file_path}' not found in framework"
        except Exception as e:
            return f"Error reading framework file: {e}"

        # Apply the edit to the raw content
        if tool_name == "replace_lines":
            start_line = int(tool_args.get("start_line", 0))
            end_line = int(tool_args.get("end_line", 0))
            new_content = tool_args.get("new_content", "")
            lines = raw.split("\n")
            n = len(lines)
            if start_line < 1 or end_line > n or start_line > end_line:
                return f"Error: invalid line range {start_line}-{end_line} (file has {n} lines)"
            new_lines = new_content.split("\n")
            result = "\n".join(lines[:start_line - 1] + new_lines + lines[end_line:])
        elif tool_name == "insert_lines":
            line_number = int(tool_args.get("line_number", 0))
            new_content = tool_args.get("new_content", "")
            lines = raw.split("\n")
            n = len(lines)
            if line_number < 0 or line_number > n:
                return f"Error: invalid line number {line_number} (file has {n} lines)"
            new_lines = new_content.split("\n")
            result = "\n".join(lines[:line_number] + new_lines + lines[line_number:])
        elif tool_name == "append_to_file":
            new_content = tool_args.get("content", "")
            separator = "" if raw.endswith("\n") else "\n"
            result = raw + separator + new_content
        else:
            return f"Unknown edit tool: {tool_name}"

        # Write to shadow
        return shadow.apply_change(file_path, result)

    return f"Unknown framework write tool: {tool_name}"


async def execute_chat_tool(tool_name: str, tool_args: Dict[str, Any], session_id: str = "", sleep_mode: bool = False) -> str:
    """Execute a tool for the chat ReAct loop. Always returns a string."""
    sandbox, executor = _build_sandbox()

    try:
        # ── File I/O (scope-aware) ────────────────────────────────
        if tool_name == "read_file":
            path = tool_args.get("path", "")
            scope = tool_args.get("scope", "default")
            return str(executor.read_file(path, scope=scope))

        elif tool_name == "write_file":
            path = tool_args.get("path", "")
            content = tool_args.get("content", "")
            scope = tool_args.get("scope", "default")
            if scope == "framework":
                return _framework_write_via_shadow("write_file", {
                    "file_path": path, "content": content, "scope": "framework",
                })
            return str(executor.write_file(path, content, scope=scope))

        # ── Surgical Edit Tools ───────────────────────────────────
        elif tool_name == "replace_lines":
            scope = tool_args.get("scope", "default")
            if scope == "framework":
                return _framework_write_via_shadow("replace_lines", tool_args)
            result = executor.replace_lines(
                tool_args.get("file_path", ""),
                int(tool_args.get("start_line", 0)),
                int(tool_args.get("end_line", 0)),
                tool_args.get("new_content", ""),
                scope=scope,
            )
            return str(result)

        elif tool_name == "insert_lines":
            scope = tool_args.get("scope", "default")
            if scope == "framework":
                return _framework_write_via_shadow("insert_lines", tool_args)
            result = executor.insert_lines(
                tool_args.get("file_path", ""),
                int(tool_args.get("line_number", 0)),
                tool_args.get("new_content", ""),
                scope=scope,
            )
            return str(result)

        elif tool_name == "append_to_file":
            scope = tool_args.get("scope", "default")
            if scope == "framework":
                return _framework_write_via_shadow("append_to_file", tool_args)
            result = executor.append_to_file(
                tool_args.get("file_path", ""),
                tool_args.get("content", ""),
                scope=scope,
            )
            return str(result)

        # ── Command execution ─────────────────────────────────────
        elif tool_name == "run_command":
            return str(executor.run_command(tool_args.get("command", "")))

        # ── Todo ──────────────────────────────────────────────────
        elif tool_name == "update_todo":
            result = executor.update_todo(tool_args.get("key", ""), tool_args.get("value", ""))
            return str(result)

        # ── User Notes ────────────────────────────────────────────
        elif tool_name == "read_user_notes":
            return str(executor.read_user_notes())
        elif tool_name == "write_user_notes":
            return str(executor.write_user_notes(tool_args.get("content", "")))

        # ── Goal ──────────────────────────────────────────────────
        elif tool_name == "set_goal":
            goal = tool_args.get("goal", "")
            session_obj = registry.get(session_id)
            if session_obj:
                session_obj.current_goal = goal
            return f"Goal set: {goal}" if goal else "No goal provided"

        # ── Memory Tools ──────────────────────────────────────────
        elif tool_name == "set_current_node":
            return executor.set_current_node(tool_args.get("node_id", ""))
        elif tool_name == "read_detail":
            return executor.read_detail(tool_args.get("key", ""), sleep_mode=sleep_mode)
        elif tool_name == "create_memory":
            return executor.create_memory(
                title=tool_args.get("title", ""),
                detail=tool_args.get("detail", ""),
                linked_ids=tool_args.get("linked_ids", ""),
                is_root=tool_args.get("is_root", False),
            )
        elif tool_name == "update_memory":
            return executor.update_memory(
                node_id=tool_args.get("id", ""),
                title=tool_args.get("title", ""),
                detail=tool_args.get("detail", ""),
                linked_ids=tool_args.get("linked_ids", ""),
            )
        elif tool_name == "refine_memory_methodology":
            return executor.refine_memory_methodology(
                tool_args.get("new_rules", ""),
                tool_args.get("reflection", "")
            )

        # ── Self-Development Pipeline ─────────────────────────────
        elif tool_name == "propose_change":
            shadow = get_shadow_sandbox()
            if shadow.status == "IDLE":
                shadow.create_shadow()
            return shadow.apply_change(tool_args.get("file_path", ""), tool_args.get("content", ""))

        elif tool_name == "run_self_test":
            shadow = get_shadow_sandbox()
            if shadow.status == "IDLE":
                return "No shadow initialized. Use propose_change first."
            results = await asyncio.to_thread(shadow.run_tests)
            return json.dumps(results, indent=2) if isinstance(results, dict) else str(results)

        elif tool_name == "deploy_change":
            shadow = get_shadow_sandbox()
            if shadow.status == "IDLE":
                return "No shadow initialized."
            return shadow.deploy_to_live()

        # ── Communication & Control ───────────────────────────────
        elif tool_name == "ask_user":
            question = tool_args.get("question", "")
            return f"[ASK_USER:{question}]"

        elif tool_name == "finish_task":
            summary = tool_args.get("summary", "")
            return f"[FINISH_TASK:{summary}]"

        else:
            return f"Unknown tool: {tool_name}"

    except Exception as e:
        import traceback
        return f"Error: {e}\n{traceback.format_exc()}"


def find_tool_call_start(content: str) -> int:
    """Find where the tool call JSON block starts. Returns -1 if not found."""
    tag_m = re.search(r'<\|?tool_call\|?>', content)
    if tag_m:
        return tag_m.start()
    fence_m = re.search(r'```(?:json)?\s*\{.*?(?:"tool"|"tool_name").*?\}', content, re.DOTALL)
    if fence_m:
        return fence_m.start()
    for key_pattern in [r'"tool"\s*:', r'"tool_name"\s*:']:
        m = re.search(r'\{\s*' + key_pattern, content)
        if m:
            return m.start()
    return -1


async def stream_chat_response(session_id: str, message: str, sleep_mode: bool = False):
    """ReAct loop: LLM can call tools conversationally, streams all output.
    Approval mode dictates WHO approves tools in REVIEW_TOOLS:
      AUTO_APPROVE      → execute immediately
      CHECK_WITH_OVERSEER → overseer reviews, rejected → feed back to agent
      WAIT_FOR_USER        → user approves/rejects via approval banner
    Tools not in REVIEW_TOOLS execute immediately without any approval.
    If sleep_mode=True, uses SLEEP_SYSTEM_PROMPT and modifies finish_task behavior."""
    lm_client = LMStudioClient()
    overseer = OverseerAgent()
    try:
        models = await lm_client.get_models()
        model_name = models['data'][0]['id'] if (models and 'data' in models and models['data']) else None
        if not model_name:
            await manager.broadcast({"type": "chat_done", "session_id": session_id, "response": "[Error: No model available]"})
            return
    except Exception as e:
        await manager.broadcast({"type": "chat_done", "session_id": session_id, "response": f"[Error: {e}]"})
        return

    session = registry.get(session_id)
    if not session:
        await manager.broadcast({"type": "chat_done", "session_id": session_id, "response": "[Error: Session not found]"})
        return

    # Reset stale stop flag from previous run
    session.stop_requested = False
    session.pause_requested = False

    from app.prompts import SLEEP_SYSTEM_PROMPT
    system_prompt = SLEEP_SYSTEM_PROMPT if sleep_mode else CHAT_SYSTEM_PROMPT

    history = session.chat_history if hasattr(session, 'chat_history') else []
    messages = [{"role": "system", "content": system_prompt}]
    # For sleep mode, start fresh — no history carryover
    if not sleep_mode:
        messages.extend(history)
    # If user pressed continue (empty respond) and last message is from user,
    # don't add another user message — let LLM respond to the existing one
    if message == "__CONTINUE__" and history and history[-1]["role"] == "user":
        pass
    else:
        content = "Please continue." if message == "__CONTINUE__" else message
        messages.append({"role": "user", "content": content})
        # Save user messages to chat_history for page reload
        session.chat_history.append({"role": "user", "content": content})

    clean_text = ""

    # ── Build initial memory context (static across rounds) ──────
    graph = get_memory_graph()
    if sleep_mode:
        now_ts = time.time()
        earliest = min((n.created_at for n in graph._nodes.values()), default=now_ts)
        memory_context = graph.generate_sleep_context(earliest, now_ts)
    else:
        memory_context = graph.current_context()

    await manager.broadcast({"type": "chat_start", "session_id": session_id, "message": message})

    for rnd in range(MAX_CHAT_ROUNDS):
        if session.stop_requested:
            await manager.broadcast({"type": "chat_done", "session_id": session_id, "response": "[Stopped]"})
            return

        # ── Inject todo context into system message (refreshed each round) ──
        todo_context = ""
        todo_path = Path(__file__).parent / "todo.json"
        if todo_path.exists():
            try:
                todo_data = json.loads(todo_path.read_text(encoding="utf-8"))
                todo_items = todo_data.get("todo_items", [])
                completed_items = todo_data.get("completed_items", [])
                parts = []
                if todo_items:
                    parts.append("Pending: " + json.dumps(todo_items))
                if completed_items:
                    parts.append("Completed: " + json.dumps(completed_items))
                if parts:
                    todo_context = "\n\n## Current Todo List\n" + "\n".join(parts)
            except Exception:
                pass
        messages[0] = {"role": "system", "content": system_prompt + "\n\n## Memory Context (always accessible; use read_detail for full details)\n" + memory_context + todo_context}

        # ── Streaming LLM call ──────────────────────────────────
        t0 = time.time()
        content_buffer = ""
        tok_count = 0
        last_diag_ts = t0

        await manager.broadcast({"type": "llm_call", "session_id": session_id})

        try:
            async for token_type, token in lm_client.chat_completion_stream(model=model_name, messages=messages, temperature=0.7):
                if session.stop_requested and not sleep_mode:
                    raise asyncio.CancelledError()

                if token_type == "reasoning":
                    await manager.broadcast({
                        "type": "chat_reasoning_token",
                        "session_id": session_id,
                        "token": token
                    })
                elif token_type == "content":
                    content_buffer += token
                    tok_count += 1
                    await manager.broadcast({
                        "type": "chat_token",
                        "session_id": session_id,
                        "token": token
                    })
                    # Periodic diagnostics every 200ms
                    now = time.time()
                    if now - last_diag_ts >= 0.2:
                        elapsed = now - t0
                        tps = tok_count / elapsed if elapsed > 0 else 0
                        await manager.broadcast({
                            "type": "chat_stream_diag",
                            "session_id": session_id,
                            "diagnostics": {
                                "generation_time_s": elapsed,
                                "tokens_per_second": tps,
                                "token_count": tok_count
                            }
                        })
                        last_diag_ts = now
        except asyncio.CancelledError:
            # Save partial output so agent sees it next round
            if content_buffer.strip():
                if not sleep_mode:
                    session.chat_history.append({"role": "assistant", "content": content_buffer})
            return

        t1 = time.time()
        gen_time = t1 - t0
        tps = tok_count / gen_time if gen_time > 0 else 0
        diag = {"generation_time_s": gen_time, "tokens_per_second": tps, "token_count": tok_count}

        # ── Pause check (after stream finishes, before next action) ──
        if session.pause_requested:
            await manager.broadcast({"type": "chat_paused", "session_id": session_id})
            await session.resume_event.wait()
            session.resume_event.clear()
            if session.stop_requested and not sleep_mode:
                await manager.broadcast({"type": "chat_done", "session_id": session_id, "response": "[Stopped]"})
                return

        # ── Detect tool call ─────────────────────────────────────
        tool_call = extract_tool_call(content_buffer)

        if not tool_call:
            await manager.broadcast({
                "type": "chat_done", "session_id": session_id,
                "response": content_buffer,
                "diagnostics": diag
            })
            session.chat_history.append({"role": "assistant", "content": content_buffer})
            return

        # ── Extract text before tool call ──────────────────────────
        tool_start = find_tool_call_start(content_buffer)
        text_before = content_buffer[:tool_start].strip() if tool_start > 0 else ""
        if text_before:
            clean_text += ("\n\n" if clean_text else "") + text_before

        tool_name = tool_call.get("tool", "")
        tool_args = tool_call.get("args", {})

        # ── Broadcast tool card ─────────────────────────────────────
        await manager.broadcast({
            "type": "chat_tool", "session_id": session_id,
            "tool_name": tool_name, "tool_args": tool_args,
            "clean_text": clean_text,
            "diagnostics": diag
        })

        observation = ""

        # ── Approval gate (bypass for ask_user and finish_task in sleep mode) ──
        if sleep_mode and tool_name == "finish_task":
            pass  # no approval needed in sleep mode
        elif tool_name in REVIEW_TOOLS and tool_name not in ("ask_user",):
            mode = session.approval_mode

            if mode == "CHECK_WITH_OVERSEER":
                previous_block = ""
                if len(messages) >= 2:
                    for m in messages[-2:]:
                        role = m.get("role", "unknown")
                        c = m.get("content", "")[:1000]
                        previous_block += f"[{role}]: {c}\n"

                # Include current todo state + goal for goal/todo changes
                if tool_name in ("set_goal", "update_todo"):
                    todo_path = Path(__file__).parent / "todo.json"
                    if todo_path.exists():
                        try:
                            todo_data = json.loads(todo_path.read_text(encoding="utf-8"))
                            goal_line = f"Current goal: {session.current_goal or '(none)'}"
                            ctx = f"\n--- Current state ---\n{goal_line}\nCurrent todo: {json.dumps(todo_data.get('todo_items', []))}\nCompleted: {json.dumps(todo_data.get('completed_items', []))}\nProposed: {tool_name} with args: {json.dumps(tool_args)}"
                            previous_block = (previous_block or "") + ctx
                        except Exception:
                            pass

                await manager.broadcast({"type": "overseer_review_start", "session_id": session_id})
                review = await overseer.review_action(
                    tool_name=tool_name, tool_args=tool_args,
                    thought=content_buffer[:500], previous_block=previous_block,
                    sandbox_dir=str(_sandbox_root()),
                )
                review_status = review.get("status", "REJECTED").upper()
                review_reasoning = review.get("reasoning", "")
                review_feedback = review.get("feedback", "")
                approved = review_status == "APPROVED"

                if review_reasoning:
                    await stream_text(session_id, review_reasoning + "\n", chunk_size=5, delay=0.01)
                await manager.broadcast({
                    "type": "overseer_review", "session_id": session_id,
                    "status": review_status, "reasoning": review_reasoning,
                    "feedback": review_feedback, "approved": approved
                })

                if not approved:
                    observation = f"[Overseer rejected: {review_feedback}]"
                    await manager.broadcast({"type": "chat_tool_result", "session_id": session_id, "observation": observation})
                    messages.append({"role": "assistant", "content": content_buffer})
                    messages.append({"role": "user", "content": f"Overseer rejected your {tool_name} action. Feedback: {review_feedback}. Try a different approach."})
                    continue

            elif mode == "WAIT_FOR_USER":
                thought = f"The agent wants to run: {tool_name}"
                if tool_name in ("set_goal", "update_todo"):
                    todo_path = Path(__file__).parent / "todo.json"
                    if todo_path.exists():
                        try:
                            todo_data = json.loads(todo_path.read_text(encoding="utf-8"))
                            thought += f"\nCurrent goal: {session.current_goal or '(none)'}\nCurrent todo: {json.dumps(todo_data.get('todo_items', []))}\nCompleted: {json.dumps(todo_data.get('completed_items', []))}"
                        except Exception:
                            pass
                await manager.broadcast({
                    "type": "awaiting_user_approval", "session_id": session_id,
                    "tool_name": tool_name, "tool_args": tool_args,
                    "thought": thought
                })
                try:
                    approval = await asyncio.wait_for(session.user_response_queue.get(), timeout=300.0)
                except asyncio.TimeoutError:
                    observation = "[Approval timed out]"
                    await manager.broadcast({"type": "chat_tool_result", "session_id": session_id, "observation": observation})
                    await manager.broadcast({"type": "chat_done", "session_id": session_id, "response": "[Approval timed out]"})
                    return

                if not approval.get("approved", False):
                    feedback = approval.get("feedback", "User rejected")
                    observation = f"[Rejected: {feedback}]"
                    await manager.broadcast({"type": "chat_tool_result", "session_id": session_id, "observation": observation})
                    messages.append({"role": "assistant", "content": content_buffer})
                    messages.append({"role": "user", "content": f"Your {tool_name} action was rejected by the user. Feedback: {feedback}. Try a different approach or explain why it's needed."})
                    continue

            # mode == "AUTO_APPROVE": fall through — execute immediately

        # ── Execute tool ────────────────────────────────────────────
        if not observation:
            observation = await execute_chat_tool(tool_name, tool_args, session_id, sleep_mode=sleep_mode)

        obs_trunc = 600 if tool_name != "read_detail" else 100000
        await manager.broadcast({
            "type": "chat_tool_result", "session_id": session_id,
            "tool_name": tool_name, "observation": observation[:obs_trunc]
        })

        # ── Special tool handling ────────────────────────────────────

        if tool_name == "finish_task":
            summary = tool_args.get("summary", observation.replace("[FINISH_TASK:", "").rstrip("]"))
            await manager.broadcast({
                "type": "task_complete", "session_id": session_id,
                "status": "COMPLETED", "summary": summary
            })
            await stream_text(session_id, summary)

            if sleep_mode:
                # In sleep mode: first finish_task → ask to reflect
                # Check if we already did a reflection round
                last_user_msg = messages[-1]["content"] if messages else ""
                if "reflect on your work" in last_user_msg.lower():
                    # Already reflected — this is the second call, truly done
                    session.sleep_mode = False
                    await manager.broadcast({"type": "chat_done", "session_id": session_id, "response": f"[Sleep complete] {summary}"})
                    return
                # First call — prompt reflection
                messages.append({"role": "assistant", "content": content_buffer})
                messages.append({"role": "user", "content": "Now reflect on your work. Consider calling refine_memory_methodology to update your memory management rules. When you are truly finished (or if you decide more work is needed), call finish_task again."})
                continue
            else:
                session.chat_history.append({"role": "assistant", "content": content_buffer})
                await manager.broadcast({"type": "chat_done", "session_id": session_id, "response": summary})
                return

        if tool_name == "ask_user":
            question = tool_args.get("question", tool_args.get("message", "I have a question."))
            await manager.broadcast({"type": "ask_user", "session_id": session_id, "question": question})
            try:
                answer = await asyncio.wait_for(session.user_response_queue.get(), timeout=600.0)
            except asyncio.TimeoutError:
                answer = "[User did not respond]"
            answer_text = answer.get("feedback", answer) if isinstance(answer, dict) else str(answer)
            messages.append({"role": "assistant", "content": content_buffer})
            messages.append({"role": "user", "content": f"User answered your question: {answer_text}"})
            continue

        if tool_name == "set_goal":
            new_goal = tool_args.get("goal", "")
            session.current_goal = new_goal
            await manager.broadcast({"type": "goal_set", "session_id": session_id, "goal": new_goal})

        obs_trunc = 100000 if tool_name == "read_detail" else 1500
        messages.append({"role": "assistant", "content": content_buffer})
        continuation = "Continue your memory consolidation work." if sleep_mode else "Continue your response naturally."
        messages.append({"role": "user", "content": f"Tool {tool_name} returned:\n{observation[:obs_trunc]}\n\n{continuation}"})

    await manager.broadcast({"type": "chat_done", "session_id": session_id, "response": "[I've completed what I can do. Feel free to ask for more.]"})


@app.post("/api/chat")
async def chat(payload: ChatPayload, background_tasks: BackgroundTasks):
    """Send a chat message via ReAct loop (tool-using conversational agent)."""
    session_id = payload.session_id
    if not session_id or not registry.get(session_id):
        sess = registry.create()
        session_id = sess.session_id
    else:
        sess = registry.get(session_id)

    # Cancel any existing chat for this session
    existing = _chat_tasks.get(session_id)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(stream_chat_response(session_id, payload.message))
    task.add_done_callback(lambda _: _chat_tasks.pop(session_id, None))
    _chat_tasks[session_id] = task
    return {"status": "ok", "session_id": session_id}


@app.post("/api/chat/send")
async def chat_send(payload: ChatPayload):
    """Post a user message to chat history without triggering the agent."""
    sid = payload.session_id if payload and payload.session_id else "default"
    session = registry.get(sid)
    if not session:
        return {"status": "error", "message": "Session not found"}
    if payload.message:
        session.chat_history.append({"role": "user", "content": payload.message})
        await manager.broadcast({"type": "user_message", "session_id": sid, "message": payload.message})
    return {"status": "ok", "session_id": sid}


@app.post("/api/chat/stop")
async def stop_chat(payload: CreateSessionPayload = None):
    """Stop the current chat response immediately. All output stays visible."""
    sid = payload.session_id if payload and payload.session_id else "default"
    session = registry.get(sid)
    if session:
        session.stop_requested = True
    existing = _chat_tasks.get(sid)
    if existing and not existing.done():
        existing.cancel()
        await manager.broadcast({"type": "chat_done", "session_id": sid, "response": "[Stopped]"})
    return {"status": "stopped", "session_id": sid}


@app.post("/api/chat/pause")
async def pause_chat(payload: CreateSessionPayload = None):
    """Pause after current LLM response finishes (soft pause between rounds)."""
    sid = payload.session_id if payload and payload.session_id else "default"
    session = registry.get(sid)
    if session:
        session.pause_requested = True
    return {"status": "pausing", "session_id": sid}


@app.post("/api/chat/resume")
async def resume_chat(payload: CreateSessionPayload = None):
    """Resume a paused chat."""
    sid = payload.session_id if payload and payload.session_id else "default"
    session = registry.get(sid)
    if session:
        session.pause_requested = False
        session.resume_event.set()
    return {"status": "resumed", "session_id": sid}


@app.post("/api/chat/sleep-start")
async def sleep_start(payload: SleepStartPayload):
    """Start sleep-flow optimization via the chat ReAct loop."""
    sid = payload.session_id if payload and payload.session_id else "default"
    session = registry.get(sid)
    if not session:
        session = registry.create()
        sid = session.session_id
    session.sleep_mode = True

    existing = _chat_tasks.get(sid)
    if existing and not existing.done():
        existing.cancel()

    task = asyncio.create_task(stream_chat_response(sid, payload.message, sleep_mode=True))
    task.add_done_callback(lambda _: _chat_tasks.pop(sid, None))
    _chat_tasks[sid] = task
    return {"status": "sleep_started", "session_id": sid}


@app.post("/api/chat/sleep-wake")
async def sleep_wake(payload: CreateSessionPayload = None):
    """End sleep mode and stop the sleep flow."""
    sid = payload.session_id if payload and payload.session_id else "default"
    session = registry.get(sid)
    if session:
        session.sleep_mode = False
        session.stop_requested = True
    existing = _chat_tasks.get(sid)
    if existing and not existing.done():
        existing.cancel()
        await manager.broadcast({"type": "chat_done", "session_id": sid, "response": "[Sleep ended]"})
    return {"status": "sleep_ended", "session_id": sid}




@app.get("/api/state")
async def get_state(session_id: str = Query("default")):
    try:
        base = os.path.dirname(os.path.abspath(__file__))
        memory_path = os.path.join(base, "memory.json")
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
    """Return the flat memory node list."""
    graph = get_memory_graph()
    return {
        "current_node_id": graph.current_node_id,
        "nodes": graph.get_all_nodes(),
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


# ── Todo List (standalone todo.json file) ────────────────────────

TODO_PATH = Path(__file__).parent / "todo.json"


@app.get("/api/todos")
async def get_todos():
    """Return the todo items list."""
    default = {"todo_items": [], "completed_items": []}
    if TODO_PATH.exists():
        try:
            return json.loads(TODO_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return default


@app.put("/api/todos")
async def update_todos(payload: DirectTalkPayload):
    """Update the todo items list."""
    try:
        data = json.loads(TODO_PATH.read_text(encoding="utf-8")) if TODO_PATH.exists() else {"todo_items": [], "completed_items": []}
        updated = json.loads(payload.message)
        for k, v in updated.items():
            data[k] = v
        TODO_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return {"status": "updated"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Sleep Context ────────────────────────────────────────────────

@app.post("/api/sleep-context")
async def generate_sleep_context(payload: SleepContextPayload):
    """Generate a recursive sleep context for preview (no optimization)."""
    start = payload.start_time or 0.0
    end = payload.end_time or time.time()
    from app.memory_graph import get_memory_graph
    graph = get_memory_graph()
    context = graph.generate_sleep_context(start, end)
    return {"status": "generated", "context": context, "start_time": start, "end_time": end}


@app.post("/api/sleep-flow")
async def trigger_sleep_flow(payload: SleepContextPayload):
    """Run the sleep-flow optimization cycle for the given time range."""
    from app.sleep_flow import run_sleep_cycle
    start = payload.start_time or 0.0
    end = payload.end_time or time.time()
    asyncio.create_task(run_sleep_cycle(start_time=start, end_time=end))
    return {"status": "started", "start_time": start, "end_time": end}


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
