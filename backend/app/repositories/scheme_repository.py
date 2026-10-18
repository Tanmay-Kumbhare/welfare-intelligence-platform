"""
Scheme repository — async SQLAlchemy queries for scheme domain tables.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.scheme import SchemeMaster


class SchemeRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_all_active(self, as_of: date | None = None) -> Sequence[SchemeMaster]:
        """Fetch all active schemes with rules and documents eagerly loaded.

        Only schemes that are ACTIVE, have started (start_date is null or <= as_of),
        and have not expired (end_date is null or >= as_of) are returned.
        """
        ref_date = as_of if as_of is not None else datetime.now(timezone.utc).date()
        result = await self.db.execute(
            select(SchemeMaster)
            .where(
                SchemeMaster.status == "ACTIVE",
                or_(SchemeMaster.start_date.is_(None), SchemeMaster.start_date <= ref_date),
                or_(SchemeMaster.end_date.is_(None), SchemeMaster.end_date >= ref_date),
            )
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

    async def get_all_active_for_evaluation(
        self, as_of: date | None = None
    ) -> Sequence[SchemeMaster]:
        """Fetch only the rule graph required by the eligibility engine.

        Documents are presentation/application requirements and are not read
        while evaluating a citizen.  Joining the small current rule graph
        avoids separate scheme, group, and rule round trips; ``unique``
        restores one ORM scheme object per joined result set.
        Only schemes that are ACTIVE, have started (start_date is null or <= as_of),
        and have not expired (end_date is null or >= as_of) are returned.
        """
        ref_date = as_of if as_of is not None else datetime.now(timezone.utc).date()
        result = await self.db.execute(
            select(SchemeMaster)
            .where(
                SchemeMaster.status == "ACTIVE",
                or_(SchemeMaster.start_date.is_(None), SchemeMaster.start_date <= ref_date),
                or_(SchemeMaster.end_date.is_(None), SchemeMaster.end_date >= ref_date),
            )
            .options(
                joinedload(SchemeMaster.rule_groups).joinedload(
                    SchemeMaster.rule_groups.property.mapper.class_.rules
                )
            )
        )
        return result.unique().scalars().all()
