"""
Tests for the fix-classroom branch:
  1. Naive/aware expiry conversion in oauth.py
  2. InvalidToken handling in oauth.py and classroom API endpoints
"""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from cryptography.fernet import InvalidToken
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _aware_utc(dt: datetime) -> datetime:
    """Attach UTC tzinfo to a naive datetime (simulates Postgres return)."""
    return dt.replace(tzinfo=timezone.utc)


def _naive_utc(dt: datetime) -> datetime:
    """Strip tzinfo from a datetime."""
    return dt.replace(tzinfo=None)


# ===========================================================================
# 1. Unit tests for _to_naive_utc / _to_aware_utc helpers
# ===========================================================================

class TestDatetimeConversion:
    """Ensure _to_naive_utc and _to_aware_utc handle all edge cases."""

    def test_to_naive_utc_from_aware(self):
        from app.classroom.oauth import _to_naive_utc
        aware = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = _to_naive_utc(aware)
        assert result.tzinfo is None
        assert result == datetime(2026, 6, 15, 12, 0, 0)

    def test_to_naive_utc_from_naive(self):
        from app.classroom.oauth import _to_naive_utc
        naive = datetime(2026, 6, 15, 12, 0, 0)
        result = _to_naive_utc(naive)
        assert result.tzinfo is None
        assert result == naive

    def test_to_naive_utc_from_none(self):
        from app.classroom.oauth import _to_naive_utc
        assert _to_naive_utc(None) is None

    def test_to_naive_utc_from_non_utc_timezone(self):
        from app.classroom.oauth import _to_naive_utc
        ist = timezone(timedelta(hours=5, minutes=30))
        aware_ist = datetime(2026, 6, 15, 17, 30, 0, tzinfo=ist)
        result = _to_naive_utc(aware_ist)
        assert result.tzinfo is None
        # IST 17:30 = UTC 12:00
        assert result == datetime(2026, 6, 15, 12, 0, 0)

    def test_to_aware_utc_from_naive(self):
        from app.classroom.oauth import _to_aware_utc
        naive = datetime(2026, 6, 15, 12, 0, 0)
        result = _to_aware_utc(naive)
        assert result.tzinfo == timezone.utc
        assert result == datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def test_to_aware_utc_from_aware(self):
        from app.classroom.oauth import _to_aware_utc
        aware = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        result = _to_aware_utc(aware)
        assert result.tzinfo == timezone.utc
        assert result == aware

    def test_to_aware_utc_from_none(self):
        from app.classroom.oauth import _to_aware_utc
        assert _to_aware_utc(None) is None


# ===========================================================================
# 2. _build_credentials must always pass naive UTC expiry to google-auth
# ===========================================================================

