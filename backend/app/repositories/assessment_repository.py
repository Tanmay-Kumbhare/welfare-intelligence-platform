"""
Assessment repository — async SQLAlchemy queries for eligibility assessments.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Sequence

from sqlalchemy import func, select
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
                "updated_at": func.clock_timestamp(),
            },
        ).returning(EligibilityAssessment)

        result = await self.db.execute(
            stmt,
            execution_options={"populate_existing": True},
        )
        return result.scalar_one()

    async def upsert_assessments(
        self,
        assessments: list[dict[str, Any]],
    ) -> Sequence[EligibilityAssessment]:
        """Persist a citizen's evaluation results in one PostgreSQL upsert.

        Eligibility evaluates every active scheme together.  Sending one
        insert per scheme made the write path sequential even though all
        rows share the same conflict target and transaction.  This preserves
        the existing latest-assessment semantics and response shape while
        reducing those database round trips to one statement.
        """
        if not assessments:
            return []

        stmt = insert(EligibilityAssessment).values(assessments)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_citizen_scheme_assessment",
            set_={
                "eligibility_result": stmt.excluded.eligibility_result,
                "confidence_score": stmt.excluded.confidence_score,
                "reason": stmt.excluded.reason,
                "evaluation_details": stmt.excluded.evaluation_details,
                "assessment_date": stmt.excluded.assessment_date,
                "updated_at": func.clock_timestamp(),
            },
        ).returning(EligibilityAssessment)

        result = await self.db.execute(
            stmt,
            execution_options={"populate_existing": True},
        )
        return result.scalars().all()

    async def get_citizen_assessments(
        self,
        citizen_id: uuid.UUID,
        active_only: bool = False,
        as_of: date | None = None,
    ) -> Sequence[EligibilityAssessment]:
        """
        Fetch all assessments for a citizen, including the scheme and required documents.
        When active_only is True, filters to schemes that are ACTIVE and within validity dates.
        """
        query = (
            select(EligibilityAssessment)
            .where(EligibilityAssessment.citizen_id == citizen_id)
        )
        if active_only:
            from app.repositories.scheme_repository import SchemeRepository

            query = query.join(EligibilityAssessment.scheme).where(
                *SchemeRepository.active_and_valid_criterion(as_of)
            )

        query = query.options(
            selectinload(EligibilityAssessment.scheme).selectinload(
                SchemeMaster.documents
            )
        )
        result = await self.db.execute(query)
        return result.scalars().all()
