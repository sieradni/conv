import pytest
from unittest.mock import MagicMock, patch, AsyncMock, PropertyMock
from pathlib import Path
from app.tools import ToolExecutor


@pytest.fixture
def mock_sandbox():
    sb = MagicMock()
    sb.workspace_path = Path("/tmp/sandbox")
    sb.read_file.return_value = "line1\nline2\nline3"
    sb.read_file_numbered.return_value = "1: line1\n2: line2\n3: line3"
    sb.write_file.return_value = "Successfully wrote file to test.txt"
    return sb


@pytest.fixture
def executor(mock_sandbox):
    return ToolExecutor(mock_sandbox)


@pytest.fixture
def tmp_app_dir(tmp_workspace):
    import app.tools as tools_mod
    with patch.object(tools_mod, '__file__', str(tmp_workspace / 'test.py')):
        yield tmp_workspace


class TestToolExecutorFileIO:
    def test_write_file(self, executor, mock_sandbox):
        result = executor.write_file("test.txt", "content")
        mock_sandbox.write_file.assert_called_once_with("test.txt", "content", scope="default")
        assert "success" in result.lower() or "Successfully" in result
        assert len(executor.execution_log) == 1
        assert executor.execution_log[0]["status"] == "success"

    def test_write_file_failure(self, executor, mock_sandbox):
        mock_sandbox.write_file.side_effect = PermissionError("Access denied")
        with pytest.raises(Exception, match="Error writing file"):
            executor.write_file("bad.txt", "content")
        assert executor.execution_log[-1]["status"] == "failed"

    def test_read_file(self, executor, mock_sandbox):
        result = executor.read_file("test.txt")
        mock_sandbox.read_file_numbered.assert_called_once_with("test.txt", scope="default")
        assert "1:" in result
        assert executor.execution_log[-1]["status"] == "success"

    def test_read_file_failure(self, executor, mock_sandbox):
        mock_sandbox.read_file_numbered.side_effect = FileNotFoundError("Not found")
        with pytest.raises(Exception, match="Error reading file"):
            executor.read_file("missing.txt")


class TestToolExecutorSurgicalEdits:
    def test_replace_lines(self, executor, mock_sandbox):
        result = executor.replace_lines("file.py", 2, 2, "new_line")
        assert "Replaced lines 2-2" in result
        mock_sandbox.write_file.assert_called_once()

    def test_replace_lines_invalid_range(self, executor, mock_sandbox):
        result = executor.replace_lines("file.py", 10, 20, "content")
        assert "invalid line range" in result

    def test_replace_lines_invalid_start(self, executor, mock_sandbox):
        result = executor.replace_lines("file.py", 0, 2, "content")
        assert "invalid line range" in result

    def test_insert_lines(self, executor, mock_sandbox):
        result = executor.insert_lines("file.py", 1, "inserted")
        assert "Inserted 1 line(s) after line 1" in result
        mock_sandbox.write_file.assert_called_once()

    def test_insert_lines_at_beginning(self, executor, mock_sandbox):
        result = executor.insert_lines("file.py", 0, "top")
        assert "Inserted 1 line(s) after line 0" in result

    def test_insert_lines_invalid(self, executor, mock_sandbox):
        result = executor.insert_lines("file.py", 99, "content")
        assert "invalid line number" in result

    def test_append_to_file(self, executor, mock_sandbox):
        result = executor.append_to_file("file.py", "appended")
        assert "Appended 1 line(s)" in result

    def test_append_to_file_with_newline(self, executor, mock_sandbox):
        mock_sandbox.read_file.return_value = "line1\n"
        result = executor.append_to_file("file.py", "appended")
        assert "Appended 1 line(s)" in result


class TestToolExecutorCommand:
    def test_run_command_success(self, executor, mock_sandbox):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "hello world"
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            result = executor.run_command("echo hello")
            assert "hello world" in result

    def test_run_command_with_stderr(self, executor, mock_sandbox):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "output"
            mock_result.stderr = "warning"
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            result = executor.run_command("cmd")
            assert "[STDERR]" in result
            assert "warning" in result

    def test_run_command_timeout(self, executor, mock_sandbox):
        with patch("subprocess.run") as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired("cmd", 10)
            with pytest.raises(Exception, match="Command timeout"):
                executor.run_command("sleep 100", timeout=1)

    def test_run_command_failure(self, executor, mock_sandbox):
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = Exception("Something broke")
            with pytest.raises(Exception, match="Error running command"):
                executor.run_command("invalid")


