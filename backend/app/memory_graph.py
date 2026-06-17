"""Flat memory graph with linked nodes, root markers, and recursive sleep context.

All nodes live at the same level; hierarchy emerges organically via linked_ids.
Nodes with many incoming links act as hubs. Root nodes (is_root=True) are always
visible in the agent's context.
"""

import json
import time
import uuid
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Set
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("memory_graph")


def _fmt_time(ts: float) -> str:
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


@dataclass
class MemoryNode:
    id: str
    title: str
    detail: str = ""
    linked_ids: List[str] = field(default_factory=list)
    is_root: bool = False
    access_count: int = 0
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class MemoryGraph:
    """File-backed flat graph of memory nodes with linked connections."""

    def __init__(self, path: str = ""):
        if not path:
            path = str(Path(__file__).parent / "memory.json")
        self.path = Path(path)
        self._nodes: Dict[str, MemoryNode] = {}
        self._current_node_id: Optional[str] = None
        self._load_or_init()

    def _load_or_init(self):
        if self.path.exists() and self.path.stat().st_size > 0:
            try:
                with open(self.path) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, ValueError):
                logger.warning(f"Corrupt memory file {self.path}, starting fresh")
                self._nodes = {}
                self._current_node_id = None
                self._save()
                return
            for node_data in data.get("nodes", []):
                node_data = self._migrate_node(node_data)
                try:
                    node = MemoryNode(**node_data)
                    self._nodes[node.id] = node
                except TypeError as e:
                    logger.warning(f"Skipping node {node_data.get('id', '?' )}: {e}")
            self._current_node_id = data.get("current_node_id") or None
            logger.info(f"Loaded {len(self._nodes)} memory nodes")
        else:
            logger.info("Initialized empty memory graph")

    @staticmethod
    def _migrate_node(node_data: dict) -> dict:
        """Migrate old-format nodes (v1) to new format (v2)."""
        migrated = dict(node_data)
        # v1 → v2: parent_id/child_ids → linked_ids, summary → title, has_deeper_detail removed
        if "parent_id" in migrated or "child_ids" in migrated:
            lids = set(migrated.get("linked_ids", []))
            if migrated.get("parent_id"):
                lids.add(migrated["parent_id"])
            lids.update(migrated.get("child_ids", []))
            migrated["linked_ids"] = sorted(lids)
            was_root = migrated.get("parent_id") is None
            migrated.pop("parent_id", None)
            migrated.pop("child_ids", None)
            migrated.pop("has_deeper_detail", None)
            if "is_root" not in migrated:
                migrated["is_root"] = was_root
        if "summary" in migrated and migrated["summary"]:
            migrated["title"] = migrated["title"] or migrated["summary"]
            migrated.pop("summary", None)
        # Ensure defaults for new fields
        migrated.setdefault("linked_ids", [])
        migrated.setdefault("is_root", False)
        migrated.setdefault("detail", migrated.get("detail") or "")
        return migrated

    def _save(self):
        data = {
            "nodes": [asdict(n) for n in self._nodes.values()],
            "current_node_id": self._current_node_id,
            "format": "hswm_v2",
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

    def get_node(self, node_id: str) -> Optional[dict]:
        node = self._nodes.get(node_id)
        return asdict(node) if node else None

    # ── Navigation ────────────────────────────────────────────────

    def set_current_node(self, node_id: Optional[str]) -> Optional[MemoryNode]:
        if node_id is None or node_id == "":
            self._current_node_id = None
            self._save()
            return None
        if node_id in self._nodes:
            self._current_node_id = node_id
            self._save()
            return self._nodes[node_id]
        return None

    # ── CRUD ──────────────────────────────────────────────────────

    def create_memory(
        self,
        title: str,
        detail: str = "",
        linked_ids: Optional[List[str]] = None,
        is_root: bool = False,
    ) -> MemoryNode:
        node_id = uuid.uuid4().hex[:12]
        node = MemoryNode(
            id=node_id,
            title=title,
            detail=detail or "",
            linked_ids=list(dict.fromkeys(linked_ids or [])),
            is_root=is_root,
        )
        self._nodes[node_id] = node
        self._save()
        return node

    def update_memory(
        self,
        node_id: str,
        title: Optional[str] = None,
        detail: Optional[str] = None,
        linked_ids: Optional[List[str]] = None,
    ) -> Optional[MemoryNode]:
        node = self._nodes.get(node_id)
        if not node:
            return None
        if title is not None:
            node.title = title
        if detail is not None:
            node.detail = detail
        if linked_ids is not None:
            node.linked_ids = list(dict.fromkeys(linked_ids))
        node.access_count = 0
        node.updated_at = time.time()
        self._save()
        return node

    def delete_node(self, node_id: str):
        node = self._nodes.pop(node_id, None)
        if not node:
            return
        # Remove from linked_ids of all other nodes
        for n in self._nodes.values():
            if node_id in n.linked_ids:
                n.linked_ids.remove(node_id)
                n.updated_at = time.time()
        if self._current_node_id == node_id:
            self._current_node_id = None
        self._save()

    def read_detail(self, node_id: str, sleep_mode: bool = False) -> Optional[str]:
        node = self._nodes.get(node_id)
        if not node:
            return None
        if not sleep_mode:
            node.access_count += 1
            node.updated_at = time.time()
            self._save()

        lines = [f"ID: {node.id}", f"Title: {node.title}"]
        detail = node.detail.strip() if node.detail else ""
        if detail:
            lines.append(f"Detail: {detail}")
        else:
            lines.append("Detail: No further details")
        if node.linked_ids:
            lines.append("Links:")
            for lid in node.linked_ids:
                linked = self._nodes.get(lid)
                if linked:
                    lines.append(f"  [{lid}] {linked.title}")
                else:
                    lines.append(f"  [{lid}] (deleted)")
        else:
            lines.append("Links: none")
        lines.append(f"Created: {_fmt_time(node.created_at)}")
        lines.append(f"Updated: {_fmt_time(node.updated_at)}")
        lines.append(f"Access count: {node.access_count}")
        if node.is_root:
            lines.append("Root: yes")
        return "\n".join(lines)

    # ── Context for system prompt ─────────────────────────────────

    def current_context(self) -> str:
        parts = []
        roots = [n for n in self._nodes.values() if n.is_root]
        if roots:
            for r in sorted(roots, key=lambda n: n.created_at):
                parts.append(f"  [root {r.id}] {r.title}")
        current = self.current_node
        if current:
            parts.append(f"  ► [current {current.id}] {current.title}")
        if not parts:
            return "[no memory]"
        return "\n".join(parts)

    def get_root_nodes(self) -> List[MemoryNode]:
        return sorted(
            (n for n in self._nodes.values() if n.is_root),
            key=lambda n: n.created_at,
        )

    def get_all_nodes(self) -> List[dict]:
        return [asdict(n) for n in self._nodes.values()]

    # ── Sleep context ─────────────────────────────────────────────

    def generate_sleep_context(self, start_time: float, end_time: float) -> str:
        """Show all nodes in the time range flatly, grouped with linked neighbors."""
        lo = int(start_time)
        hi = int(end_time) + 1  # ceil so nodes at end_time are included

        in_range = [
            self._nodes[nid] for nid, n in self._nodes.items()
            if lo <= int(n.created_at) <= hi
        ]
        if not in_range:
            return "[no memories in range]"

        in_range_set = {n.id for n in in_range}
        result: List[str] = []

        for node in sorted(in_range, key=lambda n: n.created_at):
            detail = node.detail.strip() if node.detail else "No further details"
            tags = []
            if node.is_root:
                tags.append("root")
            tag_str = (" [" + ", ".join(tags) + "]") if tags else ""

            result.append(
                f"[{node.id}] {node.title}{tag_str} | "
                f"{detail[:200]} | "
                f"links: {len(node.linked_ids)} | "
                f"access: {node.access_count} | "
                f"created: {_fmt_time(node.created_at)} | "
                f"updated: {_fmt_time(node.updated_at)}"
            )

            if node.linked_ids:
                link_names = []
                for lid in node.linked_ids:
                    linked = self._nodes.get(lid)
                    if linked:
                        label = f"[{lid}] {linked.title}"
                        if lid not in in_range_set:
                            label += " (outside range)"
                    else:
                        label = f"[{lid[:8]}] (deleted)"
                    link_names.append(label)
                result.append(f"  links to: {', '.join(link_names)}")

        return "\n".join(result)

    # ── Maintenance ───────────────────────────────────────────────

    def optimize(self):
        """Remove stale low-access nodes and promote hubs."""
        now = time.time()
        deleted = 0

        # Count incoming links
        incoming: Dict[str, int] = {}
        for n in self._nodes.values():
            for lid in n.linked_ids:
                incoming[lid] = incoming.get(lid, 0) + 1

        for node in list(self._nodes.values()):
            age_days = (now - node.updated_at) / 86400
            is_hub = incoming.get(node.id, 0) >= 3
            # Delete only if stale, low-access, no links, not root
            if (
                not is_hub
                and age_days > 7
                and node.access_count < 2
                and not node.linked_ids
                and not node.is_root
            ):
                self.delete_node(node.id)
                deleted += 1

        # Reset access counters
        for node in self._nodes.values():
            node.access_count = max(0, node.access_count - 2)

        self._save()
        logger.info(f"Sleep-flow: deleted={deleted}, total={len(self._nodes)}")


# Singleton
_graph: Optional[MemoryGraph] = None


def get_memory_graph() -> MemoryGraph:
    global _graph
    if _graph is None:
        _graph = MemoryGraph()
    return _graph


def set_memory_graph(graph: MemoryGraph):
    global _graph
    _graph = graph
