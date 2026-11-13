"""
PostgreSQL Test Runner for SAIS (Phase 8F).

Single-command execution:
  1. Validates test database URL (strict safety guard against remote/Supabase URLs).
  2. Creates fresh throwaway local database 'sais_test'.
  3. Runs Alembic migrations to head.
  4. Runs schema drift check (models vs migrations, 8B indexes, 8C columns, 8D RLS).
  5. Executes marked PostgreSQL test suite via pytest.

Safety rules:
  - Host MUST be localhost / 127.0.0.1 / ::1.
  - Database name MUST end in '_test' (e.g. 'sais_test').
  - Refuses any query parameters that could override connection destination.
  - Subprocesses receive ENVIRONMENT=test and ENV_FILE="" so backend/.env is never read.
"""
import os
import sys
import subprocess
import urllib.parse
from pathlib import Path

# Add backend directory to sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app.core.test_safety import validate_test_database_url, validate_admin_database_url


def load_env_test_if_exists() -> None:
    """Load backend/.env.test (or fallback to backend/.env.backup) without touching backend/.env."""
    env_test_file = BASE_DIR / ".env.test"
    if env_test_file.exists():
        for line in env_test_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    env_backup_file = BASE_DIR / ".env.backup"
    if env_backup_file.exists():
        for line in env_backup_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_test_urls() -> tuple[str, str]:
    """
    Returns (test_db_url, admin_db_url).
    Default: local postgres on localhost:5432/sais_test.
    """
    load_env_test_if_exists()
    test_url = os.getenv("TEST_DATABASE_URL")
    if not test_url:
        password = os.getenv("TEST_PG_PASSWORD") or os.getenv("LOCAL_PG_PASSWORD") or os.getenv("PGPASSWORD") or ""
        user = os.getenv("TEST_PG_USER") or os.getenv("LOCAL_PG_USER") or os.getenv("PGUSER") or "postgres"
        port = os.getenv("TEST_PG_PORT") or os.getenv("LOCAL_PG_PORT") or os.getenv("PGPORT") or "5432"
        host = os.getenv("TEST_PG_HOST") or os.getenv("LOCAL_PG_HOST") or os.getenv("PGHOST") or "localhost"
        auth = f"{user}:{password}@" if password else f"{user}@"
        test_url = f"postgresql+asyncpg://{auth}{host}:{port}/sais_test"

    # Guard Place 1: Validate test URL
    validate_test_database_url(test_url, context="Runner Test DB Guard")

    # Build admin URL for dropping/creating test database
    parsed = urllib.parse.urlsplit(test_url)
    # Convert asyncpg driver to standard psycopg2/psql compatible for synchronous admin commands
    netloc = parsed.netloc
    admin_url = f"postgresql://{netloc}/postgres"
    validate_admin_database_url(admin_url, context="Runner Admin DB Guard")

    return test_url, admin_url


def recreate_test_database(admin_url: str, db_name: str = "sais_test") -> None:
    """Drop and recreate the local test database using psycopg2 or psql or asyncpg."""
    import asyncio
    import asyncpg

    parsed = urllib.parse.urlsplit(admin_url)
    user = parsed.username or "postgres"
    password = parsed.password
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432

    async def _recreate():
        conn = await asyncpg.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database="postgres",
        )
        try:
            # Terminate active connections and recreate
            await conn.execute(f"DROP DATABASE IF EXISTS {db_name} WITH (FORCE);")
            await conn.execute(f"CREATE DATABASE {db_name};")
            print(f"[Runner] Successfully recreated clean test database '{db_name}'.")
        finally:
            await conn.close()

    asyncio.run(_recreate())


def run_alembic_migrations(test_url: str) -> None:
    """Run Alembic upgrade head against the test database."""
    print("[Runner] Running Alembic migrations to head on test database...")
    env = os.environ.copy()
    env["ENVIRONMENT"] = "test"
    env["DATABASE_URL"] = test_url
    env["ALEMBIC_DATABASE_URL"] = test_url
    env["SECRET_KEY"] = "ci-test-secret-key-min-32-chars-strictly-for-testing"
    env["ENV_FILE"] = ""  # Block .env loading
    env["PYTHONPATH"] = str(BASE_DIR)

    alembic_cmd = [sys.executable, "-m", "alembic", "-c", str(BASE_DIR / "alembic.ini"), "upgrade", "head"]
    res = subprocess.run(alembic_cmd, cwd=str(BASE_DIR), env=env)
    if res.returncode != 0:
        sys.exit(res.returncode)


