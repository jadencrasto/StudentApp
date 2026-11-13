import asyncio
import os
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

# 1. Import application settings and ORM Base
from app.config import settings
from app.database import Base

# 2. Import all models so Alembic can detect every table
import app.models  # noqa: F401

config = context.config

# Interpret the config file for Python logging if present
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLAlchemy URL from app settings or environment override
db_url = os.getenv("ALEMBIC_DATABASE_URL") or settings.DATABASE_URL
if os.getenv("ENVIRONMENT") == "test" or os.getenv("ALEMBIC_DATABASE_URL"):
    from app.core.test_safety import validate_test_database_url
    validate_test_database_url(db_url, context="Alembic Migration Guard")

if db_url.startswith("postgres://"):
    db_url = "postgresql+asyncpg://" + db_url[len("postgres://"):]
elif db_url.startswith("postgresql://"):
    db_url = "postgresql+asyncpg://" + db_url[len("postgresql://"):]
config.set_main_option("sqlalchemy.url", db_url)

target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    """
    Filter objects for Alembic autogenerate and schema comparison.
    
    uq_college_events_dedup is a custom PostgreSQL functional unique index
    (using COALESCE, LOWER, REGEXP_REPLACE, and CASE expressions) created in
    migration f5b7c3e1a9d2. Alembic cannot reverse-engineer expression-based
    functional indexes into declarative model column tuples, so autogenerate
    would mistakenly detect it as a removed index. We explicitly ignore it.
    """
    if type_ == "index" and name == "uq_college_events_dedup":
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    is_sqlite = url.startswith("sqlite")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=is_sqlite,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations using the active synchronous connection wrapped by async engine."""
    is_sqlite = connection.dialect.name == "sqlite"
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=is_sqlite,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode using async SQLAlchemy engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = db_url

    engine_kwargs = {
        "prefix": "sqlalchemy.",
        "poolclass": pool.NullPool,
    }
    if not db_url.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"statement_cache_size": 0}

    connectable = async_engine_from_config(
        configuration,
        **engine_kwargs,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point for online migrations."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
