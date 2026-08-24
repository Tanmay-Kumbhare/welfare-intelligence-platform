"""
Assessment repository — async SQLAlchemy queries for eligibility assessments.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.assessment import EligibilityAssessment
from app.models.scheme import SchemeMaster


class AssessmentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def upsert_assessment(
        self,
        citizen_id: uuid.UUID,
        scheme_id: uuid.UUID,
        eligibility_result: bool,
        reason: str | None,
        evaluation_details: dict[str, Any],
    ) -> EligibilityAssessment:
        """
        Create or update an assessment for a citizen-scheme pair.
        Uses PostgreSQL ON CONFLICT DO UPDATE.
        """
        stmt = insert(EligibilityAssessment).values(
            citizen_id=citizen_id,
            scheme_id=scheme_id,
            eligibility_result=eligibility_result,
            reason=reason,
            evaluation_details=evaluation_details,
        )

        # On conflict (citizen_id, scheme_id), update the result and details
        stmt = stmt.on_conflict_do_update(
            constraint="uq_citizen_scheme_assessment",
            set_={
                "eligibility_result": stmt.excluded.eligibility_result,
                "reason": stmt.excluded.reason,
                "evaluation_details": stmt.excluded.evaluation_details,
                "assessment_date": stmt.excluded.assessment_date,
            },
        ).returning(EligibilityAssessment)

        result = await self.db.execute(stmt)
        return result.scalar_one()

    async def get_citizen_assessments(
        self, citizen_id: uuid.UUID
    ) -> Sequence[EligibilityAssessment]:
        """
        Fetch all assessments for a citizen, including the scheme and required documents.
        """
        result = await self.db.execute(
            select(EligibilityAssessment)
            .where(EligibilityAssessment.citizen_id == citizen_id)
            .options(
                selectinload(EligibilityAssessment.scheme).selectinload(
                    SchemeMaster.documents
                )
            )
        )
        return result.scalars().all()
