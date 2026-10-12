"""
Test (b): Register → Login → GET /auth/me flow.
Test (c): Protected endpoints return 401 without a token.
"""
import pytest


# ── (b) Full auth flow ───────────────────────────────────────────────

class TestAuthFlow:
    """Register a user, log in, and verify /auth/me."""

    @pytest.mark.asyncio
    async def test_register_creates_user(self, client):
        resp = await client.post("/api/v1/auth/register", json={
            "email": "authflow@example.com",
            "username": "authflow",
            "full_name": "Auth Flow",
            "password": "Passw0rd!123",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["email"] == "authflow@example.com"
        assert data["username"] == "authflow"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email_fails(self, client):
        payload = {
            "email": "dup@example.com",
            "username": "dup_user_1",
            "full_name": "Dup",
            "password": "Passw0rd!123",
        }
        resp1 = await client.post("/api/v1/auth/register", json=payload)
        assert resp1.status_code == 201

        payload["username"] = "dup_user_2"  # different username, same email
        resp2 = await client.post("/api/v1/auth/register", json=payload)
        assert resp2.status_code == 400

    @pytest.mark.asyncio
    async def test_login_returns_token(self, client, registered_user):
        resp = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["_password"],
        })
        assert resp.status_code == 200
        body = resp.json()
        assert "access_token" in body
        assert body["token_type"] == "bearer"

    @pytest.mark.asyncio
    async def test_login_wrong_password_fails(self, client, registered_user):
        resp = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": "WrongPassword999",
        })
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_get_me_with_valid_token(self, client, auth_headers, registered_user):
        resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        me = resp.json()
        assert me["email"] == registered_user["email"]
        assert me["username"] == registered_user["username"]


# ── (c) Protected endpoints return 401 without a token ───────────────

class TestProtectedEndpoints:
    """Every protected route should return 401/403 when no token is sent."""

    PROTECTED_ROUTES = [
        ("GET",    "/api/v1/auth/me"),
        ("GET",    "/api/v1/assignments"),
        ("POST",   "/api/v1/assignments"),
        ("GET",    "/api/v1/attendance/subjects"),
        ("POST",   "/api/v1/attendance/subjects"),
        ("POST",   "/api/v1/attendance/mark"),
        ("GET",    "/api/v1/attendance/summary"),
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("method,path", PROTECTED_ROUTES)
    async def test_no_token_returns_401_or_403(self, client, method, path):
        resp = await client.request(method, path)
        assert resp.status_code in (401, 403), (
            f"{method} {path} returned {resp.status_code} instead of 401/403"
        )
