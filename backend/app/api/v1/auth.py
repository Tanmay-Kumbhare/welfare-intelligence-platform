"""
Auth API routes.

Public Email/Password:
  POST /auth/register
  POST /auth/login

Google OAuth 2.0 / OpenID Connect:
  GET  /auth/google/url
  POST /auth/google/callback

DigiLocker OAuth 2.0:
  GET  /auth/digilocker/url
  POST /auth/digilocker/callback

Protected / Session:
  GET  /auth/me
  POST /auth/logout
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import _extract_bearer_token, get_current_user
from app.auth.oauth import (
    OAuthConfigurationError,
    OAuthVerificationError,
    exchange_digilocker_code,
    exchange_google_code,
    generate_code_challenge,
    generate_code_verifier,
    generate_oauth_state,
    get_digilocker_auth_url,
    get_digilocker_user_info,
    get_google_auth_url,
    get_google_user_info,
    verify_oauth_state,
)
from app.database import get_db
from app.models.auth import UserAccount
from app.schemas.citizen import CitizenCreate
from app.services.auth_service import (
    AuthService,
    AuthServiceError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
)

router = APIRouter()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    citizen: CitizenCreate


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    token: str
    user_id: uuid.UUID
    email: str


class MeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    full_name: str | None = None
    citizen_id: uuid.UUID | None = None
    citizen_name: str | None = None


class OAuthUrlResponse(BaseModel):
    url: str
    state: str
    code_verifier: Optional[str] = None


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str
    code_verifier: Optional[str] = None


def _citizen_body_from_create(citizen_create: CitizenCreate) -> dict:
    return {
        "full_name": citizen_create.full_name,
        "date_of_birth": citizen_create.date_of_birth,
        "gender": citizen_create.gender,
        "mobile_number": citizen_create.mobile_number,
        "email_id": citizen_create.email_id,
        "citizen_type": citizen_create.citizen_type,
        "demographic": citizen_create.demographic.model_dump(),
        "financial": citizen_create.financial.model_dump(),
        "location": citizen_create.location.model_dump(),
    }


# ---------------------------------------------------------------------------
# Email & Password Flow
# ---------------------------------------------------------------------------

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = AuthService(db)
    try:
        user, _ = await service.register(
            email=body.email,
            password=body.password,
            citizen_data=_citizen_body_from_create(body.citizen),
        )
    except UserAlreadyExistsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    user, token = await service.login(body.email, body.password)
    return TokenResponse(
        token=token,
        user_id=user.user_id,
        email=user.email,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = AuthService(db)
    try:
        user, token = await service.login(body.email, body.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    return TokenResponse(
        token=token,
        user_id=user.user_id,
        email=user.email,
    )


# ---------------------------------------------------------------------------
# Google OAuth 2.0 / OpenID Connect Flow
# ---------------------------------------------------------------------------

@router.get("/google/url", response_model=OAuthUrlResponse)
async def google_auth_url(
    redirect_path: str = Query("/", description="Destination path after login"),
) -> Any:
    """Generate official Google OAuth 2.0 authorization URL with state & PKCE."""
    try:
        state = generate_oauth_state("GOOGLE", redirect_path)
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)
        url = get_google_auth_url(state, code_challenge)
        return OAuthUrlResponse(url=url, state=state, code_verifier=code_verifier)
    except OAuthConfigurationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/google/callback", response_model=TokenResponse)
async def google_callback(
    body: OAuthCallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Handle Google OAuth code exchange, verify ID token, and create application session."""
    try:
        verify_oauth_state(body.state, "GOOGLE")
        token_data = await exchange_google_code(body.code, body.code_verifier)
        user_info = await get_google_user_info(token_data["access_token"])
    except (OAuthConfigurationError, OAuthVerificationError) as exc:
        status_code = getattr(exc, "status_code", 400)
        raise HTTPException(status_code=status_code, detail=str(exc.detail))

    google_id = user_info.get("sub")
    email = user_info.get("email")
    email_verified = user_info.get("email_verified", False)
    name = user_info.get("name")

    if not google_id or not email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google profile did not contain required identity fields.",
        )

    service = AuthService(db)
    try:
        user, token = await service.authenticate_google_user(
            google_id=google_id,
            email=email,
            email_verified=bool(email_verified),
            full_name=name,
        )
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    return TokenResponse(
        token=token,
        user_id=user.user_id,
        email=user.email,
    )


# ---------------------------------------------------------------------------
# DigiLocker / MeriPehchaan OAuth 2.0 Flow
# ---------------------------------------------------------------------------

@router.get("/digilocker/url", response_model=OAuthUrlResponse)
async def digilocker_auth_url(
    redirect_path: str = Query("/", description="Destination path after login"),
) -> Any:
    """Generate official DigiLocker OAuth authorization URL with state & PKCE."""
    try:
        state = generate_oauth_state("DIGILOCKER", redirect_path)
        code_verifier = generate_code_verifier()
        code_challenge = generate_code_challenge(code_verifier)
        url = get_digilocker_auth_url(state, code_challenge)
        return OAuthUrlResponse(url=url, state=state, code_verifier=code_verifier)
    except OAuthConfigurationError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post("/digilocker/callback", response_model=TokenResponse)
async def digilocker_callback(
    body: OAuthCallbackRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Handle DigiLocker OAuth code exchange, verify user details, and create application session."""
    if not body.code_verifier:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_verifier is required for DigiLocker PKCE callback.",
        )

    try:
        verify_oauth_state(body.state, "DIGILOCKER")
        token_data = await exchange_digilocker_code(body.code, body.code_verifier)
        user_info = await get_digilocker_user_info(token_data["access_token"])
    except (OAuthConfigurationError, OAuthVerificationError) as exc:
        status_code = getattr(exc, "status_code", 400)
        raise HTTPException(status_code=status_code, detail=str(exc.detail))

    # DigiLocker response: digilockerid / sub / name / email / dob / gender
    digilocker_id = (
        user_info.get("digilockerid")
        or user_info.get("sub")
        or user_info.get("digilocker_id")
    )
    if not digilocker_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="DigiLocker did not return a valid user identifier.",
        )

    name = user_info.get("name")
    email = user_info.get("email")
    dob = user_info.get("dob")
    gender = user_info.get("gender")

    service = AuthService(db)
    try:
        user, token = await service.authenticate_digilocker_user(
            digilocker_id=str(digilocker_id),
            name=name,
            email=email,
            dob=dob,
            gender=gender,
        )
    except AuthServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    return TokenResponse(
        token=token,
        user_id=user.user_id,
        email=user.email,
    )


# ---------------------------------------------------------------------------
# Current User & Logout
# ---------------------------------------------------------------------------

@router.get("/me", response_model=MeResponse)
async def me(
    current_user: UserAccount = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Return identity and linked citizen profile of the authenticated user."""
    service = AuthService(db)
    citizen = await service.get_citizen_for_user(current_user)
    return MeResponse(
        user_id=current_user.user_id,
        email=current_user.email,
        full_name=current_user.full_name,
        citizen_id=citizen.citizen_id if citizen is not None else None,
        citizen_name=citizen.full_name if citizen is not None else None,
    )


@router.post("/logout", response_model=None)
async def logout(
    authorization: str = Header(..., description="Bearer token to invalidate"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Invalidate current session token."""
    token = _extract_bearer_token(authorization)
    if token:
        service = AuthService(db)
        await service.logout(token)
    return {"ok": True}
