"""
Scheme repository — async SQLAlchemy queries for scheme domain tables.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.scheme import SchemeMaster


class SchemeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all_active(self) -> Sequence[SchemeMaster]:
        """Fetch all active schemes with rules and documents eagerly loaded."""
        result = await self.db.execute(
            select(SchemeMaster)
            .where(SchemeMaster.status == "ACTIVE")
            .options(
                selectinload(SchemeMaster.rule_groups).selectinload(
                    SchemeMaster.rule_groups.property.mapper.class_.rules
                ),
                selectinload(SchemeMaster.documents),
            )
        )
        return result.scalars().all()

    async def get_by_id(self, scheme_id: uuid.UUID) -> SchemeMaster | None:
        """Fetch a specific scheme with rules and documents eagerly loaded."""
        result = await self.db.execute(
            select(SchemeMaster)
            .where(SchemeMaster.scheme_id == scheme_id)
            .options(
                selectinload(SchemeMaster.rule_groups).selectinload(
                    SchemeMaster.rule_groups.property.mapper.class_.rules
                ),
                selectinload(SchemeMaster.documents),
            )
        )
        return result.scalar_one_or_none()
