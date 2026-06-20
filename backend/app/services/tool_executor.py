"""Tool executor — registry-based dispatch for all agent tools."""

import logging
from typing import Any, Callable, Optional

from app.core.config import REVIEW_TOOLS

logger = logging.getLogger("tool_executor")

ToolFunc = Callable[..., str]


class ToolExecutor:
    """Registry and executor for agent tools.

    Tools are registered by name and dispatched by execute().
    """

    def __init__(self):
        self._tools: dict[str, ToolFunc] = {}

    def register(self, name: str, func: ToolFunc):
        self._tools[name] = func

    def get(self, name: str) -> Optional[ToolFunc]:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def requires_approval(self, name: str) -> bool:
        return name in REVIEW_TOOLS

    def execute(self, name: str, **kwargs) -> str:
        func = self._tools.get(name)
        if func is None:
            return f"Unknown tool: {name}"
        try:
            return func(**kwargs)
        except Exception as e:
            import traceback
            logger.error(f"Tool {name} failed: {e}\n{traceback.format_exc()}")
            return f"Error executing {name}: {e}"


# Singleton
_executor: Optional[ToolExecutor] = None


def get_executor() -> ToolExecutor:
    global _executor
    if _executor is None:
        _executor = ToolExecutor()
        _register_defaults(_executor)
    return _executor


def _register_defaults(executor: ToolExecutor):
    """Register all built-in tools."""
    from app.tools import file_io, memory_tools, system_tools, self_dev_tools, reminder_tools

    # File I/O
    executor.register("read_file", file_io.read_file)
    executor.register("write_file", file_io.write_file)
    executor.register("replace_lines", file_io.replace_lines)
    executor.register("insert_lines", file_io.insert_lines)
    executor.register("append_to_file", file_io.append_to_file)
    executor.register("run_command", file_io.run_command)

    # Memory
    executor.register("set_current_node", memory_tools.set_current_node)
    executor.register("read_detail", memory_tools.read_detail)
    executor.register("create_memory", memory_tools.create_memory)
    executor.register("update_memory", memory_tools.update_memory)
    executor.register("refine_memory_methodology", memory_tools.refine_memory_methodology)

    # System
    executor.register("update_todo", system_tools.update_todo)
    executor.register("read_user_notes", system_tools.read_user_notes)
    executor.register("write_user_notes", system_tools.write_user_notes)
    executor.register("set_goal", system_tools.set_goal)
    executor.register("ask_user", system_tools.ask_user)
    executor.register("finish_task", system_tools.finish_task)

    # Self-dev
    executor.register("propose_change", self_dev_tools.propose_change)
    executor.register("run_self_test", self_dev_tools.run_self_test)
    executor.register("deploy_change", self_dev_tools.deploy_change)

    # Reminders
    executor.register("create_reminder", reminder_tools.create_reminder)
    executor.register("list_reminders", reminder_tools.list_reminders)
    executor.register("update_reminder", reminder_tools.update_reminder)
    executor.register("delete_reminder", reminder_tools.delete_reminder)
