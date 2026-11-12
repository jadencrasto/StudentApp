"""
Phase 8D Security Tests.
Covers:
  1. Pure httpOnly cookie authentication (no Authorization Bearer fallback).
  2. Token version ("ver") revocation working with cookie auth.
  3. Logout endpoint clearing auth cookie.
  4. CSRF protection: X-Requested-With required on all non-safe requests (POST, PUT, PATCH, DELETE).
  5. Security headers: X-Content-Type-Options, X-Frame-Options, Referrer-Policy, HSTS, CSP.
  6. Production startup gates: DEBUG=False, COOKIE_SECURE=True, strong SECRET_KEY.
  7. DNS rebinding protection: IPv4-mapped IPv6, multi-IP fail-closed, PinnedIPAdapter hostname validation.
  8. Google Classroom OAuth: atomic single-use state nonce and user match check.
  9. Rate limiter DB persistence with resilient fallback if DB is down.
  10. CORS: Authorization removed from allow_headers, allow_credentials enabled.
"""
import ssl
import uuid
from datetime import datetime, timezone
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, settings
from app.core.security import create_access_token
from app.models.user import User
from app.models.rate_limit import RateLimitEvent
from app.college_events.safe_scraper import (
    is_safe_ip,
    resolve_and_validate_hostname,
    PinnedIPAdapter,
)
from app.classroom.oauth import _state_token, _decode_state, exchange_code_and_store
from app.core.rate_limiter import (
    failed_login_tracker,
    join_attempt_tracker,
    ai_extraction_tracker,
    quota_cooldown_tracker,
    record_rate_limit_event,
)


@pytest.mark.asyncio
class TestCookieAuthentication:
    """Verify pure httpOnly cookie authentication and token version revocation."""

    async def test_cookie_auth_success(self, client: AsyncClient, registered_user: dict):
        """User can access protected endpoint with valid access_token cookie."""
        resp = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["_password"],
        })
        assert resp.status_code == 200
        # Verify access_token cookie is returned in Set-Cookie
        assert "access_token" in resp.cookies

        # Client automatically retains cookie
        me_resp = await client.get("/api/v1/auth/me")
        assert me_resp.status_code == 200
        assert me_resp.json()["email"] == registered_user["email"]

    async def test_missing_cookie_rejected_401(self, client: AsyncClient):
        """Request without access_token cookie returns 401."""
        client.cookies.clear()
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert "credentials" in resp.json()["detail"].lower()

    async def test_bearer_alone_rejected_without_cookie_fallback(self, client: AsyncClient, registered_user: dict):
        """
        Request with Authorization: Bearer <token> but no cookie is rejected with 401.
        Confirms no fallback to Authorization header exists on GET or POST.
        """
        token = create_access_token(registered_user["id"], token_version=0)
        client.cookies.clear()
        # X-No-Cookie-Bridge tells the event hook to skip Bearer→cookie bridging
        resp_get = await client.get(
            "/api/v1/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "X-No-Cookie-Bridge": "1",
            },
        )
        assert resp_get.status_code == 401

        # Also verify state-changing POST with Authorization alone gives 401
        resp_post = await client.post(
            "/api/v1/assignments",
            json={"title": "Test Assignment", "due_date": "2026-12-31T23:59:59"},
            headers={
                "Authorization": f"Bearer {token}",
                "X-No-Cookie-Bridge": "1",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        assert resp_post.status_code == 401

    async def test_token_version_revocation_with_cookie(
        self, client: AsyncClient, registered_user: dict, db_session: AsyncSession
    ):
        """Incrementing user's token_version immediately invalidates active cookie."""
        resp = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["_password"],
        })
        assert resp.status_code == 200

        # Before revocation: /auth/me works
        me_resp = await client.get("/api/v1/auth/me")
        assert me_resp.status_code == 200

        # Revoke session by bumping token_version
        user_res = await db_session.execute(
            select(User).where(User.id == uuid.UUID(registered_user["id"]))
        )
        db_user = user_res.scalar_one()
        db_user.token_version = (db_user.token_version or 0) + 1
        await db_session.commit()

        # After revocation: same cookie is now rejected with 401
        revoked_resp = await client.get("/api/v1/auth/me")
        assert revoked_resp.status_code == 401

    async def test_logout_clears_cookie(self, client: AsyncClient, registered_user: dict):
        """POST /auth/logout clears the access_token cookie."""
        await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["_password"],
        })
        assert "access_token" in client.cookies

        logout_resp = await client.post("/api/v1/auth/logout")
        assert logout_resp.status_code == 200
        assert logout_resp.json()["message"] == "Logged out successfully"

        # Cookie deleted / expired
        cookie_header = logout_resp.headers.get("set-cookie", "")
        assert 'access_token=""' in cookie_header or "Max-Age=0" in cookie_header


