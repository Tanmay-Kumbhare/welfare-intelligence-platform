import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.citizen import CitizenCreate, CitizenResponse
from app.services.citizen_service import CitizenService

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
