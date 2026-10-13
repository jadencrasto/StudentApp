"""
Shared test fixtures for SAIS backend tests.

Key design decisions:
  • Uses an IN-MEMORY SQLite database — never touches backend/sais.db.
  • Monkeypatches app.config.settings and app.database so every import
    in the application sees the test engine/session from the start.
  • A fresh database is created for each test-session (all tables are
    recreated from the ORM models).
"""
import os, asyncio, uuid
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

# Now it is safe to import the app
from app.config import settings  # noqa: E402
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
    from app.core.rate_limiter import limiter, failed_login_tracker, join_attempt_tracker
    try:
        limiter.reset()
    except Exception:
        pass
    failed_login_tracker._attempts.clear()
    join_attempt_tracker.reset()


@pytest_asyncio.fixture()
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """
    Yield an httpx AsyncClient wired to the FastAPI app.
    The app's `get_db` dependency is overridden to use our test session.
    """
    from app.database import get_db
    from app.main import app

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
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
    """Log in the registered_user and return a Bearer token string."""
    resp = await client.post("/api/v1/auth/login", json={
        "email": registered_user["email"],
        "password": registered_user["_password"],
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest_asyncio.fixture()
async def auth_headers(auth_token: str) -> dict:
    """Convenience: returns headers dict with Bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}
