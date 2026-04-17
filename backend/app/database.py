from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from sqlalchemy import event
from app.config import settings

# Create async engine
engine_kwargs = {
    "echo": False,
}
if settings.DATABASE_URL.startswith("sqlite"):
    # SQLite: use StaticPool to share one connection (avoids "database is locked")
    # and set a generous busy-timeout via connect_args.
    engine_kwargs["connect_args"] = {"timeout": 30, "check_same_thread": False}
    engine_kwargs["poolclass"] = StaticPool
else:
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 20

engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)


# Enable WAL mode + foreign keys for every new SQLite connection
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record):
    """Enable WAL journal mode and foreign keys for SQLite connections."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA busy_timeout=30000")   # 30-second retry on lock
    cursor.close()


async def ensure_assignment_ai_metadata_column() -> None:
    async with engine.begin() as conn:
        if settings.DATABASE_URL.startswith("sqlite"):
            try:
                await conn.exec_driver_sql("ALTER TABLE assignments ADD COLUMN ai_metadata JSON")
            except Exception:
                pass
        else:
            try:
                await conn.exec_driver_sql("ALTER TABLE assignments ADD COLUMN IF NOT EXISTS ai_metadata JSON")
            except Exception:
                pass


async def ensure_assignment_classroom_id_column() -> None:
    """Add classroom_id column to assignments table for Google Classroom sync."""
    async with engine.begin() as conn:
        if settings.DATABASE_URL.startswith("sqlite"):
            try:
                await conn.exec_driver_sql(
                    "ALTER TABLE assignments ADD COLUMN classroom_id VARCHAR(255)"
                )
            except Exception:
                pass  # column already exists
        else:
            try:
                await conn.exec_driver_sql(
                    "ALTER TABLE assignments ADD COLUMN IF NOT EXISTS classroom_id VARCHAR(255)"
                )
            except Exception:
                pass


async def ensure_activity_recurrence_columns() -> None:
    """Add recurrence columns to activities table (idempotent)."""
    new_columns = [
        "ALTER TABLE activities ADD COLUMN recurrence_type VARCHAR(50) DEFAULT 'none'",
        "ALTER TABLE activities ADD COLUMN recurrence_start_date DATE",
        "ALTER TABLE activities ADD COLUMN recurrence_end_date DATE",
        "ALTER TABLE activities ADD COLUMN custom_interval INTEGER",
        "ALTER TABLE activities ADD COLUMN custom_interval_unit VARCHAR(20)",
        "ALTER TABLE activities ADD COLUMN parent_activity_id VARCHAR(36)",
        "ALTER TABLE activities ADD COLUMN is_recurring_instance BOOLEAN DEFAULT 0",
    ]
    async with engine.begin() as conn:
        for stmt in new_columns:
            try:
                await conn.exec_driver_sql(stmt)
            except Exception:
                pass  # column already exists


async def ensure_notification_columns() -> None:
    """Add notification tracking columns to attendance_records table (idempotent)."""
    new_columns = [
        "ALTER TABLE attendance_records ADD COLUMN notification_sent BOOLEAN DEFAULT 0",
        "ALTER TABLE attendance_records ADD COLUMN notification_sent_at DATETIME",
    ]
    async with engine.begin() as conn:
        for stmt in new_columns:
            try:
                await conn.exec_driver_sql(stmt)
            except Exception:
                pass  # column already exists


async def ensure_attendance_slot_columns() -> None:
    """
    Idempotent startup migration for attendance_records:

    1. Adds class_start_time VARCHAR(10)  — "HH:MM" slot key for per-slot upsert.
    2. Adds marked_at DATETIME            — client-side click timestamp.
    3. Drops the old uq_attendance_per_day index (per day, not per slot) so that
       two lectures of the same subject on the same day can each have their own row.
    4. Creates uq_attendance_per_slot (per day + slot).
    """
    import logging as _logging
    _log = _logging.getLogger(__name__)

    async with engine.begin() as conn:
        # ── Step 1: add new columns ───────────────────────────────────────────
        for stmt in [
            "ALTER TABLE attendance_records ADD COLUMN class_start_time VARCHAR(10)",
            "ALTER TABLE attendance_records ADD COLUMN marked_at DATETIME",
        ]:
            try:
                await conn.exec_driver_sql(stmt)
            except Exception:
                pass  # column already exists — that's fine

        # ── Step 2: fix the unique constraint ────────────────────────────────
        if settings.DATABASE_URL.startswith("sqlite"):
            # SQLite: drop the old named index (created by SQLAlchemy from the
            # UniqueConstraint name="uq_attendance_per_day").
            # Named indexes ARE droppable; sqlite_autoindex_* are not.
            try:
                await conn.exec_driver_sql(
                    "DROP INDEX IF EXISTS uq_attendance_per_day"
                )
            except Exception as exc:
                _log.warning("Could not drop uq_attendance_per_day: %s", exc)

            # Create the new per-slot index (IF NOT EXISTS = idempotent).
            try:
                await conn.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_per_slot "
                    "ON attendance_records (user_id, subject_id, class_date, class_start_time)"
                )
            except Exception as exc:
                _log.warning("Could not create uq_attendance_per_slot: %s", exc)
        else:
            # PostgreSQL supports proper ALTER TABLE constraint DDL.
            for stmt in [
                "ALTER TABLE attendance_records DROP CONSTRAINT IF EXISTS uq_attendance_per_day",
                (
                    "ALTER TABLE attendance_records "
                    "ADD CONSTRAINT uq_attendance_per_slot "
                    "UNIQUE (user_id, subject_id, class_date, class_start_time)"
                ),
            ]:
                try:
                    await conn.exec_driver_sql(stmt)
                except Exception:
                    pass

# Session factory
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,   # keep objects usable after commit
)


# Base class for all ORM models
class Base(DeclarativeBase):
    pass


# Dependency — yields a DB session per request, closes it after
async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
