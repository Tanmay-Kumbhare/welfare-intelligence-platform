import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.citizen import (
    CitizenCreate,
    CitizenResponse,
    CitizenUpdate,
    CitizenUpdateResponse,
)
from app.services.citizen_service import CitizenService
from app.services.profile_sync_service import ProfileSyncService

router = APIRouter()


@router.post("/", response_model=CitizenResponse, status_code=status.HTTP_201_CREATED)
async def register_citizen(
    data: CitizenCreate,
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = CitizenService(db)
    return await service.register_citizen(data)


@router.get("/{citizen_id}", response_model=CitizenResponse)
async def get_citizen(
    citizen_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = CitizenService(db)
    citizen = await service.get_citizen(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")
    return citizen


@router.put("/{citizen_id}", response_model=CitizenUpdateResponse)
async def update_citizen(
    citizen_id: uuid.UUID,
    data: CitizenUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
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
