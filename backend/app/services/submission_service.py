"""
Submission service — orchestration for the submission lifecycle:
create draft → save progress (answers) → complete.

Design notes:
  - A submission is pinned to (form_id, form_version); answers always
    validate against the question set of that exact version. Version 1
    submissions never silently adopt version 2 questions (Part 12).
  - Draft/IN_PROGRESS saves are lenient: partial answers are fine and
    required validation only runs at completion time (Part 6).
  - Completion computes applicability from stored answers via the shared
    condition evaluator, so hidden required questions never block and
    hidden questions never enter the completion denominator (Parts 7/9).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Sequence

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.form import FormCondition, FormDefinition, FormQuestion
from app.models.submission import FormAnswer, FormSubmission
from app.repositories.citizen_repository import CitizenRepository
from app.repositories.form_repository import FormRepository
from app.repositories.submission_repository import SubmissionRepository
from app.schemas.form import (
    AnswerInput,
    EDITABLE_SUBMISSION_STATUSES,
    SubmissionAnswerResponse,
    SubmissionCreate,
    SubmissionResponse,
    SubmissionUpdate,
)
from app.services.form_logic import (
    CitizenNotFoundError,
    FormNotFoundError,
    IncompleteSubmissionError,
    InvalidStatusTransitionError,
    ProgressStats,
    QuestionNotInFormError,
    SubmissionNotFoundError,
    SubmissionNotEditableError,
    SubmissionOwnershipError,
    answer_value,
    compute_progress,
    is_answered,
    set_typed_value,
    validate_and_map_answer,
)

_COMPLETED = "COMPLETED"
_ABANDONED = "ABANDONED"
_EDITABLE = EDITABLE_SUBMISSION_STATUSES


@dataclass(frozen=True)
class _ConditionSnapshot:
    """Plain-object copy of the condition attributes used by the condition
    evaluator — immune to session expiry (see _refresh_progress)."""

    depends_on_question_id: uuid.UUID
    operator: str | None
    comparison_value: str | None
    action: str | None
    condition_group: int | None

    @classmethod
    def from_orm(cls, condition: FormCondition) -> "_ConditionSnapshot":
        return cls(
            depends_on_question_id=condition.depends_on_question_id,
            operator=condition.operator,
            comparison_value=condition.comparison_value,
            action=condition.action,
            condition_group=condition.condition_group,
        )


@dataclass(frozen=True)
class _QuestionSnapshot:
    """Plain-object copy of the question attributes used by progress/
    applicability computation — immune to session expiry."""

    question_id: uuid.UUID
    question_code: str | None
    question_type: str | None
    status: str | None
    required: bool
    conditions: tuple[_ConditionSnapshot, ...] = field(default=())

    @classmethod
    def from_orm(cls, question: FormQuestion) -> "_QuestionSnapshot":
        return cls(
            question_id=question.question_id,
            question_code=question.question_code,
            question_type=question.question_type,
            status=question.status,
            required=bool(question.required),
            conditions=tuple(
                _ConditionSnapshot.from_orm(c) for c in (question.conditions or [])
            ),
        )


class SubmissionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = SubmissionRepository(db)
        self.form_repo = FormRepository(db)
        self.citizen_repo = CitizenRepository(db)
    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _form_questions(self, form: FormDefinition) -> list[FormQuestion]:
        """
        Answerable questions of the submission's exact form version:
        active sections/questions only. `file` questions are display/upload
        placeholders whose real storage arrives with the document store, so
        they are excluded from typed-answer validation and completion math.
        """
        return [
            q
            for s in form.sections
            if s.status == "ACTIVE"
            for q in s.questions
            if q.status == "ACTIVE" and q.question_type != "file"
        ]

    async def _get_owned_editable_submission(
        self, submission_id: uuid.UUID, citizen_id: uuid.UUID
    ) -> FormSubmission:
        submission = await self.repo.get_by_id(submission_id)
        if submission is None:
            raise SubmissionNotFoundError()
        if submission.citizen_id != citizen_id:
            raise SubmissionOwnershipError()
        if submission.status not in _EDITABLE:
            raise SubmissionNotEditableError(
                f"Submission status '{submission.status}' cannot be modified"
            )
        return submission

    @staticmethod
    def _answers_by_qid(submission: FormSubmission) -> dict:
        return {
            a.question_id: answer_value(a)
            for a in submission.answers
            if is_answered(answer_value(a))
        }

    async def _load_form(self, submission: FormSubmission) -> FormDefinition:
        form = await self.form_repo.get_by_id(submission.form_id)
        if form is None:  # pragma: no cover — FK guarantees existence
            raise FormNotFoundError("Form for this submission no longer exists")
        return form

    def _to_response(
        self,
        submission: FormSubmission,
        form: FormDefinition,
        stats,
    ) -> SubmissionResponse:
        return SubmissionResponse(
            submission_id=submission.submission_id,
            citizen_id=submission.citizen_id,
            form_id=submission.form_id,
            form_code=form.form_code,
            form_version=submission.form_version,
            status=submission.status,
            completion_percentage=submission.completion_percentage,
            started_at=submission.started_at,
            completed_at=submission.completed_at,
            applicable_questions=stats.applicable_count,
            answered_questions=stats.answered_count,
            missing_required=stats.missing_required,
            answers=[
                SubmissionAnswerResponse(
                    answer_id=a.answer_id,
                    question_id=a.question_id,
                    question_code=(
                        a.question.question_code if a.question is not None else None
                    ),
                    answer_text=a.answer_text,
                    answer_number=a.answer_number,
                    answer_decimal=(
                        float(a.answer_decimal) if a.answer_decimal is not None else None
                    ),
                    answer_boolean=a.answer_boolean,
                    answer_date=a.answer_date,
                    answer_json=a.answer_json,
                    source=a.source,
                    confidence=float(a.confidence) if a.confidence is not None else None,
                    updated_at=a.updated_at,
                )
                for a in submission.answers
            ],
        )

    async def _apply_answers(
        self,
        submission: FormSubmission,
        form: FormDefinition,
        answers: Sequence[AnswerInput],
    ) -> None:
        """Validate and upsert every answer in the payload.

        Batched: one SELECT for all existing answers of the submission (the
        eager-loaded submission usually already carries them), one flush for
        inserts — the per-answer query pattern was the dominant save cost on
        the remote database.
        """
        if not answers:
            return
        questions = await self._form_questions(form)
        by_id = {q.question_id: q for q in questions}

        # Validate every answer before touching storage (all-or-nothing per
        # request, matching the previous sequential behavior).
        resolved: list[tuple[FormQuestion, AnswerInput, str, Any]] = []
        for item in answers:
            question = by_id.get(item.question_id)
            if question is None:
                # Also reject questions that exist in the form but are
                # inactive/file-only — they are not answerable.
                raise QuestionNotInFormError()
            column, typed = validate_and_map_answer(
                question, item.value, item.source or "USER_INPUT"
            )
            resolved.append((question, item, column, typed))

        # Index existing answers once. The eager-loaded submission carries
        # its answers; anything else (e.g. a just-created DRAFT with an
        # unloaded relationship) uses the targeted batched SELECT — a lazy
        # load here would blow up inside the async session (MissingGreenlet).
        try:
            existing_answers = list(submission.answers)
        except Exception:
            existing_answers = []
        if existing_answers:
            existing_by_qid = {a.question_id: a for a in existing_answers}
        else:
            rows = await self.repo.list_answers(submission.submission_id)
            existing_by_qid = {a.question_id: a for a in rows}

        to_add: list[FormAnswer] = []
        to_delete: list[FormAnswer] = []
        for question, item, column, typed in resolved:
            if column is None:
                # value=null explicitly clears a saved answer.
                existing = existing_by_qid.get(question.question_id)
                if existing is not None:
                    to_delete.append(existing)
                    existing_by_qid.pop(question.question_id, None)
                continue

            existing = existing_by_qid.get(question.question_id)
            if existing is not None:
                set_typed_value(existing, column, typed)
                existing.source = item.source
                if item.value is not None:
                    existing.confidence = None
            else:
                answer = FormAnswer(
                    submission_id=submission.submission_id,
                    question_id=question.question_id,
                    source=item.source,
                )
                set_typed_value(answer, column, typed)
                to_add.append(answer)
                existing_by_qid[question.question_id] = answer

        await self.repo.add_answers(to_add)
        await self.repo.delete_answers(to_delete)

    async def _refresh_progress(
        self,
        submission: FormSubmission,
        form: FormDefinition | None = None,
    ) -> tuple[FormSubmission, FormDefinition, ProgressStats]:
        """
        Recompute and persist completion stats from stored answers.

        Re-fetches the submission (populate_existing picks up answers written
        earlier in this session). When the caller already holds the loaded
        form hierarchy, it is passed as `form` and reused — a full hierarchy
        re-load is pure latency on the remote database. The question data is
        snapshotted into plain objects BEFORE the re-fetch, because
        populate_existing also refreshes the shared FormDefinition and
        FormQuestion rows (selectinload paths on FormSubmission.form),
        expiring their relationships; async sessions forbid the implicit lazy
        load that would then fire inside the sync condition evaluator.
        Callers that omit `form` get the original post-refresh hierarchy load.
        """
        snapshot = None
        if form is not None:
            snapshot = [
                _QuestionSnapshot.from_orm(q) for q in await self._form_questions(form)
            ]

        # Re-fetch to see answers added/removed in this session.
        fresh = await self.repo.get_by_id(submission.submission_id)
        assert fresh is not None
        if snapshot is None:
            form = await self._load_form(fresh)
            questions = await self._form_questions(form)
        else:
            questions = snapshot
        stats = compute_progress(questions, self._answers_by_qid(fresh))
        fresh.completion_percentage = stats.percentage
        await self.db.flush()
        return fresh, form, stats

    # ------------------------------------------------------------------
    # Public operations
    # ------------------------------------------------------------------

    async def create_submission(
        self, form_code: str, data: SubmissionCreate
    ) -> SubmissionResponse:
        # Lean existence check (identity row only) — the eagerly-loaded
        # profile fetch is wasted work the submission flow never reads.
        if not await self.citizen_repo.exists(data.citizen_id):
            raise CitizenNotFoundError()

        form = await self._resolve_active_form(form_code)

        # Resume: reuse an existing editable submission for the same
        # citizen + form instead of spawning duplicates.
        existing = await self.repo.get_latest_editable_for_citizen_form(
            data.citizen_id, form.form_id
        )
        if existing is not None:
            if data.answers:
                await self._apply_answers(existing, form, data.answers)
                existing.status = "IN_PROGRESS"
            fresh, form, stats = await self._refresh_progress(existing, form)
            return self._to_response(fresh, form, stats)

        # Citizen existence was already verified above via the dedicated
        # identity SELECT; no need to fetch the citizen again here.
        submission = FormSubmission(
            citizen_id=data.citizen_id,
            form_id=form.form_id,
            form_version=form.version,
            status="DRAFT",
        )
        await self.repo.create(submission)
        if data.answers:
            await self._apply_answers(submission, form, data.answers)
            submission.status = "IN_PROGRESS"
        fresh, form, stats = await self._refresh_progress(submission, form)
        return self._to_response(fresh, form, stats)

    async def _resolve_active_form(self, form_code: str) -> FormDefinition:
        form = await self.form_repo.get_active_by_code(form_code)
        if form is None:
            raise FormNotFoundError(f"Form '{form_code}' not found or not active")
        return form

    async def get_submission(
        self, submission_id: uuid.UUID, citizen_id: uuid.UUID
    ) -> SubmissionResponse:
        submission = await self.repo.get_by_id(submission_id)
        if submission is None:
            raise SubmissionNotFoundError()
        if submission.citizen_id != citizen_id:
            raise SubmissionOwnershipError()
        form = await self._load_form(submission)
        questions = await self._form_questions(form)
        stats = compute_progress(questions, self._answers_by_qid(submission))
        return self._to_response(submission, form, stats)

    async def update_submission(
        self, submission_id: uuid.UUID, data: SubmissionUpdate
    ) -> SubmissionResponse:
        submission = await self._get_owned_editable_submission(
            submission_id, data.citizen_id
        )
        if data.status is not None and data.status not in _EDITABLE:
            raise InvalidStatusTransitionError(
                f"Status must be one of {list(_EDITABLE)}; "
                f"use the complete endpoint to finish a submission"
            )
        form = await self._load_form(submission)
        if data.answers:
            await self._apply_answers(submission, form, data.answers)
        if data.status is not None:
            submission.status = data.status
        elif submission.status == "DRAFT" and data.answers:
            submission.status = "IN_PROGRESS"
        fresh, form, stats = await self._refresh_progress(submission, form)
        return self._to_response(fresh, form, stats)

    async def complete_submission(
        self, submission_id: uuid.UUID, citizen_id: uuid.UUID
    ) -> SubmissionResponse:
        submission = await self._get_owned_editable_submission(
            submission_id, citizen_id
        )
        form = await self._load_form(submission)

        questions = await self._form_questions(form)
        stats = compute_progress(questions, self._answers_by_qid(submission))
        if stats.missing_required:
            raise IncompleteSubmissionError(extra={"missing_required": stats.missing_required})

        submission.status = _COMPLETED
        submission.completed_at = func.now()
        fresh, form, final_stats = await self._refresh_progress(submission, form)
        return self._to_response(fresh, form, final_stats)
