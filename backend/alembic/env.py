"""
Alembic environment configuration.
Reads DATABASE_URL from app settings (which loads from backend/.env).
Supports both online (connected) and offline (SQL script) migration modes.
"""

import asyncio
import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

# Ensure the backend/ directory is on sys.path so app.* imports resolve
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import get_settings
from app.database import Base

# Import all models so Alembic can see their metadata
import app.models  # noqa: F401

config = context.config
settings = get_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live database connection (generates SQL script)."""
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations with a live async database connection."""
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
