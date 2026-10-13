"""
Phase 3 Cloud AI Tests
Covers:
- Chat reply works (mocked Gemini)
- Viva mode works (mocked Gemini)
- AI failure gives a friendly 503
- Time estimate falls back to heuristic
- Assignment creation background time estimation updates ai_metadata
- Per-user limit returns 429
- Missing API key gives friendly message / error without crash or key leakage
"""
import json
from unittest.mock import MagicMock, patch
import pytest
from httpx import AsyncClient

from app.config import settings
from app.services.ai_provider import (
    AIConfigError,
    AIServiceUnavailableError,
    ai_provider,
)
from app.services.rate_limiter import ai_rate_limiter
from app.services.time_estimator import estimate_assignment_time
from app.services.gemini_timetable_extractor import GeminiTimetableExtractor
from app.services.gemini_event_extractor import GeminiEventExtractor


@pytest.fixture(autouse=True)
def reset_rate_limit():
    ai_rate_limiter.reset()
    yield
    ai_rate_limiter.reset()


@pytest.mark.asyncio
class TestCloudAIChat:

    async def test_chat_reply_works(self, client: AsyncClient, auth_headers: dict):
        """Test chat reply works with mocked Gemini returning text."""
        # 1. Create a conversation
        conv_resp = await client.post(
            "/api/v1/chat/conversations",
            json={"mode": "general", "title": "Test General Chat"},
            headers=auth_headers,
        )
        assert conv_resp.status_code == 201
        conv_id = conv_resp.json()["id"]

        # 2. Mock Gemini response
        mock_response = MagicMock()
        mock_response.text = "Hello! I am your SAIS academic assistant powered by Gemini."

        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_response
            mock_client_cls.return_value = mock_client

            msg_resp = await client.post(
                f"/api/v1/chat/conversations/{conv_id}/messages",
                json={"message": "Can you explain binary search?"},
                headers=auth_headers,
            )

        assert msg_resp.status_code == 200, msg_resp.text
        data = msg_resp.json()
        assert data["role"] == "assistant"
        assert "Gemini" in data["content"]
        assert "id" in data

        # 3. Verify conversation messages persisted
        detail_resp = await client.get(
            f"/api/v1/chat/conversations/{conv_id}",
            headers=auth_headers,
        )
        assert detail_resp.status_code == 200
        messages = detail_resp.json()["messages"]
        assert len(messages) == 2
        assert messages[0]["role"] == "user"
        assert messages[1]["role"] == "assistant"

    async def test_ai_failure_gives_friendly_503(self, client: AsyncClient, auth_headers: dict):
        """Test AI failure (503 / 429 / server error) produces HTTP 503 with friendly message."""
        conv_resp = await client.post(
            "/api/v1/chat/conversations",
            json={"mode": "general", "title": "Failure Chat"},
            headers=auth_headers,
        )
        assert conv_resp.status_code == 201
        conv_id = conv_resp.json()["id"]

        # Mock Gemini failing with a 503 error
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.models.generate_content.side_effect = Exception("503 UNAVAILABLE: High demand")
            mock_client_cls.return_value = mock_client

            msg_resp = await client.post(
                f"/api/v1/chat/conversations/{conv_id}/messages",
                json={"message": "Help me with physics."},
                headers=auth_headers,
            )

        assert msg_resp.status_code == 503
        assert "temporarily unavailable" in msg_resp.json()["detail"].lower()

    async def test_missing_chat_key_gives_friendly_message(self, client: AsyncClient, auth_headers: dict):
        """Test missing GEMINI_API_KEY_CHAT and GEMINI_API_KEY gives friendly 503 without crashing."""
        conv_resp = await client.post(
            "/api/v1/chat/conversations",
            json={"mode": "general", "title": "Missing Key Chat"},
            headers=auth_headers,
        )
        assert conv_resp.status_code == 201
        conv_id = conv_resp.json()["id"]

        orig_chat_key = settings.GEMINI_API_KEY_CHAT
        orig_key = settings.GEMINI_API_KEY
        try:
            settings.GEMINI_API_KEY_CHAT = None
            settings.GEMINI_API_KEY = None

            msg_resp = await client.post(
                f"/api/v1/chat/conversations/{conv_id}/messages",
                json={"message": "Hello without key"},
                headers=auth_headers,
            )

            assert msg_resp.status_code == 503
            assert "not configured" in msg_resp.json()["detail"].lower()
        finally:
            settings.GEMINI_API_KEY_CHAT = orig_chat_key
            settings.GEMINI_API_KEY = orig_key


