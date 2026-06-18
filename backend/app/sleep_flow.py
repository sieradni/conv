"""Sleep Flow — offline memory optimization via recursive context generation.

Runs as a background task to:
1. Generate a full recursive context of the memory graph within a time range.
2. Feed it to an LLM to propose prunes, merges, and link adjustments.
3. Apply the LLM's suggestions.
"""

import asyncio
import json
import logging
import time
from typing import Optional
from app.memory_graph import get_memory_graph, _fmt_time
from app.lm_client import LMStudioClient

logger = logging.getLogger("sleep_flow")

SLEEP_OPTIMIZER_PROMPT = """You are a memory optimization agent. Your task is to analyze the memory graph context below and suggest improvements.

Rules:
- Merge duplicate or highly similar memories into one.
- Delete memories that are obsolete, redundant, or low-value.
- Add links between related memories that should be connected.
- Keep root nodes for essential, high-level topics.
- Return your suggestions as a JSON array of actions:
  [
    {"action": "merge", "keep": "<id>", "delete": ["<id>", ...], "new_content": "...", "new_extraneous_detail": "..."},
    {"action": "delete", "id": "<id>"},
    {"action": "link", "id": "<id>", "link_to": "<id>"},
    {"action": "unlink", "id": "<id>", "unlink_from": "<id>"},
    {"action": "set_root", "id": "<id>", "is_root": true},
    {"action": "update", "id": "<id>", "content": "...", "extraneous_detail": "..."}
  ]

Current memory graph context:
"""


async def run_sleep_cycle(start_time: Optional[float] = None, end_time: Optional[float] = None):
    """Execute one full sleep optimization cycle within the given time range."""
    logger.info("Sleep flow starting...")
    graph = get_memory_graph()

    if start_time is None:
        start_time = 0.0
    if end_time is None:
        end_time = time.time()

    context = graph.generate_sleep_context(start_time, end_time)
    logger.info(f"Sleep context generated ({len(context)} chars)")

    # Try LLM optimization
    try:
        lm = LMStudioClient(timeout=60.0)
        models = await lm.get_models()
        model_name = models['data'][0]['id'] if (models and 'data' in models and models['data']) else None
        if model_name:
            messages = [
                {"role": "system", "content": SLEEP_OPTIMIZER_PROMPT + context},
                {"role": "user", "content": "Analyze this memory graph and suggest optimizations."},
            ]
            response = await lm.chat_completion(model=model_name, messages=messages, temperature=0.3)
            if response:
                content = response["choices"][0]["message"]["content"]
                logger.info(f"Sleep LLM response ({len(content)} chars)")
                actions = _parse_actions(content)
                if actions:
                    _apply_actions(actions, graph)
                    logger.info(f"Applied {len(actions)} sleep optimizations")
                else:
                    logger.info("No optimizations suggested")
        else:
            logger.warning("No model available for sleep optimization")
    except Exception as e:
        logger.error(f"Sleep optimization error: {e}")

    # Always run basic maintenance
    graph.optimize()
    logger.info("Sleep flow complete.")


def _parse_actions(content: str) -> list:
    """Extract action JSON from LLM response."""
    import re
    m = re.search(r'\[.*?\]', content, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return []


def _apply_actions(actions: list, graph):
    """Apply optimization actions to the memory graph."""
    for action in actions:
        try:
            act = action.get("action", "")
            if act == "delete":
                graph.delete_node(action["id"])
            elif act == "merge":
                keep_id = action["keep"]
                for del_id in action.get("delete", []):
                    # Relink delete node's links to keep node
                    del_node = graph._nodes.get(del_id)
                    if del_node:
                        for lid in del_node.linked_ids:
                            if lid != keep_id and lid not in graph._nodes[keep_id].linked_ids:
                                graph._nodes[keep_id].linked_ids.append(lid)
                        graph.delete_node(del_id)
                if action.get("new_content"):
                    graph._nodes[keep_id].content = action["new_content"]
                if action.get("new_extraneous_detail"):
                    graph._nodes[keep_id].extraneous_detail = action["new_extraneous_detail"]
                graph._nodes[keep_id].updated_at = time.time()
            elif act == "link":
                node = graph._nodes.get(action["id"])
                link_to = action["link_to"]
                if node and link_to in graph._nodes and link_to not in node.linked_ids:
                    node.linked_ids.append(link_to)
                    node.updated_at = time.time()
            elif act == "unlink":
                node = graph._nodes.get(action["id"])
                unlink = action["unlink_from"]
                if node and unlink in node.linked_ids:
                    node.linked_ids.remove(unlink)
                    node.updated_at = time.time()
            elif act == "set_root":
                node = graph._nodes.get(action["id"])
                if node:
                    node.is_root = bool(action.get("is_root", True))
                    node.updated_at = time.time()
            elif act == "update":
                node = graph._nodes.get(action["id"])
                if node:
                    if action.get("content"):
                        node.content = action["content"]
                    if action.get("extraneous_detail"):
                        node.extraneous_detail = action["extraneous_detail"]
                    node.updated_at = time.time()
        except Exception as e:
            logger.warning(f"Skip action {action}: {e}")
    graph._save()


async def sleep_loop(interval_seconds: int = 3600):
    """Run the sleep flow periodically every `interval_seconds`."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await run_sleep_cycle()
        except Exception as e:
            logger.error(f"Sleep flow error: {e}")
