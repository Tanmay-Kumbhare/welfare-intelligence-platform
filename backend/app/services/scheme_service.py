"""
Scheme service — orchestrates scheme operations.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheme import SchemeMaster
from app.repositories.scheme_repository import SchemeRepository


class SchemeService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = SchemeRepository(db)

    async def get_all_schemes(self) -> Sequence[SchemeMaster]:
        return await self.repo.get_all_active()

    async def get_scheme(self, scheme_id: uuid.UUID) -> SchemeMaster | None:
        return await self.repo.get_by_id(scheme_id)