@pytest.mark.asyncio
class TestCSRFProtection:
    """Verify CSRF defense requiring X-Requested-With on all mutations."""

    async def test_post_without_csrf_header_rejected_403(self, client: AsyncClient):
        """POST without X-Requested-With header fails with 403."""
        resp = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@sais.edu", "password": "pass"},
            headers={"X-Requested-With": ""},  # Override default to empty
        )
        assert resp.status_code == 403
        assert "CSRF validation failed" in resp.json()["detail"]

    async def test_cookie_authenticated_post_without_csrf_header_gives_403(
        self, client: AsyncClient, registered_user: dict
    ):
        """A valid auth cookie cannot execute POST mutations without X-Requested-With header."""
        # 1. Log in to establish access_token cookie
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["_password"],
        })
        assert login_resp.status_code == 200
        assert "access_token" in client.cookies

        # 2. Make authenticated POST without X-Requested-With header
        mut_resp = await client.post(
            "/api/v1/assignments",
            json={"title": "CSRF Attack Attempt", "due_date": "2026-12-31T23:59:59"},
            headers={"X-Requested-With": ""},
        )
        assert mut_resp.status_code == 403
        assert "CSRF validation failed" in mut_resp.json()["detail"]

    async def test_put_without_csrf_header_rejected_403(self, client: AsyncClient):
        """PUT without X-Requested-With fails with 403."""
        resp = await client.put(
            "/api/v1/assignments/00000000-0000-0000-0000-000000000000",
            json={"title": "foo"},
            headers={"X-Requested-With": ""},
        )
        assert resp.status_code == 403

    async def test_delete_without_csrf_header_rejected_403(self, client: AsyncClient):
        """DELETE without X-Requested-With fails with 403."""
        resp = await client.delete(
            "/api/v1/assignments/00000000-0000-0000-0000-000000000000",
            headers={"X-Requested-With": ""},
        )
        assert resp.status_code == 403

    async def test_get_does_not_require_csrf_header(self, client: AsyncClient):
        """Safe methods (GET) do not require X-Requested-With."""
        resp = await client.get("/health", headers={"X-Requested-With": ""})
        assert resp.status_code == 200


@pytest.mark.asyncio
class TestSecurityHeadersAndCORS:
    """Verify security response headers and CORS headers."""

    async def test_security_headers_present(self, client: AsyncClient):
        """Check X-Content-Type-Options, X-Frame-Options, Referrer-Policy, and CSP."""
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.headers["X-Content-Type-Options"] == "nosniff"
        assert resp.headers["X-Frame-Options"] == "DENY"
        assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

        # CSP Report-Only by default
        csp_key = "Content-Security-Policy-Report-Only" if settings.CSP_REPORT_ONLY else "Content-Security-Policy"
        assert csp_key in resp.headers
        csp = resp.headers[csp_key]
        assert "default-src 'self'" in csp
        assert "script-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        # Verify no localhost in live rules and no supabase storage in img-src
        assert "localhost" not in csp
        assert "supabase" not in csp

    async def test_cors_configuration(self, client: AsyncClient):
        """CORS preflight checks allow_credentials and excludes Authorization from headers."""
        resp = await client.options(
            "/api/v1/auth/me",
            headers={
                "Origin": "http://127.0.0.1:5173",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "X-Requested-With",
            },
        )
        assert resp.status_code == 200
        assert resp.headers.get("access-control-allow-credentials") == "true"
        allowed_headers = resp.headers.get("access-control-allow-headers", "").lower()
        assert "authorization" not in allowed_headers
        assert "x-requested-with" in allowed_headers


