"""
Shared FastAPI dependencies for route-level authorization.

The backend is the authoritative security boundary: frontend gates
(AdminGate etc.) are UX only. Every /admin/* route must depend on
require_admin so a citizen manually calling the API receives 403.
"""

from __future__ import annotations

import uuid

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


async def get_optional_user(
    authorization: str | None = Header(None, description="Bearer token"),
    db: AsyncSession = Depends(get_db),
) -> UserAccount | None:
    """Resolve the bearer token when one is present, else None (anonymous).

    A present-but-invalid token still raises 401 — anonymous fallback is
    never used to bypass a rejected credential.
    """
    if not authorization:
        return None
    return await get_authenticated_user(authorization=authorization, db=db)


async def require_same_citizen(
    user: UserAccount | None,
    citizen_id: uuid.UUID,
    db: AsyncSession,
) -> None:
    """Ownership guard for citizen-scoped endpoints that historically took a
    client-supplied citizen_id (guest flow).

    When the request is authenticated, the citizen_id must belong to the
    authenticated user — otherwise another citizen's profile, submissions,
    answers, or assessments could be read/written by anyone who obtains the
    UUID. ADMINs bypass (they have the dedicated admin API). Anonymous
    requests keep the legacy behavior so the pre-auth guest flow still works.
    """
    if user is None:
        return
    service = AuthService(db)
    roles = await service.get_roles_for_user(user)
    if "ADMIN" in roles:
        return
    citizen = await service.get_citizen_for_user(user)
    if citizen is None or citizen.citizen_id != citizen_id:
        raise HTTPException(
            status_code=403,
            detail="You can only access your own citizen profile",
        )


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
