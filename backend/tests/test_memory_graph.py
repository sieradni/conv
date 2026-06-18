import json
import time
import pytest
from app.memory_graph import MemoryGraph, MemoryNode, _fmt_time


class TestMemoryGraphCRUD:
    def test_create_memory(self, memory_graph):
        node = memory_graph.create_memory("Test Title", extraneous_detail="Some detail")
        assert node.id in memory_graph._nodes
        assert node.content == "Test Title"
        assert node.extraneous_detail == "Some detail"
        assert node.is_root is False
        assert node.linked_ids == []
        assert node.access_count == 0

    def test_create_memory_with_links(self, memory_graph):
        a = memory_graph.create_memory("A")
        b = memory_graph.create_memory("B", linked_ids=[a.id])
        assert b.linked_ids == [a.id]

    def test_create_root_memory(self, memory_graph):
        node = memory_graph.create_memory("Root", is_root=True)
        assert node.is_root is True

    def test_create_memory_deduplicates_links(self, memory_graph):
        a = memory_graph.create_memory("A")
        b = memory_graph.create_memory("B", linked_ids=[a.id, a.id])
        assert b.linked_ids == [a.id]

    def test_get_node(self, memory_graph):
        node = memory_graph.create_memory("Test")
        result = memory_graph.get_node(node.id)
        assert result is not None
        assert result["content"] == "Test"

    def test_get_nonexistent_node(self, memory_graph):
        assert memory_graph.get_node("nonexistent") is None

    def test_update_memory_content(self, memory_graph):
        node = memory_graph.create_memory("Old Content")
        updated = memory_graph.update_memory(node.id, content="New Content")
        assert updated.content == "New Content"
        assert memory_graph._nodes[node.id].content == "New Content"

    def test_update_memory_extraneous_detail(self, memory_graph):
        node = memory_graph.create_memory("Test")
        memory_graph.update_memory(node.id, extraneous_detail="Updated detail")
        assert memory_graph._nodes[node.id].extraneous_detail == "Updated detail"

    def test_update_memory_links(self, memory_graph):
        a = memory_graph.create_memory("A")
        b = memory_graph.create_memory("B")
        memory_graph.update_memory(a.id, linked_ids=[b.id])
        assert a.linked_ids == [b.id]

    def test_update_memory_nonexistent(self, memory_graph):
        result = memory_graph.update_memory("nonexistent", content="New")
        assert result is None

    def test_update_resets_access_count(self, memory_graph):
        node = memory_graph.create_memory("Test")
        node.access_count = 5
        memory_graph.update_memory(node.id, content="Updated")
        assert node.access_count == 0

    def test_delete_node(self, memory_graph):
        node = memory_graph.create_memory("To Delete")
        memory_graph.delete_node(node.id)
        assert node.id not in memory_graph._nodes

    def test_delete_node_removes_links(self, memory_graph):
        a = memory_graph.create_memory("A")
        b = memory_graph.create_memory("B", linked_ids=[a.id])
        memory_graph.delete_node(a.id)
        assert a.id not in b.linked_ids

    def test_delete_node_clears_current(self, memory_graph):
        node = memory_graph.create_memory("Current")
        memory_graph.set_current_node(node.id)
        memory_graph.delete_node(node.id)
        assert memory_graph.current_node_id is None


class TestMemoryGraphNavigation:
    def test_set_current_node(self, memory_graph):
        node = memory_graph.create_memory("Focus")
        result = memory_graph.set_current_node(node.id)
        assert result.id == node.id
        assert memory_graph.current_node_id == node.id

    def test_set_current_node_nonexistent(self, memory_graph):
        result = memory_graph.set_current_node("nonexistent")
        assert result is None

    def test_set_current_node_clear(self, memory_graph):
        node = memory_graph.create_memory("Focus")
        memory_graph.set_current_node(node.id)
        memory_graph.set_current_node(None)
        assert memory_graph.current_node_id is None

    def test_set_current_node_empty_string(self, memory_graph):
        node = memory_graph.create_memory("Focus")
        memory_graph.set_current_node(node.id)
        memory_graph.set_current_node("")
        assert memory_graph.current_node_id is None

    def test_current_node_property(self, memory_graph):
        node = memory_graph.create_memory("Focus")
        memory_graph.set_current_node(node.id)
        assert memory_graph.current_node.id == node.id

    def test_current_node_property_none(self, memory_graph):
        assert memory_graph.current_node is None


class TestMemoryGraphReadDetail:
    def test_read_detail_basic(self, memory_graph):
        node = memory_graph.create_memory("Test", extraneous_detail="Detail text")
        detail = memory_graph.read_detail(node.id)
        assert node.id in detail
        assert "Test" in detail
        assert "Detail text" in detail

    def test_read_detail_no_detail(self, memory_graph):
        node = memory_graph.create_memory("Minimal")
        detail = memory_graph.read_detail(node.id)
        assert "Extraneous detail:" in detail

    def test_read_detail_increments_access(self, memory_graph):
        node = memory_graph.create_memory("Test")
        old = node.access_count
        memory_graph.read_detail(node.id)
        assert node.access_count == old + 1

    def test_read_detail_sleep_mode_no_increment(self, memory_graph):
        node = memory_graph.create_memory("Test")
        old = node.access_count
        memory_graph.read_detail(node.id, sleep_mode=True)
        assert node.access_count == old

    def test_read_detail_includes_links(self, memory_graph):
        a = memory_graph.create_memory("A")
        b = memory_graph.create_memory("B", linked_ids=[a.id])
        detail = memory_graph.read_detail(b.id)
        assert a.id in detail
        assert "A" in detail

    def test_read_detail_nonexistent(self, memory_graph):
        assert memory_graph.read_detail("nonexistent") is None

    def test_read_detail_root_marker(self, memory_graph):
        node = memory_graph.create_memory("Root", is_root=True)
        detail = memory_graph.read_detail(node.id)
        assert "Root: yes" in detail


