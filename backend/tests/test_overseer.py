import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from app.services.overseer import OverseerAgent


@pytest.fixture
def overseer():
    return OverseerAgent()


class TestOverseerInitialization:
    @pytest.mark.asyncio
    async def test_initialize_success_loaded_llm(self, overseer):
        with patch.object(overseer.lm_client, "get_models_v2", new=AsyncMock()) as mock_get:
            mock_get.return_value = {
                "models": [
                    {"key": "unloaded-model", "type": "embedding"},
                    {"key": "llama-3", "type": "llm", "loaded_instances": [{"id": "llama-3-instance"}]},
                ]
            }
            await overseer.initialize()
            assert overseer.model_name == "llama-3-instance"

    @pytest.mark.asyncio
    async def test_initialize_fallback_unloaded_llm(self, overseer):
        with patch.object(overseer.lm_client, "get_models_v2", new=AsyncMock()) as mock_get:
            mock_get.return_value = {
                "models": [
                    {"key": "llama-3", "type": "llm"},
                ]
            }
            await overseer.initialize()
            assert overseer.model_name == "llama-3"

    @pytest.mark.asyncio
    async def test_initialize_legacy_fallback(self, overseer):
        with patch.object(overseer.lm_client, "get_models_v2", new=AsyncMock()) as mock_get, \
             patch.object(overseer.lm_client, "get_models_legacy", new=AsyncMock()) as mock_legacy:
            mock_get.return_value = {}
            mock_legacy.return_value = {"data": [{"id": "legacy-model"}]}
            await overseer.initialize()
            assert overseer.model_name == "legacy-model"

    @pytest.mark.asyncio
    async def test_initialize_no_models(self, overseer):
        with patch.object(overseer.lm_client, "get_models_v2", new=AsyncMock()) as mock_get, \
             patch.object(overseer.lm_client, "get_models_legacy", new=AsyncMock()) as mock_legacy:
            mock_get.return_value = {"models": []}
            mock_legacy.return_value = {"data": []}
            await overseer.initialize()
            assert overseer.model_name is None


class TestOverseerReviewAction:
    @pytest.mark.asyncio
    async def test_review_approved(self, overseer):
        overseer.model_name = "test-model"
        mock_response = {
            "output": [{"type": "message", "content": json.dumps({
                "status": "APPROVED",
                "reasoning": "Looks safe",
                "feedback": ""
            })}],
            "stats": {"tokens": 10},
        }
        with patch.object(overseer.lm_client, "chat_completion_v2", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = mock_response
            result = await overseer.review_action("read_file", {"path": "test.txt"}, "Read a file")
            assert result["status"] == "APPROVED"
            assert result["reasoning"] == "Looks safe"

    @pytest.mark.asyncio
    async def test_review_rejected(self, overseer):
        overseer.model_name = "test-model"
        mock_response = {
            "output": [{"type": "message", "content": json.dumps({
                "status": "REJECTED",
                "reasoning": "Security risk",
                "feedback": "Don't do that"
            })}],
        }
        with patch.object(overseer.lm_client, "chat_completion_v2", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = mock_response
            result = await overseer.review_action("write_file", {"path": "/etc/passwd"}, "Write to system")
            assert result["status"] == "REJECTED"

    @pytest.mark.asyncio
    async def test_review_unparseable_response(self, overseer):
        overseer.model_name = "test-model"
        mock_response = {
            "output": [{"type": "message", "content": "This is not JSON at all"}],
        }
        with patch.object(overseer.lm_client, "chat_completion_v2", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = mock_response
            result = await overseer.review_action("read_file", {}, "")
            assert result["status"] == "REJECTED"
            assert "unparseable" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_review_json_in_code_block(self, overseer):
        overseer.model_name = "test-model"
        mock_response = {
            "output": [{"type": "message", "content": '```json\n{"status": "APPROVED", "reasoning": "ok", "feedback": ""}\n```'}],
        }
        with patch.object(overseer.lm_client, "chat_completion_v2", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = mock_response
            result = await overseer.review_action("read_file", {}, "")
            assert result["status"] == "APPROVED"

    @pytest.mark.asyncio
    async def test_review_no_response(self, overseer):
        overseer.model_name = "test-model"
        with patch.object(overseer.lm_client, "chat_completion_v2", new=AsyncMock()) as mock_chat:
            mock_chat.return_value = None
            result = await overseer.review_action("read_file", {}, "")
            assert result["status"] == "REJECTED"
            assert "failed to respond" in result["reasoning"]

    @pytest.mark.asyncio
    async def test_review_auto_initialize(self, overseer):
        overseer.model_name = None
        with patch.object(overseer.lm_client, "get_models_v2", new=AsyncMock()) as mock_get:
            mock_get.return_value = {
                "models": [{"key": "llama-3", "type": "llm", "loaded_instances": [{"id": "llama-3"}]}]
            }
            with patch.object(overseer.lm_client, "chat_completion_v2", new=AsyncMock()) as mock_chat:
                mock_chat.return_value = {
                    "output": [{"type": "message", "content": json.dumps({"status": "APPROVED", "reasoning": "ok", "feedback": ""})}]
                }
                result = await overseer.review_action("read_file", {}, "")
                assert result["status"] == "APPROVED"

    @pytest.mark.asyncio
    async def test_review_init_failure(self, overseer):
        overseer.model_name = None
        with patch.object(overseer.lm_client, "get_models_v2", new=AsyncMock()) as mock_get, \
             patch.object(overseer.lm_client, "get_models_legacy", new=AsyncMock()) as mock_legacy:
            mock_get.return_value = None
            mock_legacy.return_value = None
            result = await overseer.review_action("read_file", {}, "")
            assert result["status"] == "REJECTED"
            assert "not initialized" in result["reasoning"]


class TestOverseerReadSandboxFile:
    @pytest.mark.asyncio
    async def test_read_within_sandbox(self, overseer):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            file_path = os.path.join(tmp, "test.txt")
            with open(file_path, "w") as f:
                f.write("hello")
            content = await overseer._read_sandbox_file(tmp, "test.txt")
            assert content == "hello"

    @pytest.mark.asyncio
    async def test_read_traversal_blocked(self, overseer):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            result = await overseer._read_sandbox_file(tmp, "../etc/passwd")
            assert "blocked" in result

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, overseer):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            result = await overseer._read_sandbox_file(tmp, "missing.txt")
            assert "not found" in result

    @pytest.mark.asyncio
    async def test_read_empty_path(self, overseer):
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            result = await overseer._read_sandbox_file(tmp, "")
            assert "not found" in result or "blocked" in result
