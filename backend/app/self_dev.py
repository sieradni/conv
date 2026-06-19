"""Self-Development Pipeline — Shadow Sandbox & Hot-Swap.

Allows the agent to safely modify its own codebase by:
1. Copying the framework to a shadow directory
2. Running the test suite inside the shadow
3. On success, hot-swapping changes to the live server
"""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from app.sandbox import LocalSandbox

logger = logging.getLogger("self_dev")

FRAMEWORK_ROOT = Path(__file__).resolve().parent.parent.parent  # agent-framework/
BACKEND_DIR = FRAMEWORK_ROOT / "backend"
APP_DIR = BACKEND_DIR / "app"
VENV_DIR = BACKEND_DIR / "venv"


class ShadowSandbox:
    """Manages a shadow copy of the framework for safe self-modification."""

    def __init__(self):
        self._shadow_dir: Optional[Path] = None
        self._sandbox: Optional[LocalSandbox] = None
        self._proposed_changes: List[Dict[str, Any]] = []
        self._test_results: Optional[Dict[str, Any]] = None
        self._status: str = "IDLE"  # IDLE, COPYING, TESTING, READY, DEPLOYED, FAILED

    @property
    def shadow_dir(self) -> Optional[Path]:
        return self._shadow_dir

    @property
    def status(self) -> str:
        return self._status

    def create_shadow(self) -> str:
        """Create a shadow copy of the framework codebase."""
        if self._shadow_dir and self._shadow_dir.exists():
            shutil.rmtree(self._shadow_dir)

        self._proposed_changes = []
        self._test_results = None
        self._shadow_dir = Path(tempfile.mkdtemp(prefix="agent_shadow_"))
        self._sandbox = LocalSandbox(str(self._shadow_dir))
        self._status = "COPYING"

        # Copy backend/ and frontend/
        for src in [BACKEND_DIR, FRAMEWORK_ROOT / "frontend"]:
            dst = self._shadow_dir / src.name
            if src.exists():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns(
                    "__pycache__", "*.pyc", ".git", "venv", ".pytest_cache"
                ))

        # Create a symlink to the virtual env so tests can run
        venv_link = self._shadow_dir / "backend" / "venv"
        if VENV_DIR.exists() and not venv_link.exists():
            try:
                os.symlink(str(VENV_DIR.resolve()), str(venv_link),
                           target_is_directory=True)
            except OSError:
                pass

        self._status = "READY"
        size = sum(f.stat().st_size for f in self._shadow_dir.rglob("*") if f.is_file())
        logger.info(f"Shadow created at {self._shadow_dir} ({size / 1024:.1f} KB)")
        return f"Shadow created at {self._shadow_dir}"

    def apply_change(self, file_path: str, content: str) -> str:
        """Apply a file change inside the shadow copy."""
        if not self._sandbox:
            return "Error: No shadow directory. Call create_shadow first."

        rel = Path(file_path)
        if rel.is_absolute():
            return "Error: Use relative paths within the framework."

        # Map common prefixes: if path already starts with backend/ or frontend/,
        # use it as-is; otherwise prepend backend/
        if rel.parts and rel.parts[0] in ("backend", "frontend"):
            subpath = str(rel)
        else:
            subpath = str(Path("backend") / rel)

        self._sandbox.write_file(subpath, content)

        self._proposed_changes.append({
            "file_path": str(rel),
            "timestamp": time.time(),
        })
        logger.info(f"Change applied to shadow: {rel}")
        return f"Applied change to {rel} in shadow"

    def run_tests(self, timeout: int = 120) -> Dict[str, Any]:
        """Run the test suite inside the shadow sandbox."""
        if not self._shadow_dir or not self._shadow_dir.exists():
            return {"status": "FAILED", "error": "No shadow directory"}

        self._status = "TESTING"
        test_dir = self._shadow_dir / "backend"
        python_path = str(test_dir / "venv" / "bin" / "python")

        if not Path(python_path).exists():
            python_path = "python3"

        results = {
            "status": "PASSED",
            "tests_run": 0,
            "passed": 0,
            "failed": 0,
            "errors": [],
            "output": "",
            "started_at": time.time(),
        }

        try:
            result = subprocess.run(
                [python_path, "-m", "pytest", "test_sandbox.py",
                 "-v", "--tb=short"],
                cwd=str(test_dir),
                capture_output=True,
                text=True,
                timeout=timeout,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
            )

            output = result.stdout + "\n" + result.stderr
            results["output"] = output

            if result.returncode != 0:
                results["status"] = "FAILED"
                results["errors"] = self._parse_test_errors(output)

            results["tests_run"] = output.count("PASSED") + output.count("FAILED")
            results["passed"] = output.count("PASSED")
            results["failed"] = output.count("FAILED")

        except subprocess.TimeoutExpired:
            results["status"] = "TIMEOUT"
            results["error"] = f"Tests exceeded {timeout}s timeout"
        except Exception as e:
            results["status"] = "FAILED"
            results["error"] = str(e)

        self._test_results = results
        self._status = "READY" if results["status"] == "PASSED" else "FAILED"
        return results

    def deploy_to_live(self) -> str:
        """Copy approved shadow changes to the live codebase."""
        if not self._proposed_changes:
            return "No changes to deploy."

        if not self._test_results or self._test_results.get("status") != "PASSED":
            return "Error: Tests must pass before deploying."

        deployed = []
        for change in self._proposed_changes:
            file_path = change["file_path"]
            rel = Path(file_path)

            if rel.parts and rel.parts[0] in ("backend", "frontend"):
                src = self._shadow_dir / rel
                dst = FRAMEWORK_ROOT / rel
            else:
                src = self._shadow_dir / "backend" / rel
                dst = FRAMEWORK_ROOT / "backend" / rel

            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(src), str(dst))
                deployed.append(str(rel))
                logger.info(f"Deployed {rel} to live")

        self._status = "DEPLOYED"
        msg = f"Deployed {len(deployed)} file(s): {', '.join(deployed)}"
        return msg

    def status_report(self) -> Dict[str, Any]:
        return {
            "status": self._status,
            "shadow_dir": str(self._shadow_dir) if self._shadow_dir else None,
            "proposed_changes": len(self._proposed_changes),
            "test_results": self._test_results,
        }

    def _parse_test_errors(self, output: str) -> List[str]:
        errors = []
        for line in output.split("\n"):
            if "FAILED" in line or "ERROR" in line:
                errors.append(line.strip())
        return errors

    def cleanup(self):
        """Remove the shadow directory."""
        if self._shadow_dir and self._shadow_dir.exists():
            shutil.rmtree(self._shadow_dir)
            self._shadow_dir = None
            self._sandbox = None
            self._proposed_changes = []
            self._status = "IDLE"


# Singleton
_shadow_sandbox: Optional[ShadowSandbox] = None


def get_shadow_sandbox() -> ShadowSandbox:
    global _shadow_sandbox
    if _shadow_sandbox is None:
        _shadow_sandbox = ShadowSandbox()
    return _shadow_sandbox