class TestToolExecutorMemory:
    def test_set_current_node(self, executor):
        with patch("app.memory_graph.get_memory_graph") as mock_get:
            mock_graph = MagicMock()
            mock_graph.set_current_node.return_value = MagicMock(id="abc12345xyz", content="Test")
            mock_get.return_value = mock_graph
            result = executor.set_current_node("abc12345xyz")
            assert "✓" in result

    def test_set_current_node_not_found(self, executor):
        with patch("app.memory_graph.get_memory_graph") as mock_get:
            mock_graph = MagicMock()
            mock_graph.set_current_node.return_value = None
            mock_get.return_value = mock_graph
            result = executor.set_current_node("nonexistent")
            assert "not found" in result

    def test_read_detail_found(self, executor):
        with patch("app.memory_graph.get_memory_graph") as mock_get:
            mock_graph = MagicMock()
            mock_graph.read_detail.return_value = "Detail for node abc"
            mock_get.return_value = mock_graph
            result = executor.read_detail("abc")
            assert "Detail for node abc" in result

    def test_read_detail_not_found(self, executor):
        with patch("app.memory_graph.get_memory_graph") as mock_get:
            mock_graph = MagicMock()
            mock_graph.read_detail.return_value = None
            mock_get.return_value = mock_graph
            result = executor.read_detail("nonexistent")
            assert "not found" in result

    def test_create_memory(self, executor):
        with patch("app.memory_graph.get_memory_graph") as mock_get:
            mock_graph = MagicMock()
            mock_graph.create_memory.return_value = MagicMock(id="abc123", content="New Mem")
            mock_get.return_value = mock_graph
            result = executor.create_memory("New Mem", "details", "link1,link2", True)
            assert "✓" in result

    def test_update_memory(self, executor):
        with patch("app.memory_graph.get_memory_graph") as mock_get:
            mock_graph = MagicMock()
            mock_graph.update_memory.return_value = MagicMock(id="abc", content="Updated")
            mock_get.return_value = mock_graph
            result = executor.update_memory("abc", content="Updated")
            assert "✓" in result


class TestToolExecutorTodoAndNotes:
    def test_update_todo(self, executor, tmp_app_dir):
        result = executor.update_todo("todo_items", ["task1"])
        assert "✓" in result
        todo = tmp_app_dir / "todo.json"
        assert todo.exists()
        import json
        data = json.loads(todo.read_text())
        assert data["todo_items"] == ["task1"]

    def test_refine_memory_methodology(self, executor, tmp_app_dir):
        result = executor.refine_memory_methodology("new rules", "reflection")
        assert "✓" in result
        rules = tmp_app_dir / "memory_rules.md"
        assert rules.exists()
        assert rules.read_text() == "new rules"
        history = tmp_app_dir / "meta_prompt_history.log"
        assert history.exists()
        assert "new rules" in history.read_text()

    def test_read_user_notes_exists(self, executor, tmp_app_dir):
        notes = tmp_app_dir / "user_notes.md"
        notes.write_text("# My Notes")
        result = executor.read_user_notes()
        assert "# My Notes" in result

    def test_read_user_notes_missing(self, executor, tmp_app_dir):
        result = executor.read_user_notes()
        assert "No notes yet" in result

    def test_write_user_notes(self, executor, tmp_app_dir):
        result = executor.write_user_notes("new content")
        assert "✓" in result
        notes = tmp_app_dir / "user_notes.md"
        assert notes.exists()
        assert notes.read_text() == "new content"


class TestToolExecutorSelfDev:
    def test_propose_change(self, executor):
        with patch("app.self_dev.get_shadow_sandbox") as mock_get:
            mock_sandbox = MagicMock()
            mock_sandbox.status = "READY"
            mock_sandbox.apply_change.return_value = "Applied change"
            mock_get.return_value = mock_sandbox
            result = executor.propose_change("file.py", "content")
            assert "Applied" in result

    def test_run_self_test(self, executor):
        with patch("app.self_dev.get_shadow_sandbox") as mock_get:
            mock_sandbox = MagicMock()
            mock_sandbox.status = "READY"
            mock_sandbox.run_tests.return_value = {"status": "PASSED", "output": "All tests passed"}
            mock_get.return_value = mock_sandbox
            result = executor.run_self_test()
            assert "PASSED" in result

    def test_deploy_change(self, executor):
        with patch("app.self_dev.get_shadow_sandbox") as mock_get:
            mock_sandbox = MagicMock()
            mock_sandbox.status = "READY"
            mock_sandbox.deploy_to_live.return_value = "Deployed 2 files"
            mock_get.return_value = mock_sandbox
            result = executor.deploy_change()
            assert "Deployed" in result


class TestToolExecutorSingleton:
    def test_get_executor_uninitialized(self):
        from app.tools import get_executor
        with pytest.raises(RuntimeError, match="not initialized"):
            get_executor()

    def test_set_and_get_executor(self):
        from app.tools import set_executor, get_executor
        mock_exec = MagicMock(spec=ToolExecutor)
        set_executor(mock_exec)
        result = get_executor()
        assert result is mock_exec
        set_executor(None)
