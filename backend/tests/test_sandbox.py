import pytest
import os
from pathlib import Path
from app.sandbox import LocalSandbox


class TestSandboxSecurity:
    def test_write_and_read_inside_sandbox(self, sandbox_instance):
        result = sandbox_instance.write_file("test.txt", "hello")
        assert "Successfully wrote" in result
        content = sandbox_instance.read_file("test.txt")
        assert content == "hello"

    def test_read_file_numbered_format(self, sandbox_instance):
        sandbox_instance.write_file("multi.py", "def foo():\n    pass\n\nx = 1")
        numbered = sandbox_instance.read_file_numbered("multi.py")
        assert "1: def foo():" in numbered
        assert "2:     pass" in numbered
        assert "3:" in numbered
        assert "4: x = 1" in numbered

    def test_directory_traversal_blocked(self, sandbox_instance):
        with pytest.raises(PermissionError):
            sandbox_instance.write_file("../escape.txt", "bad")

    def test_absolute_path_escape_blocked(self, sandbox_instance):
        with pytest.raises(PermissionError):
            sandbox_instance.write_file("/etc/passwd", "bad")

    def test_complex_traversal_blocked(self, sandbox_instance):
        with pytest.raises(PermissionError):
            sandbox_instance.write_file("../../home/user/dangerous.txt", "bad")

    def test_deep_nested_directory_traversal_blocked(self, sandbox_instance):
        with pytest.raises(PermissionError):
            sandbox_instance.write_file("a/../../b/../../../c.txt", "bad")

    def test_symlink_blocked(self, sandbox_instance, tmp_workspace):
        link_path = tmp_workspace / "link_to_root"
        try:
            os.symlink("/", link_path)
            with pytest.raises(PermissionError):
                sandbox_instance.read_file("link_to_root/etc/passwd")
        except OSError:
            pass

    def test_list_files(self, sandbox_instance):
        sandbox_instance.write_file("a.txt", "a")
        sandbox_instance.write_file("b.txt", "b")
        files = sandbox_instance.list_files(".")
        assert "a.txt" in files
        assert "b.txt" in files

    def test_list_files_nonexistent_directory(self, sandbox_instance):
        with pytest.raises(FileNotFoundError):
            sandbox_instance.list_files("nonexistent")

    def test_read_nonexistent_file(self, sandbox_instance):
        with pytest.raises(FileNotFoundError):
            sandbox_instance.read_file("does_not_exist.txt")

    def test_nested_directory_creation(self, sandbox_instance):
        result = sandbox_instance.write_file("subdir/nested/file.txt", "nested")
        assert "Successfully wrote" in result
        content = sandbox_instance.read_file("subdir/nested/file.txt")
        assert content == "nested"

    def test_empty_content(self, sandbox_instance):
        sandbox_instance.write_file("empty.txt", "")
        content = sandbox_instance.read_file("empty.txt")
        assert content == ""

    def test_unicode_content(self, sandbox_instance):
        text = "héllo wörld 🌍"
        sandbox_instance.write_file("unicode.txt", text)
        content = sandbox_instance.read_file("unicode.txt")
        assert content == text


class TestSandboxScopes:
    def test_unknown_scope_raises(self, sandbox_instance):
        with pytest.raises(PermissionError, match="Unknown scope"):
            sandbox_instance.read_file("test.txt", scope="nonexistent")

    def test_add_and_use_custom_scope(self, sandbox_instance, tmp_workspace):
        scope_root = tmp_workspace / "custom"
        sandbox_instance.add_scope("custom", scope_root)
        sandbox_instance.write_file("test.txt", "custom scope content", scope="custom")
        content = sandbox_instance.read_file("test.txt", scope="custom")
        assert content == "custom scope content"

    def test_scope_isolation(self, sandbox_instance, tmp_workspace):
        scope_root = tmp_workspace / "isolated"
        sandbox_instance.add_scope("isolated", scope_root)
        sandbox_instance.write_file("shared.txt", "default", scope="default")
        with pytest.raises(FileNotFoundError):
            sandbox_instance.read_file("shared.txt", scope="isolated")

    def test_traversal_in_custom_scope(self, sandbox_instance, tmp_workspace):
        scope_root = tmp_workspace / "safe_zone"
        sandbox_instance.add_scope("safe_zone", scope_root)
        with pytest.raises(PermissionError):
            sandbox_instance.write_file("../outside.txt", "bad", scope="safe_zone")

    def test_get_root(self, sandbox_instance, tmp_workspace):
        root = sandbox_instance.get_root("default")
        assert root == tmp_workspace.resolve()

    def test_get_root_unknown_scope(self, sandbox_instance):
        with pytest.raises(PermissionError, match="Unknown scope"):
            sandbox_instance.get_root("undefined")

    def test_workspace_path_property(self, sandbox_instance, tmp_workspace):
        assert sandbox_instance.workspace_path == tmp_workspace.resolve()

    def test_scope_update_replaces_root(self, sandbox_instance, tmp_workspace):
        new_root = tmp_workspace / "updated"
        sandbox_instance.add_scope("default", new_root)
        assert sandbox_instance.get_root("default") == new_root.resolve()

    def test_scope_creates_directory(self, sandbox_instance, tmp_workspace):
        new_path = tmp_workspace / "auto_created" / "nested"
        sandbox_instance.add_scope("new_scope", new_path)
        assert new_path.exists()
