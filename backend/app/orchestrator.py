"""Orchestrator - Core agent execution loop and state management"""

import json
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, Optional
import httpx

from app.state import AgentState, StepLog
from app.tools import ToolExecutor, set_executor
from app.sandbox import LocalSandbox
from app.lm_client import LMStudioClient
from app.prompts import SYSTEM_PROMPT
from app.overseer import OverseerAgent
from app.memory_graph import get_memory_graph, set_memory_graph, MemoryGraph


class AgentOrchestrator:
    """Orchestrates autonomous agent execution with LM Studio backend."""
    
    def __init__(
        self,
        task_goal: str,
        lm_studio_url: str = "http://localhost:1234/v1",
        sandbox_dir: str = "sandbox",
        max_steps: int = 15,
        approval_mode: str = "AUTO_APPROVE",
        session_id: str = "default"
    ):
        """Initialize the agent orchestrator.
        
        Args:
            task_goal: The main objective for the agent
            lm_studio_url: LM Studio API base URL
            sandbox_dir: Path to the sandbox directory
            max_steps: Maximum execution steps before timeout
            approval_mode: Approval strategy
            session_id: Session identifier for multi-session support
        """
        self.session_id = session_id
        self.task_goal = task_goal
        self.lm_studio_url = lm_studio_url
        self.sandbox = LocalSandbox(workspace_dir=sandbox_dir)
        self.executor = ToolExecutor(self.sandbox)
        set_executor(self.executor)
        
        self.lm_client = LMStudioClient(base_url=lm_studio_url, timeout=120.0)
        self.state = AgentState(
            session_id=session_id,
            task_goal=task_goal,
            max_steps=max_steps,
            approval_mode=approval_mode
        )
        self.state.status = "RUNNING"
        
        # Initialize Overseer agent
        self.overseer = OverseerAgent(api_url=lm_studio_url)
        
        # Memory Graph (HSWM) — shared singleton across sessions
        self.memory_graph = get_memory_graph()
        
        # UI and HITL Hooks
        self.ui_manager = None  # Will be set by FastAPI
        self.user_queue = None   # Will be set by FastAPI
        
        # Get active model
        self.model_name = None
    
    async def initialize(self):
        """Initialize the orchestrator by fetching available models."""
        models = await self.lm_client.get_models()
        if models and 'data' in models and models['data']:
            self.model_name = models['data'][0]['id']
            print(f"[*] Using model: {self.model_name}")
        else:
            raise RuntimeError("No models available in LM Studio")
        
        # Initialize Overseer agent
        await self.overseer.initialize()
        print(f"[*] Overseer initialized with approval mode: {self.state.approval_mode}")
    
    async def run_loop(self) -> AgentState:
        """Execute the main agent loop until task completion or max steps.
        
        Returns:
            Final AgentState with execution history
        """
        while True:
            # Initialize diagnostics for this step
            diagnostics = {"generation_time_s": 0, "tokens_per_second": 0, "token_count": 0}

            # Check termination conditions
            if self.state.exceeded_max_steps():
                self.state.mark_failed(f"Exceeded maximum steps ({self.state.max_steps})")
                print(f"\n[-] Max steps exceeded. Terminating.")
                break
            
            if self.state.status == "COMPLETED":
                print(f"\n[+] Task completed successfully.")
                break
            
            if self.state.status == "FAILED":
                print(f"\n[-] Task failed: {self.state.system_metrics.get('failure_reason', 'Unknown')}")
                break
            
            # Check for stop request (immediate abort)
            if self.user_queue and hasattr(self.user_queue, '_session_stop'):
                # We use a separate mechanism via the session object
                pass

            # Check direct talk queue before each step
            if self.user_queue is not None:
                # Try to get the session from the registry
                from app.session import registry as sess_registry
                session = sess_registry.get(self.session_id)
                if session and session.stop_requested:
                    session.stop_requested = False
                    self.state.mark_failed("Stopped by user")
                    print(f"\n[-] Task stopped by user request.")
                    break
                if session and session.stop_after_step:
                    session.stop_after_step = False
                    session.status = "PAUSED"
                    self.state.status = "PAUSED"
                    print(f"\n[*] Paused after step by user request.")
                    if self.ui_manager:
                        await self.ui_manager.broadcast({
                            "type": "status_update", "session_id": self.session_id,
                            "status": "PAUSED", "message": "Paused after step"
                        })
                    # Wait for resume signal
                    resume = await session.user_response_queue.get()
                    if resume.get("approved") or resume.get("resume"):
                        session.status = "RUNNING"
                        self.state.status = "RUNNING"
                        print(f"\n[*] Resuming...")
                    else:
                        self.state.mark_failed("Cancelled after pause")
                        break
                # Check for direct talk messages
                if session and not session.direct_talk_queue.empty():
                    try:
                        msg = session.direct_talk_queue.get_nowait()
                        print(f"\n[*] Direct talk received: {msg[:80]}")
                        # Inject as a one-off step
                        step_log = StepLog(
                            step_number=self.state.current_step,
                            thought="[Direct user instruction]",
                            tool_name="direct_talk",
                            tool_args={"message": msg},
                            observation=f"User said: {msg}"
                        )
                        self.state.add_step(step_log)
                        if self.ui_manager:
                            await self.ui_manager.broadcast({
                                "type": "step_update", "session_id": self.session_id,
                                "step": step_log.dict()
                            })
                    except asyncio.QueueEmpty:
                        pass

            # Build system prompt with current goal
            system_prompt = SYSTEM_PROMPT.format(goal=self.task_goal)
            
            # Dynamically inject memory and guidelines
            system_prompt = self._compile_prompt_with_memory(system_prompt)
            
            # Build message history (only include context from last few steps to manage token usage)
            messages = self._build_messages(system_prompt)
            
            # Broadcast step start
            if self.ui_manager:
                await self.ui_manager.broadcast({
                    "type": "step_start",
                    "session_id": self.session_id,
                    "step_number": self.state.current_step,
                    "max_steps": self.state.max_steps,
                    "diagnostics": diagnostics,
                })

            # Call LM Studio
            print(f"\n[Step {self.state.current_step}] Calling LM Studio...")
            if self.ui_manager:
                await self.ui_manager.broadcast({
                    "type": "llm_call",
                    "session_id": self.session_id,
                    "step_number": self.state.current_step,
                    "status": "calling"
                })
            try:
                call_start = time.time()
                response = await self.lm_client.chat_completion(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.1
                )
                call_duration = time.time() - call_start
            except Exception as e:
                self.state.mark_failed(f"LM Studio API error: {str(e)}")
                print(f"[-] LM Studio error: {str(e)}")
                if self.ui_manager:
                    await self.ui_manager.broadcast({
                        "type": "error",
                        "session_id": self.session_id,
                        "message": f"LM Studio API error: {str(e)}"
                    })
                break

            # Compute diagnostics
            diagnostics = {"generation_time_s": call_duration, "tokens_per_second": 0, "token_count": 0}
            if response and 'usage' in response:
                usage = response['usage']
                total_tokens = usage.get('total_tokens', 0) or usage.get('completion_tokens', 0) or 0
                diagnostics['token_count'] = total_tokens
                if call_duration > 0 and total_tokens > 0:
                    diagnostics['tokens_per_second'] = round(total_tokens / call_duration, 1)

            # Broadcast LLM response received
            if self.ui_manager:
                await self.ui_manager.broadcast({
                    "type": "llm_response",
                    "session_id": self.session_id,
                    "step_number": self.state.current_step,
                    "status": "received",
                    "diagnostics": diagnostics,
                })
            
            # Parse response
            if not response or 'choices' not in response:
                self.state.mark_failed("Invalid response from LM Studio")
                print(f"[-] Invalid LM Studio response")
                break
            
            response_text = response['choices'][0]['message']['content'].strip()
            print(f"[*] Raw response:\n{response_text[:200]}...")
            
            # Strip markdown code block wrapper if present
            if response_text.startswith("```json"):
                response_text = response_text[7:]  # Remove ```json
                if response_text.startswith("\n"):
                    response_text = response_text[1:]
            if response_text.startswith("```"):
                response_text = response_text[3:]  # Remove ```
                if response_text.startswith("\n"):
                    response_text = response_text[1:]
            if response_text.endswith("```"):
                response_text = response_text[:-3]
            response_text = response_text.strip()
            
            # Try to parse JSON
            try:
                action = json.loads(response_text)
            except json.JSONDecodeError as e:
                # Parsing failed - feedback to model
                observation = f"Error: Your output was not valid JSON. Parse error: {str(e)}. Please try again with valid JSON."
                print(f"[!] JSON parse error: {str(e)}")
                print(f"[*] Feeding back error to model...")
                
                # Add failed parsing attempt to history
                step_log = StepLog(
                    step_number=self.state.current_step,
                    thought="[Invalid JSON attempt]",
                    tool_name="[parse_error]",
                    tool_args={},
                    observation=observation
                )
                self.state.add_step(step_log)
                continue
            
            # Validate action schema
            if not self._validate_action(action):
                observation = "Error: Your action did not match the required schema. Please provide 'thought', 'tool_name', and 'tool_args'."
                print(f"[!] Invalid action schema")
                
                step_log = StepLog(
                    step_number=self.state.current_step,
                    thought=action.get("thought", "[Invalid action]"),
                    tool_name="[schema_error]",
                    tool_args={},
                    observation=observation
                )
                self.state.add_step(step_log)
                continue
            
            # Extract action details
            thought = action.get("thought", "")
            tool_name = action.get("tool_name", "")
            tool_args = action.get("tool_args", {})
            
            print(f"[*] Thought: {thought[:100]}...")
            print(f"[*] Tool: {tool_name}")
            print(f"[*] Args: {tool_args}")
            
            # Check if this tool requires approval
            requires_approval = tool_name in ["write_file", "run_command", "finish_task", "ask_user"]
            
            # For finish_task, we ALWAYS want verification if possible
            should_run_gate = False
            current_mode = self.state.approval_mode

            if requires_approval:
                if current_mode != "AUTO_APPROVE":
                    should_run_gate = True
                elif tool_name == "finish_task":
                    # Force Overseer check even in AUTO_APPROVE for finish_task
                    should_run_gate = True
                    current_mode = "CHECK_WITH_OVERSEER"
                elif tool_name == "ask_user":
                    # ask_user always requires user input
                    should_run_gate = True
                    current_mode = "WAIT_FOR_USER"

            # Apply approval gate if required
            if should_run_gate:
                approval_result = await self._apply_approval_gate(thought, tool_name, tool_args, mode_override=current_mode)
                if not approval_result["approved"]:
                    observation = f"Action REJECTED by {approval_result['source']}: {approval_result['feedback']}"
                    print(f"[!] {observation}")
                else:
                    if tool_name == "ask_user":
                        observation = f"User answered: {approval_result['feedback']}"
                    else:
                        observation = await self._execute_tool(tool_name, tool_args)
            else:
                observation = await self._execute_tool(tool_name, tool_args)
            
            # Log step
            step_log = StepLog(
                step_number=self.state.current_step,
                thought=thought,
                tool_name=tool_name,
                tool_args=tool_args,
                observation=observation
            )
            self.state.add_step(step_log)
            
            # Broadcast update to UI with diagnostics
            if self.ui_manager:
                await self.ui_manager.broadcast({
                    "type": "step_update",
                    "session_id": self.session_id,
                    "step": step_log.dict(),
                    "diagnostics": diagnostics,
                })
            
            # Check if task is finished
            if tool_name == "finish_task":
                self.state.mark_completed()
        
        return self.state
    
    async def _execute_tool(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        """Execute the specified tool and return observation.
        
        Args:
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool
        
        Returns:
            Observation/output from the tool
        """
        try:
            if tool_name == "write_file":
                path = tool_args.get("path", "")
                content = tool_args.get("content", "")
                result = self.executor.write_file(path, content)
                return f"✓ {result}"
            
            elif tool_name == "read_file":
                path = tool_args.get("path", "")
                content = self.executor.read_file(path)
                # Truncate very large file reads
                if len(content) > 5000:
                    content = content[:5000] + f"\n... [truncated, total {len(content)} bytes]"
                return f"File contents:\n{content}"
            
            elif tool_name == "run_command":
                command = tool_args.get("command", "")
                output = self.executor.run_command(command, timeout=15)
                # Truncate very large outputs
                if len(output) > 5000:
                    output = output[:5000] + f"\n... [truncated, total {len(output)} bytes]"
                return f"Command output:\n{output}"
            
            elif tool_name == "read_memory":
                memory = self.executor.read_memory()
                return f"Current memory state:\n{json.dumps(memory, indent=2)}"
            
            elif tool_name == "write_memory":
                key = tool_args.get("key", "")
                value = tool_args.get("value", None)
                result = self.executor.write_memory(key, value)
                return f"✓ {result}"
            
            elif tool_name == "refine_memory_methodology":
                new_rules = tool_args.get("new_rules", "")
                reflection = tool_args.get("reflection", "")
                result = self.executor.refine_memory_methodology(new_rules, reflection)
                return f"✓ {result}"
            
            elif tool_name == "ask_overseer":
                question = tool_args.get("question", "")
                response = await self.overseer.ask_overseer(question)
                return f"Overseer Response:\n{response}"
            
            elif tool_name == "finish_task":
                summary = tool_args.get("summary", "Task completed")
                return f"Task finished. Summary: {summary}"
            
            # HSWM Navigation Tools
            elif tool_name == "navigate_up":
                return self.executor.navigate_up()
            
            elif tool_name == "navigate_down":
                return self.executor.navigate_down(tool_args.get("node_id", ""))
            
            elif tool_name == "return_to_base":
                return self.executor.return_to_base()
            
            elif tool_name == "read_detail":
                return self.executor.read_detail(tool_args.get("node_id", ""))
            
            elif tool_name == "create_memory":
                return self.executor.create_memory(
                    title=tool_args.get("title", ""),
                    summary=tool_args.get("summary", ""),
                    detail=tool_args.get("detail", ""),
                    parent_id=tool_args.get("parent_id", ""),
                    link_to_ids=tool_args.get("link_to_ids", ""),
                )

            # Self-Development Tools
            elif tool_name == "propose_change":
                return self.executor.propose_change(
                    file_path=tool_args.get("file_path", ""),
                    content=tool_args.get("content", ""),
                )

            elif tool_name == "run_self_test":
                return self.executor.run_self_test()

            elif tool_name == "deploy_change":
                return self.executor.deploy_change()

            # User Notes Tool
            elif tool_name == "read_user_notes":
                return self.executor.read_user_notes()

            # Ask User (pauses for user input — handled by approval gate)
            elif tool_name == "ask_user":
                return f"[ASK_USER] {tool_args.get('question', '')}"

            else:
                return f"Error: Unknown tool '{tool_name}'. Available tools: write_file, read_file, run_command, finish_task, navigate_up, navigate_down, return_to_base, read_detail, create_memory, propose_change, run_self_test, deploy_change, read_user_notes, ask_user"
        
        except Exception as e:
            return f"Error executing {tool_name}: {str(e)}"
    
    def _validate_action(self, action: Dict[str, Any]) -> bool:
        """Validate that action matches required schema.
        
        Args:
            action: Action dictionary to validate
        
        Returns:
            True if valid, False otherwise
        """
        required_fields = {"thought", "tool_name", "tool_args"}
        return isinstance(action, dict) and required_fields.issubset(action.keys())
    
    async def _apply_approval_gate(
        self,
        actor_thought: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        mode_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """Apply approval gate for critical tools based on approval_mode.
        
        Args:
            actor_thought: Actor's reasoning for the action
            tool_name: Name of the tool to execute
            tool_args: Arguments for the tool
            mode_override: Optional mode to use instead of self.state.approval_mode
        
        Returns:
            Dictionary with "approved", "source", and "feedback" keys
        """
        
        mode = mode_override or self.state.approval_mode
        
        if mode == "AUTO_APPROVE":
            # Auto-approve (shouldn't reach here in run_loop, but for safety)
            return {"approved": True, "source": "AUTO_APPROVE", "feedback": ""}
        
        elif mode == "CHECK_WITH_OVERSEER":
            # Get file context for Overseer review
            files_context = self._get_sandbox_file_context()
            
            # Broadcast Overseer review started
            if self.ui_manager:
                await self.ui_manager.broadcast({
                    "type": "overseer_review_start",
                    "session_id": self.session_id,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "thought": actor_thought
                })
            
            # Ask Overseer to review the action
            print(f"[*] Requesting Overseer review of {tool_name}...")
            review = await self.overseer.review_action(
                actor_thought=actor_thought,
                tool_name=tool_name,
                tool_args=tool_args,
                files_context=files_context
            )
            
            # Check Overseer's decision
            status = review.get("status", "REJECTED")
            reasoning = review.get("reasoning", "No reasoning provided")
            feedback = review.get("feedback", "")
            
            print(f"[Overseer] Status: {status}")
            print(f"[Overseer] Reasoning: {reasoning}")
            if feedback:
                print(f"[Overseer] Feedback: {feedback}")
            
            # Broadcast Overseer review result
            if self.ui_manager:
                await self.ui_manager.broadcast({
                    "type": "overseer_review",
                    "session_id": self.session_id,
                    "status": status,
                    "reasoning": reasoning,
                    "feedback": feedback,
                    "approved": status == "APPROVED",
                    "tool_name": tool_name
                })
            
            return {
                "approved": status == "APPROVED",
                "source": "OVERSEER",
                "feedback": f"{reasoning}. {feedback}".strip()
            }
        
        elif mode == "WAIT_FOR_USER":
            # For ask_user, we use a specific type so frontend can display differently
            is_ask_user = tool_name == "ask_user"
            broadcast_type = "ask_user" if is_ask_user else "awaiting_user_approval"

            # 1. Broadcast the pending action to the WebSocket if available
            if self.ui_manager:
                await self.ui_manager.broadcast({
                    "type": broadcast_type,
                    "session_id": self.session_id,
                    "tool_name": tool_name,
                    "tool_args": tool_args,
                    "thought": actor_thought
                })

            # 2. Await the response from the FastAPI Queue or fallback to CLI
            if self.user_queue:
                print(f"[*] Pausing and waiting for user {'answer' if is_ask_user else 'approval'} on Web UI...")
                user_response = await self.user_queue.get()
                
                # Broadcast the decision
                if self.ui_manager:
                    await self.ui_manager.broadcast({
                        "type": "user_decision",
                        "session_id": self.session_id,
                        "approved": user_response["approved"],
                        "feedback": user_response.get("feedback", "")
                    })
                
                if is_ask_user:
                    # For ask_user, the feedback IS the answer
                    return {
                        "approved": True,
                        "source": "USER_UI",
                        "feedback": user_response.get("feedback") or "[User provided no answer]"
                    }
                
                if not user_response["approved"]:
                    return {
                        "approved": False,
                        "source": "USER_UI",
                        "feedback": user_response.get("feedback") or "User rejected the action"
                    }
                else:
                    return {"approved": True, "source": "USER_UI", "feedback": ""}
            else:
                # Fallback to CLI if no queue provided
                label = "Question" if is_ask_user else "Approval Required"
                print(f"\n[!] {label} (CLI Fallback)!")
                print(f"    Actor: {tool_name}")
                print(f"    Details: {actor_thought}")
                if is_ask_user:
                    question = tool_args.get("question", "")
                    print(f"    Question: {question}")
                    print(f"\n    Type your answer: ", end="")
                    user_input = input().strip()
                    return {"approved": True, "source": "USER_CLI", "feedback": user_input if user_input else "[User provided no answer]"}
                else:
                    print(f"    Arguments: {json.dumps(tool_args, indent=2)}")
                    print(f"\n    Type 'approve' to allow, or provide feedback: ", end="")
                    user_input = input().strip().lower()
                    if user_input == "approve":
                        return {"approved": True, "source": "USER_CLI", "feedback": ""}
                    else:
                        return {
                            "approved": False,
                            "source": "USER_CLI",
                            "feedback": user_input if user_input else "User rejected the action"
                        }
        
        else:
            # Unknown approval mode, default to rejection
            return {
                "approved": False,
                "source": "SYSTEM",
                "feedback": f"Unknown approval mode: {self.state.approval_mode}"
            }
    
    def _get_sandbox_file_context(self) -> str:
        """Get a summary of files currently in the sandbox for Overseer review.
        
        Returns:
            String representation of sandbox files
        """
        try:
            files = self.sandbox.list_files(".")
            if not files:
                return "[No files in sandbox]"
            
            context_lines = ["Files in sandbox:"]
            for file in files:
                try:
                    if file.endswith(".py") and file != "__pycache__":
                        content = self.sandbox.read_file(file)
                        # Limit to first 200 chars per file
                        preview = content[:200] + "..." if len(content) > 200 else content
                        context_lines.append(f"  {file}: {preview}")
                    else:
                        context_lines.append(f"  {file}")
                except:
                    context_lines.append(f"  {file}")
            
            return "\n".join(context_lines)
        except Exception as e:
            return f"[Could not read sandbox files: {str(e)}]"
    
    def _compile_prompt_with_memory(self, base_prompt: str) -> str:
        """Dynamically compile system prompt with HSWM graph context.
        
        Args:
            base_prompt: Base system prompt template
        
        Returns:
            Compiled prompt with memory injection
        """
        try:
            # Read memory rules
            memory_rules_path = Path(__file__).parent / "memory_rules.md"
            memory_rules = ""
            if memory_rules_path.exists():
                with open(memory_rules_path) as f:
                    memory_rules = f.read()
            else:
                memory_rules = "No memory guidelines loaded."

            # Get HSWM context
            graph_context = self.memory_graph.current_context()

            compiled = f"""{base_prompt}

---
MEMORY GUIDELINES (You can modify these using 'refine_memory_methodology'):
{memory_rules}

---
HIERARCHICAL MEMORY (navigate with navigate_up/down/read_detail/create_memory):
{graph_context}
"""
            
            return compiled
        except Exception as e:
            print(f"[!] Warning: Could not compile prompt with memory: {e}")
            return base_prompt
    
    def _build_messages(self, system_prompt: str) -> list:
        """Build message history for LM Studio with aggressive context pruning.
        
        Args:
            system_prompt: System prompt for the agent
        
        Returns:
            List of message dictionaries (only last 2 steps + system prompt)
        """
        messages = [{"role": "user", "content": system_prompt}]
        
        # Include last 5 steps for better context retention
        recent_steps = self.state.history[-5:] if self.state.history else []
        
        if recent_steps:
            # Build context from last 2 steps
            context_lines = ["Recent steps:"]
            for step in recent_steps:
                context_lines.append(f"Step {step.step_number}:")
                context_lines.append(f"  Tool: {step.tool_name}")
                context_lines.append(f"  Observation: {step.observation[:300]}")
            
            context = "\n".join(context_lines)
            messages.append({"role": "assistant", "content": context})
        
        # Add continuation prompt
        messages.append({
            "role": "user",
            "content": "Continue with the next action. Output only valid JSON."
        })
        
        return messages
    
    def print_summary(self):
        """Print a summary of the execution."""
        print("\n" + "=" * 70)
        print("AGENT EXECUTION SUMMARY")
        print("=" * 70)
        print(f"Task Goal: {self.state.task_goal}")
        print(f"Final Status: {self.state.status}")
        print(f"Steps Executed: {len(self.state.history)}")
        print(f"Model Used: {self.model_name}")
        
        if self.state.system_metrics:
            print("\nSystem Metrics:")
            for key, value in self.state.system_metrics.items():
                print(f"  {key}: {value}")
        
        print("\n" + "-" * 70)
        print("STEP HISTORY")
        print("-" * 70)
        
        for step in self.state.history:
            print(f"\nStep {step.step_number}:")
            print(f"  Thought: {step.thought}")
            print(f"  Tool: {step.tool_name}")
            print(f"  Args: {step.tool_args}")
            print(f"  Observation: {step.observation[:300]}")
            if len(step.observation) > 300:
                print(f"    ... [truncated]")
        
        print("\n" + "=" * 70)


async def run_agent(
    task_goal: str,
    lm_studio_url: str = "http://localhost:1234/v1",
    sandbox_dir: str = "sandbox",
    max_steps: int = 15,
    approval_mode: str = "AUTO_APPROVE"
) -> AgentState:
    """Run an agent to completion.
    
    Args:
        task_goal: The objective for the agent
        lm_studio_url: LM Studio API URL
        sandbox_dir: Sandbox directory path
        max_steps: Maximum execution steps
        approval_mode: Approval strategy ("AUTO_APPROVE", "CHECK_WITH_OVERSEER", "WAIT_FOR_USER")
    
    Returns:
        Final agent state
    """
    orchestrator = AgentOrchestrator(
        task_goal=task_goal,
        lm_studio_url=lm_studio_url,
        sandbox_dir=sandbox_dir,
        max_steps=max_steps,
        approval_mode=approval_mode
    )
    
    await orchestrator.initialize()
    final_state = await orchestrator.run_loop()
    orchestrator.print_summary()
    
    return final_state
