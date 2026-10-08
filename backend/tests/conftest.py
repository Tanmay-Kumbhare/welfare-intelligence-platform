"""
Shared pytest fixtures for the backend test suite.
"""

from __future__ import annotations

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings

_test_engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
_TestSession = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db() -> AsyncSession:
    """Yield an async session whose transaction is always rolled back."""
    async with _TestSession() as session:
        try:
            yield session
        finally:
            await session.rollback()
