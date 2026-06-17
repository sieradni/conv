"""Overseer Agent - Quality assurance and approval authority for Actor agent decisions"""

import json
import os
from typing import Dict, Any, Optional
from app.lm_client import LMStudioClient

OVERSEER_SYSTEM_PROMPT = """You are an elite, skeptical Software Quality Assurance Engineer and Security Auditor.
Your job is to review the Actor agent's proposed tool calls before they execute.

You have the ability to read files from the sandbox to verify the agent's claims.
When reviewing, examine the tool name, arguments, surrounding conversation context, and any files you choose to read.

You must be highly critical. Look for:
1. Missing edge cases in code or tests.
2. Security concerns (e.g., unauthorized path escapes, dangerous command execution).
3. Poorly justified changes.

Output a JSON object:
{
    "status": "APPROVED" or "REJECTED",
    "reasoning": "Detailed explanation of your review",
    "feedback": "If REJECTED, list explicit steps the Actor must take to get approval. If APPROVED, can be empty."
}
"""


class OverseerAgent:
    def __init__(self, api_url: str = "http://localhost:1234/v1"):
        self.api_url = api_url
        self.lm_client = LMStudioClient(base_url=api_url, timeout=120.0)
        self.model_name = None

    async def initialize(self):
        """Initialize the overseer by fetching available models."""
        models = await self.lm_client.get_models()
        if models and 'data' in models and models['data']:
            self.model_name = models['data'][0]['id']
            print(f"[Overseer] Initialized with model: {self.model_name}")
        else:
            print("[Overseer] Warning: No models available in LM Studio")

    async def _read_sandbox_file(self, sandbox_dir: str, path: str) -> str:
        """Read a file from the sandbox directory for review purposes."""
        try:
            full_path = os.path.normpath(os.path.join(sandbox_dir, path))
            if not full_path.startswith(os.path.normpath(sandbox_dir)):
                return f"[Path traversal blocked: {path}]"
            if not os.path.isfile(full_path):
                return f"[File not found: {path}]"
            with open(full_path, encoding="utf-8", errors="replace") as f:
                return f.read()
        except Exception as e:
            return f"[Error reading {path}: {e}]"

    async def review_action(
        self,
        tool_name: str,
        tool_args: dict,
        thought: str,
        previous_block: str = "",
        sandbox_dir: str = "",
    ) -> Dict[str, Any]:
        """Review a proposed tool action before execution.

        Args:
            tool_name: Name of the tool being called.
            tool_args: Arguments for the tool.
            thought: The agent's reasoning/thought text.
            previous_block: The last user message + last assistant message for context.
            sandbox_dir: Path to the sandbox directory (for reading files to verify).
        """
        if not self.model_name:
            await self.initialize()
            if not self.model_name:
                return {
                    "status": "REJECTED",
                    "reasoning": "Overseer not initialized (no models found)",
                    "feedback": "Ensure LM Studio is running and a model is loaded."
                }

        # Build files context: if tool reads/writes a file, show relevant files
        file_context = ""
        if sandbox_dir and os.path.isdir(sandbox_dir):
            target_path = ""
            if tool_name in ("read_file", "write_file"):
                target_path = tool_args.get("path", "")
            elif tool_name == "run_command":
                cmd = tool_args.get("command", "")
                # Check if command references specific files
                for word in cmd.split():
                    if word.endswith((".py", ".js", ".ts", ".json", ".md", ".txt", ".yaml", ".yml")):
                        target_path = word
                        break
            if target_path:
                content = await self._read_sandbox_file(sandbox_dir, target_path)
                file_context = f"\nFile '{target_path}' contents:\n{content[:2000]}"

        prompt = f"""CONVERSATION CONTEXT (previous turn):
{previous_block or "None available"}

ACTOR PROPOSED ACTION:
- Tool: {tool_name}
- Arguments: {json.dumps(tool_args, indent=2)}
- Thought: {thought}
{file_context}

Review this proposal. Is it safe, correct, and well-justified given the context?"""
        messages = [
            {"role": "system", "content": OVERSEER_SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]

        response = await self.lm_client.chat_completion(
            model=self.model_name,
            messages=messages,
            temperature=0.1
        )

        if response and response.get('choices'):
            content = response['choices'][0]['message']['content']

            cleaned_content = content.strip()
            if "```json" in cleaned_content:
                cleaned_content = cleaned_content.split("```json")[1].split("```")[0]
            elif "```" in cleaned_content:
                cleaned_content = cleaned_content.split("```")[1].split("```")[0]

            try:
                result = json.loads(cleaned_content.strip())
                result["status"] = result.get("status", "REJECTED").upper()
                return result
            except json.JSONDecodeError:
                return {
                    "status": "REJECTED",
                    "reasoning": "Overseer returned unparseable response",
                    "feedback": f"The overseer output was: {content[:500]}. Please ensure standard JSON output."
                }
        else:
            return {
                "status": "REJECTED",
                "reasoning": "Overseer failed to respond.",
                "feedback": "Check LM Studio connection."
            }

    async def ask_overseer(self, question: str) -> str:
        """Packages the question and sends it to the Overseer LLM."""
        if not self.model_name:
            await self.initialize()
            if not self.model_name:
                return "Error: Overseer not initialized."

        messages = [
            {"role": "system", "content": OVERSEER_SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]

        response = await self.lm_client.chat_completion(
            model=self.model_name,
            messages=messages,
            temperature=0.7
        )

        if response and response.get('choices'):
            return response['choices'][0]['message']['content']
        else:
            return "Overseer failed to respond."
