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
