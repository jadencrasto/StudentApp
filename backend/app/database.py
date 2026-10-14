from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import StaticPool
from sqlalchemy import event
from app.config import settings

# Create async engine
is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# Create async engine
engine_kwargs = {
    "echo": False,
}
if is_sqlite:
    # SQLite: use StaticPool to share one connection (avoids "database is locked")
    # and set a generous busy-timeout via connect_args.
    engine_kwargs["connect_args"] = {"timeout": 30, "check_same_thread": False}
    engine_kwargs["poolclass"] = StaticPool
else:
    # PostgreSQL (Supabase Session Pooler):
    # - pool_pre_ping: tests liveness before checkout to prevent using closed connections
    # - pool_recycle: recycles connections periodically (5 min) to prevent stale socket drops
    # - statement_cache_size=0: prevents prepared statement collisions in pooled connections
    engine_kwargs["pool_pre_ping"] = True
    engine_kwargs["pool_recycle"] = 300
    engine_kwargs["pool_size"] = 10
    engine_kwargs["max_overflow"] = 5
    engine_kwargs["connect_args"] = {"statement_cache_size": 0}

engine = create_async_engine(settings.DATABASE_URL, **engine_kwargs)


# Enable WAL mode + foreign keys only for SQLite connections
if is_sqlite:
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, _connection_record):
        """Enable WAL journal mode and foreign keys for SQLite connections."""
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=30000")   # 30-second retry on lock
        cursor.close()


async def ensure_assignment_ai_metadata_column() -> None:
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    async with engine.begin() as conn:
        try:
            await conn.exec_driver_sql("ALTER TABLE assignments ADD COLUMN ai_metadata JSON")
        except Exception:
            pass


async def ensure_assignment_classroom_id_column() -> None:
    """Add classroom_id column to assignments table for Google Classroom sync (SQLite only)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    async with engine.begin() as conn:
        try:
            await conn.exec_driver_sql(
                "ALTER TABLE assignments ADD COLUMN classroom_id VARCHAR(255)"
            )
        except Exception:
            pass  # column already exists


async def ensure_activity_recurrence_columns() -> None:
    """Add recurrence columns to activities table (SQLite only)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
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
    """Add notification tracking columns to attendance_records table (SQLite only)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
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
    Idempotent startup migration for attendance_records (SQLite only).
    PostgreSQL schema is handled by Alembic migrations.
    """
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    import logging as _logging
    _log = _logging.getLogger(__name__)

    async with engine.begin() as conn:
        for stmt in [
            "ALTER TABLE attendance_records ADD COLUMN class_start_time VARCHAR(10)",
            "ALTER TABLE attendance_records ADD COLUMN marked_at DATETIME",
        ]:
            try:
                await conn.exec_driver_sql(stmt)
            except Exception:
                pass  # column already exists

        try:
            await conn.exec_driver_sql(
                "DROP INDEX IF EXISTS uq_attendance_per_day"
            )
        except Exception as exc:
            _log.warning("Could not drop uq_attendance_per_day: %s", exc)

        try:
            await conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_attendance_per_slot "
                "ON attendance_records (user_id, subject_id, class_date, class_start_time)"
            )
        except Exception as exc:
            _log.warning("Could not create uq_attendance_per_slot: %s", exc)


async def ensure_phase5a_columns() -> None:
    """Add Phase 5A multi-tenant role and onboarding columns to users table (SQLite only)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    new_columns = [
        "ALTER TABLE users ADD COLUMN role VARCHAR(30) DEFAULT 'student'",
        "ALTER TABLE users ADD COLUMN institution_id VARCHAR(36)",
        "ALTER TABLE users ADD COLUMN cohort_id VARCHAR(36)",
        "ALTER TABLE users ADD COLUMN must_change_password BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN onboarding_completed BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN education_level VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN grade_or_year VARCHAR(50)",
        "ALTER TABLE users ADD COLUMN location VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN institution_name_text VARCHAR(255)",
        "ALTER TABLE users ADD COLUMN extra_info JSON",
    ]
    async with engine.begin() as conn:
        for stmt in new_columns:
            try:
                await conn.exec_driver_sql(stmt)
            except Exception:
                pass  # column already exists


async def ensure_phase6a_columns() -> None:
    """Add Phase 6A student management and token columns to users table (SQLite dev only)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    new_columns = [
        "ALTER TABLE users ADD COLUMN created_by_admin BOOLEAN DEFAULT 0",
        "ALTER TABLE users ADD COLUMN archived_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN password_changed_at TIMESTAMP",
        "ALTER TABLE users ADD COLUMN token_version INTEGER DEFAULT 1",
    ]
    new_indexes = [
        "CREATE INDEX IF NOT EXISTS ix_users_full_name ON users (full_name)",
        "CREATE INDEX IF NOT EXISTS ix_users_institution_role ON users (institution_id, role)",
    ]
    async with engine.begin() as conn:
        for stmt in new_columns:
            try:
                await conn.exec_driver_sql(stmt)
            except Exception:
                pass
        for stmt in new_indexes:
            try:
                await conn.exec_driver_sql(stmt)
            except Exception:
                pass


