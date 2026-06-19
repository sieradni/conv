import pytest
from unittest.mock import MagicMock, AsyncMock


@pytest.fixture
def cm():
    from app.core.events import ConnectionManager
    return ConnectionManager()


def _mock_ws():
    ws = MagicMock()
    ws.send_json = AsyncMock()
    ws.accept = AsyncMock()  # connect() calls await websocket.accept()
    return ws


class TestConnectionManager:
    async def test_connect_global(self, cm):
        ws = _mock_ws()
        await cm.connect(ws)
        assert ws in cm._global

    async def test_connect_with_session(self, cm):
        ws = _mock_ws()
        await cm.connect(ws, session_id="sess1")
        assert ws in cm._global
        assert ws in cm._by_session["sess1"]

    async def test_disconnect_global(self, cm):
        ws = _mock_ws()
        await cm.connect(ws)
        cm.disconnect(ws)
        assert ws not in cm._global

    async def test_disconnect_with_session(self, cm):
        ws = _mock_ws()
        await cm.connect(ws, session_id="sess1")
        cm.disconnect(ws, session_id="sess1")
        assert ws not in cm._by_session.get("sess1", [])

    async def test_broadcast_global_sends_to_all(self, cm):
        ws1, ws2 = _mock_ws(), _mock_ws()
        await cm.connect(ws1)
        await cm.connect(ws2)
        await cm.broadcast({"type": "ping"})
        ws1.send_json.assert_awaited_once_with({"type": "ping"})
        ws2.send_json.assert_awaited_once_with({"type": "ping"})

    async def test_broadcast_removes_dead_connections(self, cm):
        ws = _mock_ws()
        ws.send_json = AsyncMock(side_effect=Exception("disconnected"))
        await cm.connect(ws)
        await cm.broadcast({"type": "test"})
        assert ws not in cm._global

    async def test_broadcast_to_session_only(self, cm):
        ws1, ws2 = _mock_ws(), _mock_ws()
        await cm.connect(ws1, session_id="s1")
        await cm.connect(ws2)
        await cm.broadcast_to_session({"type": "s1only"}, "s1")
        ws1.send_json.assert_awaited_once_with({"type": "s1only"})
        ws2.send_json.assert_not_awaited()

    async def test_broadcast_to_session_nonexistent(self, cm):
        await cm.broadcast_to_session({"type": "x"}, "nonexistent")
        # Should not raise

    async def test_broadcast_session_removes_dead(self, cm):
        ws = _mock_ws()
        ws.send_json = AsyncMock(side_effect=Exception("dead"))
        await cm.connect(ws, session_id="s1")
        await cm.broadcast_to_session({"type": "t"}, "s1")
        assert ws not in cm._by_session.get("s1", [])