class TestMemoryGraphContext:
    def test_current_context_no_memory(self, memory_graph):
        ctx = memory_graph.current_context()
        assert ctx == "[no memory]"

    def test_current_context_with_root(self, memory_graph):
        memory_graph.create_memory("Root1", is_root=True)
        memory_graph.create_memory("Root2", is_root=True)
        ctx = memory_graph.current_context()
        assert "[root" in ctx
        assert "Root1" in ctx

    def test_current_context_with_current(self, memory_graph):
        node = memory_graph.create_memory("Current")
        memory_graph.set_current_node(node.id)
        ctx = memory_graph.current_context()
        assert "► [current" in ctx
        assert "Current" in ctx

    def test_get_root_nodes(self, memory_graph):
        memory_graph.create_memory("Root", is_root=True)
        memory_graph.create_memory("NonRoot")
        roots = memory_graph.get_root_nodes()
        assert len(roots) == 1
        assert roots[0].content == "Root"

    def test_get_all_nodes(self, memory_graph):
        memory_graph.create_memory("A")
        memory_graph.create_memory("B")
        all_nodes = memory_graph.get_all_nodes()
        assert len(all_nodes) == 2


class TestMemoryGraphSleepContext:
    def test_sleep_context_empty(self, memory_graph):
        ctx = memory_graph.generate_sleep_context(0, time.time())
        assert ctx == "[no memories in range]"

    def test_sleep_context_basic(self, memory_graph):
        node = memory_graph.create_memory("Test", extraneous_detail="Detail")
        ctx = memory_graph.generate_sleep_context(0, time.time() + 1)
        assert node.id in ctx
        assert "Test" in ctx
        assert "Detail" in ctx

    def test_sleep_context_outside_range(self, memory_graph):
        node = memory_graph.create_memory("Old")
        ctx = memory_graph.generate_sleep_context(node.created_at + 100, node.created_at + 200)
        assert ctx == "[no memories in range]"

    def test_sleep_context_with_links(self, memory_graph):
        a = memory_graph.create_memory("A")
        b = memory_graph.create_memory("B", linked_ids=[a.id])
        ctx = memory_graph.generate_sleep_context(0, time.time() + 1)
        assert "outside range" in ctx or "links to" in ctx


class TestMemoryGraphMigration:
    def test_v1_to_v2_parent_id(self, memory_graph_path):
        v1_data = {
            "nodes": [
                {"id": "abc", "title": "Old Node", "parent_id": None, "child_ids": ["def"], "summary": "Old Node", "detail": "x"}
            ],
            "current_node_id": "abc"
        }
        memory_graph_path.write_text(json.dumps(v1_data))
        g = MemoryGraph(str(memory_graph_path))
        node = g._nodes["abc"]
        assert node.is_root
        assert "def" in node.linked_ids
        assert node.content == "Old Node"

    def test_v1_to_v2_with_parent(self, memory_graph_path):
        v1_data = {
            "nodes": [
                {"id": "abc", "title": "Child", "parent_id": "parent1", "child_ids": [], "summary": "content", "detail": "x"}
            ],
            "current_node_id": None
        }
        memory_graph_path.write_text(json.dumps(v1_data))
        g = MemoryGraph(str(memory_graph_path))
        node = g._nodes["abc"]
        assert "parent1" in node.linked_ids
        assert not node.is_root

    def test_corrupt_json_starts_fresh(self, memory_graph_path):
        memory_graph_path.write_text("not valid json")
        g = MemoryGraph(str(memory_graph_path))
        assert len(g._nodes) == 0
        assert g.path.exists()


class TestMemoryGraphOptimize:
    def test_optimize_removes_stale_node(self, memory_graph):
        node = memory_graph.create_memory("Stale")
        node.updated_at = time.time() - 8 * 86400
        memory_graph.optimize()
        assert node.id not in memory_graph._nodes

    def test_optimize_keeps_hub(self, memory_graph):
        hub = memory_graph.create_memory("Hub")
        for _ in range(3):
            n = memory_graph.create_memory("Leaf", linked_ids=[hub.id])
            n.updated_at = time.time() - 8 * 86400
        memory_graph.optimize()
        assert hub.id in memory_graph._nodes

    def test_optimize_keeps_root(self, memory_graph):
        node = memory_graph.create_memory("Root", is_root=True)
        node.updated_at = time.time() - 10 * 86400
        memory_graph.optimize()
        assert node.id in memory_graph._nodes

    def test_optimize_keeps_recent_node(self, memory_graph):
        node = memory_graph.create_memory("Recent")
        node.updated_at = time.time() - 1 * 86400
        memory_graph.optimize()
        assert node.id in memory_graph._nodes

    def test_optimize_reduces_access_counts(self, memory_graph):
        node = memory_graph.create_memory("Test")
        node.access_count = 5
        memory_graph.optimize()
        assert node.access_count == 3


class TestMemoryGraphPersistence:
    def test_save_and_load(self, memory_graph_path):
        g1 = MemoryGraph(str(memory_graph_path))
        n1 = g1.create_memory("Saved")
        n2 = g1.create_memory("Also Saved", linked_ids=[n1.id])
        g1.set_current_node(n1.id)
        del g1
        g2 = MemoryGraph(str(memory_graph_path))
        assert len(g2._nodes) == 2
        assert g2.current_node_id == n1.id
        assert g2._nodes[n2.id].linked_ids == [n1.id]
