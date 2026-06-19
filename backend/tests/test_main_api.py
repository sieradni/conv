import pytest
import json
import time
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "app"


@pytest.fixture(autouse=True)
def reset_state():
    from app.memory_graph import set_memory_graph, MemoryGraph
    from app.session import registry, manager
    from app.self_dev import get_shadow_sandbox
    import tempfile
    set_memory_graph(MemoryGraph(str(Path(tempfile.mkdtemp()) / "mem.json")))
    registry._sessions.clear()
    manager._global.clear()
    manager._by_session.clear()
    shadow = get_shadow_sandbox()
    shadow.cleanup()
    todo_path = BASE / "todo.json"
    notes_path = BASE / "user_notes.md"
    todo_backup = todo_path.read_text(encoding="utf-8") if todo_path.exists() else None
    notes_backup = notes_path.read_text(encoding="utf-8") if notes_path.exists() else None
    if todo_path.exists():
        todo_path.unlink()
    if notes_path.exists():
        notes_path.unlink()
    yield
    if todo_backup is not None:
        todo_path.write_text(todo_backup, encoding="utf-8")
    elif todo_path.exists():
        todo_path.unlink()
    if notes_backup is not None:
        notes_path.write_text(notes_backup, encoding="utf-8")
    elif notes_path.exists():
        notes_path.unlink()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    import sys
    sys.path.insert(0, str(BASE.parent))
    from app.main import app
    return TestClient(app)


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_lm_status(self, client):
        resp = client.get("/api/lm/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data


class TestSessions:
    def test_create_session(self, client):
        resp = client.post("/api/session/create", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] is True
        assert len(data["session_id"]) == 8

    def test_create_session_with_approval_mode(self, client):
        resp = client.post("/api/session/create", json={"approval_mode": "AUTO_APPROVE"})
        assert resp.json()["approval_mode"] == "AUTO_APPROVE"

    def test_list_sessions(self, client):
        client.post("/api/session/create", json={})
        resp = client.get("/api/sessions")
        assert resp.status_code == 200
        assert len(resp.json()["sessions"]) >= 1

    def test_list_sessions_empty(self, client):
        resp = client.get("/api/sessions")
        assert resp.json()["sessions"] == []

    def test_delete_session(self, client):
        create_resp = client.post("/api/session/create", json={})
        sid = create_resp.json()["session_id"]
        resp = client.delete(f"/api/session/{sid}")
        assert resp.status_code == 200

    def test_session_info_found(self, client):
        create_resp = client.post("/api/session/create", json={})
        sid = create_resp.json()["session_id"]
        resp = client.get(f"/api/session/info?session_id={sid}")
        assert resp.status_code == 200
        assert resp.json()["session_id"] == sid

    def test_session_info_not_found(self, client):
        resp = client.get("/api/session/info?session_id=nonexistent")
        assert resp.status_code == 404

    def test_session_history(self, client):
        create_resp = client.post("/api/session/create", json={})
        sid = create_resp.json()["session_id"]
        resp = client.get(f"/api/session/{sid}/history")
        assert resp.status_code == 200
        assert "history" in resp.json()


class TestApprovalMode:
    @pytest.fixture(autouse=True)
    def setup_session(self, client):
        resp = client.post("/api/session/create", json={})
        self.sid = resp.json()["session_id"]

    def test_set_approval_mode(self, client):
        for mode in ["AUTO_APPROVE", "CHECK_WITH_OVERSEER", "WAIT_FOR_USER"]:
            resp = client.post("/api/session/approval-mode", json={
                "mode": mode, "session_id": self.sid
            })
            assert resp.status_code == 200
            assert resp.json()["approval_mode"] == mode

    def test_set_approval_mode_invalid(self, client):
        resp = client.post("/api/session/approval-mode", json={
            "mode": "INVALID", "session_id": self.sid
        })
        assert resp.status_code == 400

    def test_set_approval_mode_session_not_found(self, client):
        resp = client.post("/api/session/approval-mode", json={
            "mode": "AUTO_APPROVE", "session_id": "nonexistent"
        })
        assert resp.status_code == 404


class TestMemory:
    def test_get_memory(self, client):
        resp = client.get("/api/memory")
        assert resp.status_code == 200
        assert "nodes" in resp.json()
        assert "current_node_id" in resp.json()

    def test_get_state(self, client):
        resp = client.get("/api/state")
        assert resp.status_code == 200
        assert "memory" in resp.json()
        assert "rules" in resp.json()

    def test_optimize_memory(self, client):
        resp = client.post("/api/memory/optimize")
        assert resp.status_code == 200
        assert resp.json()["status"] == "optimized"


class TestNotes:
    def test_get_notes_default(self, client):
        resp = client.get("/api/notes")
        assert resp.status_code == 200
        assert "content" in resp.json()

    def test_update_notes(self, client):
        resp = client.put("/api/notes", json={"message": "# Updated Notes"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "updated"
        get_resp = client.get("/api/notes")
        assert "# Updated Notes" in get_resp.json()["content"]


class TestTodos:
    def test_get_todos_default(self, client):
        resp = client.get("/api/todos")
        assert resp.status_code == 200
        assert resp.json() == {"todo_items": [], "completed_items": []}

    def test_update_todos(self, client):
        resp = client.put("/api/todos", json={
            "message": json.dumps({"todo_items": ["task1"], "completed_items": []})
        })
        assert resp.status_code == 200
        get_resp = client.get("/api/todos")
        assert get_resp.json()["todo_items"] == ["task1"]


class TestSelfDev:
    def test_self_dev_init(self, client):
        resp = client.post("/api/self-dev/init")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_self_dev_propose(self, client):
        client.post("/api/self-dev/init")
        resp = client.post("/api/self-dev/propose", json={
            "file_path": "test.txt", "content": "hello"
        })
        assert resp.status_code == 200

    def test_self_dev_status_after_init(self, client):
        client.post("/api/self-dev/init")
        resp = client.get("/api/self-dev/status")
        assert resp.status_code == 200
        assert resp.json()["status"] in ("READY", "IDLE")

    def test_self_dev_test_no_shadow(self, client):
        resp = client.post("/api/self-dev/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_self_dev_deploy_no_shadow(self, client):
        resp = client.post("/api/self-dev/deploy")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("status") == "error" or "error" in data.get("message", "").lower()


class TestDiagnostics:
    def test_get_diagnostics_default(self, client):
        resp = client.get("/api/diagnostics")
        assert resp.status_code == 200
        assert "history" in resp.json()

    def test_record_diagnostics(self, client):
        resp = client.post("/api/diagnostics/record", json={
            "generation_time_s": 1.5,
            "tokens_per_second": 10.0,
            "token_count": 100,
        })
        assert resp.status_code == 200


class TestSleep:
    def test_sleep_context(self, client):
        resp = client.post("/api/sleep-context", json={
            "start_time": 0.0, "end_time": 0.0
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "generated"

    def test_sleep_flow(self, client):
        resp = client.post("/api/sleep-flow", json={
            "start_time": 0.0, "end_time": time.time()
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"


class TestApprovalEndpoint:
    def test_submit_approval_session_not_found(self, client):
        resp = client.post("/api/approve", json={
            "approved": True, "session_id": "nonexistent"
        })
        assert resp.status_code == 404

    def test_submit_approval(self, client):
        create_resp = client.post("/api/session/create", json={})
        sid = create_resp.json()["session_id"]
        resp = client.post("/api/approve", json={
            "approved": True, "session_id": sid
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"


class TestChat:
    def test_chat_send_no_session(self, client):
        resp = client.post("/api/chat/send", json={
            "message": "Hello", "session_id": "nonexistent"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_chat_send(self, client):
        create_resp = client.post("/api/session/create", json={})
        sid = create_resp.json()["session_id"]
        resp = client.post("/api/chat/send", json={
            "message": "Hi", "session_id": sid
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_chat_stop(self, client):
        create_resp = client.post("/api/session/create", json={})
        sid = create_resp.json()["session_id"]
        resp = client.post("/api/chat/stop", json={"session_id": sid})
        assert resp.status_code == 200
        assert resp.json()["status"] == "stopped"

    def test_chat_pause(self, client):
        create_resp = client.post("/api/session/create", json={})
        sid = create_resp.json()["session_id"]
        resp = client.post("/api/chat/pause", json={"session_id": sid})
        assert resp.status_code == 200
        assert resp.json()["status"] == "pausing"

    def test_chat_resume(self, client):
        create_resp = client.post("/api/session/create", json={})
        sid = create_resp.json()["session_id"]
        client.post("/api/chat/pause", json={"session_id": sid})
        resp = client.post("/api/chat/resume", json={"session_id": sid})
        assert resp.status_code == 200
        assert resp.json()["status"] == "resumed"

    def test_chat_message_creates_session(self, client):
        resp = client.post("/api/chat", json={
            "message": "What can you do?",
            "session_id": None,
        })
        assert resp.status_code == 200
        assert "session_id" in resp.json()
