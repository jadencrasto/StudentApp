"""
End-to-End Smoke Test Orchestrator (Phase 8F).

Starts:
  1. Real local PostgreSQL database (sais_test) with migrations to head
  2. Seeds 3 throwaway test users (student, admin, super_admin) - NEVER demo@sais.edu
  3. Launches backend FastAPI process with explicit dummy env overrides (no .env loading)
  4. Launches frontend Vite process on http://localhost:5173
  5. Executes Playwright smoke suite
  6. Safely tears down frontend and backend processes
"""
import os
import sys
import time
import uuid
import urllib.parse
import subprocess
import signal
from pathlib import Path
import urllib.request
import asyncio
import asyncpg

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
ROOT_DIR = BASE_DIR.parent
FRONTEND_DIR = ROOT_DIR / "frontend"
sys.path.insert(0, str(BASE_DIR))

# Ensure dummy defaults so config import does not fail before get_test_urls()
os.environ.setdefault("SECRET_KEY", "ci-dummy-secret-key-32chars-min-length-123456789")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres@localhost:5432/sais_test")

from app.core.test_safety import validate_test_database_url, validate_admin_database_url
from app.core.security import hash_password
from scripts.run_postgres_tests import get_test_urls, recreate_test_database, run_alembic_migrations


async def seed_e2e_throwaway_users(test_url: str) -> None:
    """Insert throwaway users for E2E testing into sais_test."""
    print("[E2E Runner] Seeding throwaway users into sais_test...")
    parsed = urllib.parse.urlsplit(test_url.replace("+asyncpg", ""))
    user = parsed.username or "postgres"
    password = parsed.password
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    db_name = parsed.path.lstrip("/")

    conn = await asyncpg.connect(
        user=user,
        password=password,
        host=host,
        port=port,
        database=db_name,
    )
    try:
        pw_hash = hash_password("E2ePass123!")
        users_data = [
            (uuid.uuid4(), "e2e_student@test.local", "e2e_student", "E2E Student", pw_hash, "student", False, True, True),
            (uuid.uuid4(), "e2e_admin@test.local", "e2e_admin", "E2E Admin", pw_hash, "admin", False, True, True),
            (uuid.uuid4(), "e2e_superadmin@test.local", "e2e_superadmin", "E2E Super Admin", pw_hash, "super_admin", False, True, True),
        ]
        for uid, email, uname, fname, phash, role, mcp, obc, act in users_data:
            await conn.execute(
                """
                INSERT INTO users (
                    id, email, username, full_name, hashed_password, role,
                    must_change_password, onboarding_completed, is_active,
                    token_version, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, 1, NOW(), NOW())
                ON CONFLICT (email) DO UPDATE SET
                    hashed_password = EXCLUDED.hashed_password,
                    role = EXCLUDED.role,
                    must_change_password = EXCLUDED.must_change_password,
                    onboarding_completed = EXCLUDED.onboarding_completed;
                """,
                uid, email, uname, fname, phash, role, mcp, obc, act,
            )
        print("[E2E Runner] Successfully seeded 3 throwaway test users.")
    finally:
        await conn.close()


def wait_for_url(url: str, timeout_sec: int = 25) -> bool:
    """Poll a URL until it responds with 200 or timeout."""
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "E2E-Check"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status in (200, 304):
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main():
    test_url, admin_url = get_test_urls()
    validate_test_database_url(test_url, context="E2E Runner Test DB Guard")

    # 1. Recreate clean test database & migrate
    recreate_test_database(admin_url, "sais_test")
    run_alembic_migrations(test_url)

    # 2. Seed throwaway users
    asyncio.run(seed_e2e_throwaway_users(test_url))

    # 3. Start backend process with isolated env
    backend_env = os.environ.copy()
    backend_env["ENVIRONMENT"] = "test"
    backend_env["ENV_FILE"] = ""  # Strictly disables .env loading
    backend_env["DATABASE_URL"] = test_url
    backend_env["SECRET_KEY"] = "e2e-dummy-test-secret-key-32chars-min-length-123456789"
    backend_env["STORAGE_BACKEND"] = "local"
    backend_env["LOCAL_STORAGE_DIR"] = str(BASE_DIR / "test_storage")
    backend_env["ALLOWED_ORIGINS"] = "http://localhost:5173"
    backend_env["SEED_DEMO_USER"] = "false"
    backend_env["GEMINI_API_KEY"] = ""
    backend_env["GOOGLE_CLIENT_ID"] = ""
    backend_env["GOOGLE_CLIENT_SECRET"] = ""
    backend_env["PYTHONPATH"] = str(BASE_DIR)

    print("[E2E Runner] Launching backend on http://127.0.0.1:8000 ...")
    backend_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8000", "--host", "127.0.0.1"],
        cwd=str(BASE_DIR),
        env=backend_env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    frontend_proc = None
    try:
        if not wait_for_url("http://127.0.0.1:8000/health", timeout_sec=15):
            print("[E2E Runner] ERROR: Backend failed to start or respond to /health.")
            sys.exit(1)
        print("[E2E Runner] Backend is UP and healthy.")

        # 4. Start frontend process
        print("[E2E Runner] Launching frontend on http://localhost:5173 ...")
        frontend_proc = subprocess.Popen(
            "npx vite --port 5173 --host localhost",
            shell=True,
            cwd=str(FRONTEND_DIR),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        if not wait_for_url("http://localhost:5173", timeout_sec=20):
            print("[E2E Runner] ERROR: Frontend failed to start on http://localhost:5173.")
            sys.exit(1)
        print("[E2E Runner] Frontend is UP and responsive.")

        # 5. Run Playwright E2E tests
        print("[E2E Runner] Running Playwright smoke tests...")
        res = subprocess.run(
            "npx playwright test",
            shell=True,
            cwd=str(FRONTEND_DIR),
        )

        if res.returncode == 0:
            print("\n[E2E Runner] Playwright E2E smoke suite PASSED successfully!")
        else:
            print(f"\n[E2E Runner] Playwright E2E smoke suite FAILED with code {res.returncode}")
        sys.exit(res.returncode)

    finally:
        print("[E2E Runner] Cleaning up processes...")
        if frontend_proc:
            try:
                subprocess.run(f"taskkill /F /T /PID {frontend_proc.pid}", shell=True, capture_output=True)
            except Exception:
                pass
        if backend_proc:
            try:
                subprocess.run(f"taskkill /F /T /PID {backend_proc.pid}", shell=True, capture_output=True)
            except Exception:
                pass


if __name__ == "__main__":
    main()