class TestProductionStartupGates:
    """Verify strict startup validation in production mode."""

    def test_production_fails_if_debug_true(self):
        s = Settings(
            ENVIRONMENT="production",
            DEBUG=True,
            COOKIE_SECURE=True,
            SECRET_KEY="A" * 32,
        )
        with pytest.raises(RuntimeError, match="DEBUG is True"):
            s.validate_production_security()

    def test_production_fails_if_cookie_secure_false(self):
        s = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            COOKIE_SECURE=False,
            SECRET_KEY="A" * 32,
        )
        with pytest.raises(RuntimeError, match="COOKIE_SECURE is False"):
            s.validate_production_security()

    def test_production_fails_if_secret_key_short(self):
        s = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            COOKIE_SECURE=True,
            SECRET_KEY="A" * 32,
        )
        object.__setattr__(s, "SECRET_KEY", "too-short-key")
        with pytest.raises(RuntimeError, match="SECRET_KEY is default or weak"):
            s.validate_production_security()

    def test_production_fails_if_secret_key_is_known_default(self):
        s = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            COOKIE_SECURE=True,
            SECRET_KEY="A" * 32,
        )
        object.__setattr__(s, "SECRET_KEY", "your-super-secret-key-change-this-in-production-min-32-chars")
        with pytest.raises(RuntimeError, match="SECRET_KEY is default or weak"):
            s.validate_production_security()

    def test_production_passes_when_all_secure(self):
        s = Settings(
            ENVIRONMENT="production",
            DEBUG=False,
            COOKIE_SECURE=True,
            SECRET_KEY="a" * 48,
        )
        # Should not raise
        s.validate_production_security()


