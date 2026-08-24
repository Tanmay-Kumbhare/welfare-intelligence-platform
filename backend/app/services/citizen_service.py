"""
Citizen service — orchestrates citizen domain operations.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.citizen import CitizenMaster
from app.repositories.citizen_repository import CitizenRepository
from app.schemas.citizen import CitizenCreate


class CitizenService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = CitizenRepository(db)

    async def register_citizen(self, data: CitizenCreate) -> CitizenMaster:
        # Additional business logic/validation could go here
        return await self.repo.create(data)

    async def get_citizen(self, citizen_id: uuid.UUID) -> Optional[CitizenMaster]:
        return await self.repo.get_by_id(citizen_id)
