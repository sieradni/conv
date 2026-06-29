"""Local Sandbox - Safe execution environment for agent file operations"""

import os
from pathlib import Path
from typing import Optional


class LocalSandbox:
    """Sandbox for safe file operations within a restricted workspace directory.
    
    Supports multiple named scopes, each mapped to a directory root.
    The 'default' scope is created automatically from the workspace_dir argument.
    Additional scopes can be registered via add_scope().
    """
    
    def __init__(self, workspace_dir: str = "sandbox"):
        """Initialize the sandbox with a default workspace scope.
        
        Args:
            workspace_dir: Path to the default sandbox workspace directory
        """
        self._scopes: dict[str, Path] = {}
        self.add_scope("default", Path(workspace_dir))

    @property
    def workspace_path(self) -> Path:
        return self._scopes.get("default", Path())

    def add_scope(self, name: str, root_path: Path) -> Path:
        """Register a new named scope with its own root directory.
        
        If the scope already exists, its root is updated (useful
        when the shadow directory is re-created).
        
        Args:
            name: Scope name (e.g. 'framework', 'shadow')
            root_path: Root directory for this scope
        
        Returns:
            The resolved root Path
        """
        p = Path(root_path).resolve()
        p.mkdir(parents=True, exist_ok=True)
        self._scopes[name] = p
        return p

    def get_root(self, scope: str = "default") -> Path:
        """Get the root path for a named scope."""
        if scope not in self._scopes:
            raise PermissionError(f"Unknown scope: '{scope}'")
        return self._scopes[scope]

    def _safe_path(self, relative_path: str, scope: str = "default") -> Path:
        """Resolves path and raises PermissionError if it escapes the scope's root.
        
        Args:
            relative_path: Relative path within the scope
            scope: The named scope to resolve against
        
        Returns:
            Resolved Path object
        
        Raises:
            PermissionError: If the path attempts to escape the scope directory
        """
        root = self.get_root(scope)
        target_path = (root / relative_path).resolve()
        if not target_path.is_relative_to(root):
            raise PermissionError(
                f"Access denied: path '{relative_path}' escapes scope '{scope}'."
            )
        return target_path

    def write_file(self, relative_path: str, content: str, scope: str = "default") -> str:
        """Write content to a file in the sandbox.
        
        Args:
            relative_path: Relative path within the scope
            content: Content to write to the file
            scope: Named scope to operate in (default: 'default')
        
        Returns:
            Success message with the file path
        
        Raises:
            PermissionError: If the path escapes the scope directory
        """
        target = self._safe_path(relative_path, scope=scope)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote file to {relative_path}"

    def read_file(self, relative_path: str, scope: str = "default") -> str:
        """Read raw content from a file in the sandbox.
        
        Args:
            relative_path: Relative path within the scope
            scope: Named scope to operate in (default: 'default')
        
        Returns:
            Raw file content as a string (no line numbers — use
            read_file_numbered() for the agent-facing version)
        
        Raises:
            PermissionError: If the path escapes the scope directory
            FileNotFoundError: If the file does not exist
        """
        target = self._safe_path(relative_path, scope=scope)
        if not target.exists():
            raise FileNotFoundError(f"File {relative_path} does not exist in scope '{scope}'.")
        return target.read_text(encoding="utf-8")

    def read_file_numbered(self, relative_path: str, scope: str = "default") -> str:
        """Read file content with 1-indexed line numbers prepended.
        
        The returned format is:
             1: def foo():
             2:     pass
        
        Args:
            relative_path: Relative path within the scope
            scope: Named scope to operate in
        
        Returns:
            File content with line numbers
        """
        raw = self.read_file(relative_path, scope=scope)
        lines = raw.split("\n")
        width = len(str(len(lines)))
        numbered = "\n".join(f"{i+1:>{width}}: {l}" for i, l in enumerate(lines))
        return numbered

    def list_files(self, relative_path: str = ".", scope: str = "default") -> list:
        """List files and directories in a sandbox directory.
        
        Args:
            relative_path: Relative path within the scope
            scope: Named scope to operate in (default: 'default')
        
        Returns:
            List of file and directory names
        
        Raises:
            PermissionError: If the path escapes the scope directory
        """
        target = self._safe_path(relative_path, scope=scope)
        if not target.exists():
            raise FileNotFoundError(f"Directory {relative_path} does not exist in scope '{scope}'.")
        return [item.name for item in target.iterdir()]
