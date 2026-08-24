import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.scheme import SchemeDetailResponse, SchemeResponse
from app.services.scheme_service import SchemeService

router = APIRouter()


@router.get("/", response_model=List[SchemeResponse])
async def list_schemes(
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = SchemeService(db)
    return await service.get_all_schemes()


@router.get("/{scheme_id}", response_model=SchemeDetailResponse)
async def get_scheme(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> Any:
    service = SchemeService(db)
    scheme = await service.get_scheme(scheme_id)
    if not scheme:
        raise HTTPException(status_code=404, detail="Scheme not found")
    return scheme
