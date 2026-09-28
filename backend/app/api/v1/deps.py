"""
Shared FastAPI dependencies for route-level authorization.

The backend is the authoritative security boundary: frontend gates
(AdminGate etc.) are UX only. Every /admin/* route must depend on
require_admin so a citizen manually calling the API receives 403.
"""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.auth import UserAccount
from app.services.auth_service import (
    AuthService,
    SessionExpiredError,
    UnauthorizedError,
)


async def get_authenticated_user(
    authorization: str | None = Header(None, description="Bearer token"),
    db: AsyncSession = Depends(get_db),
) -> UserAccount:
    """Resolve the request's bearer token to a UserAccount or raise 401."""
    if not authorization:
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = (
        authorization.removeprefix("Bearer ")
        if authorization.startswith("Bearer ")
        else authorization
    )
    service = AuthService(db)
    try:
        return await service.get_authenticated_user(token)
    except (UnauthorizedError, SessionExpiredError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


async def require_admin(
    user: UserAccount = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> UserAccount:
    """
    Allow the request only for users holding the ADMIN role.

    401 for missing/invalid tokens (via get_authenticated_user),
    403 for authenticated non-admins.
    """
    service = AuthService(db)
    roles = await service.get_roles_for_user(user)
    if "ADMIN" not in roles:
        raise HTTPException(
            status_code=403,
            detail="Administrator privileges required",
        )
    return user
