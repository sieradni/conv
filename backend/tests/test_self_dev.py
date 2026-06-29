import pytest
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call

from app.self_dev import ShadowSandbox, FRAMEWORK_ROOT, BACKEND_DIR, APP_DIR, VENV_DIR


@pytest.fixture
def shadow():
    s = ShadowSandbox()
    yield s
    s.cleanup()


class TestShadowSandboxCreate:
    def test_initial_state(self, shadow):
        assert shadow.status == "IDLE"
        assert shadow.shadow_dir is None
        assert shadow._proposed_changes == []
        assert shadow._test_results is None

    def test_create_shadow(self, shadow):
        result = shadow.create_shadow()
        assert "Shadow created" in result
        assert shadow.status == "READY"
        assert shadow.shadow_dir is not None
        assert shadow.shadow_dir.exists()
        assert (shadow.shadow_dir / "backend").exists()

    def test_create_shadow_cleans_up_previous(self, shadow):
        shadow.create_shadow()
        first_dir = shadow.shadow_dir
        shadow.create_shadow()
        assert first_dir is not shadow.shadow_dir
        assert not first_dir.exists()

    def test_shadow_contains_backend_and_frontend(self, shadow):
        shadow.create_shadow()
        assert (shadow.shadow_dir / "backend" / "app").exists()
        assert (shadow.shadow_dir / "frontend" / "index.html").exists()

    def test_shadow_ignores_pycache(self, shadow):
        shadow.create_shadow()
        pycache_dirs = list(shadow.shadow_dir.rglob("__pycache__"))
        assert len(pycache_dirs) == 0


class TestShadowSandboxApplyChange:
    def test_apply_change_no_shadow(self, shadow):
        result = shadow.apply_change("file.py", "content")
        assert "No shadow" in result

    def test_apply_change_absolute_path(self, shadow):
        shadow.create_shadow()
        result = shadow.apply_change("/absolute/path.py", "content")
        assert "relative paths" in result

    def test_apply_change_backend_prefix(self, shadow):
        shadow.create_shadow()
        result = shadow.apply_change("backend/app/main.py", "new content")
        assert "Applied" in result

    def test_apply_change_no_prefix(self, shadow):
        shadow.create_shadow()
        result = shadow.apply_change("app/main.py", "new content")
        assert "Applied" in result

    def test_apply_change_frontend_prefix(self, shadow):
        shadow.create_shadow()
        result = shadow.apply_change("frontend/index.html", "new content")
        assert "Applied" in result

    def test_apply_change_tracks_proposed(self, shadow):
        shadow.create_shadow()
        shadow.apply_change("file.py", "content")
        assert len(shadow._proposed_changes) == 1

    def test_apply_change_writes_file(self, shadow):
        shadow.create_shadow()
        shadow.apply_change("test_module.py", "x = 1")
        content = (shadow.shadow_dir / "backend" / "test_module.py").read_text()
        assert content == "x = 1"


class TestShadowSandboxRunTests:
    def test_run_tests_no_shadow(self, shadow):
        results = shadow.run_tests()
        assert results["status"] == "FAILED"
        assert "No shadow" in results.get("error", "")

    def test_run_tests_success(self, shadow):
        shadow.create_shadow()
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "test_sandbox.py PASSED\n1 passed"
            mock_result.stderr = ""
            mock_result.returncode = 0
            mock_run.return_value = mock_result
            results = shadow.run_tests(timeout=30)
            assert results["status"] == "PASSED"
            assert shadow.status == "READY"

    def test_run_tests_failure(self, shadow):
        shadow.create_shadow()
        with patch("subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.stdout = "test_sandbox.py FAILED\n1 failed"
            mock_result.stderr = ""
            mock_result.returncode = 1
            mock_run.return_value = mock_result
            results = shadow.run_tests(timeout=30)
            assert results["status"] == "FAILED"
            assert shadow.status == "FAILED"

    def test_run_tests_timeout(self, shadow):
        shadow.create_shadow()
        with patch("subprocess.run") as mock_run:
            import subprocess
            mock_run.side_effect = subprocess.TimeoutExpired("pytest", 30)
            results = shadow.run_tests(timeout=30)
            assert results["status"] == "TIMEOUT"


class TestShadowSandboxDeploy:
    def test_deploy_no_changes(self, shadow):
        shadow.create_shadow()
        result = shadow.deploy_to_live()
        assert "No changes" in result

    def test_deploy_without_tests(self, shadow):
        shadow.create_shadow()
        shadow.apply_change("file.py", "x = 1")
        result = shadow.deploy_to_live()
        assert "Tests must pass" in result

    def test_deploy_success(self, shadow):
        shadow.create_shadow()
        shadow.apply_change("test_deploy_file.txt", "deployed content")
        shadow._test_results = {"status": "PASSED", "tests_run": 1, "passed": 1, "failed": 0}
        with patch("shutil.copy2") as mock_copy:
            result = shadow.deploy_to_live()
            assert "Deployed" in result
            mock_copy.assert_called_once()

    def test_deploy_updates_status(self, shadow):
        shadow.create_shadow()
        shadow.apply_change("file.txt", "x")
        shadow._test_results = {"status": "PASSED"}
        with patch("shutil.copy2"):
            shadow.deploy_to_live()
            assert shadow.status == "DEPLOYED"


class TestShadowSandboxCleanup:
    def test_cleanup(self, shadow):
        shadow.create_shadow()
        shadow_dir = shadow.shadow_dir
        shadow.cleanup()
        assert shadow.status == "IDLE"
        assert shadow.shadow_dir is None
        assert not shadow_dir.exists()

    def test_cleanup_idle(self, shadow):
        shadow.cleanup()
        assert shadow.status == "IDLE"


class TestShadowSandboxStatus:
    def test_status_report_idle(self, shadow):
        report = shadow.status_report()
        assert report["status"] == "IDLE"
        assert report["proposed_changes"] == 0

    def test_status_report_after_create(self, shadow):
        shadow.create_shadow()
        report = shadow.status_report()
        assert report["status"] == "READY"
        assert report["shadow_dir"] is not None


class TestShadowSandboxParseErrors:
    def test_parse_test_errors(self, shadow):
        output = "FAILED test_a\nERROR test_b\nPASSED test_c"
        errors = shadow._parse_test_errors(output)
        assert "FAILED test_a" in errors
        assert "ERROR test_b" in errors
        assert "PASSED test_c" not in errors

    def test_parse_test_errors_all(self, shadow):
        output = "\n".join([f"FAILED test_{i}" for i in range(50)])
        errors = shadow._parse_test_errors(output)
        assert len(errors) == 50


class TestShadowSandboxSingleton:
    def test_get_shadow_sandbox(self):
        from app.self_dev import get_shadow_sandbox
        s1 = get_shadow_sandbox()
        s2 = get_shadow_sandbox()
        assert s1 is s2
