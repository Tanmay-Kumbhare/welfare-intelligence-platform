import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.api.v1.deps import get_optional_user, require_same_citizen
from app.database import get_db
from app.models.auth import UserAccount
from app.schemas.citizen import (
    CitizenCreate,
    CitizenResponse,
    CitizenUpdate,
    CitizenUpdateResponse,
)
from app.schemas.profile_audit import ProfileAuditResponse
from app.services.citizen_service import CitizenService
from app.services.profile_sync_service import ProfileSyncService

router = APIRouter()


@router.post("/", response_model=CitizenResponse, status_code=status.HTTP_201_CREATED)
async def register_citizen(
    data: CitizenCreate,
    current_user: Optional[UserAccount] = Depends(get_current_user_optional),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = CitizenService(db)
    user_id = current_user.user_id if current_user else None
    return await service.register_citizen(data, user_id=user_id)


@router.get("/{citizen_id}", response_model=CitizenResponse)
async def get_citizen(
    citizen_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_optional_user),
) -> Any:
    service = CitizenService(db)
    citizen = await service.get_citizen(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")
    # Authenticated callers may only read their own profile (admins excepted).
    await require_same_citizen(user, citizen_id, db)
    return citizen


@router.put("/{citizen_id}", response_model=CitizenUpdateResponse)
async def update_citizen(
    citizen_id: uuid.UUID,
    data: CitizenUpdate,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_optional_user),
) -> Any:
    # Ownership first: an authenticated user must not edit another citizen.
    await require_same_citizen(user, citizen_id, db)
    service = CitizenService(db)
    citizen = await service.update_citizen(citizen_id, data)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")
    # Keep the profile-fact layer in step with the profile edit — the
    # eligibility engine reads facts, not profile columns, and a direct
    # edit used to be invisible to it until the next full form submission.
    sync = ProfileSyncService(db)
    sync_summary = await sync.sync_facts_from_profile(citizen_id)
    return {
        **_citizen_response_dict(citizen),
        "fact_sync": sync_summary,
    }


def _citizen_response_dict(citizen) -> dict:
    return CitizenResponse.model_validate(citizen).model_dump()


@router.get("/audit/{citizen_id}", response_model=ProfileAuditResponse)
async def audit_citizen_profile(
    citizen_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_optional_user),
) -> Any:
    """
    Audits a citizen profile for conflicting facts, stale records,
    document mismatches, and missing information. Read-only.
    """
    await require_same_citizen(user, citizen_id, db)

    from app.repositories.citizen_repository import CitizenRepository
    from app.repositories.scheme_repository import SchemeRepository
    from app.services.document_service import DocumentService
    from app.services.profile_audit_service import ProfileAuditService

    citizen_repo = CitizenRepository(db)
    citizen = await citizen_repo.get_full_profile(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")

    scheme_repo = SchemeRepository(db)
    schemes = await scheme_repo.get_all_active_for_evaluation()

    doc_service = DocumentService(db)
    documents = await doc_service.get_citizen_documents(citizen_id)

    return ProfileAuditService.audit_citizen_profile(
        citizen=citizen,
        schemes=schemes,
        documents=documents,
    )
