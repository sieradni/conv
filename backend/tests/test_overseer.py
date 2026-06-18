import pytest
import json
import os
import tempfile
from unittest.mock import MagicMock, AsyncMock, patch
from app.overseer import OverseerAgent


@pytest.fixture
def overseer():
    return OverseerAgent(api_url="http://test:1234/v1")


class TestOverseerInitialization:
    @pytest.mark.asyncio
    async def test_initialize_success(self, overseer):
        with patch.object(overseer.lm_client, "get_models", new=AsyncMock()) as mock_get:
            mock_get.return_value = {"data": [{"id": "test-model"}]}
            await overseer.initialize()
            assert overseer.model_name == "test-model"

    @pytest.mark.asyncio
    async def test_initialize_no_models(self, overseer):
        with patch.object(overseer.lm_client, "get_models", new=AsyncMock()) as mock_get:
            mock_get.return_value = {"data": []}
            await overseer.initialize()
            assert overseer.model_name is None

    @pytest.mark.asyncio
    async def test_initialize_no_data_key(self, overseer):
        with patch.object(overseer.lm_client, "get_models", new=AsyncMock()) as mock_get:
            mock_get.return_value = {}
            await overseer.initialize()
            assert overseer.model_name is None

    @pytest.mark.asyncio
    async def test_initialize_request_failure(self, overseer):
        with patch.object(overseer.lm_client, "get_models", new=AsyncMock()) as mock_get:
            mock_get.return_value = None
            await overseer.initialize()
            assert overseer.model_name is None


class TestOverseerReviewAction:
    @pytest.mark.asyncio
    async def test_review_approved(self, overseer):
        overseer.model_name = "test-model"
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "status": "APPROVED",
                        "reasoning": "Looks safe",
                        "feedback": ""
                    })
                }
            }]
        }
        with patch.object(overseer.lm_client, "chat_completion", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = mock_response
            result = await overseer.review_action("read_file", {"path": "test.txt"}, "Read a file")
            assert result["status"] == "APPROVED"
            assert result["reasoning"] == "Looks safe"

    @pytest.mark.asyncio
    async def test_review_rejected(self, overseer):
        overseer.model_name = "test-model"
        mock_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "status": "REJECTED",
                        "reasoning": "Security risk",
                        "feedback": "Don't do that"
                    })
                }
            }]
        }
        with patch.object(overseer.lm_client, "chat_completion", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = mock_response
            result = await overseer.review_action("write_file", {"path": "/etc/passwd"}, "Write to system")
            assert result["status"] == "REJECTED"

    @pytest.mark.asyncio
    async def test_review_unparseable_response(self, overseer):
        overseer.model_name = "test-model"
        mock_response = {
            "choices": [{
                "message": {
                    "content": "This is not JSON at all"
                }
            }]
        }
        with patch.object(overseer.lm_client, "chat_completion", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = mock_response
            result = await overseer.review_action("read_file", {}, "")
            assert result["status"] == "REJECTED"
            assert "unparseable" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_review_json_in_code_block(self, overseer):
        overseer.model_name = "test-model"
        mock_response = {
            "choices": [{
                "message": {
                    "content": '```json\n{"status": "APPROVED", "reasoning": "ok", "feedback": ""}\n```'
                }
            }]
        }
        with patch.object(overseer.lm_client, "chat_completion", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = mock_response
            result = await overseer.review_action("read_file", {}, "")
            assert result["status"] == "APPROVED"

    @pytest.mark.asyncio
    async def test_review_no_response(self, overseer):
        overseer.model_name = "test-model"
        with patch.object(overseer.lm_client, "chat_completion", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = None
            result = await overseer.review_action("read_file", {}, "")
            assert result["status"] == "REJECTED"
            assert "failed to respond" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_review_auto_initialize(self, overseer):
        overseer.model_name = None
        with patch.object(overseer.lm_client, "get_models", new=AsyncMock()) as mock_get:
            mock_get.return_value = {"data": [{"id": "test-model"}]}
            with patch.object(overseer.lm_client, "chat_completion", new=AsyncMock()) as mock_chat:
                mock_chat.return_value = {
                    "choices": [{"message": {"content": json.dumps({"status": "APPROVED", "reasoning": "ok", "feedback": ""})}}]
                }
                result = await overseer.review_action("read_file", {}, "")
                assert result["status"] == "APPROVED"

    @pytest.mark.asyncio
    async def test_review_init_failure(self, overseer):
        overseer.model_name = None
        with patch.object(overseer.lm_client, "get_models", new=AsyncMock()) as mock_get:
            mock_get.return_value = None
            result = await overseer.review_action("read_file", {}, "")
            assert result["status"] == "REJECTED"
            assert "not initialized" in result["reasoning"]


class TestOverseerReadSandboxFile:
    def test_read_within_sandbox(self, overseer):
        with tempfile.TemporaryDirectory() as tmp:
            file_path = os.path.join(tmp, "test.txt")
            with open(file_path, "w") as f:
                f.write("hello")
            content = overseer._read_sandbox_file_sync(tmp, "test.txt")
            assert content == "hello"

    def test_read_traversal_blocked(self, overseer):
        with tempfile.TemporaryDirectory() as tmp:
            result = overseer._read_sandbox_file_sync(tmp, "../etc/passwd")
            assert "blocked" in result

    def test_read_nonexistent_file(self, overseer):
        with tempfile.TemporaryDirectory() as tmp:
            result = overseer._read_sandbox_file_sync(tmp, "missing.txt")
            assert "not found" in result

    def test_read_empty_path(self, overseer):
        with tempfile.TemporaryDirectory() as tmp:
            result = overseer._read_sandbox_file_sync(tmp, "")
            assert "not found" in result or "blocked" in result


class TestOverseerAskOverseer:
    @pytest.mark.asyncio
    async def test_ask_overseer_success(self, overseer):
        overseer.model_name = "test-model"
        with patch.object(overseer.lm_client, "chat_completion", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = {
                "choices": [{"message": {"content": "Here is my analysis."}}]
            }
            result = await overseer.ask_overseer("Is this safe?")
            assert "Here is my analysis" in result

    @pytest.mark.asyncio
    async def test_ask_overseer_no_response(self, overseer):
        overseer.model_name = "test-model"
        with patch.object(overseer.lm_client, "chat_completion", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = None
            result = await overseer.ask_overseer("Question?")
            assert "failed to respond" in result

    @pytest.mark.asyncio
    async def test_ask_overseer_auto_initialize(self, overseer):
        overseer.model_name = None
        with patch.object(overseer.lm_client, "get_models", new=AsyncMock()) as mock_get:
            mock_get.return_value = {"data": [{"id": "test-model"}]}
            with patch.object(overseer.lm_client, "chat_completion", new=AsyncMock()) as mock_chat:
                mock_chat.return_value = {
                    "choices": [{"message": {"content": "Analysis result"}}]
                }
                result = await overseer.ask_overseer("Question?")
                assert "Analysis" in result


# Helper: synchronous wrapper for testing _read_sandbox_file
def _read_sandbox_file_sync(self, sandbox_dir, path):
    import asyncio
    return asyncio.run(self._read_sandbox_file(sandbox_dir, path))


OverseerAgent._read_sandbox_file_sync = _read_sandbox_file_sync
