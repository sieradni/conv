"""Hierarchical Small-World Memory (HSWM) graph store.

Replaces flat working_memory.json with a directed graph of memory nodes
supporting tree navigation, lateral small-world links, and access-count-based
promotion/compression.
"""

import json
import time
import uuid
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("memory_graph")


@dataclass
class MemoryNode:
    id: str
    title: str
    summary: str
    detail: str = ""
    parent_id: Optional[str] = None
    child_ids: List[str] = field(default_factory=list)
    linked_ids: List[str] = field(default_factory=list)
    has_deeper_detail: bool = False
    access_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class MemoryGraph:
    """File-backed directed graph of memory nodes with navigation and
    small-world linking."""

    def __init__(self, path: str = ""):
        if not path:
            path = str(Path(__file__).parent / "working_memory.json")
        self.path = Path(path)
        self._nodes: Dict[str, MemoryNode] = {}
        self._current_node_id: Optional[str] = None
        self._load_or_init()

    def _load_or_init(self):
        if self.path.exists():
            with open(self.path) as f:
                data = json.load(f)
            for node_data in data.get("nodes", []):
                node = MemoryNode(**node_data)
                self._nodes[node.id] = node
            self._current_node_id = data.get("current_node_id")
            logger.info(f"Loaded {len(self._nodes)} memory nodes")
        else:
            # Create root node
            root = MemoryNode(
                id=uuid.uuid4().hex[:12],
                title="Root Core Memory",
                summary="High-level project context, decisions, and discovered facts.",
            )
            self._nodes[root.id] = root
            self._current_node_id = root.id
            self._save()
            logger.info("Initialized empty memory graph with root node")

    def _save(self):
        data = {
            "nodes": [asdict(n) for n in self._nodes.values()],
            "current_node_id": self._current_node_id,
            "format": "hswm_v1",
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump(data, f, indent=2)

    # ── Properties ────────────────────────────────────────────────

    @property
    def current_node(self) -> Optional[MemoryNode]:
        if self._current_node_id and self._current_node_id in self._nodes:
            return self._nodes[self._current_node_id]
        return None

    @property
    def current_node_id(self) -> Optional[str]:
        return self._current_node_id

    def root(self) -> Optional[MemoryNode]:
        for n in self._nodes.values():
            if n.parent_id is None:
                return n
        return None

    def ensure_root(self, title: str = "Root Core Memory", summary: str = "High-level project context, decisions, and discovered facts.") -> MemoryNode:
        root = self.root()
        if root is None:
            node = MemoryNode(
                id=uuid.uuid4().hex[:12],
                title=title,
                summary=summary,
            )
            self._nodes[node.id] = node
            self._current_node_id = node.id
            self._save()
            logger.info("Created root node (was empty)")
            return node
        return root

    # ── Navigation ────────────────────────────────────────────────

    def navigate_up(self) -> Optional[MemoryNode]:
        current = self.current_node
        if current and current.parent_id and current.parent_id in self._nodes:
            self._current_node_id = current.parent_id
            self._save()
            return self._nodes[current.parent_id]
        return None

    def navigate_down(self, node_id: str) -> Optional[MemoryNode]:
        current = self.current_node
        if current and node_id in current.child_ids and node_id in self._nodes:
            self._current_node_id = node_id
            self._save()
            return self._nodes[node_id]
        return None

    def return_to_base(self) -> Optional[MemoryNode]:
        root = self.root()
        if root:
            self._current_node_id = root.id
            self._save()
        return root

    def read_detail(self, node_id: str) -> Optional[str]:
        node = self._nodes.get(node_id)
        if node:
            node.access_count += 1
            node.updated_at = time.time()
            self._save()
            return node.detail
        return None

    def create_memory(
        self,
        title: str,
        summary: str,
        detail: str = "",
        parent_id: Optional[str] = None,
        link_to_ids: Optional[List[str]] = None,
    ) -> MemoryNode:
        # Default parent to current node if no parent specified
        if parent_id is None and self._current_node_id:
            parent_id = self._current_node_id

        node_id = uuid.uuid4().hex[:12]
        node = MemoryNode(
            id=node_id,
            title=title,
            summary=summary,
            detail=detail,
            parent_id=parent_id,
            linked_ids=link_to_ids or [],
            has_deeper_detail=bool(detail),
        )
        self._nodes[node_id] = node

        if parent_id and parent_id in self._nodes:
            parent = self._nodes[parent_id]
            if node_id not in parent.child_ids:
                parent.child_ids.append(node_id)
                parent.updated_at = time.time()

        if link_to_ids:
            for lid in link_to_ids:
                if lid in self._nodes:
                    linked = self._nodes[lid]
                    if node_id not in linked.linked_ids:
                        linked.linked_ids.append(node_id)
                        linked.updated_at = time.time()

        self._save()
        return node

    # ── Queries ───────────────────────────────────────────────────

    def get_node(self, node_id: str) -> Optional[dict]:
        node = self._nodes.get(node_id)
        return asdict(node) if node else None

    def get_neighborhood(self, node_id: Optional[str] = None) -> Dict[str, Any]:
        nid = node_id or self._current_node_id
        if not nid or nid not in self._nodes:
            return {"current": None, "children": [], "links": [], "root": None}

        node = self._nodes[nid]
        children = [asdict(self._nodes[cid]) for cid in node.child_ids if cid in self._nodes]
        links = [asdict(self._nodes[lid]) for lid in node.linked_ids if lid in self._nodes]
        root = self.root()

        return {
            "current": asdict(node),
            "children": children,
            "links": links,
            "root": asdict(root) if root else None,
        }

    def current_context(self) -> str:
        """Return formatted context string for the system prompt."""
        parts = []
        root = self.root()
        if root:
            parts.append(f"  [{root.title}]: {root.summary}")

        current = self.current_node
        if current and (not root or current.id != root.id):
            parts.append(f"  ► [{current.title}]: {current.summary[:200]}")

        if current and current.child_ids:
            parts.append("  Children:")
            for cid in current.child_ids:
                child = self._nodes.get(cid)
                if child:
                    depth = "▼" if child.has_deeper_detail else " "
                    parts.append(f"    {depth} {child.id[:8]} [{child.title}]: {child.summary[:120]}")

        if current and current.linked_ids:
            parts.append("  Linked:")
            for lid in current.linked_ids:
                linked = self._nodes.get(lid)
                if linked:
                    parts.append(f"    ↔ {linked.id[:8]} [{linked.title}]: {linked.summary[:120]}")

        return "\n".join(parts) if parts else "[no memory]"

    # ── Maintenance ───────────────────────────────────────────────

    def delete_node(self, node_id: str):
        node = self._nodes.pop(node_id, None)
        if not node:
            return

        if node.parent_id and node.parent_id in self._nodes:
            parent = self._nodes[node.parent_id]
            if node_id in parent.child_ids:
                parent.child_ids.remove(node_id)
                parent.updated_at = time.time()

        for lid in node.linked_ids:
            if lid in self._nodes:
                linked = self._nodes[lid]
                if node_id in linked.linked_ids:
                    linked.linked_ids.remove(node_id)
                    linked.updated_at = time.time()

        self._save()

    def optimize(self):
        """Sleep-flow: compress stale nodes, promote hot nodes, refresh counters."""
        now = time.time()
        deleted = 0
        promoted = 0

        for node in list(self._nodes.values()):
            # Delete very old, low-access leaf nodes
            age_days = (now - node.updated_at) / 86400
            if node.access_count < 2 and age_days > 7 and not node.child_ids:
                self.delete_node(node.id)
                deleted += 1
                continue

            # Promote high-access nodes into parent summary
            if node.access_count > 10 and node.parent_id and node.parent_id in self._nodes:
                parent = self._nodes[node.parent_id]
                tag = f"\n  ✦ {node.title}: {node.summary[:200]}"
                if tag not in parent.summary:
                    parent.summary += tag
                    parent.updated_at = now
                    promoted += 1

            node.access_count = 0
            node.updated_at = now

        self._save()
        logger.info(f"Sleep-flow: deleted={deleted}, promoted={promoted}, total={len(self._nodes)}")


# Singleton
_graph: Optional[MemoryGraph] = None


def get_memory_graph() -> MemoryGraph:
    global _graph
    if _graph is None:
        _graph = MemoryGraph()
    _graph.ensure_root()
    return _graph


def set_memory_graph(graph: MemoryGraph):
    global _graph
    _graph = graph
