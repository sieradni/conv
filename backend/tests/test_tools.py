import pytest
from unittest.mock import MagicMock, patch
from app.services.tool_executor import ToolExecutor, get_executor


class TestToolExecutor:
    def test_register_and_execute(self):
        executor = ToolExecutor()
        executor.register("hello", lambda who: f"Hello, {who}!")
        assert executor.list_tools() == ["hello"]
        result = executor.execute("hello", who="World")
        assert result == "Hello, World!"

    def test_execute_unknown_tool(self):
        executor = ToolExecutor()
        result = executor.execute("nonexistent")
        assert "Unknown tool" in result

    def test_execute_error_handling(self):
        executor = ToolExecutor()
        def failing(**kwargs):
            raise ValueError("something went wrong")
        executor.register("fail", failing)
        result = executor.execute("fail")
        assert "Error executing fail" in result

    def test_requires_approval(self):
        executor = ToolExecutor()
        assert executor.requires_approval("write_file") is True
        assert executor.requires_approval("read_file") is True
        assert executor.requires_approval("create_memory") is False
        assert executor.requires_approval("nonexistent") is False

    def test_get_executor_singleton(self):
        e1 = get_executor()
        e2 = get_executor()
        assert e1 is e2
        assert len(e1.list_tools()) > 0

    def test_registered_tools_contain_expected(self):
        executor = get_executor()
        tools = executor.list_tools()
        for name in ["read_file", "write_file", "run_command", "ask_user",
                      "set_goal", "finish_task", "update_todo",
                      "create_memory", "update_memory",
                      "propose_change", "run_self_test", "deploy_change"]:
            assert name in tools, f"Missing tool: {name}"


class TestFileIoTools:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.executor = ToolExecutor()
        with patch("app.tools.file_io._make_sandbox") as mock_sb:
            self.mock_sandbox = MagicMock()
            self.mock_sandbox.read_file_numbered.return_value = "1: hello\n2: world"
            self.mock_sandbox.read_file.return_value = "hello\nworld"
            self.mock_sandbox.write_file.return_value = "Successfully wrote file"
            mock_sb.return_value = self.mock_sandbox
            from app.tools import file_io
            self.executor.register("read_file", file_io.read_file)
            self.executor.register("write_file", file_io.write_file)
            self.executor.register("replace_lines", file_io.replace_lines)
            self.executor.register("insert_lines", file_io.insert_lines)
            self.executor.register("append_to_file", file_io.append_to_file)
            self.executor.register("run_command", file_io.run_command)
            yield

    def test_read_file(self):
        result = self.executor.execute("read_file", path="test.txt")
        assert "1:" in result

    def test_write_file(self):
        result = self.executor.execute("write_file", path="test.txt", content="new")
        assert "Successfully" in result or "wrote" in result.lower()

    def test_replace_lines(self):
        result = self.executor.execute("replace_lines", file_path="f.py", start_line=1, end_line=1, new_content="hi")
        assert "Replaced lines" in result

    def test_insert_lines(self):
        result = self.executor.execute("insert_lines", file_path="f.py", line_number=0, new_content="top")
        assert "Inserted" in result

    def test_append_to_file(self):
        result = self.executor.execute("append_to_file", file_path="f.py", content="end")
        assert "Appended" in result

    def test_run_command(self):
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "hello world"
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            result = self.executor.execute("run_command", command="echo hello")
            assert "hello world" in result
