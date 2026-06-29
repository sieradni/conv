import pytest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch


@pytest.fixture(autouse=True)
def isolate_session_file():
    from app.core.config import SESSION_FILE
    original = SESSION_FILE
    tmp = Path(tempfile.mkstemp(suffix=".json")[1])
    # Patch SESSION_FILE so Conversation uses our temp file
    import app.core.session as sess_mod
    orig_file = sess_mod.SESSION_FILE
    sess_mod.SESSION_FILE = tmp
    yield tmp
    sess_mod.SESSION_FILE = orig_file
    if tmp.exists():
        tmp.unlink()


class TestConversation:
    def test_init_fresh_creates_session(self):
        from app.core.session import Conversation
        c = Conversation()
        assert c.session_id
        assert len(c.session_id) == 8
        assert c.chat_history == []
        assert c.current_goal == ""
        assert c.approval_mode == "WAIT_FOR_USER"
        assert c.created_at > 0

    def test_load_existing_session(self):
        from app.core.session import Conversation
        c1 = Conversation()
        sid = c1.session_id
        c2 = Conversation()
        assert c2.session_id == sid
        assert c2.chat_history == c1.chat_history

    def test_add_message(self):
        from app.core.session import Conversation
        c = Conversation()
        c.add_message("user", "hello")
        assert len(c.chat_history) == 1
        assert c.chat_history[0]["role"] == "user"
        assert c.chat_history[0]["content"] == "hello"

    def test_add_message_with_extra(self):
        from app.core.session import Conversation
        c = Conversation()
        c.add_message("user", "hello", tool_call=True)
        assert c.chat_history[0]["tool_call"] is True

    def test_get_context_messages_all(self):
        from app.core.session import Conversation
        c = Conversation()
        c.add_message("user", "m1")
        c.add_message("assistant", "m2")
        ctx = c.get_context_messages()
        assert len(ctx) == 2

    def test_get_context_messages_truncated(self):
        from app.core.session import Conversation
        c = Conversation()
        for i in range(10):
            c.add_message("user", f"msg{i}")
        ctx = c.get_context_messages(max_messages=3)
        assert len(ctx) == 3
        assert ctx[0]["content"] == "msg7"

    def test_get_context_messages_zero_returns_all(self):
        from app.core.session import Conversation
        c = Conversation()
        c.add_message("user", "m1")
        ctx = c.get_context_messages(max_messages=0)
        assert len(ctx) == 1

    def test_resume_event_property(self):
        from app.core.session import Conversation
        import asyncio
        c = Conversation()
        e = c.resume_event
        assert isinstance(e, asyncio.Event)
        assert c._resume_event is e
        # Same Event returned on second access
        assert c.resume_event is e

    def test_reset_flow_control(self):
        from app.core.session import Conversation
        c = Conversation()
        c.stop_requested = True
        c.pause_requested = True
        _ = c.resume_event
        c.reset_flow_control()
        assert c.stop_requested is False
        assert c.pause_requested is False
        assert c._resume_event is None

    def test_to_dict(self):
        from app.core.session import Conversation
        c = Conversation()
        d = c.to_dict()
        assert d["session_id"] == c.session_id
        assert d["message_count"] == 0
        assert d["approval_mode"] == "WAIT_FOR_USER"

    def test_save_and_reload_persists_data(self):
        from app.core.session import Conversation
        c1 = Conversation()
        c1.add_message("user", "persistent")
        c1.current_goal = "test goal"
        c1.approval_mode = "AUTO_APPROVE"
        c1._save()

        c2 = Conversation()
        assert c2.session_id == c1.session_id
        assert len(c2.chat_history) == 1
        assert c2.chat_history[0]["content"] == "persistent"
        assert c2.current_goal == "test goal"
        assert c2.approval_mode == "AUTO_APPROVE"

    def test_corrupted_file_falls_back_to_fresh(self):
        from app.core.session import Conversation
        from app.core.config import SESSION_FILE
        SESSION_FILE.write_text("{corrupted json", encoding="utf-8")
        c = Conversation()
        assert c.session_id
        assert c.chat_history == []

    def test_user_response_queue(self):
        from app.core.session import Conversation
        import asyncio
        c = Conversation()
        assert isinstance(c.user_response_queue, asyncio.Queue)

    def test_default_thinking_level(self):
        from app.core.session import Conversation
        c = Conversation()
        assert c.thinking_level == ""

    def test_set_thinking_level(self):
        from app.core.session import Conversation
        c = Conversation()
        c.set_thinking_level("high")
        assert c.thinking_level == "high"

    def test_set_thinking_level_persists(self):
        from app.core.session import Conversation, reset_conversation
        c1 = Conversation()
        c1.set_thinking_level("low")
        reset_conversation()
        c2 = Conversation()
        assert c2.thinking_level == "low"

    def test_set_thinking_level_invalid_raises(self):
        from app.core.session import Conversation
        c = Conversation()
        with pytest.raises(ValueError):
            c.set_thinking_level("invalid")

    def test_thinking_level_in_to_dict(self):
        from app.core.session import Conversation
        c = Conversation()
        c.set_thinking_level("low")
        d = c.to_dict()
        assert d["thinking_level"] == "low"


class TestGetConversation:
    def test_get_conversation_singleton(self):
        from app.core.session import get_conversation, reset_conversation
        reset_conversation()
        c1 = get_conversation()
        c2 = get_conversation()
        assert c1 is c2

    def test_reset_conversation_creates_new(self):
        from app.core.session import get_conversation, reset_conversation
        reset_conversation()
        c1 = get_conversation()
        reset_conversation()
        c2 = get_conversation()
        assert c1 is not c2
