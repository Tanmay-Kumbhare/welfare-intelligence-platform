"""
Auth API routes.

Public:
  POST /auth/register
  POST /auth/login

Protected:
  GET  /auth/me

Utility:
  POST /auth/logout   (invalidate current token)

Token handling for this stage:
  The frontend sends the token in Authorization: Bearer <token>.
  Register and login return the token in the response body.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.database import get_db
from app.schemas.citizen import CitizenCreate
from app.services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    UnauthorizedError,
    UserAlreadyExistsError,
    SessionExpiredError,
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
    roles: list[str] = []


class MeResponse(BaseModel):
    user_id: uuid.UUID
    email: str
    citizen_id: uuid.UUID | None = None
    citizen_name: str | None = None
    roles: list[str] = []


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


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=TokenResponse)
async def register(
    body: RegisterRequest,
    db=Depends(get_db),
) -> Any:
    service = AuthService(db)
    try:
        user, citizen = await service.register(
            email=body.email,
            password=body.password,
            citizen_data=_citizen_body_from_create(body.citizen),
        )
    except UserAlreadyExistsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    # Issue the first token after account + owned citizen profile are created.
    user, token = await service.login(body.email, body.password)
    roles = await service.get_roles_for_user(user)
    return TokenResponse(
        token=token,
        user_id=user.user_id,
        email=user.email,
        roles=roles,
    )


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db=Depends(get_db),
) -> Any:
    service = AuthService(db)
    try:
        user, token = await service.login(body.email, body.password)
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    # Roles ride along with the token response so the frontend can route
    # admins to /admin immediately without a second request.
    roles = await service.get_roles_for_user(user)
    return TokenResponse(
        token=token,
        user_id=user.user_id,
        email=user.email,
        roles=roles,
    )


@router.get("/me", response_model=MeResponse)
async def me(
    authorization: str = Header(..., description="Bearer token from Authorization header"),
    db=Depends(get_db),
) -> Any:
    token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else authorization
    service = AuthService(db)
    try:
        user = await service.get_authenticated_user(token)
    except (UnauthorizedError, SessionExpiredError) as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    citizen = await service.get_citizen_for_user(user)
    roles = await service.get_roles_for_user(user)
    return MeResponse(
        user_id=user.user_id,
        email=user.email,
        citizen_id=citizen.citizen_id if citizen is not None else None,
        citizen_name=citizen.full_name if citizen is not None else None,
        roles=roles,
    )


@router.post("/logout", response_model=None)
async def logout(
    authorization: str = Header(..., description="Bearer token to invalidate"),
    db=Depends(get_db),
) -> Any:
    token = authorization.removeprefix("Bearer ") if authorization.startswith("Bearer ") else authorization
    service = AuthService(db)
    try:
        _ = await service.get_authenticated_user(token)
    except (UnauthorizedError, SessionExpiredError):
        raise HTTPException(status_code=status.HTTP_200_OK, detail="Already invalid")

    await service.logout(token)
    return {"ok": True}
