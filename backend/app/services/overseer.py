"""Overseer Agent — reviews tool calls before execution."""

import json
import os
import logging
from typing import Optional

from app.services.lm_client import LMStudioClient

logger = logging.getLogger("overseer")

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
    def __init__(self):
        self.lm_client = LMStudioClient()
        self.model_name: Optional[str] = None

    async def initialize(self):
        models = await self.lm_client.get_models_v2()
        if models and "models" in models and models["models"]:
            # Find the first loaded LLM
            for m in models["models"]:
                if m.get("type") == "llm" and m.get("loaded_instances"):
                    self.model_name = m["loaded_instances"][0]["id"]
                    logger.info(f"Overseer using model: {self.model_name}")
                    return
            # Fallback: first model
            for m in models["models"]:
                if m.get("type") == "llm":
                    self.model_name = m["key"]
                    logger.info(f"Overseer using model (not loaded): {self.model_name}")
                    return
        # Legacy fallback
        models_legacy = await self.lm_client.get_models_legacy()
        if models_legacy and "data" in models_legacy and models_legacy["data"]:
            self.model_name = models_legacy["data"][0]["id"]
            logger.info(f"Overseer using legacy model: {self.model_name}")

    async def _read_sandbox_file(self, sandbox_dir: str, path: str) -> str:
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
    ) -> dict:
        if not self.model_name:
            await self.initialize()
            if not self.model_name:
                return {
                    "status": "REJECTED",
                    "reasoning": "Overseer not initialized (no models found)",
                    "feedback": "Ensure LM Studio is running and a model is loaded.",
                }

        file_context = ""
        if sandbox_dir and os.path.isdir(sandbox_dir):
            target_path = ""
            if tool_name in ("read_file", "write_file"):
                target_path = tool_args.get("path", "")
            elif tool_name == "run_command":
                cmd = tool_args.get("command", "")
                for word in cmd.split():
                    if word.endswith((".py", ".js", ".ts", ".json", ".md", ".txt", ".yaml", ".yml")):
                        target_path = word
                        break
            if target_path:
                content = await self._read_sandbox_file(sandbox_dir, target_path)
                file_context = f"\nFile '{target_path}' contents:\n{content}"

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
            {"role": "user", "content": prompt},
        ]

        response = await self.lm_client.chat_completion_v2(
            model=self.model_name,
            messages=messages,
            temperature=0.1,
        )

        if response:
            # Extract message content from v2 output format
            output = response.get("output", [])
            content = ""
            for item in output:
                if item.get("type") == "message":
                    content += item.get("content", "")
            if not content:
                # Legacy fallback
                content = response.get("choices", [{}])[0].get("message", {}).get("content", "")

            cleaned = content.strip()
            if "```json" in cleaned:
                cleaned = cleaned.split("```json")[1].split("```")[0]
            elif "```" in cleaned:
                cleaned = cleaned.split("```")[1].split("```")[0]

            try:
                result = json.loads(cleaned.strip())
                result["status"] = result.get("status", "REJECTED").upper()
                return result
            except json.JSONDecodeError:
                return {
                    "status": "REJECTED",
                    "reasoning": "Overseer returned unparseable response",
                    "feedback": f"The overseer output was: {content}. Please ensure standard JSON output.",
                }
        else:
            return {
                "status": "REJECTED",
                "reasoning": "Overseer failed to respond.",
                "feedback": "Check LM Studio connection.",
            }