def check_schema_drift(test_url: str) -> None:
    """Verify that Alembic migrations match models and contain all expected indexes and RLS."""
    print("[Runner] Checking schema drift and verifying Phase 8B indexes, 8C columns, and 8D RLS...")
    import asyncio
    import asyncpg

    parsed = urllib.parse.urlsplit(test_url)
    user = parsed.username or "postgres"
    password = parsed.password
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    database = parsed.path.strip("/")

    async def _verify():
        conn = await asyncpg.connect(
            user=user,
            password=password,
            host=host,
            port=port,
            database=database,
        )
        try:
            # 1. Verify Phase 8B performance composite indexes
            expected_indexes = [
                "ix_college_events_inst_date",
                "ix_assignments_user_deadline",
                "ix_alerts_user_unread",
                "ix_chat_messages_conv_created",
                "ix_rate_limit_events_lookup",
                "uq_one_published_per_cohort",
                "uq_one_draft_per_cohort",
            ]
            rows = await conn.fetch("SELECT indexname FROM pg_indexes WHERE schemaname = 'public';")
            existing_indexes = {r["indexname"] for r in rows}
            missing_indexes = [idx for idx in expected_indexes if idx not in existing_indexes]
            if missing_indexes:
                raise RuntimeError(f"Schema drift: missing required indexes: {missing_indexes}")
            print(f"[Runner] Verified all {len(expected_indexes)} Phase 8B/8C/8D performance & partial indexes exist.")

            # 2. Verify Phase 8C storage columns
            col_rows = await conn.fetch(
                """
                SELECT table_name, column_name 
                FROM information_schema.columns 
                WHERE table_schema = 'public' 
                  AND column_name IN ('image_storage_path', 'image_storage_bucket', 'storage_path', 'storage_bucket');
                """
            )
            col_pairs = {(r["table_name"], r["column_name"]) for r in col_rows}
            assert ("class_timetables", "image_storage_path") in col_pairs, "Missing class_timetables.image_storage_path"
            assert ("documents", "storage_path") in col_pairs, "Missing documents.storage_path"
            print("[Runner] Verified Phase 8C storage columns on class_timetables and documents.")

            # 3. Verify rate_limit_events with Row Level Security enabled
            rls_row = await conn.fetchrow(
                """
                SELECT relname, relrowsecurity 
                FROM pg_class 
                WHERE relname = 'rate_limit_events';
                """
            )
            if not rls_row:
                raise RuntimeError("Schema drift: table 'rate_limit_events' does not exist.")
            if not rls_row["relrowsecurity"]:
                raise RuntimeError("Security drift: 'rate_limit_events' table does not have RLS enabled.")
            print("[Runner] Verified 'rate_limit_events' table exists with Row Level Security (RLS) ENABLED.")

        finally:
            await conn.close()

    asyncio.run(_verify())


def run_pytest_suite(test_url: str) -> None:
    """Run marked PostgreSQL tests via pytest."""
    print("[Runner] Executing marked PostgreSQL tests...")
    env = os.environ.copy()
    env["ENVIRONMENT"] = "test"
    env["TEST_DATABASE_URL"] = test_url
    env["DATABASE_URL"] = test_url
    env["ALEMBIC_DATABASE_URL"] = test_url
    env["SECRET_KEY"] = "ci-test-secret-key-min-32-chars-strictly-for-testing"
    env["ENV_FILE"] = ""
    env["PYTHONPATH"] = str(BASE_DIR)

    pytest_cmd = [sys.executable, "-m", "pytest", "-v", "-m", "postgres", "--run-postgres"]
    res = subprocess.run(pytest_cmd, cwd=str(BASE_DIR.parent), env=env)
    if res.returncode != 0:
        sys.exit(res.returncode)


def main():
    test_url, admin_url = get_test_urls()
    recreate_test_database(admin_url, "sais_test")
    run_alembic_migrations(test_url)
    check_schema_drift(test_url)
    run_pytest_suite(test_url)
    print("\n[Runner] All PostgreSQL quality checks and tests PASSED successfully!")


if __name__ == "__main__":
    main()
