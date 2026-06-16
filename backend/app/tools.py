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
    
    def read_memory(self) -> Dict[str, Any]:
        """Read and return current working memory.
        
        Returns:
            Dictionary containing working memory state
        
        Raises:
            Exception: If memory file cannot be read
        """
        try:
            memory_path = Path(__file__).parent / "working_memory.json"
            if not memory_path.exists():
                return {
                    "project_overview": "Not initialized",
                    "facts_discovered": {},
                    "active_decisions": [],
                    "todo_list": [],
                    "completed_tasks": []
                }
            
            with open(memory_path, 'r') as f:
                memory = json.load(f)
            
            self.execution_log.append({
                "tool": "read_memory",
                "status": "success",
                "keys_read": list(memory.keys())
            })
            
            return memory
        except Exception as e:
            error_msg = f"Error reading memory: {str(e)}"
            self.execution_log.append({
                "tool": "read_memory",
                "status": "failed",
                "error": str(e)
            })
            raise Exception(error_msg)
    
    def write_memory(self, key: str, value: Any) -> str:
        """Update a key in working memory and save to disk.
        
        Args:
            key: Top-level key in working_memory.json
            value: Value to set for the key
        
        Returns:
            Success message
        
        Raises:
            Exception: If memory file cannot be written
        """
        try:
            memory_path = Path(__file__).parent / "working_memory.json"
            
            # Read existing memory
            if memory_path.exists():
                with open(memory_path, 'r') as f:
                    memory = json.load(f)
            else:
                memory = {
                    "project_overview": "Not initialized",
                    "facts_discovered": {},
                    "active_decisions": [],
                    "todo_list": [],
                    "completed_tasks": []
                }
            
            # Update the specified key
            memory[key] = value
            
            # Write back to file
            with open(memory_path, 'w') as f:
                json.dump(memory, f, indent=2)
            
            self.execution_log.append({
                "tool": "write_memory",
                "key": key,
                "status": "success"
            })
            
            return f"✓ Updated memory key '{key}'"
        except Exception as e:
            error_msg = f"Error writing memory: {str(e)}"
            self.execution_log.append({
                "tool": "write_memory",
                "key": key,
                "status": "failed",
                "error": str(e)
            })
            raise Exception(error_msg)
    
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