class TestBuildCredentials:
    """Verify that _build_credentials strips timezone before passing to Credentials."""

    def test_aware_expiry_becomes_naive(self):
        from app.classroom.oauth import _build_credentials
        aware_expiry = datetime(2026, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        creds = _build_credentials("token", "refresh", aware_expiry, None)
        # Credentials.expiry should be naive (google-auth compares with utcnow())
        assert creds.expiry is not None
        assert creds.expiry.tzinfo is None

    def test_naive_expiry_stays_naive(self):
        from app.classroom.oauth import _build_credentials
        naive_expiry = datetime(2026, 6, 15, 12, 0, 0)
        creds = _build_credentials("token", "refresh", naive_expiry, None)
        assert creds.expiry.tzinfo is None

    def test_none_expiry_stays_none(self):
        from app.classroom.oauth import _build_credentials
        creds = _build_credentials("token", "refresh", None, None)
        assert creds.expiry is None


# ===========================================================================
# 3. InvalidToken handling in get_valid_access_token
# ===========================================================================

class TestInvalidTokenHandling:
    """Verify that corrupted Fernet tokens produce a clear 403."""

    @pytest.mark.asyncio
    async def test_invalid_token_raises_403(self, db_session: AsyncSession):
        """When decrypt_secret raises InvalidToken, get_valid_access_token
        should raise HTTPException(403) with a reconnect message."""
        from app.models.integrations import GoogleToken
        from app.classroom.oauth import get_valid_access_token

        user_id = uuid.uuid4()
        record = GoogleToken(
            user_id=user_id,
            access_token="corrupted-cipher-text",
            refresh_token=None,
            expiry=None,
            scope="",
        )
        db_session.add(record)
        await db_session.flush()

        with patch("app.classroom.oauth.decrypt_secret", side_effect=InvalidToken):
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as exc_info:
                await get_valid_access_token(db_session, user_id)
            assert exc_info.value.status_code == 403
            assert "reconnect" in exc_info.value.detail.lower()


# ===========================================================================
# 4. API endpoint tests for InvalidToken
# ===========================================================================

class TestClassroomEndpointsInvalidToken:
    """Test that classroom API endpoints handle InvalidToken gracefully."""

    @pytest.mark.asyncio
    async def test_status_returns_not_connected_on_invalid_token(
        self, client: AsyncClient, auth_headers: dict, db_session: AsyncSession,
        registered_user: dict,
    ):
        """GET /classroom/status should return connected=False with error message
        when Fernet decryption fails."""
        from app.models.integrations import GoogleToken

        user_id = uuid.UUID(registered_user["id"])
        record = GoogleToken(
            user_id=user_id,
            access_token="bad-encrypted-data",
            refresh_token=None,
            expiry=None,
            scope="",
        )
        db_session.add(record)
        await db_session.flush()

        with patch("app.api.classroom.decrypt_secret", side_effect=InvalidToken):
            resp = await client.get("/api/v1/classroom/status", headers=auth_headers)

        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is False
        assert "reconnect" in data.get("error", "").lower()

    @pytest.mark.asyncio
    async def test_sync_returns_403_on_invalid_token(
        self, client: AsyncClient, auth_headers: dict,
    ):
        """GET /classroom/sync should return 403 when tokens can't be decrypted."""
        with patch("app.classroom.oauth.decrypt_secret", side_effect=InvalidToken):
            with patch("app.api.classroom.sync_all", side_effect=InvalidToken):
                resp = await client.get("/api/v1/classroom/sync", headers=auth_headers)

        assert resp.status_code == 403
        assert "reconnect" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_events_returns_403_on_invalid_token(
        self, client: AsyncClient, auth_headers: dict,
    ):
        """GET /classroom/events should return 403 when tokens can't be decrypted."""
        with patch("app.api.classroom.get_events", side_effect=InvalidToken):
            resp = await client.get("/api/v1/classroom/events", headers=auth_headers)

        assert resp.status_code == 403
        assert "reconnect" in resp.json()["detail"].lower()


# ===========================================================================
# 5. Expiry round-trip: store aware -> load -> build creds -> save after refresh
# ===========================================================================

class TestExpiryRoundTrip:
    """Simulate the full lifecycle of expiry through DB and google-auth."""

    def test_expired_check_works_with_aware_db_expiry(self):
        """Simulate: Postgres returns aware expiry, _build_credentials converts
        to naive, and Credentials.expired check doesn't crash."""
        from app.classroom.oauth import _build_credentials

        # Simulate an expired token from Postgres (aware UTC, in the past)
        past_aware = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        creds = _build_credentials("old-token", "refresh-token", past_aware, None)
        # This used to crash with TypeError: can't compare offset-naive and offset-aware
        assert creds.expired is True

    def test_valid_check_works_with_aware_db_expiry(self):
        """Same but with a future expiry — should not be expired."""
        from app.classroom.oauth import _build_credentials

        future_aware = datetime.now(timezone.utc) + timedelta(hours=1)
        creds = _build_credentials("fresh-token", "refresh-token", future_aware, None)
        assert creds.expired is False

    def test_refreshed_expiry_stored_as_aware(self):
        """After refresh, creds.expiry is naive UTC from google-auth.
        _to_aware_utc should make it aware for DB storage."""
        from app.classroom.oauth import _to_aware_utc

        # google-auth returns naive UTC after refresh
        naive_from_google = datetime(2026, 12, 25, 10, 0, 0)
        stored = _to_aware_utc(naive_from_google)
        assert stored.tzinfo == timezone.utc
        assert stored.year == 2026
        assert stored.month == 12
