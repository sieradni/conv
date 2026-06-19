import pytest
import json
from unittest.mock import patch
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "app"


@pytest.fixture(autouse=True)
def reset_state():
    from app.memory_graph import set_memory_graph, MemoryGraph
    from app.core.session import reset_conversation
    from app.core.events import manager
    import tempfile
    set_memory_graph(MemoryGraph(str(Path(tempfile.mkdtemp()) / "mem.json")))
    # Remove old session file so reset creates a fresh one
    from app.core.config import SESSION_FILE
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
    reset_conversation()
    manager._global.clear()
    manager._by_session.clear()
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


class TestSession:
    def test_get_session(self, client):
        resp = client.get("/api/session")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert "approval_mode" in data

    def test_delete_session(self, client):
        resp = client.delete("/api/session")
        assert resp.status_code == 200
        assert resp.json()["status"] == "reset"

    def test_session_history(self, client):
        resp = client.get("/api/session/history")
        assert resp.status_code == 200
        assert "history" in resp.json()

    def test_set_approval_mode(self, client):
        for mode in ["AUTO_APPROVE", "CHECK_WITH_OVERSEER", "WAIT_FOR_USER"]:
            resp = client.post("/api/session/approval-mode", json={"mode": mode})
            assert resp.status_code == 200
            assert resp.json()["approval_mode"] == mode

    def test_set_approval_mode_invalid(self, client):
        resp = client.post("/api/session/approval-mode", json={"mode": "INVALID"})
        assert resp.status_code == 400


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
        # Ensure clean state first
        from app.self_dev import get_shadow_sandbox
        get_shadow_sandbox().cleanup()
        resp = client.post("/api/self-dev/test")
        assert resp.status_code == 200
        assert resp.json()["status"] == "error"

    def test_self_dev_deploy_no_shadow(self, client):
        from app.self_dev import get_shadow_sandbox
        get_shadow_sandbox().cleanup()
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
            "start_time": 0.0, "end_time": 1700000000.0
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "started"


class TestApprovalEndpoint:
    def test_submit_approval(self, client):
        resp = client.post("/api/approve", json={"approved": True})
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"

    def test_submit_approval_rejected(self, client):
        resp = client.post("/api/approve", json={
            "approved": False, "feedback": "Not needed"
        })
        assert resp.status_code == 200
        assert resp.json()["status"] == "received"


class TestChat:
    def test_chat_send(self, client):
        resp = client.post("/api/chat/send", json={"message": "Hi"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_chat_stop(self, client):
        resp = client.post("/api/chat/stop", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] in ("stopped", "ok")

    def test_chat_pause(self, client):
        resp = client.post("/api/chat/pause", json={})
        assert resp.status_code == 200
        assert "paus" in resp.json()["status"].lower()

    def test_chat_resume(self, client):
        resp = client.post("/api/chat/resume", json={})
        assert resp.status_code == 200
        assert "resum" in resp.json()["status"].lower()

    def test_chat_message_creates_session(self, client):
        resp = client.get("/api/session")
        assert resp.status_code == 200
        assert "session_id" in resp.json()
