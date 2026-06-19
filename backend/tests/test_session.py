import pytest
import asyncio
from app.session import Session, SessionRegistry, ConnectionManager


class TestSession:
    def test_session_initial_state(self):
        session = Session("test-1")
        assert session.session_id == "test-1"
        assert session.stop_requested is False
        assert session.pause_requested is False
        assert session.approval_mode == "WAIT_FOR_USER"
        assert session.chat_history == []
        assert session.sleep_mode is False
        assert session.current_goal == ""

    def test_session_touch_updates_active(self):
        session = Session("test-1")
        old = session.last_active_at
        session.touch()
        assert session.last_active_at >= old

    def test_session_to_dict(self):
        session = Session("test-1")
        d = session.to_dict()
        assert d["session_id"] == "test-1"
        assert d["stop_requested"] is False
        assert d["approval_mode"] == "WAIT_FOR_USER"

    def test_session_queues(self):
        session = Session("test-1")
        assert isinstance(session.user_response_queue, asyncio.Queue)
        assert isinstance(session.direct_talk_queue, asyncio.Queue)
        assert isinstance(session.resume_event, asyncio.Event)


class TestSessionRegistry:
    def test_create_session(self):
        registry = SessionRegistry()
        session = registry.create()
        assert session.session_id is not None
        assert len(session.session_id) == 8

    def test_get_existing_session(self):
        registry = SessionRegistry()
        created = registry.create()
        retrieved = registry.get(created.session_id)
        assert retrieved is created

    def test_get_nonexistent_session(self):
        registry = SessionRegistry()
        assert registry.get("nonexistent") is None

    def test_get_or_create_existing(self):
        registry = SessionRegistry()
        created = registry.create()
        result = registry.get_or_create(created.session_id)
        assert result is created

    def test_get_or_create_new(self):
        registry = SessionRegistry()
        result = registry.get_or_create("new-id")
        assert result.session_id is not None
        assert len(result.session_id) == 8

    def test_get_or_create_none(self):
        registry = SessionRegistry()
        result = registry.get_or_create(None)
        assert result.session_id is not None
        assert len(result.session_id) == 8

    def test_delete_session(self):
        registry = SessionRegistry()
        session = registry.create()
        registry.delete(session.session_id)
        assert registry.get(session.session_id) is None

    def test_delete_nonexistent(self):
        registry = SessionRegistry()
        registry.delete("nonexistent")

    def test_list_empty(self):
        registry = SessionRegistry()
        assert registry.list() == []

    def test_list_multiple(self):
        registry = SessionRegistry()
        s1 = registry.create()
        s2 = registry.create()
        sessions = registry.list()
        assert len(sessions) == 2
        ids = [s["session_id"] for s in sessions]
        assert s1.session_id in ids
        assert s2.session_id in ids


class TestConnectionManager:
    @pytest.mark.asyncio
    async def test_connect_disconnect_global(self):
        manager = ConnectionManager()
        mock_ws = MockWebSocket()
        await manager.connect(mock_ws)
        assert len(manager._global) == 1
        manager.disconnect(mock_ws)
        assert len(manager._global) == 0

    @pytest.mark.asyncio
    async def test_connect_with_session(self):
        manager = ConnectionManager()
        mock_ws = MockWebSocket()
        await manager.connect(mock_ws, session_id="sess-1")
        assert len(manager._global) == 1
        assert "sess-1" in manager._by_session
        assert len(manager._by_session["sess-1"]) == 1

    @pytest.mark.asyncio
    async def test_broadcast_global(self):
        manager = ConnectionManager()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await manager.connect(ws1)
        await manager.connect(ws2)
        await manager.broadcast({"type": "test"})
        assert ws1.sent == [{"type": "test"}]
        assert ws2.sent == [{"type": "test"}]

    @pytest.mark.asyncio
    async def test_broadcast_session_scoped(self):
        manager = ConnectionManager()
        ws_sess = MockWebSocket()
        ws_global = MockWebSocket()
        await manager.connect(ws_global)
        await manager.connect(ws_sess, session_id="sess-1")
        await manager.broadcast({"type": "session_msg"}, session_id="sess-1")
        assert ws_sess.sent == [{"type": "session_msg"}, {"type": "session_msg"}]
        assert ws_global.sent == [{"type": "session_msg"}]

    @pytest.mark.asyncio
    async def test_broadcast_to_session_only(self):
        manager = ConnectionManager()
        ws_sess = MockWebSocket()
        ws_other = MockWebSocket()
        await manager.connect(ws_other)
        await manager.connect(ws_sess, session_id="sess-1")
        await manager.broadcast_to_session({"type": "private"}, "sess-1")
        assert ws_sess.sent == [{"type": "private"}]
        assert ws_other.sent == []

    @pytest.mark.asyncio
    async def test_disconnect_removes_from_session(self):
        manager = ConnectionManager()
        ws = MockWebSocket()
        await manager.connect(ws, session_id="sess-1")
        manager.disconnect(ws, session_id="sess-1")
        assert ws not in manager._by_session.get("sess-1", [])

    @pytest.mark.asyncio
    async def test_broadcast_handles_dead_connections(self):
        manager = ConnectionManager()
        ws = MockWebSocket()
        ws.should_fail = True
        await manager.connect(ws)
        await manager.broadcast({"type": "test"})
        assert len(manager._global) == 0

    @pytest.mark.asyncio
    async def test_accept_called_on_connect(self):
        manager = ConnectionManager()
        ws = MockWebSocket()
        await manager.connect(ws)
        assert ws.accepted is True

    @pytest.mark.asyncio
    async def test_multiple_sessions_broadcast(self):
        manager = ConnectionManager()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await manager.connect(ws1, session_id="a")
        await manager.connect(ws2, session_id="b")
        await manager.broadcast({"type": "all"})
        assert ws1.sent == [{"type": "all"}]
        assert ws2.sent == [{"type": "all"}]


class MockWebSocket:
    def __init__(self):
        self.sent = []
        self.accepted = False
        self.should_fail = False

    async def accept(self):
        self.accepted = True

    async def send_json(self, data):
        if self.should_fail:
            raise Exception("Connection dead")
        self.sent.append(data)

    async def receive_text(self):
        return "{}"

    async def close(self):
        pass

    def __repr__(self):
        return "MockWebSocket()"
