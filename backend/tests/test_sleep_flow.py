import json
import time
import pytest
from app.sleep_flow import _parse_actions, _apply_actions


class TestParseActions:
    def test_parse_json_array(self):
        content = '[{"action": "delete", "id": "abc123"}]'
        actions = _parse_actions(content)
        assert len(actions) == 1
        assert actions[0]["action"] == "delete"
        assert actions[0]["id"] == "abc123"

    def test_parse_multiple_actions(self):
        content = json.dumps([
            {"action": "delete", "id": "a"},
            {"action": "link", "id": "b", "link_to": "c"},
        ])
        actions = _parse_actions(content)
        assert len(actions) == 2

    def test_parse_in_markdown(self):
        content = 'Here are my suggestions:\n```json\n[{"action": "delete", "id": "x"}]\n```\nEnd.'
        actions = _parse_actions(content)
        assert len(actions) == 1
        assert actions[0]["id"] == "x"

    def test_parse_no_array(self):
        content = "No action array here"
        actions = _parse_actions(content)
        assert actions == []

    def test_parse_malformed_json(self):
        content = '[{broken json]'
        actions = _parse_actions(content)
        assert actions == []

    def test_parse_with_extra_text(self):
        content = 'Some text [{"action": "delete", "id": "abc"}] trailing text'
        actions = _parse_actions(content)
        assert len(actions) == 1
        assert actions[0]["id"] == "abc"

    def test_parse_empty_array(self):
        content = '[]'
        actions = _parse_actions(content)
        assert actions == []


class TestApplyActions:
    def test_apply_delete(self, memory_graph):
        node = memory_graph.create_memory("To Delete")
        _apply_actions([{"action": "delete", "id": node.id}], memory_graph)
        assert node.id not in memory_graph._nodes

    def test_apply_link(self, memory_graph):
        a = memory_graph.create_memory("A")
        b = memory_graph.create_memory("B")
        _apply_actions([{"action": "link", "id": a.id, "link_to": b.id}], memory_graph)
        assert b.id in a.linked_ids

    def test_apply_unlink(self, memory_graph):
        a = memory_graph.create_memory("A")
        b = memory_graph.create_memory("B", linked_ids=[a.id])
        _apply_actions([{"action": "unlink", "id": b.id, "unlink_from": a.id}], memory_graph)
        assert a.id not in b.linked_ids

    def test_apply_set_root(self, memory_graph):
        node = memory_graph.create_memory("Make Root")
        _apply_actions([{"action": "set_root", "id": node.id, "is_root": True}], memory_graph)
        assert node.is_root is True

    def test_apply_unset_root(self, memory_graph):
        node = memory_graph.create_memory("Unroot", is_root=True)
        _apply_actions([{"action": "set_root", "id": node.id, "is_root": False}], memory_graph)
        assert node.is_root is False

    def test_apply_update_title(self, memory_graph):
        node = memory_graph.create_memory("Old Title")
        _apply_actions([{"action": "update", "id": node.id, "title": "New Title"}], memory_graph)
        assert node.title == "New Title"

    def test_apply_update_detail(self, memory_graph):
        node = memory_graph.create_memory("Test")
        _apply_actions([{"action": "update", "id": node.id, "detail": "New detail"}], memory_graph)
        assert node.detail == "New detail"

    def test_apply_merge(self, memory_graph):
        keep = memory_graph.create_memory("Keep")
        delete = memory_graph.create_memory("Delete", linked_ids=["some_id"])
        _apply_actions([{
            "action": "merge",
            "keep": keep.id,
            "delete": [delete.id],
            "new_title": "Merged Title",
            "new_detail": "Merged detail",
        }], memory_graph)
        assert delete.id not in memory_graph._nodes
        assert keep.title == "Merged Title"
        assert keep.detail == "Merged detail"

    def test_apply_merge_relinks(self, memory_graph):
        keep = memory_graph.create_memory("Keep")
        other = memory_graph.create_memory("Other")
        delete = memory_graph.create_memory("Delete", linked_ids=[other.id])
        _apply_actions([{
            "action": "merge",
            "keep": keep.id,
            "delete": [delete.id],
        }], memory_graph)
        assert other.id in keep.linked_ids

    def test_apply_error_skips_action(self, memory_graph):
        _apply_actions([{"action": "delete", "id": "nonexistent"}], memory_graph)
        _apply_actions([{"action": "unknown_action", "id": "abc"}], memory_graph)

    def test_apply_multiple_actions(self, memory_graph):
        a = memory_graph.create_memory("A")
        b = memory_graph.create_memory("B")
        _apply_actions([
            {"action": "link", "id": a.id, "link_to": b.id},
            {"action": "set_root", "id": a.id, "is_root": True},
        ], memory_graph)
        assert b.id in a.linked_ids
        assert a.is_root is True
