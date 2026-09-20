"""
Form service — orchestration for form read APIs.

Maps ORM form hierarchies to response schemas with ACTIVE filtering,
display-order sorting, and condition depends_on codes resolved for the
frontend. Routers never talk to the repository directly.
"""

from __future__ import annotations

from typing import Sequence

from app.models.form import (
    FormCondition,
    FormDefinition,
    FormQuestion,
    FormSection,
)
from app.repositories.form_repository import FormRepository
from app.schemas.form import (
    FormConditionResponse,
    FormDetail,
    FormQuestionOptionResponse,
    FormQuestionResponse,
    FormSectionResponse,
    FormSummary,
    FormVersionSummary,
    FormVersionsResponse,
)
from app.services.form_logic import FormNotFoundError, FormVersionNotFoundError

_ACTIVE = "ACTIVE"


class FormService:
    def __init__(self, repo: FormRepository) -> None:
        self.repo = repo

    # ------------------------------------------------------------------
    # Hierarchy mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _condition_response(
        condition: FormCondition, code_by_qid: dict
    ) -> FormConditionResponse:
        return FormConditionResponse(
            condition_id=condition.condition_id,
            question_id=condition.question_id,
            depends_on_question_id=condition.depends_on_question_id,
            depends_on_question_code=code_by_qid.get(condition.depends_on_question_id),
            operator=condition.operator,
            comparison_value=condition.comparison_value,
            action=condition.action,
            condition_group=condition.condition_group,
        )

    @staticmethod
    def _question_response(
        question: FormQuestion, code_by_qid: dict
    ) -> FormQuestionResponse:
        return FormQuestionResponse(
            question_id=question.question_id,
            question_code=question.question_code,
            question_text=question.question_text,
            question_type=question.question_type,
            data_type=question.data_type,
            required=bool(question.required),
            display_order=question.display_order,
            profile_field=question.profile_field,
            validation_rule=question.validation_rule,
            help_text=question.help_text,
            placeholder=question.placeholder,
            options=[
                FormQuestionOptionResponse(
                    option_id=o.option_id,
                    option_code=o.option_code,
                    option_label=o.option_label,
                    display_order=o.display_order,
                )
                for o in sorted(
                    (o for o in question.options if o.status == _ACTIVE),
                    key=lambda o: o.display_order,
                )
            ],
            conditions=[
                FormService._condition_response(c, code_by_qid)
                for c in question.conditions
            ],
        )

    @classmethod
    def _section_response(
        cls, section: FormSection, code_by_qid: dict
    ) -> FormSectionResponse:
        return FormSectionResponse(
            section_id=section.section_id,
            section_code=section.section_code,
            section_name=section.section_name,
            description=section.description,
            display_order=section.display_order,
            questions=[
                cls._question_response(q, code_by_qid)
                for q in sorted(
                    (q for q in section.questions if q.status == _ACTIVE),
                    key=lambda q: q.display_order,
                )
            ],
        )

    @classmethod
    def _form_detail(cls, form: FormDefinition) -> FormDetail:
        # Resolve depends_on codes for the whole form in one pass.
        code_by_qid = {
            q.question_id: q.question_code
            for section in form.sections
            for q in section.questions
        }
        return FormDetail(
            form_id=form.form_id,
            form_code=form.form_code,
            form_name=form.form_name,
            description=form.description,
            target_citizen_type=form.target_citizen_type,
            version=form.version,
            status=form.status,
            sections=[
                cls._section_response(s, code_by_qid)
                for s in sorted(
                    (s for s in form.sections if s.status == _ACTIVE),
                    key=lambda s: s.display_order,
                )
            ],
        )

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def list_active_forms(
        self, target_citizen_type: str | None = None
    ) -> list[FormSummary]:
        """
        Latest ACTIVE version per form_code. Only ACTIVE forms/sections/
        questions/options surface here; the version snapshot returned is
        the highest active one.
        """
        rows = await self.repo.list_active_versions(target_citizen_type)
        latest_by_code: dict[str, FormDefinition] = {}
        for form in rows:  # already ordered by (code, version desc)
            latest_by_code.setdefault(form.form_code, form)
        return [
            FormSummary(
                form_id=f.form_id,
                form_code=f.form_code,
                form_name=f.form_name,
                description=f.description,
                target_citizen_type=f.target_citizen_type,
                version=f.version,
                status=f.status,
            )
            for f in sorted(latest_by_code.values(), key=lambda f: f.form_code)
        ]

    async def get_active_form(self, form_code: str) -> FormDetail:
        form = await self.repo.get_active_by_code(form_code)
        if form is None:
            raise FormNotFoundError(f"Form '{form_code}' not found or not active")
        return self._form_detail(form)

    async def list_versions(self, form_code: str) -> FormVersionsResponse:
        versions = await self.repo.list_versions(form_code)
        if not versions:
            raise FormNotFoundError(f"Form '{form_code}' not found")
        return FormVersionsResponse(
            form_code=form_code,
            versions=[
                FormVersionSummary(
                    version=v.version, status=v.status, created_at=v.created_at
                )
                for v in versions
            ],
        )

    async def get_form_version(self, form_code: str, version: int) -> FormDetail:
        form = await self.repo.get_by_code_and_version(form_code, version)
        if form is None:
            raise FormVersionNotFoundError(
                f"Form '{form_code}' version {version} not found"
            )
        if form.status != _ACTIVE:
            raise FormVersionNotFoundError(
                f"Form '{form_code}' version {version} is not active"
            )
        return self._form_detail(form)
