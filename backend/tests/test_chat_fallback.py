"""
Tests for AI Chat Fallback Model behavior (GEMINI_FALLBACK_MODEL).

Covers:
1. 503 on primary then fallback OK
2. 503 on primary then fallback 503 (friendly message, no crash)
3. Timeout on primary then straight to fallback OK (skip primary retry)
4. 429 on primary: no retry, no fallback, 5-minute cooldown set
5. Fallback 404 (retired) / setup error handled gracefully (friendly message, no crash)
6. Setting empty = old behaviour (primary retry once on 503, no fallback)
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from app.config import settings
from app.core.rate_limiter import quota_cooldown_tracker
from app.services.ai_provider import (
    AIConfigError,
    AIServiceUnavailableError,
    ai_provider,
)


@pytest.fixture(autouse=True)
def reset_cooldown():
    quota_cooldown_tracker.reset()
    yield
    quota_cooldown_tracker.reset()


@pytest.mark.asyncio
class TestChatFallbackModel:

    async def test_503_then_fallback_ok(self):
        """Primary returns 503 twice; fallback model is called once and succeeds."""
        calls = []

        def _mock_call(model_name: str) -> str:
            calls.append(model_name)
            if model_name == "gemini-3.8-flash":
                raise Exception("503 UNAVAILABLE: High demand on primary model")
            if model_name == "gemini-3.5-flash":
                return "Fallback answer from 3.5 flash"
            raise ValueError(f"Unexpected model: {model_name}")

        orig_primary = settings.GEMINI_MODEL
        orig_fallback = settings.GEMINI_FALLBACK_MODEL
        try:
            settings.GEMINI_MODEL = "gemini-3.8-flash"
            settings.GEMINI_FALLBACK_MODEL = "gemini-3.5-flash"

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await ai_provider._execute_chat_with_fallback(_mock_call)

            assert result == "Fallback answer from 3.5 flash"
            # Primary called twice (initial + 3s retry), then fallback called once
            assert calls == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-3.5-flash"]
            mock_sleep.assert_awaited_once_with(3.0)
        finally:
            settings.GEMINI_MODEL = orig_primary
            settings.GEMINI_FALLBACK_MODEL = orig_fallback

    async def test_503_then_fallback_503(self):
        """Primary returns 503 twice; fallback returns 503; friendly message returned."""
        calls = []

        def _mock_call(model_name: str) -> str:
            calls.append(model_name)
            raise Exception("503 UNAVAILABLE: Service overloaded")

        orig_primary = settings.GEMINI_MODEL
        orig_fallback = settings.GEMINI_FALLBACK_MODEL
        try:
            settings.GEMINI_MODEL = "gemini-3.8-flash"
            settings.GEMINI_FALLBACK_MODEL = "gemini-3.5-flash"

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(AIServiceUnavailableError) as exc_info:
                    await ai_provider._execute_chat_with_fallback(_mock_call)

            assert "Google's AI is busy right now. Please try again in a few minutes." in str(exc_info.value)
            assert "start from scratch" not in str(exc_info.value)
            # Primary called twice, fallback called once
            assert calls == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-3.5-flash"]
        finally:
            settings.GEMINI_MODEL = orig_primary
            settings.GEMINI_FALLBACK_MODEL = orig_fallback

    async def test_timeout_then_fallback_ok(self):
        """Timeout on primary model skips same-model retry and goes straight to fallback."""
        calls = []

        def _mock_call(model_name: str) -> str:
            calls.append(model_name)
            if model_name == "gemini-3.8-flash":
                # Simulate timeout
                raise asyncio.TimeoutError()
            return "Fallback answer after primary timeout"

        orig_primary = settings.GEMINI_MODEL
        orig_fallback = settings.GEMINI_FALLBACK_MODEL
        try:
            settings.GEMINI_MODEL = "gemini-3.8-flash"
            settings.GEMINI_FALLBACK_MODEL = "gemini-3.5-flash"

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                result = await ai_provider._execute_chat_with_fallback(_mock_call)

            assert result == "Fallback answer after primary timeout"
            # Primary called ONCE (no retry on timeout), fallback called ONCE
            assert calls == ["gemini-3.8-flash", "gemini-3.5-flash"]
            # Sleep was never called because retry was skipped
            mock_sleep.assert_not_called()
        finally:
            settings.GEMINI_MODEL = orig_primary
            settings.GEMINI_FALLBACK_MODEL = orig_fallback

    async def test_429_no_fallback_and_sets_cooldown(self):
        """429 daily quota never retries, never falls back, and triggers 5-minute cooldown."""
        calls = []

        def _mock_call(model_name: str) -> str:
            calls.append(model_name)
            raise Exception("429 RESOURCE_EXHAUSTED: Daily quota exceeded")

        orig_primary = settings.GEMINI_MODEL
        orig_fallback = settings.GEMINI_FALLBACK_MODEL
        try:
            settings.GEMINI_MODEL = "gemini-3.8-flash"
            settings.GEMINI_FALLBACK_MODEL = "gemini-3.5-flash"

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(AIServiceUnavailableError) as exc_info:
                    await ai_provider._execute_chat_with_fallback(_mock_call)

            assert "AI daily quota reached. Please try again tomorrow." in str(exc_info.value)
            # Exactly 1 call, never retried, never fallen back
            assert calls == ["gemini-3.8-flash"]
            mock_sleep.assert_not_called()
            # 5-minute cooldown must be active
            assert quota_cooldown_tracker.is_in_cooldown() is True
        finally:
            settings.GEMINI_MODEL = orig_primary
            settings.GEMINI_FALLBACK_MODEL = orig_fallback

    async def test_fallback_404_handled_gracefully(self):
        """Fallback returning 404 (retired model) is caught, logged, and returns friendly message."""
        calls = []

        def _mock_call(model_name: str) -> str:
            calls.append(model_name)
            if model_name == "gemini-3.8-flash":
                raise Exception("503 UNAVAILABLE: High demand")
            if model_name == "gemini-2.5-flash":
                # Model retired
                raise Exception("404 NOT_FOUND: models/gemini-2.5-flash is not found")
            raise ValueError(f"Unexpected model: {model_name}")

        orig_primary = settings.GEMINI_MODEL
        orig_fallback = settings.GEMINI_FALLBACK_MODEL
        try:
            settings.GEMINI_MODEL = "gemini-3.8-flash"
            settings.GEMINI_FALLBACK_MODEL = "gemini-2.5-flash"

            with patch("asyncio.sleep", new_callable=AsyncMock):
                with pytest.raises(AIServiceUnavailableError) as exc_info:
                    await ai_provider._execute_chat_with_fallback(_mock_call)

            assert "Google's AI is busy right now. Please try again in a few minutes." in str(exc_info.value)
            assert calls == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-2.5-flash"]
        finally:
            settings.GEMINI_MODEL = orig_primary
            settings.GEMINI_FALLBACK_MODEL = orig_fallback

    async def test_setting_empty_preserves_old_behaviour(self):
        """When GEMINI_FALLBACK_MODEL is empty, 503 retries primary once and then raises without fallback."""
        calls = []

        def _mock_call(model_name: str) -> str:
            calls.append(model_name)
            raise Exception("503 UNAVAILABLE: Overloaded")

        orig_primary = settings.GEMINI_MODEL
        orig_fallback = settings.GEMINI_FALLBACK_MODEL
        try:
            settings.GEMINI_MODEL = "gemini-3.8-flash"
            settings.GEMINI_FALLBACK_MODEL = ""

            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                with pytest.raises(AIServiceUnavailableError) as exc_info:
                    await ai_provider._execute_chat_with_fallback(_mock_call)

            assert "Google's AI is busy right now. Please try again in a few minutes." in str(exc_info.value)
            # Primary called twice, fallback NEVER called
            assert calls == ["gemini-3.8-flash", "gemini-3.8-flash"]
            mock_sleep.assert_awaited_once_with(3.0)
        finally:
            settings.GEMINI_MODEL = orig_primary
            settings.GEMINI_FALLBACK_MODEL = orig_fallback

    async def test_api_chat_endpoint_uses_fallback_model_on_503(
        self,
        client,
        auth_headers,
    ):
        """End-to-end test via /api/v1/chat/conversations/{id}/messages verifying fallback model is invoked."""
        conv_resp = await client.post(
            "/api/v1/chat/conversations",
            json={"mode": "general", "title": "Fallback Integration Chat"},
            headers=auth_headers,
        )
        assert conv_resp.status_code == 201
        conv_id = conv_resp.json()["id"]

        called_models = []

        def mock_generate_content(*args, **kwargs):
            model = kwargs.get("model")
            called_models.append(model)
            if model == "gemini-3.8-flash":
                raise Exception("503 UNAVAILABLE: High demand on primary")
            if model == "gemini-3.5-flash":
                mock_resp = MagicMock()
                mock_resp.text = "Hello from fallback 3.5 flash!"
                return mock_resp
            raise ValueError(f"Unknown model: {model}")

        orig_primary = settings.GEMINI_MODEL
        orig_fallback = settings.GEMINI_FALLBACK_MODEL
        try:
            settings.GEMINI_MODEL = "gemini-3.8-flash"
            settings.GEMINI_FALLBACK_MODEL = "gemini-3.5-flash"

            with patch("google.genai.Client") as mock_client_cls, patch("asyncio.sleep", new_callable=AsyncMock):
                mock_client = MagicMock()
                mock_client.models.generate_content.side_effect = mock_generate_content
                mock_client_cls.return_value = mock_client

                msg_resp = await client.post(
                    f"/api/v1/chat/conversations/{conv_id}/messages",
                    json={"message": "Can you help me?"},
                    headers=auth_headers,
                )

            assert msg_resp.status_code == 200, msg_resp.text
            data = msg_resp.json()
            assert data["role"] == "assistant"
            assert "Hello from fallback 3.5 flash!" in data["content"]
            assert called_models == ["gemini-3.8-flash", "gemini-3.8-flash", "gemini-3.5-flash"]
        finally:
            settings.GEMINI_MODEL = orig_primary
            settings.GEMINI_FALLBACK_MODEL = orig_fallback

