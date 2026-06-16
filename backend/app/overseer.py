"""Overseer Agent - Quality assurance and approval authority for Actor agent decisions"""

import json
from typing import Dict, Any, Optional
from app.lm_client import LMStudioClient

OVERSEER_SYSTEM_PROMPT = """You are an elite, skeptical Software Quality Assurance Engineer and Security Auditor.
Your job is to review the Actor agent's proposed plans, executed commands, and final completions.

You must be highly critical. Look for:
1. Missing edge cases in code or tests.
2. Security concerns (e.g., unauthorized path escapes, dangerous command execution).
3. Poorly documented changes or empty memory files.

For standard reviews of plans/actions, output a JSON object:
{
    "status": "APPROVED" or "REJECTED",
    "reasoning": "Detailed explanation of your review",
    "feedback": "If REJECTED, list explicit steps the Actor must take to get approval."
}

For answering direct questions from the Actor, respond with a helpful, analytical explanation.
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

    async def review_action(self, actor_thought: str, tool_name: str, tool_args: dict, files_context: str) -> Dict[str, Any]:
        """Review a critical action or a completion request."""
        if not self.model_name:
            await self.initialize()
            if not self.model_name:
                return {
                    "status": "REJECTED",
                    "reasoning": "Overseer not initialized (no models found)",
                    "feedback": "Ensure LM Studio is running and a model is loaded."
                }

        prompt = f"""
ACTOR PROPOSED ACTION:
- Thought: {actor_thought}
- Tool to call: {tool_name}
- Arguments: {tool_args}

CURRENT DIRECTORY FILE STATE:
{files_context}

Please review this proposal. Output your response as a valid JSON object matching the requested schema.
"""
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
            
            # Robust JSON cleaning
            cleaned_content = content.strip()
            if "```json" in cleaned_content:
                cleaned_content = cleaned_content.split("```json")[1].split("```")[0]
            elif "```" in cleaned_content:
                cleaned_content = cleaned_content.split("```")[1].split("```")[0]
            
            try:
                return json.loads(cleaned_content.strip())
            except json.JSONDecodeError:
                return {
                    "status": "REJECTED",
                    "reasoning": "Overseer returned invalid JSON",
                    "feedback": f"The overseer output was: {content}. Please ensure standard JSON output."
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
