import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_optional
from app.database import get_db
from app.models.auth import UserAccount
from app.schemas.citizen import CitizenCreate, CitizenResponse, CitizenUpdate
from app.services.citizen_service import CitizenService

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
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = CitizenService(db)
    citizen = await service.get_citizen(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")
    return citizen


@router.put("/{citizen_id}", response_model=CitizenResponse)
async def update_citizen(
    citizen_id: uuid.UUID,
    data: CitizenUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = CitizenService(db)
    citizen = await service.update_citizen(citizen_id, data)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")
    return citizen
