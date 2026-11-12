"""
Shared test fixtures for SAIS backend tests.

Key design decisions:
  • Uses an IN-MEMORY SQLite database — never touches backend/sais.db.
  • Monkeypatches app.config.settings and app.database so every import
    in the application sees the test engine/session from the start.
  • A fresh database is created for each test-session (all tables are
    recreated from the ORM models).
"""
import os, asyncio, uuid, tempfile, shutil
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.pool import StaticPool


# ── 1. Build a throw-away Settings object pointing at an in-memory DB ──
# We MUST do this BEFORE importing anything from app.* because app/config.py
# evaluates `settings = get_settings()` at import time.

os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"  # in-memory SQLite for tests
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-ci-only-not-production")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("GEMINI_API_KEY_CHAT", "test-gemini-chat-key")
os.environ.setdefault("GEMINI_API_KEY_TIMETABLE", "test-gemini-timetable-key")
_TEST_UPLOAD_DIR = tempfile.mkdtemp(prefix="sais_test_uploads_")
os.environ["UPLOAD_DIR"] = _TEST_UPLOAD_DIR
os.environ["STORAGE_BACKEND"] = "fake"

# Now it is safe to import the app
from app.config import settings  # noqa: E402
settings.UPLOAD_DIR = _TEST_UPLOAD_DIR
settings.STORAGE_BACKEND = "fake"
from app.database import Base  # noqa: E402

# ── 2. Create a separate async engine for tests ───────────────────────
TEST_ENGINE = create_async_engine(
    "sqlite+aiosqlite://",            # in-memory, NOT sais.db
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,             # share one connection across threads
)

TestSessionLocal = async_sessionmaker(
    TEST_ENGINE, class_=AsyncSession, expire_on_commit=False
)

import app.database
app.database.engine = TEST_ENGINE
app.database.AsyncSessionLocal = TestSessionLocal


# ── 3. Fixtures ───────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _create_tables():
    """Create all ORM tables once per session (in the in-memory DB)."""
    # Import all models so Base.metadata is fully populated
    import app.models  # noqa: F401

    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with TEST_ENGINE.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture()
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a fresh DB session; rolls back after each test."""
    async with TestSessionLocal() as session:
        yield session
        # Roll back any uncommitted changes so tests are isolated
        await session.rollback()


@pytest.fixture(autouse=True)
def _reset_rate_limiters():
    """Reset rate limiters between tests so test execution doesn't throttle itself."""
    from app.core.rate_limiter import (
        limiter,
        failed_login_tracker,
        join_attempt_tracker,
        ai_extraction_tracker,
        quota_cooldown_tracker,
    )
    try:
        limiter.reset()
    except Exception:
        pass
    failed_login_tracker._attempts.clear()
    join_attempt_tracker.reset()
    ai_extraction_tracker.reset()
    quota_cooldown_tracker.reset()
    try:
        from app.api.college_events import _institution_scrape_times
        _institution_scrape_times.clear()
    except Exception:
        pass


def login_client(client: AsyncClient, token: str) -> None:
    """Shared helper to log in a test client by setting the access_token httpOnly cookie."""
    client.cookies.set("access_token", token)


async def _bridge_auth_to_cookie(request):
    """
    httpx event hook (runs at the httpx layer before transport conversion).
    Bridges legacy test ``Authorization: Bearer <token>`` headers into an
    ``access_token`` cookie so the application's pure-cookie auth works
    unchanged for all existing tests.

    Tests that want to verify Bearer-alone-is-rejected can pass the header
    ``X-No-Cookie-Bridge: 1`` to skip bridging for that request.
    """
    if request.headers.get("x-no-cookie-bridge"):
        del request.headers["x-no-cookie-bridge"]
        return

    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:].strip()
        cookie_val = request.headers.get("cookie", "")
        parts = [p.strip() for p in cookie_val.split(";") if p.strip() and not p.strip().startswith("access_token=")]
        parts.append(f"access_token={token}")
        request.headers["cookie"] = "; ".join(parts)


@pytest_asyncio.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Yield an httpx AsyncClient wired to the FastAPI app.
    The app's `get_db` dependency is overridden to use our test session.

    Backwards-compatible with all existing tests:
      • Default ``X-Requested-With: XMLHttpRequest`` header satisfies the
        CSRF middleware for every request.
      • An event hook transparently copies any ``Authorization: Bearer``
        value into an ``access_token`` cookie so pure-cookie auth works.
    """
    from app.database import get_db
    from app.main import app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
        headers={"X-Requested-With": "XMLHttpRequest"},
        event_hooks={"request": [_bridge_auth_to_cookie]},
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── 4. Auth helpers ───────────────────────────────────────────────────

@pytest_asyncio.fixture()
async def registered_user(client: AsyncClient) -> dict:
    """Register a random user and return the JSON response."""
    unique = uuid.uuid4().hex[:8]
    payload = {
        "email": f"test_{unique}@example.com",
        "username": f"user_{unique}",
        "full_name": "Test User",
        "password": "StrongPass123!",
    }
    resp = await client.post("/api/v1/auth/register", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    data["_password"] = payload["password"]   # stash for login helper
    return data


@pytest_asyncio.fixture()
async def auth_token(client: AsyncClient, registered_user: dict) -> str:
    """Log in the registered_user, store cookie in client, and return token."""
    resp = await client.post("/api/v1/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["_password"],
    })
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    login_client(client, token)
    return token


@pytest_asyncio.fixture()
async def auth_headers(auth_token: str) -> dict:
    """Convenience: returns headers dict with Bearer token (bridged to cookie via event hook)."""
    return {"Authorization": f"Bearer {auth_token}"}
