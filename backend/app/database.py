"""
Async SQLAlchemy engine and session factory.
All database access flows through the get_db() dependency injected into routes.
"""

from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import get_settings

settings = get_settings()

# ------------------------------------------------------------------
# Engine
# ------------------------------------------------------------------
# pool_pre_ping=True: reconnect automatically after idle disconnects
#   (common with Supabase which closes idle connections after ~5 min)
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    echo=settings.is_development,  # Log SQL only in development
)

# ------------------------------------------------------------------
# Session factory
# ------------------------------------------------------------------
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ------------------------------------------------------------------
# Declarative base shared by all models
# ------------------------------------------------------------------
class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


# ------------------------------------------------------------------
# FastAPI dependency
# ------------------------------------------------------------------
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Yield an async database session for a single request.
    The session is committed on success and rolled back on exception,
    then closed in all cases.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
