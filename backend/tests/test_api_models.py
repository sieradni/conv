import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from pathlib import Path


@pytest.fixture(autouse=True)
def reset_state():
    from app.memory_graph import set_memory_graph, MemoryGraph
    from app.core.session import reset_conversation
    from app.core.config import SESSION_FILE
    import tempfile
    set_memory_graph(MemoryGraph(str(Path(tempfile.mkdtemp()) / "mem.json")))
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()
    reset_conversation()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


class TestModels:
    def test_list_models(self, client):
        resp = client.get("/api/models")
        assert resp.status_code == 200
        data = resp.json()
        assert "models" in data

    def test_get_active_model_no_model(self, client):
        resp = client.get("/api/models/active")
        assert resp.status_code == 200
        assert "model_instance_id" in resp.json()

    def test_load_model_invalid_body(self, client):
        resp = client.post("/api/models/load", json={})
        assert resp.status_code == 422  # Missing required 'model' field

    def test_get_active_model_after_set(self, client):
        resp = client.get("/api/models/active")
        assert resp.status_code == 200

    @patch("app.api.models.LMStudioClient")
    def test_load_model_unknown_model(self, mock_cls, client):
        mock_client = AsyncMock()
        mock_client.load_model.return_value = None
        mock_cls.return_value = mock_client
        resp = client.post("/api/models/load", json={"model": "nonexistent-model-xyz"})
        assert resp.status_code == 502