class TestScraperSSRFAndRebinding:
    """Verify DNS rebinding hardening, IPv4-mapped IPv6, and PinnedIPAdapter."""

    def test_is_safe_ip_blocks_metadata_and_private(self):
        assert is_safe_ip("169.254.169.254")[0] is False
        assert is_safe_ip("127.0.0.1")[0] is False
        assert is_safe_ip("10.0.0.1")[0] is False
        assert is_safe_ip("192.168.1.1")[0] is False
        assert is_safe_ip("::1")[0] is False

    def test_is_safe_ip_blocks_ipv4_mapped_ipv6(self):
        # ::ffff:127.0.0.1 and ::ffff:169.254.169.254
        assert is_safe_ip("::ffff:127.0.0.1")[0] is False
        assert is_safe_ip("::ffff:169.254.169.254")[0] is False
        assert is_safe_ip("::ffff:192.168.0.1")[0] is False

    def test_is_safe_ip_allows_public_ip(self):
        assert is_safe_ip("8.8.8.8")[0] is True
        assert is_safe_ip("2607:f8b0:4005:805::200e")[0] is True

    def test_resolve_fails_closed_if_any_ip_unsafe(self, monkeypatch):
        """If a hostname resolves to one safe and one unsafe IP, it fails closed."""
        def mock_getaddrinfo(host, port):
            return [
                (2, 1, 6, "", ("93.184.216.34", 0)),  # Safe public
                (2, 1, 6, "", ("127.0.0.1", 0)),       # Unsafe private!
            ]
        monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)

        is_safe, reason, pinned = resolve_and_validate_hostname("test-dual-homed.com")
        assert is_safe is False
        assert "forbidden IP '127.0.0.1'" in reason
        assert pinned is None

    def test_pinned_adapter_builds_correct_pool_attributes(self):
        """PinnedIPAdapter sets host to pinned IP and assert_hostname/server_hostname to real host."""
        adapter = PinnedIPAdapter(pinned_ip="93.184.216.34", real_host="example.com")
        import requests
        req = requests.Request("GET", "https://example.com/notices").prepare()
        host_params, pool_kwargs = adapter.build_connection_pool_key_attributes(req, verify=True)
        assert host_params["host"] == "93.184.216.34"
        assert pool_kwargs["assert_hostname"] == "example.com"
        assert pool_kwargs["server_hostname"] == "example.com"

    def test_pinned_adapter_https_local_verification(self):
        """
        Local HTTPS test: PinnedIPAdapter connects to pinned IP (127.0.0.1),
        successfully verifies certificate matching real_host, and strictly
        rejects certificate for the wrong hostname.
        """
        import datetime, ssl, threading, http.server, tempfile, os
        import requests
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "goodhost.local")])
        san = x509.SubjectAlternativeName([x509.DNSName("goodhost.local")])
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=1))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
            .add_extension(san, critical=False)
            .sign(key, hashes.SHA256())
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as cf, tempfile.NamedTemporaryFile(delete=False, suffix=".pem") as kf:
            cf.write(cert.public_bytes(serialization.Encoding.PEM))
            kf.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
            cert_path, key_path = cf.name, kf.name

        try:
            class SimpleHandler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK")
                def log_message(self, *a): pass

            server = http.server.HTTPServer(("127.0.0.1", 0), SimpleHandler)
            ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ctx.load_cert_chain(certfile=cert_path, keyfile=key_path)
            server.socket = ctx.wrap_socket(server.socket, server_side=True)
            port = server.server_address[1]

            t = threading.Thread(target=server.serve_forever, daemon=True)
            t.start()

            # 1. Matching hostname: connects to pinned IP and validates cert
            sess = requests.Session()
            adapter_good = PinnedIPAdapter(pinned_ip="127.0.0.1", real_host="goodhost.local")
            sess.mount("https://goodhost.local", adapter_good)
            resp = sess.get(f"https://goodhost.local:{port}/", verify=cert_path)
            assert resp.status_code == 200
            assert resp.text == "OK"

            # 2. Mismatched hostname: connects to pinned IP, but cert hostname does not match
            sess_bad = requests.Session()
            adapter_bad = PinnedIPAdapter(pinned_ip="127.0.0.1", real_host="wronghost.local")
            sess_bad.mount("https://wronghost.local", adapter_bad)
            with pytest.raises(requests.exceptions.SSLError):
                sess_bad.get(f"https://wronghost.local:{port}/", verify=cert_path)

            server.shutdown()
            server.server_close()
        finally:
            if os.path.exists(cert_path): os.unlink(cert_path)
            if os.path.exists(key_path): os.unlink(key_path)

    def test_dns_rebinding_switch_prevented_by_pinned_adapter(self, monkeypatch):
        """
        DNS Rebinding test: Host initially resolves to safe public IP.
        Attacker then switches DNS to 127.0.0.1.
        PinnedIPAdapter ensures connection only targets the pinned safe IP.
        """
        import socket
        import requests
        resolutions = [
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 80))], # 1st: initial check -> safe
            [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))],      # 2nd+: rebinding to localhost
        ]

        def mock_gai(host, port, *args, **kwargs):
            if resolutions:
                return resolutions.pop(0)
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 80))]

        monkeypatch.setattr(socket, "getaddrinfo", mock_gai)
        ok, reason, pinned_ip = resolve_and_validate_hostname("attacker-rebinding.com")
        assert ok is True
        assert pinned_ip == "93.184.216.34"

        # Pinned adapter binds strictly to the verified pinned IP (not the switched DNS)
        adapter = PinnedIPAdapter(pinned_ip=pinned_ip, real_host="attacker-rebinding.com")
        host_params, pool_kwargs = adapter.build_connection_pool_key_attributes(
            requests.Request("GET", "http://attacker-rebinding.com/events").prepare(),
            {}
        )
        assert host_params["host"] == "93.184.216.34"
        assert pool_kwargs["assert_hostname"] == "attacker-rebinding.com"