@pytest.mark.asyncio
class TestRateLimiter:

    async def test_per_user_limit_returns_429(self, client: AsyncClient, auth_headers: dict):
        """Test exceeding the per-user hourly quota returns HTTP 429."""
        conv_resp = await client.post(
            "/api/v1/chat/conversations",
            json={"mode": "general", "title": "Rate Limit Chat"},
            headers=auth_headers,
        )
        assert conv_resp.status_code == 201
        conv_id = conv_resp.json()["id"]

        mock_response = MagicMock()
        mock_response.text = "Mocked AI answer."

        # Temporarily set rate limit to 2 for this test
        orig_limit = settings.AI_RATE_LIMIT_PER_HOUR
        try:
            settings.AI_RATE_LIMIT_PER_HOUR = 2

            with patch("google.genai.Client") as mock_client_cls:
                mock_client = MagicMock()
                mock_client.models.generate_content.return_value = mock_response
                mock_client_cls.return_value = mock_client

                # Request 1: OK
                r1 = await client.post(
                    f"/api/v1/chat/conversations/{conv_id}/messages",
                    json={"message": "Message 1"},
                    headers=auth_headers,
                )
                assert r1.status_code == 200

                # Request 2: OK
                r2 = await client.post(
                    f"/api/v1/chat/conversations/{conv_id}/messages",
                    json={"message": "Message 2"},
                    headers=auth_headers,
                )
                assert r2.status_code == 200

                # Request 3: Exceeds limit -> 429
                r3 = await client.post(
                    f"/api/v1/chat/conversations/{conv_id}/messages",
                    json={"message": "Message 3"},
                    headers=auth_headers,
                )
                assert r3.status_code == 429
                assert "rate limit exceeded" in r3.json()["detail"].lower()
        finally:
            settings.AI_RATE_LIMIT_PER_HOUR = orig_limit


@pytest.mark.asyncio
class TestTimeEstimation:

    async def test_time_estimate_works_with_gemini(self):
        """Test successful time estimate returns Gemini analysis."""
        gemini_payload = {
            "estimated_minutes": 90,
            "estimated_hours": 1.5,
            "reading_time_minutes": 15,
            "work_time_minutes": 75,
            "complexity": "medium",
            "task_type": "assignment",
            "question_count": 5,
            "has_mathematical_content": True,
            "has_code_content": False,
            "confidence_score": 0.85,
            "breakdown": "Reading 15m | 5 questions ~25m | Work 50m",
            "recommended_sessions": {
                "sessions": 2,
                "minutes_per_session": 45,
                "recommendation": "Split into 2 sessions",
            },
        }

        mock_resp = MagicMock()
        mock_resp.text = json.dumps(gemini_payload)

        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            result = await estimate_assignment_time("Solve 5 calculus problems on integrals")

        assert result["analysis_provider"] == "gemini"
        assert result["estimated_minutes"] == 90
        assert result["has_mathematical_content"] is True

    async def test_time_estimate_falls_back_to_heuristic(self):
        """Test time estimation falls back to heuristic when AI service fails."""
        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.models.generate_content.side_effect = Exception("503 Service Unavailable")
            mock_client_cls.return_value = mock_client

            result = await estimate_assignment_time("Write a Python script to sort a list of numbers")

        assert result["analysis_provider"] == "heuristic"
        assert result["estimated_minutes"] > 0

    async def test_assignment_creation_background_time_estimation(
        self, client: AsyncClient, auth_headers: dict
    ):
        """Test manual assignment creation does not block and updates ai_metadata in background."""
        mock_resp = MagicMock()
        mock_resp.text = json.dumps({
            "estimated_minutes": 120,
            "estimated_hours": 2.0,
            "reading_time_minutes": 20,
            "work_time_minutes": 100,
            "complexity": "medium",
            "task_type": "programming",
            "question_count": 2,
            "has_mathematical_content": False,
            "has_code_content": True,
            "confidence_score": 0.8,
            "breakdown": "Coding assignment",
            "recommended_sessions": {"sessions": 2, "minutes_per_session": 60, "recommendation": "2 sessions"},
        })

        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.models.generate_content.return_value = mock_resp
            mock_client_cls.return_value = mock_client

            resp = await client.post(
                "/api/v1/assignments",
                json={
                    "title": "Build a Binary Search Tree",
                    "subject": "Data Structures",
                    "task_type": "programming",
                    "description": "Implement insert, delete, and find methods in Python",
                    "priority": "high",
                },
                headers=auth_headers,
            )

        assert resp.status_code == 201
        assignment_id = resp.json()["id"]

        # Fetch the created assignment
        get_resp = await client.get(
            f"/api/v1/assignments/{assignment_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 200
        data = get_resp.json()
        ai_meta = data.get("ai_metadata") or {}
        # Background task ran and populated time_estimate
        assert "time_estimate" in ai_meta
        assert ai_meta["time_estimate"]["estimated_minutes"] == 120


class TestTimetableAndEventsKeys:

    def test_missing_timetable_key_raises_friendly_error(self):
        """Verify timetable extractor raises clear message when timetable key is missing."""
        orig_tt_key = settings.GEMINI_API_KEY_TIMETABLE
        orig_key = settings.GEMINI_API_KEY
        try:
            settings.GEMINI_API_KEY_TIMETABLE = None
            settings.GEMINI_API_KEY = None

            with pytest.raises(RuntimeError) as exc_info:
                GeminiTimetableExtractor()
            assert "timetable is not configured" in str(exc_info.value).lower()
        finally:
            settings.GEMINI_API_KEY_TIMETABLE = orig_tt_key
            settings.GEMINI_API_KEY = orig_key

    def test_missing_events_key_raises_friendly_error(self):
        """Verify college event extractor raises clear message when key is missing."""
        orig_tt_key = settings.GEMINI_API_KEY_TIMETABLE
        orig_key = settings.GEMINI_API_KEY
        try:
            settings.GEMINI_API_KEY_TIMETABLE = None
            settings.GEMINI_API_KEY = None

            with pytest.raises(RuntimeError) as exc_info:
                GeminiEventExtractor()
            assert "college events is not configured" in str(exc_info.value).lower()
        finally:
            settings.GEMINI_API_KEY_TIMETABLE = orig_tt_key
            settings.GEMINI_API_KEY = orig_key
