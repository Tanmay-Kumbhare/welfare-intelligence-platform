"""
Auth service: registration, login, session issuance, logout, and current-user
resolution.

This is deliberately focused on account and session lifecycle. Profile creation
is kept close to citizen service, but this service helps wire the link between
an authenticated user and their citizen profile.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password, verify_password
from app.models.auth import UserAccount
from app.models.citizen import CitizenMaster
from app.repositories.auth_repository import AuthRepository
from app.repositories.citizen_repository import CitizenRepository

DEFAULT_SESSION_TTL_HOURS = 24.0


class AuthServiceError(Exception):
    status_code: int = 400
    detail: str = "Auth service error"

    def __init__(self, *, detail: str | None = None, status_code: int | None = None) -> None:
        super().__init__(detail or self.detail)
        if detail is not None:
            self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class UserAlreadyExistsError(AuthServiceError):
    status_code = 409
    detail = "An account with this email already exists"


class InvalidCredentialsError(AuthServiceError):
    status_code = 401
    detail = "Invalid email or password"


class SessionExpiredError(AuthServiceError):
    status_code = 401
    detail = "Session has expired"


class UnauthorizedError(AuthServiceError):
    status_code = 401
    detail = "Not authenticated"


def _issue_token() -> str:
    return secrets.token_urlsafe(48)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = AuthRepository(db)
        self.citizens = CitizenRepository(db)

    async def register(
        self,
        email: str,
        password: str,
        citizen_data: dict | None = None,
    ) -> tuple[UserAccount, Optional[CitizenMaster]]:
        existing = await self.users.get_by_email(email)
        if existing is not None:
            raise UserAlreadyExistsError()

        password_hash = hash_password(password)
        user = await self.users.create_user(email, password_hash)
        await self.users.add_role(user.user_id, "CITIZEN")

        citizen: CitizenMaster | None = None
        if citizen_data is not None:
            citizen = await self._create_citizen_profile(user.user_id, citizen_data)

        return user, citizen

    async def login(self, email: str, password: str) -> tuple[UserAccount, str]:
        user = await self.users.get_by_email(email)
        if user is None:
            raise InvalidCredentialsError()

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        token = _issue_token()
        session = await self.users.create_session(
            user.user_id,
            token,
            ttl_hours=DEFAULT_SESSION_TTL_HOURS,
        )
        return user, token

    async def logout(self, token: str) -> None:
        session = await self.users.find_session_by_token(token)
        if session is not None:
            await self.users.db.delete(session)
            await self.users.db.flush()

    async def refresh_session(self, token: str) -> tuple[UserAccount, str]:
        session = await self.users.find_session_by_token(token)
        if session is None:
            raise SessionExpiredError()
        if session.expires_at <= datetime.now(timezone.utc):
            await self.users.db.delete(session)
            await self.users.db.flush()
            raise SessionExpiredError()

        await self.users.refresh_session_last_used(session)
        new_token = _issue_token()
        new_session = await self.users.create_session(
            session.user_id,
            new_token,
            ttl_hours=DEFAULT_SESSION_TTL_HOURS,
        )
        await self.users.db.delete(session)
        await self.users.db.flush()
        user = await self.users.get_by_id(session.user_id)
        if user is None:
            raise UnauthorizedError()
        return user, new_token

    async def get_authenticated_user(self, token: str) -> UserAccount:
        session = await self.users.find_session_by_token(token)
        if session is None:
            raise UnauthorizedError()
        if session.expires_at <= datetime.now(timezone.utc):
            await self.users.db.delete(session)
            await self.users.db.flush()
            raise SessionExpiredError()
        await self.users.refresh_session_last_used(session)
        user = await self.users.get_by_id(session.user_id)
        if user is None:
            raise UnauthorizedError()
        return user

    async def get_citizen_for_user(self, user: UserAccount) -> CitizenMaster | None:
        return await self.citizens.get_by_owning_user(user.user_id)

    async def _create_citizen_profile(
        self,
        user_id: uuid.UUID,
        data: dict,
    ) -> CitizenMaster:
        citizen = await self.citizens.create_for_user(user_id, data)
        return citizen
