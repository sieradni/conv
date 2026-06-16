"""Local Sandbox - Safe execution environment for agent file operations"""

import os
from pathlib import Path


class LocalSandbox:
    """Sandbox for safe file operations within a restricted workspace directory."""
    
    def __init__(self, workspace_dir: str = "sandbox"):
        """Initialize the sandbox with a workspace directory.
        
        Args:
            workspace_dir: Path to the sandbox workspace directory
        """
        self.workspace_path = Path(workspace_dir).resolve()
        self.workspace_path.mkdir(exist_ok=True)

    def _safe_path(self, relative_path: str) -> Path:
        """Resolves path and raises PermissionError if it escapes the workspace directory.
        
        Args:
            relative_path: Relative path within the sandbox
        
        Returns:
            Resolved Path object
        
        Raises:
            PermissionError: If the path attempts to escape the sandbox directory
        """
        target_path = Path(self.workspace_path / relative_path).resolve()
        if not target_path.is_relative_to(self.workspace_path):
            raise PermissionError("Access denied: Attempted to escape sandbox directory.")
        return target_path

    def write_file(self, relative_path: str, content: str) -> str:
        """Write content to a file in the sandbox.
        
        Args:
            relative_path: Relative path within the sandbox
            content: Content to write to the file
        
        Returns:
            Success message with the file path
        
        Raises:
            PermissionError: If the path escapes the sandbox directory
        """
        target = self._safe_path(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote file to {relative_path}"

    def read_file(self, relative_path: str) -> str:
        """Read content from a file in the sandbox.
        
        Args:
            relative_path: Relative path within the sandbox
        
        Returns:
            File content as a string
        
        Raises:
            PermissionError: If the path escapes the sandbox directory
            FileNotFoundError: If the file does not exist
        """
        target = self._safe_path(relative_path)
        if not target.exists():
            raise FileNotFoundError(f"File {relative_path} does not exist in sandbox.")
        return target.read_text(encoding="utf-8")

    def list_files(self, relative_path: str = ".") -> list:
        """List files and directories in a sandbox directory.
        
        Args:
            relative_path: Relative path within the sandbox
        
        Returns:
            List of file and directory names
        
        Raises:
            PermissionError: If the path escapes the sandbox directory
        """
        target = self._safe_path(relative_path)
        if not target.exists():
            raise FileNotFoundError(f"Directory {relative_path} does not exist in sandbox.")
        return [item.name for item in target.iterdir()]
