"""
Submission repository — async SQLAlchemy queries for form submissions and
answers. No business logic here; only data access.
"""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.form import FormCondition, FormDefinition, FormQuestion, FormSection
from app.models.submission import FormAnswer, FormSubmission

_EDITABLE_STATUSES = ("DRAFT", "IN_PROGRESS")


class SubmissionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _loaded_options():
        """Eager-load answers and every form relationship the service reads.

        ``get_by_id`` uses ``populate_existing`` after an answer write.  A
        shallow form load would expire an already-loaded hierarchy and make a
        later ``form.sections`` access attempt an async lazy load.
        """
        to_questions = (
            selectinload(FormSubmission.form)
            .selectinload(FormDefinition.sections)
            .selectinload(FormSection.questions)
        )
        return (
            selectinload(FormSubmission.answers).selectinload(FormAnswer.question),
            to_questions.selectinload(FormQuestion.options),
            to_questions.selectinload(FormQuestion.conditions).selectinload(
                FormCondition.depends_on_question
            ),
        )

    async def create(self, submission: FormSubmission) -> FormSubmission:
        self.db.add(submission)
        await self.db.flush()
        return submission

    async def get_by_id(self, submission_id: uuid.UUID) -> Optional[FormSubmission]:
        # populate_existing: re-fetches relationships (answers) even when the
        # submission is already in the identity map, so progress recomputation
        # always sees answers added earlier in the same session.
        result = await self.db.execute(
            select(FormSubmission)
            .where(FormSubmission.submission_id == submission_id)
            .options(*self._loaded_options())
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def get_latest_editable_for_citizen_form(
        self, citizen_id: uuid.UUID, form_id: uuid.UUID
    ) -> Optional[FormSubmission]:
        """Most recent DRAFT/IN_PROGRESS submission for resume support."""
        result = await self.db.execute(
            select(FormSubmission)
            .where(
                FormSubmission.citizen_id == citizen_id,
                FormSubmission.form_id == form_id,
                FormSubmission.status.in_(_EDITABLE_STATUSES),
            )
            .order_by(FormSubmission.started_at.desc())
            .limit(1)
            .options(*self._loaded_options())
        )
        return result.scalar_one_or_none()

    async def get_latest_completed_for_citizen_form(
        self, citizen_id: uuid.UUID, form_id: uuid.UUID
    ) -> Optional[FormSubmission]:
        """Most recent COMPLETED submission — the authoritative record of the
        answers the citizen already gave, used to prefill re-visits so
        answered questions are never asked twice."""
        result = await self.db.execute(
            select(FormSubmission)
            .where(
                FormSubmission.citizen_id == citizen_id,
                FormSubmission.form_id == form_id,
                FormSubmission.status == "COMPLETED",
            )
            .order_by(FormSubmission.completed_at.desc())
            .limit(1)
            .options(*self._loaded_options())
        )
        return result.scalar_one_or_none()

    async def list_for_citizen_form_code(
        self, citizen_id: uuid.UUID, form_code: str
    ) -> Sequence[FormSubmission]:
        """All of a citizen's submissions for a form_code across every form
        version, with answers eager-loaded. Lets the saved-answers lookup
        heal history: an older version's answers still prefill the current
        version (matched by stable question_code)."""
        result = await self.db.execute(
            select(FormSubmission)
            .join(FormDefinition, FormDefinition.form_id == FormSubmission.form_id)
            .where(
                FormSubmission.citizen_id == citizen_id,
                FormDefinition.form_code == form_code,
            )
            .options(*self._loaded_options())
            .order_by(FormSubmission.started_at.desc())
            .limit(20)
        )
        return result.scalars().unique().all()

    async def get_answer(
        self, submission_id: uuid.UUID, question_id: uuid.UUID
    ) -> Optional[FormAnswer]:
        result = await self.db.execute(
            select(FormAnswer).where(
                FormAnswer.submission_id == submission_id,
                FormAnswer.question_id == question_id,
            )
        )
        return result.scalar_one_or_none()

    async def add_answer(self, answer: FormAnswer) -> FormAnswer:
        self.db.add(answer)
        await self.db.flush()
        return answer

    async def add_answers(self, answers: Sequence[FormAnswer]) -> None:
        """Batched insert: one flush for the whole payload instead of one
        round trip per answer (dominant cost on remote databases)."""
        if not answers:
            return
        self.db.add_all(answers)
        await self.db.flush()

    async def delete_answer(self, answer: FormAnswer) -> None:
        await self.db.delete(answer)
        await self.db.flush()

    async def delete_answers(self, answers: Sequence[FormAnswer]) -> None:
        """Batched delete: one flush for all cleared answers."""
        if not answers:
            return
        for answer in answers:
            await self.db.delete(answer)
        await self.db.flush()

    async def list_answers(self, submission_id: uuid.UUID) -> Sequence[FormAnswer]:
        result = await self.db.execute(
            select(FormAnswer).where(FormAnswer.submission_id == submission_id)
        )
        return result.scalars().all()

    async def get_form(self, form_id: uuid.UUID) -> Optional[FormDefinition]:
        result = await self.db.execute(
            select(FormDefinition).where(FormDefinition.form_id == form_id)
        )
        return result.scalar_one_or_none()
