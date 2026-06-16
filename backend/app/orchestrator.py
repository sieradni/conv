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


class AgentOrchestrator:
    """Orchestrates autonomous agent execution with LM Studio backend."""
    
    def __init__(
        self,
        task_goal: str,
        lm_studio_url: str = "http://localhost:1234/v1",
        sandbox_dir: str = "sandbox",
        max_steps: int = 15
    ):
        """Initialize the agent orchestrator.
        
        Args:
            task_goal: The main objective for the agent
            lm_studio_url: LM Studio API base URL
            sandbox_dir: Path to the sandbox directory
            max_steps: Maximum execution steps before timeout
        """
        self.task_goal = task_goal
        self.lm_studio_url = lm_studio_url
        self.sandbox = LocalSandbox(workspace_dir=sandbox_dir)
        self.executor = ToolExecutor(self.sandbox)
        set_executor(self.executor)
        
        self.lm_client = LMStudioClient(base_url=lm_studio_url)
        self.state = AgentState(task_goal=task_goal, max_steps=max_steps)
        self.state.status = "RUNNING"
        
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
    
    async def run_loop(self) -> AgentState:
        """Execute the main agent loop until task completion or max steps.
        
        Returns:
            Final AgentState with execution history
        """
        while True:
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
            
            # Build system prompt with current goal
            system_prompt = SYSTEM_PROMPT.format(goal=self.task_goal)
            
            # Dynamically inject memory and guidelines
            system_prompt = self._compile_prompt_with_memory(system_prompt)
            
            # Build message history (only include context from last few steps to manage token usage)
            messages = self._build_messages(system_prompt)
            
            # Call LM Studio
            print(f"\n[Step {self.state.current_step}] Calling LM Studio...")
            try:
                response = await self.lm_client.chat_completion(
                    model=self.model_name,
                    messages=messages,
                    temperature=0.1
                )
            except Exception as e:
                self.state.mark_failed(f"LM Studio API error: {str(e)}")
                print(f"[-] LM Studio error: {str(e)}")
                break
            
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
            
            # Execute tool
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
            
            elif tool_name == "finish_task":
                summary = tool_args.get("summary", "Task completed")
                return f"Task finished. Summary: {summary}"
            
            else:
                return f"Error: Unknown tool '{tool_name}'. Available tools: write_file, read_file, run_command, finish_task"
        
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
    
    def _compile_prompt_with_memory(self, base_prompt: str) -> str:
        """Dynamically compile system prompt with current memory state.
        
        Args:
            base_prompt: Base system prompt template
        
        Returns:
            Compiled prompt with memory injection
        """
        try:
            # Read memory files
            memory_rules_path = Path(__file__).parent / "memory_rules.md"
            working_memory_path = Path(__file__).parent / "working_memory.json"
            
            memory_rules = ""
            if memory_rules_path.exists():
                with open(memory_rules_path, 'r') as f:
                    memory_rules = f.read()
            else:
                memory_rules = "No memory guidelines loaded."
            
            working_memory = ""
            if working_memory_path.exists():
                with open(working_memory_path, 'r') as f:
                    working_memory = f.read()
            else:
                working_memory = "{}"
            
            # Compile prompt with memory injection
            compiled = f"""{base_prompt}

---
MEMORY GUIDELINES (You can modify these using 'refine_memory_methodology'):
{memory_rules}

---
CURRENT WORKING MEMORY STATE:
{working_memory}
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
        
        # Include ONLY the last 2 steps to keep context window extremely small
        recent_steps = self.state.history[-2:] if self.state.history else []
        
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
    max_steps: int = 15
) -> AgentState:
    """Run an agent to completion.
    
    Args:
        task_goal: The objective for the agent
        lm_studio_url: LM Studio API URL
        sandbox_dir: Sandbox directory path
        max_steps: Maximum execution steps
    
    Returns:
        Final agent state
    """
    orchestrator = AgentOrchestrator(
        task_goal=task_goal,
        lm_studio_url=lm_studio_url,
        sandbox_dir=sandbox_dir,
        max_steps=max_steps
    )
    
    await orchestrator.initialize()
    final_state = await orchestrator.run_loop()
    orchestrator.print_summary()
    
    return final_state