@pytest.mark.asyncio
class TestGoogleClassroomOAuthState:
    """Verify single-use atomic state and user match for Google OAuth."""

    async def test_oauth_state_generation_and_decoding(self):
        user_id = str(uuid.uuid4())
        token = _state_token(user_id)
        payload = _decode_state(token)
        assert payload["uid"] == user_id
        assert "jti" in payload
        assert payload["purpose"] == "google_oauth"

    async def test_oauth_state_user_mismatch_rejected(self, db_session: AsyncSession, monkeypatch):
        monkeypatch.setattr("app.classroom.oauth.settings.GOOGLE_CLIENT_ID", "mock-client-id")
        monkeypatch.setattr("app.classroom.oauth.settings.GOOGLE_CLIENT_SECRET", "mock-client-secret")
        monkeypatch.setattr("app.classroom.oauth.settings.GOOGLE_REDIRECT_URI", "http://localhost/callback")
        user_a = uuid.uuid4()
        user_b = uuid.uuid4()
        token = _state_token(str(user_a))
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await exchange_code_and_store(db_session, code="dummy", state=token, expected_user_id=user_b)
        assert exc.value.status_code == 403
        assert "mismatch" in exc.value.detail

    async def test_oauth_state_atomic_single_use(self, db_session: AsyncSession, monkeypatch):
        """Replaying the same OAuth state fails with 400."""
        user_id = uuid.uuid4()
        token = _state_token(str(user_id))

        # Mock Google token endpoint
        class MockResp:
            status_code = 200
            def json(self):
                return {"access_token": "mock-acc", "expires_in": 3600}

        class MockAsyncClient:
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def post(self, *args, **kwargs):
                return MockResp()

        monkeypatch.setattr("httpx.AsyncClient", lambda *a, **kw: MockAsyncClient())
        monkeypatch.setattr("app.classroom.oauth.settings.GOOGLE_CLIENT_ID", "mock-client-id")
        monkeypatch.setattr("app.classroom.oauth.settings.GOOGLE_CLIENT_SECRET", "mock-client-secret")
        monkeypatch.setattr("app.classroom.oauth.settings.GOOGLE_REDIRECT_URI", "http://localhost/callback")

        # First use succeeds
        res = await exchange_code_and_store(db_session, code="test-code", state=token, expected_user_id=user_id)
        assert res == str(user_id)

        # Replay attempt fails with 400
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await exchange_code_and_store(db_session, code="test-code", state=token, expected_user_id=user_id)
        assert exc.value.status_code == 400
        assert "already been used" in exc.value.detail

    async def test_oauth_callback_endpoint_replay_rejected(
        self, client: AsyncClient, registered_user: dict, monkeypatch
    ):
        """HTTP GET callback endpoint rejects state replay with 400."""
        # 1. Login user to get valid auth cookie
        await client.post("/api/v1/auth/login", json={
            "email": registered_user["email"],
            "password": registered_user["_password"],
        })

        user_id = registered_user["id"]
        token = _state_token(str(user_id))

        class MockResp:
            status_code = 200
            def json(self):
                return {"access_token": "mock-acc", "expires_in": 3600}

        class MockAsyncClient:
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, *args, **kwargs): return MockResp()

        monkeypatch.setattr("httpx.AsyncClient", lambda *a, **kw: MockAsyncClient())
        monkeypatch.setattr("app.classroom.oauth.settings.GOOGLE_CLIENT_ID", "mock-client-id")
        monkeypatch.setattr("app.classroom.oauth.settings.GOOGLE_CLIENT_SECRET", "mock-client-secret")
        monkeypatch.setattr("app.classroom.oauth.settings.GOOGLE_REDIRECT_URI", "http://localhost/callback")

        # First callback consumes state
        cb1 = await client.get(f"/auth/google/callback?code=fake-code&state={token}")
        assert cb1.status_code in (200, 302, 307)

        # Second callback with same state must fail with 400
        cb2 = await client.get(f"/auth/google/callback?code=fake-code&state={token}")
        assert cb2.status_code == 400
        assert "already been used" in cb2.json()["detail"]


@pytest.mark.asyncio
class TestRateLimiterResilience:
    """Verify database rate limit events and graceful fallback if DB is down."""

    async def test_rate_limit_event_db_persistence(self, db_session: AsyncSession):
        await record_rate_limit_event("test_scope", "key_123")
        res = await db_session.execute(
            select(RateLimitEvent).where(RateLimitEvent.scope == "test_scope", RateLimitEvent.key == "key_123")
        )
        events = res.scalars().all()
        assert len(events) >= 1

    async def test_db_failure_graceful_fallback(self, monkeypatch):
        """If AsyncSessionLocal fails, record_rate_limit_event logs and continues without error."""
        def mock_broken_session():
            raise RuntimeError("Database connection lost")

        monkeypatch.setattr("app.database.AsyncSessionLocal", mock_broken_session)
        # Should not raise exception
        await record_rate_limit_event("test_scope", "key_broken_db")
