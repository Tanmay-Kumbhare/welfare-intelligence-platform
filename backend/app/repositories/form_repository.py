"""
Form repository — async SQLAlchemy queries for form definition reads.
No business logic here; only data access.
"""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.form import (
    FormCondition,
    FormDefinition,
    FormQuestion,
    FormSection,
)


class FormRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _hierarchy_options() -> tuple:
        """
        Eager-load the full form hierarchy in a fixed number of queries:
          form -> sections -> questions -> options
                                        -> conditions -> depends_on_question
        Branching loader paths are declared separately from the shared
        form -> sections -> questions prefix.
        """
        to_questions = selectinload(FormDefinition.sections).selectinload(
            FormSection.questions
        )
        return (
            to_questions.selectinload(FormQuestion.options),
            to_questions.selectinload(FormQuestion.conditions).selectinload(
                FormCondition.depends_on_question
            ),
        )

    async def list_active_versions(
        self, target_citizen_type: Optional[str] = None
    ) -> Sequence[FormDefinition]:
        """
        All ACTIVE form versions (any form_code), highest version first.
        The service reduces this to the latest active version per form_code
        for the list endpoint.
        """
        stmt = (
            select(FormDefinition)
            .where(FormDefinition.status == "ACTIVE")
            .options(*self._hierarchy_options())
            .order_by(FormDefinition.form_code, FormDefinition.version.desc())
        )
        if target_citizen_type is not None:
            stmt = stmt.where(FormDefinition.target_citizen_type == target_citizen_type)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_by_id(self, form_id: uuid.UUID) -> Optional[FormDefinition]:
        """Fetch one form version by primary key (any status)."""
        result = await self.db.execute(
            select(FormDefinition)
            .where(FormDefinition.form_id == form_id)
            .options(*self._hierarchy_options())
        )
        return result.scalar_one_or_none()

    async def get_active_by_code(self, form_code: str) -> Optional[FormDefinition]:
        """Highest ACTIVE version of a form (form_code is shared by versions)."""
        result = await self.db.execute(
            select(FormDefinition)
            .where(FormDefinition.form_code == form_code, FormDefinition.status == "ACTIVE")
            .options(*self._hierarchy_options())
            .order_by(FormDefinition.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_code_and_version(
        self, form_code: str, version: int
    ) -> Optional[FormDefinition]:
        """
        A specific form version regardless of status. The service decides how
        to treat non-ACTIVE rows (they are listable via /versions but only
        ACTIVE ones are rendered by the default read endpoints).
        """
        result = await self.db.execute(
            select(FormDefinition)
            .where(FormDefinition.form_code == form_code, FormDefinition.version == version)
            .options(*self._hierarchy_options())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_versions(self, form_code: str) -> Sequence[FormDefinition]:
        """All versions of a form (any status), newest first."""
        result = await self.db.execute(
            select(FormDefinition)
            .where(FormDefinition.form_code == form_code)
            .order_by(FormDefinition.version.desc())
        )
        return result.scalars().all()
