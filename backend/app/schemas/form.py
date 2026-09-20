"""
Pydantic v2 schemas for the dynamic form domain (Phase 2A).

Read side exposes the full form hierarchy:
    Form -> Sections -> Questions -> (Options | Conditions)

Submission side exposes the draft -> in-progress -> completed lifecycle with
typed answers. Only API-safe fields are exposed; internal SQLAlchemy and
audit fields (created_at/updated_at of definitions, status flags of
inactive rows) are intentionally omitted.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.submission import ANSWER_SOURCES, SUBMISSION_STATUSES

# Statuses that permit editing; completing is a separate action.
EDITABLE_SUBMISSION_STATUSES = ("DRAFT", "IN_PROGRESS")


# ------------------------------------------------------------------
# Form read schemas
# ------------------------------------------------------------------


class FormQuestionOptionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    option_id: uuid.UUID
    option_code: str
    option_label: str
    display_order: int


class FormConditionResponse(BaseModel):
    """Conditional display rule attached to a question.

    depends_on_question_code is resolved by the service for frontend
    convenience; the ids are the authoritative references.
    """

    condition_id: uuid.UUID
    question_id: uuid.UUID
    depends_on_question_id: uuid.UUID
    depends_on_question_code: Optional[str] = None
    operator: str
    comparison_value: Optional[str] = None
    action: str
    condition_group: int


class FormQuestionResponse(BaseModel):
    question_id: uuid.UUID
    question_code: str
    question_text: str
    question_type: str
    data_type: str
    required: bool
    display_order: int
    profile_field: Optional[str] = None
    # Validation metadata straight from the question definition — the
    # definition remains the single source of validation truth.
    validation_rule: Optional[dict[str, Any]] = None
    help_text: Optional[str] = None
    placeholder: Optional[str] = None
    options: list[FormQuestionOptionResponse] = []
    conditions: list[FormConditionResponse] = []


class FormSectionResponse(BaseModel):
    section_id: uuid.UUID
    section_code: str
    section_name: str
    description: Optional[str] = None
    display_order: int
    questions: list[FormQuestionResponse] = []


class FormDetail(BaseModel):
    """Complete form hierarchy for rendering a dynamic form."""

    form_id: uuid.UUID
    form_code: str
    form_name: str
    description: Optional[str] = None
    target_citizen_type: Optional[str] = None
    version: int
    status: str
    sections: list[FormSectionResponse] = []


class FormSummary(BaseModel):
    """List-view entry for an available active form."""

    form_id: uuid.UUID
    form_code: str
    form_name: str
    description: Optional[str] = None
    target_citizen_type: Optional[str] = None
    version: int
    status: str


class FormVersionSummary(BaseModel):
    version: int
    status: str
    created_at: datetime


class FormVersionsResponse(BaseModel):
    form_code: str
    versions: list[FormVersionSummary] = []


# ------------------------------------------------------------------
# Submission request schemas
# ------------------------------------------------------------------


class AnswerInput(BaseModel):
    """One answer within a submission payload.

    `value` holds a native JSON value; the service validates its type
    against the question's declared data_type/question_type and maps it to
    the matching typed column. `value: null` clears a previously saved
    answer.
    """

    question_id: uuid.UUID
    value: Any = None
    source: str = "USER_INPUT"


class SubmissionCreate(BaseModel):
    """Request body for starting a submission (always created as DRAFT)."""

    citizen_id: uuid.UUID
    answers: list[AnswerInput] = []


class SubmissionUpdate(BaseModel):
    """Request body for saving progress on an editable submission.

    citizen_id is required in place of authentication (auth is out of scope
    for this phase) and must match the submission owner.
    """

    citizen_id: uuid.UUID
    answers: list[AnswerInput] = []
    status: Optional[str] = None


class SubmissionComplete(BaseModel):
    """Request body for attempting to complete a submission."""

    citizen_id: uuid.UUID


# ------------------------------------------------------------------
# Submission response schemas
# ------------------------------------------------------------------


class SubmissionAnswerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    answer_id: uuid.UUID
    question_id: uuid.UUID
    question_code: Optional[str] = None
    answer_text: Optional[str] = None
    answer_number: Optional[int] = None
    answer_decimal: Optional[float] = None
    answer_boolean: Optional[bool] = None
    answer_date: Optional[date] = None
    answer_json: Optional[Any] = None
    source: str
    confidence: Optional[float] = None
    updated_at: datetime


class SubmissionResponse(BaseModel):
    """Submission state: identity, lifecycle, progress, and stored answers.

    missing_required lists the question codes of applicable (visible)
    required questions that are unanswered — populated for diagnostics on
    every read and after every save/complete attempt.
    """

    submission_id: uuid.UUID
    citizen_id: uuid.UUID
    form_id: uuid.UUID
    form_code: Optional[str] = None
    form_version: int
    status: str
    completion_percentage: int
    started_at: datetime
    completed_at: Optional[datetime] = None
    applicable_questions: int = 0
    answered_questions: int = 0
    missing_required: list[str] = []
    answers: list[SubmissionAnswerResponse] = []


class SubmissionLifecycleError(BaseModel):
    """Structured body for 409/422 completion failures."""

    message: str
    missing_required: list[str] = []


# Re-exported so routers/tests have a single import point for canonical
# value sets without reaching into the model layer.
SUBMISSION_STATUS_VALUES = SUBMISSION_STATUSES
ANSWER_SOURCE_VALUES = ANSWER_SOURCES
