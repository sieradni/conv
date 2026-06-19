import pytest
import json
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock


class TestMemoryTools:
    @pytest.fixture(autouse=True)
    def mock_graph(self):
        with patch("app.tools.memory_tools.get_memory_graph") as mg:
            self.graph = MagicMock()
            mg.return_value = self.graph
            yield

    def test_set_current_node(self):
        from app.tools.memory_tools import set_current_node
        self.graph.set_current_node.return_value = MagicMock(id="abc", content="Test")
        result = set_current_node("abc")
        self.graph.set_current_node.assert_called_once_with("abc")
        assert "abc" in result

    def test_set_current_node_clear(self):
        from app.tools.memory_tools import set_current_node
        result = set_current_node("")
        self.graph.set_current_node.assert_called_once_with(None)

    def test_set_current_node_not_found(self):
        from app.tools.memory_tools import set_current_node
        self.graph.set_current_node.return_value = None
        result = set_current_node("nonexistent")
        assert "not found" in result

    def test_read_detail(self):
        from app.tools.memory_tools import read_detail
        self.graph.read_detail.return_value = "Detail content"
        result = read_detail("abc")
        assert "Detail content" in result
        assert "abc" in result
        self.graph.read_detail.assert_called_once_with("abc", sleep_mode=False)

    def test_read_detail_not_found(self):
        from app.tools.memory_tools import read_detail
        self.graph.read_detail.return_value = None
        result = read_detail("x")
        assert "not found" in result

    def test_create_memory(self):
        from app.tools.memory_tools import create_memory
        self.graph.create_memory.return_value = MagicMock(id="n1", content="New")
        result = create_memory("New", "details", "link1,link2", True)
        self.graph.create_memory.assert_called_once()
        _, kwargs = self.graph.create_memory.call_args
        assert kwargs["content"] == "New"
        assert kwargs["linked_ids"] == ["link1", "link2"]
        assert kwargs["is_root"] is True

    def test_create_memory_no_links(self):
        from app.tools.memory_tools import create_memory
        self.graph.create_memory.return_value = MagicMock(id="n2", content="Solo")
        result = create_memory("Solo")
        self.graph.create_memory.assert_called_once()
        _, kwargs = self.graph.create_memory.call_args
        assert kwargs["linked_ids"] is None

    def test_update_memory(self):
        from app.tools.memory_tools import update_memory
        self.graph.update_memory.return_value = MagicMock(id="abc", content="Updated")
        result = update_memory("abc", content="Updated")
        self.graph.update_memory.assert_called_once_with("abc", content="Updated")

    def test_update_memory_not_found(self):
        from app.tools.memory_tools import update_memory
        self.graph.update_memory.return_value = None
        result = update_memory("x")
        assert "not found" in result

    def test_refine_memory_methodology(self, tmp_path):
        from app.tools.memory_tools import refine_memory_methodology
        from app.core import config
        rules_file = tmp_path / "memory_rules.md"
        history_file = tmp_path / "meta_prompt_history.log"
        with patch.object(config, "MEMORY_RULES_FILE", rules_file), \
             patch.object(config, "META_PROMPT_HISTORY_LOG", str(history_file)):
            result = refine_memory_methodology("new rules", "reflection")
            assert "Updated" in result
            assert rules_file.read_text() == "new rules"
            assert "new rules" in history_file.read_text()

    def test_refine_memory_methodology_append(self, tmp_path):
        from app.tools.memory_tools import refine_memory_methodology
        from app.core import config
        history_file = tmp_path / "meta_prompt_history.log"
        history_file.write_text("prior entry\n")
        with patch.object(config, "META_PROMPT_HISTORY_LOG", str(history_file)):
            refine_memory_methodology("rules", "ref")
            assert "prior entry" in history_file.read_text()


