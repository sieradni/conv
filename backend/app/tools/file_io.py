"""File I/O tools — read, write, replace_lines, insert_lines, append_to_file."""

import json
from pathlib import Path
from typing import Any

from app.sandbox import LocalSandbox
from app.core.config import FRAMEWORK_ROOT, SANDBOX_DIR
from app.self_dev import get_shadow_sandbox


def _make_sandbox() -> LocalSandbox:
    sb = LocalSandbox(workspace_dir=str(SANDBOX_DIR))
    sb.add_scope("framework", FRAMEWORK_ROOT)
    shadow = get_shadow_sandbox()
    if shadow.shadow_dir:
        sb.add_scope("shadow", shadow.shadow_dir)
    return sb


def read_file(path: str, scope: str = "default") -> str:
    sandbox = _make_sandbox()
    return sandbox.read_file_numbered(path, scope=scope)


def write_file(path: str, content: str, scope: str = "default") -> str:
    sandbox = _make_sandbox()
    if scope == "framework":
        return _framework_write("write_file", {"file_path": path, "content": content})
    return sandbox.write_file(path, content, scope=scope)


def replace_lines(
    file_path: str, start_line: int, end_line: int,
    new_content: str, scope: str = "default",
) -> str:
    if scope == "framework":
        return _framework_write("replace_lines", {
            "file_path": file_path, "start_line": start_line,
            "end_line": end_line, "new_content": new_content,
        })
    sandbox = _make_sandbox()
    raw = sandbox.read_file(file_path, scope=scope)
    lines = raw.split("\n")
    n = len(lines)
    if start_line < 1 or end_line > n or start_line > end_line:
        return f"Error: invalid line range {start_line}-{end_line} (file has {n} lines)"
    new_lines = new_content.split("\n")
    result = "\n".join(lines[:start_line - 1] + new_lines + lines[end_line:])
    sandbox.write_file(file_path, result, scope=scope)
    return f"Replaced lines {start_line}-{end_line} in {file_path} ({len(new_lines)} lines)"


def insert_lines(
    file_path: str, line_number: int,
    new_content: str, scope: str = "default",
) -> str:
    if scope == "framework":
        return _framework_write("insert_lines", {
            "file_path": file_path, "line_number": line_number,
            "new_content": new_content,
        })
    sandbox = _make_sandbox()
    raw = sandbox.read_file(file_path, scope=scope)
    lines = raw.split("\n")
    n = len(lines)
    if line_number < 0 or line_number > n:
        return f"Error: invalid line number {line_number} (file has {n} lines)"
    new_lines = new_content.split("\n")
    result = "\n".join(lines[:line_number] + new_lines + lines[line_number:])
    sandbox.write_file(file_path, result, scope=scope)
    return f"Inserted {len(new_lines)} line(s) after line {line_number} in {file_path}"


def append_to_file(file_path: str, content: str, scope: str = "default") -> str:
    if scope == "framework":
        return _framework_write("append_to_file", {
            "file_path": file_path, "content": content,
        })
    sandbox = _make_sandbox()
    raw = sandbox.read_file(file_path, scope=scope)
    separator = "" if raw.endswith("\n") else "\n"
    sandbox.write_file(file_path, raw + separator + content, scope=scope)
    return f"Appended to {file_path}"


def run_command(command: str) -> str:
    sandbox = _make_sandbox()
    import shlex, subprocess
    args = shlex.split(command)
    try:
        result = subprocess.run(
            args, shell=False, cwd=str(SANDBOX_DIR),
            capture_output=True, text=True, timeout=10,
        )
        output = result.stdout
        if result.stderr:
            output += "\n[STDERR]\n" + result.stderr
        return output or f"[Exit code {result.returncode}]"
    except subprocess.TimeoutExpired:
        return "[Command timed out after 10s]"
    except Exception as e:
        return f"[Error: {e}]"


def _framework_write(tool_name: str, tool_args: dict) -> str:
    """Route framework-scoped writes through the shadow sandbox."""
    from app.self_dev import get_shadow_sandbox
    shadow = get_shadow_sandbox()
    if shadow.status == "IDLE":
        shadow.create_shadow()
    sandbox = _make_sandbox()
    file_path = tool_args.get("file_path", "")

    try:
        raw = sandbox.read_file(file_path, scope="framework")
    except FileNotFoundError:
        return f"Error: file '{file_path}' not found in framework"
    except Exception as e:
        return f"Error reading framework file: {e}"

    if tool_name == "write_file":
        result = tool_args.get("content", "")
    elif tool_name == "replace_lines":
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
        return f"Unknown framework write tool: {tool_name}"

    return shadow.apply_change(file_path, result)
