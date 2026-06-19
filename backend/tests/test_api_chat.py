import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path
import json
import tempfile


@pytest.fixture(autouse=True)
def reset():
    from app.memory_graph import set_memory_graph, MemoryGraph
    from app.core.session import reset_conversation
    from app.core.config import SESSION_FILE
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
    set_memory_graph(None)
    reset_conversation()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


class TestSleepEndpoints:
    def test_sleep_start(self, client):
        resp = client.post("/api/chat/sleep-start", json={"message": "optimize"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sleep_started"

    def test_sleep_wake(self, client):
        resp = client.post("/api/chat/sleep-wake")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "sleep_ended"

    def test_sleep_start_no_message(self, client):
        resp = client.post("/api/chat/sleep-start", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "sleep_started"

    @patch("app.api.chat.get_active_chat_tasks")
    @patch("app.api.chat.manager")
    @patch("app.api.chat.run_agent_loop")
    def test_sleep_start_cancels_existing(self, mock_loop, mock_mgr, mock_tasks, client):
        from app.core.session import get_conversation
        conv = get_conversation()
        mock_loop.return_value = AsyncMock()
        mock_mgr.broadcast = AsyncMock()
        old_task = MagicMock()
        old_task.done.return_value = False
        mock_tasks.return_value = {conv.session_id: old_task}
        resp = client.post("/api/chat/sleep-start", json={"message": "work"})
        assert resp.status_code == 200
        old_task.cancel.assert_called_once()

    @patch("app.api.chat.get_active_chat_tasks")
    @patch("app.api.chat.manager")
    @patch("app.api.chat.run_agent_loop")
    def test_sleep_wake_cancels_existing(self, mock_loop, mock_mgr, mock_tasks, client):
        from app.core.session import get_conversation
        conv = get_conversation()
        mock_loop.return_value = AsyncMock()
        mock_mgr.broadcast = AsyncMock()
        old_task = MagicMock()
        old_task.done.return_value = False
        mock_tasks.return_value = {conv.session_id: old_task}
        resp = client.post("/api/chat/sleep-wake")
        assert resp.status_code == 200
        old_task.cancel.assert_called_once()

    def test_sleep_flow_endpoint(self, client):
        resp = client.post("/api/sleep-flow", json={"start_time": 0.0, "end_time": 100.0})
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"

    def test_sleep_context(self, client, tmp_path):
        from app.memory_graph import MemoryGraph, set_memory_graph
        mem_path = tmp_path / "mem.json"
        g = MemoryGraph(str(mem_path))
        g.create_memory("root content", is_root=True)
        set_memory_graph(g)
        resp = client.post("/api/sleep-context", json={"start_time": 0.0, "end_time": 9999999999.0})
        assert resp.status_code == 200
        assert resp.json()["status"] == "generated"
        assert "context" in resp.json()


class TestChatEndpoints:
    def test_chat_send(self, client):
        resp = client.post("/api/chat/send", json={"message": "hello"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_chat_send_empty(self, client):
        resp = client.post("/api/chat/send", json={"message": ""})
        assert resp.status_code == 200

    def test_chat_stop(self, client):
        resp = client.post("/api/chat/stop")
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    def test_chat_pause(self, client):
        resp = client.post("/api/chat/pause")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pausing"

    def test_chat_resume(self, client):
        resp = client.post("/api/chat/resume")
        assert resp.status_code == 200
        assert resp.json()["status"] == "resumed"

    def test_approve(self, client):
        resp = client.post("/api/approve", json={"approved": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"

    def test_approve_with_feedback(self, client):
        resp = client.post("/api/approve", json={"approved": False, "feedback": "no"})
        assert resp.status_code == 200


class TestToolsEndpoints:
    def test_get_todos_default(self, client):
        resp = client.get("/api/todos")
        assert resp.status_code == 200
        data = resp.json()
        assert data["todo_items"] == []
        assert data["completed_items"] == []

    def test_get_todos_with_file(self, client, tmp_path):
        from app.core.config import TODO_FILE
        todo = {"todo_items": ["task1"], "completed_items": []}
        TODO_FILE.write_text(json.dumps(todo))
        resp = client.get("/api/todos")
        assert resp.status_code == 200
        assert resp.json()["todo_items"] == ["task1"]

    def test_update_todos(self, client, tmp_path):
        from app.core.config import TODO_FILE
        TODO_FILE.write_text(json.dumps({"todo_items": [], "completed_items": []}))
        resp = client.put("/api/todos", json={"message": '{"todo_items": ["a"]}'})
        assert resp.status_code == 200
        data = json.loads(TODO_FILE.read_text())
        assert data["todo_items"] == ["a"]

    def test_get_diagnostics_default(self, client):
        from app.core.config import DIAG_FILE
        if DIAG_FILE.exists():
            DIAG_FILE.unlink()
        resp = client.get("/api/diagnostics")
        assert resp.status_code == 200
        assert resp.json()["history"] == []

    def test_record_diagnostics(self, client):
        resp = client.post("/api/diagnostics/record", json={
            "generation_time_s": 5.0,
            "tokens_per_second": 10.0,
            "token_count": 50,
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "recorded"

    def test_get_state(self, client):
        resp = client.get("/api/state")
        assert resp.status_code == 200
        data = resp.json()
        assert "memory" in data
        assert "rules" in data
