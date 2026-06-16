"""Agent State Schema - Centralized context and execution tracking"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional
import time


class StepLog(BaseModel):
    """Record of a single agent execution step."""
    step_number: int
    thought: str
    tool_name: str
    tool_args: Dict[str, Any]
    observation: str
    timestamp: float = Field(default_factory=time.time)


class AgentState(BaseModel):
    """Central state machine for agent execution."""
    task_goal: str
    status: str = "IDLE"  # IDLE, RUNNING, PAUSED, COMPLETED, FAILED
    approval_mode: str = "WAIT_FOR_USER"  # "AUTO_APPROVE", "CHECK_WITH_OVERSEER", "WAIT_FOR_USER"
    current_step: int = 1
    max_steps: int = 15
    history: List[StepLog] = Field(default_factory=list)
    system_metrics: Dict[str, Any] = Field(default_factory=dict)

    def add_step(self, step_log: StepLog):
        """Add a step to the history."""
        self.history.append(step_log)
        self.current_step += 1

    def mark_completed(self):
        """Mark the task as completed."""
        self.status = "COMPLETED"

    def mark_failed(self, reason: str = ""):
        """Mark the task as failed."""
        self.status = "FAILED"
        self.system_metrics["failure_reason"] = reason

    def exceeded_max_steps(self) -> bool:
        """Check if maximum steps have been exceeded."""
        return self.current_step > self.max_steps
