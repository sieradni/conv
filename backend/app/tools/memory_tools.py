"""Memory graph tools — set_current_node, read_detail, create_memory, update_memory."""

from app.memory_graph import get_memory_graph


def set_current_node(node_id: str = "") -> str:
    graph = get_memory_graph()
    nid = node_id.strip() or None
    node = graph.set_current_node(nid)
    if nid is None:
        return "Current node cleared."
    if node:
        return f"Current node set to [{node.id}] {node.content}"
    return f"Node '{node_id}' not found."


def read_detail(key: str, sleep_mode: bool = False) -> str:
    graph = get_memory_graph()
    detail = graph.read_detail(key, sleep_mode=sleep_mode)
    if detail is not None:
        return f"Detail for node {key}:\n{detail}"
    return f"Node '{key}' not found."


def create_memory(
    content: str, extraneous_detail: str = "",
    linked_ids: str = "", is_root: bool = False,
) -> str:
    graph = get_memory_graph()
    lids = [x.strip() for x in linked_ids.split(",") if x.strip()] if linked_ids else None
    node = graph.create_memory(
        content=content, extraneous_detail=extraneous_detail,
        linked_ids=lids, is_root=is_root,
    )
    return f"Created memory [{node.id}] '{content}'"


def update_memory(
    node_id: str, content: str = "", extraneous_detail: str = "",
    linked_ids: str = "",
) -> str:
    graph = get_memory_graph()
    kwargs = {}
    if content:
        kwargs["content"] = content
    if extraneous_detail:
        kwargs["extraneous_detail"] = extraneous_detail
    if linked_ids:
        kwargs["linked_ids"] = [x.strip() for x in linked_ids.split(",") if x.strip()]
    node = graph.update_memory(node_id, **kwargs)
    if node:
        return f"Updated memory [{node.id}] {node.content}"
    return f"Node '{node_id}' not found."


def refine_memory_methodology(new_rules: str, reflection: str) -> str:
    from datetime import datetime
    from app.core.config import MEMORY_RULES_FILE, META_PROMPT_HISTORY_LOG

    MEMORY_RULES_FILE.write_text(new_rules, encoding="utf-8")

    timestamp = datetime.now().isoformat()
    log_entry = f"""
{"=" * 80}
Timestamp: {timestamp}
Agent Reflection:
{reflection}

New Rules Applied:
{new_rules}
{"=" * 80}

"""
    with open(META_PROMPT_HISTORY_LOG, "a") as f:
        f.write(log_entry)

    return "Updated memory methodology and logged to audit trail"
