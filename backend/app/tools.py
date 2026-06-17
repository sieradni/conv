"""Execution Tools - Agent interface to sandbox and system operations"""

import subprocess
import os
import json
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from app.sandbox import LocalSandbox


class ToolExecutor:
    """Manages tool execution within the sandbox."""
    
    def __init__(self, sandbox: LocalSandbox):
        """Initialize tool executor with a sandbox instance.
        
        Args:
            sandbox: LocalSandbox instance for safe file operations
        """
        self.sandbox = sandbox
        self.execution_log = []
    
    def write_file(self, path: str, content: str) -> str:
        """Write content to a file in the sandbox.
        
        Args:
            path: Relative path within the sandbox
            content: String content to write
        
        Returns:
            Success message
        
        Raises:
            PermissionError: If path escapes sandbox
            Exception: For other write errors
        """
        try:
            result = self.sandbox.write_file(path, content)
            self.execution_log.append({
                "tool": "write_file",
                "path": path,
                "status": "success",
                "message": result
            })
            return result
        except Exception as e:
            error_msg = f"Error writing file: {str(e)}"
            self.execution_log.append({
                "tool": "write_file",
                "path": path,
                "status": "failed",
                "error": str(e)
            })
            raise Exception(error_msg)
    
    def read_file(self, path: str) -> str:
        """Read content from a file in the sandbox.
        
        Args:
            path: Relative path within the sandbox
        
        Returns:
            File content as a string
        
        Raises:
            PermissionError: If path escapes sandbox
            FileNotFoundError: If file does not exist
        """
        try:
            content = self.sandbox.read_file(path)
            self.execution_log.append({
                "tool": "read_file",
                "path": path,
                "status": "success",
                "bytes_read": len(content)
            })
            return content
        except Exception as e:
            error_msg = f"Error reading file: {str(e)}"
            self.execution_log.append({
                "tool": "read_file",
                "path": path,
                "status": "failed",
                "error": str(e)
            })
            raise Exception(error_msg)
    
    def run_command(self, command: str, timeout: int = 10) -> str:
        """Execute a shell command in the sandbox directory.
        
        Args:
            command: Shell command to execute
            timeout: Maximum execution time in seconds (default: 10)
        
        Returns:
            Command output (stdout + stderr combined)
        
        Raises:
            subprocess.TimeoutExpired: If command exceeds timeout
            Exception: For execution errors
        """
        try:
            # Ensure we run in the sandbox directory
            sandbox_path = str(self.sandbox.workspace_path)
            
            # Execute with timeout and cwd restricted to sandbox
            result = subprocess.run(
                command,
                shell=True,
                cwd=sandbox_path,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            # Combine stdout and stderr
            output = result.stdout
            if result.stderr:
                output += "\n[STDERR]\n" + result.stderr
            
            self.execution_log.append({
                "tool": "run_command",
                "command": command,
                "status": "success",
                "return_code": result.returncode,
                "output_length": len(output)
            })
            
            return output if output else f"[Command executed with return code {result.returncode}]"
            
        except subprocess.TimeoutExpired:
            error_msg = f"Command timeout: execution exceeded {timeout} seconds"
            self.execution_log.append({
                "tool": "run_command",
                "command": command,
                "status": "timeout",
                "timeout_seconds": timeout
            })
            raise Exception(error_msg)
        except Exception as e:
            error_msg = f"Error running command: {str(e)}"
            self.execution_log.append({
                "tool": "run_command",
                "command": command,
                "status": "failed",
                "error": str(e)
            })
            raise Exception(error_msg)
    
    def read_todo(self) -> Dict[str, Any]:
        """Read the todo items from the todo file.

        Returns:
            Dict with 'todo_items' list and 'completed_items' list
        """
        todo_path = Path(__file__).parent / "todo.json"
        if not todo_path.exists():
            return {"todo_items": [], "completed_items": []}
        try:
            return json.loads(todo_path.read_text(encoding="utf-8"))
        except Exception:
            return {"todo_items": [], "completed_items": []}

    def update_todo(self, key: str, value: Any) -> str:
        """Update the todo items file.

        Args:
            key: "todo_items" or "completed_items"
            value: List of item strings

        Returns:
            Success message
        """
        todo_path = Path(__file__).parent / "todo.json"
        data = {"todo_items": [], "completed_items": []}
        if todo_path.exists():
            try:
                data = json.loads(todo_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        data[key] = value
        todo_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return f"✓ Updated {key}"

    def read_memory(self) -> Dict[str, Any]:
        return self.read_todo()

    def write_memory(self, key: str, value: Any) -> str:
        return self.update_todo(key, value)
    
    def refine_memory_methodology(self, new_rules: str, reflection: str) -> str:
        """Update memory management guidelines and log the change.
        
        Args:
            new_rules: New memory guidelines in markdown format
            reflection: Explanation of why guidelines are being updated
        
        Returns:
            Success message
        
        Raises:
            Exception: If files cannot be written
        """
        try:
            # Update memory_rules.md
            rules_path = Path(__file__).parent / "memory_rules.md"
            with open(rules_path, 'w') as f:
                f.write(new_rules)
            
            # Append to meta_prompt_history.log
            history_path = Path(__file__).parent / "meta_prompt_history.log"
            timestamp = datetime.now().isoformat()
            
            log_entry = f"""
================================================================================
Timestamp: {timestamp}
Agent Reflection:
{reflection}

New Rules Applied:
{new_rules}
================================================================================

"""
            
            with open(history_path, 'a') as f:
                f.write(log_entry)
            
            self.execution_log.append({
                "tool": "refine_memory_methodology",
                "status": "success",
                "timestamp": timestamp
            })
            
            return f"✓ Updated memory methodology and logged to audit trail"
        except Exception as e:
            error_msg = f"Error refining memory methodology: {str(e)}"
            self.execution_log.append({
                "tool": "refine_memory_methodology",
                "status": "failed",
                "error": str(e)
            })
            raise Exception(error_msg)
    
    def ask_overseer(self, question: str) -> str:
        return f"[Asking Overseer: {question[:50]}...]"

    # ── Memory Tools ────────────────────────────────────────────

    def set_current_node(self, node_id: str = "") -> str:
        """Set the current memory focus node."""
        from app.memory_graph import get_memory_graph
        graph = get_memory_graph()
        nid = node_id.strip() or None
        node = graph.set_current_node(nid)
        if nid is None:
            return "✓ Current node cleared."
        if node:
            return f"✓ Current node set to [{node.id[:8]}] {node.title}"
        return f"Node '{node_id}' not found."

    def read_detail(self, node_id: str, sleep_mode: bool = False) -> str:
        """Read the full detail block of a memory node (increments access count unless sleep_mode)."""
        from app.memory_graph import get_memory_graph
        graph = get_memory_graph()
        detail = graph.read_detail(node_id, sleep_mode=sleep_mode)
        if detail is not None:
            return f"Detail for node {node_id[:8]}:\n{detail}"
        return f"Node '{node_id}' not found."

    def create_memory(
        self, title: str, detail: str = "",
        linked_ids: str = "", is_root: bool = False
    ) -> str:
        """Create a new memory node."""
        from app.memory_graph import get_memory_graph
        graph = get_memory_graph()
        lids = [x.strip() for x in linked_ids.split(",") if x.strip()] if linked_ids else None
        node = graph.create_memory(
            title=title, detail=detail,
            linked_ids=lids, is_root=is_root,
        )
        return f"✓ Created memory [{node.id[:8]}] '{title}'"

    def update_memory(
        self, node_id: str,
        title: str = "", detail: str = "",
        linked_ids: str = "",
    ) -> str:
        """Modify an existing memory node. Empty strings mean 'leave unchanged'."""
        from app.memory_graph import get_memory_graph
        graph = get_memory_graph()
        kwargs = {}
        if title:
            kwargs["title"] = title
        if detail:
            kwargs["detail"] = detail
        if linked_ids:
            kwargs["linked_ids"] = [x.strip() for x in linked_ids.split(",") if x.strip()]
        node = graph.update_memory(node_id, **kwargs)
        if node:
            return f"✓ Updated memory [{node.id[:8]}] {node.title}"
        return f"Node '{node_id}' not found."

    # ── Self-Development Tools ────────────────────────────────────

    def propose_change(self, file_path: str, content: str) -> str:
        """Propose a change to the framework's own codebase (in shadow)."""
        from app.self_dev import get_shadow_sandbox
        sandbox = get_shadow_sandbox()
        if sandbox.status == "IDLE":
            sandbox.create_shadow()
        return sandbox.apply_change(file_path, content)

    def run_self_test(self) -> str:
        """Run the framework's test suite inside the shadow sandbox."""
        from app.self_dev import get_shadow_sandbox
        sandbox = get_shadow_sandbox()
        results = sandbox.run_tests()
        status = results.get("status", "UNKNOWN")
        output = results.get("output", "")[:1000]
        return f"Test status: {status}\n{output}"

    def deploy_change(self) -> str:
        """Deploy approved shadow changes to the live framework."""
        from app.self_dev import get_shadow_sandbox
        sandbox = get_shadow_sandbox()
        return sandbox.deploy_to_live()

    def read_user_notes(self) -> str:
        """Read the user's persistent notes scratchpad."""
        notes_path = Path(__file__).parent / "user_notes.md"
        if notes_path.exists():
            return notes_path.read_text(encoding="utf-8")
        return "# User Notes\n\nNo notes yet."



# Global tool executor instance (will be initialized in orchestrator)
_executor: Optional[ToolExecutor] = None


def set_executor(executor: ToolExecutor):
    """Set the global tool executor instance."""
    global _executor
    _executor = executor


def get_executor() -> ToolExecutor:
    """Get the global tool executor instance."""
    global _executor
    if _executor is None:
        raise RuntimeError("Tool executor not initialized")
    return _executor