class TestSystemTools:
    def test_ask_user(self):
        from app.tools.system_tools import ask_user
        result = ask_user("What?")
        assert "ASK_USER" in result
        assert "What?" in result

    def test_finish_task(self):
        from app.tools.system_tools import finish_task
        result = finish_task("summary")
        assert "FINISH_TASK" in result
        assert "summary" in result

    def test_set_goal(self):
        from app.tools.system_tools import set_goal
        result = set_goal("my goal")
        assert "Goal set:" in result

    def test_update_todo(self, tmp_path):
        from app.tools.system_tools import update_todo
        todo_file = tmp_path / "todo.json"
        with patch("app.tools.system_tools.TODO_FILE", todo_file):
            result = update_todo("todo_items", ["task1"])
            assert "Updated" in result
            data = json.loads(todo_file.read_text())
            assert data["todo_items"] == ["task1"]

    def test_update_todo_append(self, tmp_path):
        from app.tools.system_tools import update_todo
        todo_file = tmp_path / "todo.json"
        todo_file.write_text(json.dumps({"todo_items": ["existing"], "completed_items": []}))
        with patch("app.tools.system_tools.TODO_FILE", todo_file):
            result = update_todo("completed_items", ["done"])
            assert "Updated" in result
            data = json.loads(todo_file.read_text())
            assert data["todo_items"] == ["existing"]
            assert data["completed_items"] == ["done"]

    def test_read_user_notes(self, tmp_path):
        from app.tools.system_tools import read_user_notes
        notes_file = tmp_path / "user_notes.md"
        notes_file.write_text("# My Notes")
        with patch("app.tools.system_tools.NOTES_FILE", notes_file):
            result = read_user_notes()
            assert "# My Notes" in result

    def test_read_user_notes_missing(self, tmp_path):
        from app.tools.system_tools import read_user_notes
        notes_file = tmp_path / "user_notes.md"
        with patch("app.tools.system_tools.NOTES_FILE", notes_file):
            result = read_user_notes()
            assert "No notes yet" in result

    def test_write_user_notes(self, tmp_path):
        from app.tools.system_tools import write_user_notes
        notes_file = tmp_path / "user_notes.md"
        with patch("app.tools.system_tools.NOTES_FILE", notes_file):
            result = write_user_notes("new content")
            assert "Notes updated" in result
            assert notes_file.read_text() == "new content"


class TestSelfDevTools:
    @pytest.fixture(autouse=True)
    def mock_shadow(self):
        with patch("app.tools.self_dev_tools.get_shadow_sandbox") as gs:
            self.shadow = MagicMock()
            self.shadow.status = "IDLE"
            gs.return_value = self.shadow
            yield

    def test_propose_change_idle(self):
        from app.tools.self_dev_tools import propose_change
        self.shadow.apply_change.return_value = "Applied change"
        result = propose_change("f.py", "content")
        self.shadow.create_shadow.assert_called_once()
        self.shadow.apply_change.assert_called_once_with("f.py", "content")
        assert "Applied" in result

    def test_propose_change_already_ready(self):
        from app.tools.self_dev_tools import propose_change
        self.shadow.status = "READY"
        self.shadow.apply_change.return_value = "Updated"
        result = propose_change("f.py", "new")
        self.shadow.create_shadow.assert_not_called()
        self.shadow.apply_change.assert_called_once()

    def test_run_self_test_no_shadow(self):
        from app.tools.self_dev_tools import run_self_test
        self.shadow.status = "IDLE"
        result = run_self_test()
        assert "No shadow" in result

    def test_run_self_test_with_shadow(self):
        from app.tools.self_dev_tools import run_self_test
        self.shadow.status = "READY"
        self.shadow.run_tests.return_value = {"status": "PASSED", "output": "All ok"}
        result = run_self_test()
        assert "PASSED" in result

    def test_deploy_change_no_shadow(self):
        from app.tools.self_dev_tools import deploy_change
        self.shadow.status = "IDLE"
        result = deploy_change()
        assert "No shadow" in result

    def test_deploy_change_with_shadow(self):
        from app.tools.self_dev_tools import deploy_change
        self.shadow.status = "READY"
        self.shadow.deploy_to_live.return_value = "Deployed 2 files"
        result = deploy_change()
        assert "Deployed" in result
