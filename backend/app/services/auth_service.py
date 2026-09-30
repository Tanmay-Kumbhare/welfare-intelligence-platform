"""
Auth service: registration, login, session issuance, logout, current-user
resolution, and OAuth unification for Google and DigiLocker.

All authentication methods map to the single UserAccount entity and issue
the same 24-hour server-side UserSession.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.password import hash_password, verify_password
from app.auth.session import issue_raw_token
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

        full_name = citizen_data.get("full_name") if citizen_data else None
        password_hash = hash_password(password)
        user = await self.users.create_user(
            email=email,
            password_hash=password_hash,
            provider="EMAIL_PASSWORD",
            full_name=full_name,
            email_verified=False,
        )
        await self.users.add_role(user.user_id, "CITIZEN")

        citizen: CitizenMaster | None = None
        if citizen_data is not None:
            citizen = await self._create_citizen_profile(user.user_id, citizen_data)

        return user, citizen

    async def login(self, email: str, password: str) -> tuple[UserAccount, str]:
        user = await self.users.get_by_email(email)
        if user is None:
            raise InvalidCredentialsError()

        # If user registered with OAuth only (password_hash is None)
        if not user.password_hash:
            provider_name = user.provider or "social login"
            raise InvalidCredentialsError(
                detail=f"This account was registered using {provider_name}. Please continue with {provider_name}."
            )

        if not verify_password(password, user.password_hash):
            raise InvalidCredentialsError()

        token = issue_raw_token()
        await self.users.create_session(
            user.user_id,
            token,
            ttl_hours=DEFAULT_SESSION_TTL_HOURS,
        )
        return user, token

    async def authenticate_google_user(
        self,
        google_id: str,
        email: str,
        email_verified: bool,
        full_name: str | None = None,
    ) -> tuple[UserAccount, str]:
        """
        Authenticate or register a Google user.
        - Matches existing user by google_id
        - Links to existing user if email is verified by Google
        - Creates a new unified UserAccount otherwise
        - Issues the standard application session
        """
        if not email_verified:
            raise AuthServiceError(
                detail="Google account email is not verified.",
                status_code=400,
            )

        # 1. Existing user by Google ID
        user = await self.users.get_by_google_id(google_id)
        if user is not None:
            if full_name and not user.full_name:
                user.full_name = full_name
                await self.db.flush()
            token = issue_raw_token()
            await self.users.create_session(user.user_id, token, ttl_hours=DEFAULT_SESSION_TTL_HOURS)
            return user, token

        # 2. Existing user by verified Email -> Link Google ID
        user = await self.users.get_by_email(email)
        if user is not None:
            await self.users.link_google_id(user, google_id, full_name)
            token = issue_raw_token()
            await self.users.create_session(user.user_id, token, ttl_hours=DEFAULT_SESSION_TTL_HOURS)
            return user, token

        # 3. New User Account
        user = await self.users.create_oauth_user(
            email=email,
            provider="GOOGLE",
            google_id=google_id,
            full_name=full_name,
            email_verified=True,
        )
        await self.users.add_role(user.user_id, "CITIZEN")

        token = issue_raw_token()
        await self.users.create_session(user.user_id, token, ttl_hours=DEFAULT_SESSION_TTL_HOURS)
        return user, token

    async def authenticate_digilocker_user(
        self,
        digilocker_id: str,
        name: str | None = None,
        email: str | None = None,
        dob: str | None = None,
        gender: str | None = None,
    ) -> tuple[UserAccount, str]:
        """
        Authenticate or register a DigiLocker user.
        - Matches existing user by digilocker_id
        - Links to existing user if verified email matches
        - Creates a new unified UserAccount otherwise
        - Issues the standard application session
        """
        if not digilocker_id:
            raise AuthServiceError(detail="DigiLocker identifier is missing", status_code=400)

        # 1. Existing user by DigiLocker ID
        user = await self.users.get_by_digilocker_id(digilocker_id)
        if user is not None:
            if name and not user.full_name:
                user.full_name = name
                await self.db.flush()
            token = issue_raw_token()
            await self.users.create_session(user.user_id, token, ttl_hours=DEFAULT_SESSION_TTL_HOURS)
            return user, token

        # 2. If email is provided and matches existing account -> Link DigiLocker ID
        if email:
            user = await self.users.get_by_email(email)
            if user is not None:
                await self.users.link_digilocker_id(user, digilocker_id, name)
                token = issue_raw_token()
                await self.users.create_session(user.user_id, token, ttl_hours=DEFAULT_SESSION_TTL_HOURS)
                return user, token

        # 3. New User Account
        # Fallback synthetic email if DigiLocker does not provide an email
        user_email = email or f"{digilocker_id.lower()}@digilocker.meripehchaan.gov.in"
        user = await self.users.create_oauth_user(
            email=user_email,
            provider="DIGILOCKER",
            digilocker_id=digilocker_id,
            full_name=name,
            email_verified=bool(email),
        )
        await self.users.add_role(user.user_id, "CITIZEN")

        token = issue_raw_token()
        await self.users.create_session(user.user_id, token, ttl_hours=DEFAULT_SESSION_TTL_HOURS)
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
        new_token = issue_raw_token()
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
