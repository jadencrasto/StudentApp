import pytest
from httpx import AsyncClient
import io
from app.config import Settings


# ── 1. Password Strength Validation ───────────────────────────────────

class TestPasswordStrength:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("weak_pass,reason", [
        ("short1", "under 8 chars"),
        ("allletterslong", "no numbers"),
        ("1234567890", "no letters"),
        ("      1a", "whitespace padded under 8 valid chars"),
    ])
    async def test_weak_passwords_rejected(self, client: AsyncClient, weak_pass, reason):
        resp = await client.post("/api/v1/auth/register", json={
            "email": f"weak_{abs(hash(weak_pass))}@example.com",
            "username": f"user_{abs(hash(weak_pass))}"[:20],
            "password": weak_pass,
        })
        assert resp.status_code == 422, f"Expected 422 for password {reason}, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_strong_password_accepted(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "strong_pass_test@example.com",
            "username": "strong_user_ok",
            "password": "ValidPassword123",
        })
        assert resp.status_code == 201


# ── 2. Endpoint Lockdown (/extract) ───────────────────────────────────

class TestExtractEndpointSecurity:
    @pytest.mark.asyncio
    async def test_extract_without_token_returns_401(self, client: AsyncClient):
        files = {"file": ("test.txt", io.BytesIO(b"sample assignment text"), "text/plain")}
        resp = await client.post("/extract", files=files)
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"

    @pytest.mark.asyncio
    async def test_extract_with_token_authorized(self, client: AsyncClient, auth_headers):
        files = {"file": ("test.txt", io.BytesIO(b"Sample Assignment due Friday"), "text/plain")}
        resp = await client.post("/extract", files=files, headers=auth_headers)
        assert resp.status_code in (200, 422, 500)  # Reaches the endpoint logic, not rejected by auth


# ── 3. Upload File Size and Type Limits ───────────────────────────────

class TestUploadSecurityLimits:
    @pytest.mark.asyncio
    async def test_disallowed_file_type_rejected(self, client: AsyncClient, auth_headers):
        files = {"file": ("malicious.exe", io.BytesIO(b"MZ executable header"), "application/x-msdownload")}
        resp = await client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
        assert resp.status_code == 400
        assert "Unsupported file type" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_oversized_upload_rejected_with_413(self, client: AsyncClient, auth_headers):
        # 11MB payload (exceeds MAX_UPLOAD_SIZE_MB = 10)
        oversized_bytes = b"0" * (11 * 1024 * 1024)
        files = {"file": ("large.txt", io.BytesIO(oversized_bytes), "text/plain")}
        resp = await client.post("/api/v1/documents/upload", files=files, headers=auth_headers)
        assert resp.status_code == 413
        assert "File exceeds maximum upload size" in resp.json()["detail"]


# ── 4. Rate Limiting ──────────────────────────────────────────────────

class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_repeated_failed_logins_per_email_returns_429(self, client: AsyncClient, registered_user):
        email = registered_user["email"]
        # Make 5 failed attempts
        for _ in range(5):
            resp = await client.post("/api/v1/auth/login", json={
                "email": email,
                "password": "WrongPassword999",
            })
            assert resp.status_code == 401

        # The 6th attempt within the 60-second window must return 429
        locked_resp = await client.post("/api/v1/auth/login", json={
            "email": email,
            "password": "WrongPassword999",
        })
        assert locked_resp.status_code == 429
        assert "Too many failed login attempts" in locked_resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_auth_ip_rate_limiting_returns_429(self, client: AsyncClient):
        # 20 auth attempts allowed per minute per IP. 21st must return 429
        statuses = []
        for i in range(21):
            resp = await client.post("/api/v1/auth/login", json={
                "email": f"ip_test_{i}@example.com",
                "password": "WrongPass123",
            })
            statuses.append(resp.status_code)
        assert 429 in statuses


# ── 5. Security Headers ───────────────────────────────────────────────

class TestSecurityHeaders:
    @pytest.mark.asyncio
    async def test_security_headers_present_on_response(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert resp.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"


# ── 6. Secret Key Startup Validation ──────────────────────────────────

class TestSecretKeyValidation:
    def test_short_secret_key_rejected(self):
        with pytest.raises(Exception) as exc_info:
            Settings(
                SECRET_KEY="short-key",
                DATABASE_URL="sqlite+aiosqlite://",
            )
        assert "at least 32 characters" in str(exc_info.value)

    def test_placeholder_secret_key_rejected(self):
        with pytest.raises(Exception) as exc_info:
            Settings(
                SECRET_KEY="change-me-in-production-super-secret-key-32chars",
                DATABASE_URL="sqlite+aiosqlite://",
            )
        assert "placeholder" in str(exc_info.value)