async def ensure_phase6b_tables() -> None:
    """Ensure Phase 6B class attendance tables and indexes exist (SQLite dev mode)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    async with engine.begin() as conn:
        try:
            await conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS class_attendance_records (
                    id VARCHAR(36) PRIMARY KEY,
                    institution_id VARCHAR(36) NOT NULL,
                    cohort_id VARCHAR(36) NOT NULL,
                    student_id VARCHAR(36) NOT NULL,
                    class_date DATE NOT NULL,
                    subject_name VARCHAR(100) NOT NULL,
                    subject_name_normalized VARCHAR(100) NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    marked_by VARCHAR(36),
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    CONSTRAINT uq_cohort_student_date_subject UNIQUE (cohort_id, student_id, class_date, subject_name_normalized),
                    FOREIGN KEY (institution_id) REFERENCES institutions(id) ON DELETE CASCADE,
                    FOREIGN KEY (cohort_id) REFERENCES cohorts(id) ON DELETE CASCADE,
                    FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE,
                    FOREIGN KEY (marked_by) REFERENCES users(id) ON DELETE SET NULL
                )
            """)
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_class_attendance_cohort_date ON class_attendance_records (cohort_id, class_date)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_class_attendance_student_cohort ON class_attendance_records (student_id, cohort_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_class_attendance_inst ON class_attendance_records (institution_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_class_attendance_student ON class_attendance_records (student_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_class_attendance_date ON class_attendance_records (class_date)")

            await conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS class_attendance_change_logs (
                    id VARCHAR(36) PRIMARY KEY,
                    record_id VARCHAR(36) NOT NULL,
                    changed_by VARCHAR(36),
                    previous_status VARCHAR(20) NOT NULL,
                    new_status VARCHAR(20) NOT NULL,
                    changed_at TIMESTAMP NOT NULL,
                    reason VARCHAR(255),
                    FOREIGN KEY (record_id) REFERENCES class_attendance_records(id) ON DELETE CASCADE,
                    FOREIGN KEY (changed_by) REFERENCES users(id) ON DELETE SET NULL
                )
            """)
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_class_change_log_record ON class_attendance_change_logs (record_id)")
        except Exception:
            pass


async def ensure_phase6c_tables() -> None:
    """Create class_timetables table for SQLite (Phase 6C)."""
    if not settings.DATABASE_URL.startswith("sqlite"):
        return
    async with engine.begin() as conn:
        try:
            await conn.exec_driver_sql("""
                CREATE TABLE IF NOT EXISTS class_timetables (
                    id VARCHAR(36) PRIMARY KEY,
                    institution_id VARCHAR(36) NOT NULL,
                    cohort_id VARCHAR(36) NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'draft',
                    entries JSON NOT NULL DEFAULT '[]',
                    image_path VARCHAR(500),
                    created_by VARCHAR(36),
                    published_at TIMESTAMP,
                    created_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    FOREIGN KEY (institution_id) REFERENCES institutions(id) ON DELETE CASCADE,
                    FOREIGN KEY (cohort_id) REFERENCES cohorts(id) ON DELETE CASCADE,
                    FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL
                )
            """)
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_class_timetable_institution ON class_timetables (institution_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_class_timetable_cohort ON class_timetables (cohort_id)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_class_timetable_status ON class_timetables (status)")
            await conn.exec_driver_sql("CREATE INDEX IF NOT EXISTS ix_class_timetable_cohort_status ON class_timetables (cohort_id, status)")
            # Partial unique indexes for draft and published
            await conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_one_published_per_cohort ON class_timetables (cohort_id) WHERE status = 'published'")
            await conn.exec_driver_sql("CREATE UNIQUE INDEX IF NOT EXISTS uq_one_draft_per_cohort ON class_timetables (cohort_id) WHERE status = 'draft'")
            # Add image_path column if table existed without it
            try:
                await conn.exec_driver_sql("ALTER TABLE class_timetables ADD COLUMN image_path VARCHAR(500)")
            except Exception:
                pass
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
