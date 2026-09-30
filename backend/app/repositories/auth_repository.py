"""
Auth repository: user, role, and session data access only.
No business logic here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.session import hash_session_token
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

    async def get_by_google_id(self, google_id: str) -> UserAccount | None:
        result = await self.db.execute(
            select(UserAccount).where(UserAccount.google_id == google_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_digilocker_id(self, digilocker_id: str) -> UserAccount | None:
        result = await self.db.execute(
            select(UserAccount).where(UserAccount.digilocker_id == digilocker_id).limit(1)
        )
        return result.scalar_one_or_none()

    async def create_user(
        self,
        email: str,
        password_hash: str | None,
        provider: str = "EMAIL_PASSWORD",
        full_name: str | None = None,
        email_verified: bool = False,
    ) -> UserAccount:
        user = UserAccount(
            email=email,
            password_hash=password_hash,
            provider=provider,
            full_name=full_name,
            email_verified=email_verified,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def create_oauth_user(
        self,
        email: str,
        provider: str,
        google_id: str | None = None,
        digilocker_id: str | None = None,
        full_name: str | None = None,
        email_verified: bool = True,
    ) -> UserAccount:
        user = UserAccount(
            email=email,
            password_hash=None,
            provider=provider,
            google_id=google_id,
            digilocker_id=digilocker_id,
            full_name=full_name,
            email_verified=email_verified,
        )
        self.db.add(user)
        await self.db.flush()
        return user

    async def link_google_id(
        self,
        user: UserAccount,
        google_id: str,
        full_name: str | None = None,
    ) -> UserAccount:
        user.google_id = google_id
        if full_name and not user.full_name:
            user.full_name = full_name
        user.email_verified = True
        await self.db.flush()
        return user

    async def link_digilocker_id(
        self,
        user: UserAccount,
        digilocker_id: str,
        full_name: str | None = None,
    ) -> UserAccount:
        user.digilocker_id = digilocker_id
        if full_name and not user.full_name:
            user.full_name = full_name
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

    async def find_session_by_token(self, token: str) -> UserSession | None:
        """
        Lookup session by raw token.
        Queries by SHA-256 digest, with fallback to raw token for any
        pre-existing unhashed sessions.
        """
        token_digest = hash_session_token(token)
        result = await self.db.execute(
            select(UserSession).where(
                or_(
                    UserSession.token_hash == token_digest,
                    UserSession.token_hash == token,
                )
            ).limit(1)
        )
        session = result.scalar_one_or_none()
        # Transparently upgrade legacy unhashed token row to hashed
        if session is not None and session.token_hash == token and token != token_digest:
            session.token_hash = token_digest
            await self.db.flush()
        return session

    async def create_session(
        self,
        user_id: uuid.UUID,
        raw_token: str,
        ttl_hours: float = 24.0,
    ) -> UserSession:
        now = datetime.now(timezone.utc)
        session = UserSession(
            user_id=user_id,
            token_hash=hash_session_token(raw_token),
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
