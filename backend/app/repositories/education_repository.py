"""
Education repository - async SQLAlchemy queries for tbl_education_record.
"""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.education_record import EducationRecord
from app.schemas.education import EducationRecordCreate, EducationRecordUpdate


class EducationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_for_citizen(self, citizen_id: uuid.UUID) -> Sequence[EducationRecord]:
        result = await self.db.execute(
            select(EducationRecord)
            .where(EducationRecord.citizen_id == citizen_id)
            .order_by(EducationRecord.created_at.asc())
        )
        return result.scalars().all()

    async def get_by_id(
        self, record_id: uuid.UUID, citizen_id: uuid.UUID
    ) -> Optional[EducationRecord]:
        result = await self.db.execute(
            select(EducationRecord)
            .where(
                EducationRecord.record_id == record_id,
                EducationRecord.citizen_id == citizen_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create(
        self, citizen_id: uuid.UUID, data: EducationRecordCreate
    ) -> EducationRecord:
        record = EducationRecord(
            citizen_id=citizen_id,
            level=data.level,
            details=data.details,
            is_current=data.is_current,
            passing_year=data.passing_year,
            percentage=data.percentage,
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def update(
        self, record_id: uuid.UUID, citizen_id: uuid.UUID, data: EducationRecordUpdate
    ) -> Optional[EducationRecord]:
        record = await self.get_by_id(record_id, citizen_id)
        if record is None:
            return None
        if data.level is not None:
            record.level = data.level
        if data.details is not None:
            record.details = data.details
        if data.is_current is not None:
            record.is_current = data.is_current
        if data.passing_year is not None:
            record.passing_year = data.passing_year
        if data.percentage is not None:
            record.percentage = data.percentage
        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def delete(self, record_id: uuid.UUID, citizen_id: uuid.UUID) -> bool:
        record = await self.get_by_id(record_id, citizen_id)
        if record is None:
            return False
        await self.db.delete(record)
        await self.db.flush()
        return True
