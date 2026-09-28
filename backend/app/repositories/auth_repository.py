"""
Auth repository: user, role, and session data access only.
No business logic here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import UserAccount, UserRole, UserSession

KNOWN_ROLES = ("CITIZEN", "ADMIN")


class AuthRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_email(self, email: str) -> UserAccount | None:
        result = await self.db.execute(
            select(UserAccount).where(UserAccount.email == email).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> UserAccount | None:
        result = await self.db.execute(
            select(UserAccount).where(UserAccount.user_id == user_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        email: str,
        password_hash: str,
        provider: str = "EMAIL_PASSWORD",
    ) -> UserAccount:
        user = UserAccount(
            email=email,
            password_hash=password_hash,
            provider=provider,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def add_role(self, user_id: uuid.UUID, role: str) -> UserRole:
        if role not in KNOWN_ROLES:
            raise ValueError(f"Unknown user role: {role}")
        membership = UserRole(user_id=user_id, role=role)
        self.db.add(membership)
        await self.db.flush()
        return membership

    async def get_roles(self, user_id: uuid.UUID) -> list[str]:
        result = await self.db.execute(
            select(UserRole.role).where(UserRole.user_id == user_id)
        )
        return [row.role for row in result.scalars().all()]

    async def find_session_by_token(self, token_hash: str) -> UserSession | None:
        result = await self.db.execute(
            select(UserSession).where(UserSession.token_hash == token_hash).limit(1)
        )
        return result.scalar_one_or_none()

    async def create_session(
        self,
        user_id: uuid.UUID,
        token: str,
        ttl_hours: float = 24.0,
    ) -> UserSession:
        now = datetime.now(timezone.utc)
        session = UserSession(
            user_id=user_id,
            token_hash=token,
            expires_at=now + timedelta(hours=ttl_hours),
            last_used_at=now,
        )
        self.db.add(session)
        await self.db.flush()
        return session

    async def refresh_session_last_used(self, session: UserSession) -> None:
        session.last_used_at = datetime.now(timezone.utc)
        await self.db.flush()

    async def invalidate_sessions_for_user(self, user_id: uuid.UUID) -> None:
        result = await self.db.execute(
            select(UserSession).where(UserSession.user_id == user_id)
        )
        for session in result.scalars().all():
            await self.db.delete(session)
        await self.db.flush()
