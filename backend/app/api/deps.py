"""
FastAPI dependencies for authentication and database sessions.
"""

from __future__ import annotations

from typing import Optional

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.auth import UserAccount
from app.services.auth_service import (
    AuthService,
    SessionExpiredError,
    UnauthorizedError,
)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    trimmed = authorization.strip()
    if trimmed.lower().startswith("bearer "):
        return trimmed[7:].strip()
    return trimmed


async def get_current_user(
    authorization: str = Header(..., description="Bearer <session_token>"),
    db: AsyncSession = Depends(get_db),
) -> UserAccount:
    """
    Standard dependency resolving the authenticated UserAccount from the session token.
    Raises 401 if missing, invalid, or expired.
    """
    token = _extract_bearer_token(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header is required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    service = AuthService(db)
    try:
        user = await service.get_authenticated_user(token)
    except (UnauthorizedError, SessionExpiredError) as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_current_user_optional(
    authorization: Optional[str] = Header(None, description="Optional Bearer <session_token>"),
    db: AsyncSession = Depends(get_db),
) -> Optional[UserAccount]:
    """
    Optional user dependency. Returns None if unauthenticated instead of raising 401.
    """
    token = _extract_bearer_token(authorization)
    if not token:
        return None

    service = AuthService(db)
    try:
        return await service.get_authenticated_user(token)
    except (UnauthorizedError, SessionExpiredError):
        return None
