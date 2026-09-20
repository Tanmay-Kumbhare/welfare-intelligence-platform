"""
Form submission ORM models.

Tables:
  - tbl_form_submission  One citizen's run through a specific form version
  - tbl_form_answer      One saved answer within a submission

Answers are typed columns, not a single text blob: the backend can store
native values (numbers, booleans, dates, JSON) so consumers never have to
re-parse strings.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:  # pragma: no cover
    from app.models.citizen import CitizenMaster
    from app.models.form import FormDefinition, FormQuestion
    from app.models.profile_fact import ProfileFactProvenance

# Canonical submission status values.
SUBMISSION_STATUSES = ("DRAFT", "IN_PROGRESS", "COMPLETED", "ABANDONED")

# Canonical answer source values.
ANSWER_SOURCES = ("USER_INPUT", "DOCUMENT", "API", "SYSTEM_DERIVED", "ADMIN_VERIFIED")


class FormSubmission(Base):
    __tablename__ = "tbl_form_submission"
    __table_args__ = (
        CheckConstraint(
            "status IN ('DRAFT','IN_PROGRESS','COMPLETED','ABANDONED')",
            name="ck_form_submission_status",
        ),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_form_definition.form_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Denormalized snapshot of the form version answered, so a submission
    # always records which definition it targeted even if the form is
    # later versioned or retired.
    form_version: Mapped[int] = mapped_column(Integer, nullable=False)
    # DRAFT | IN_PROGRESS | COMPLETED | ABANDONED
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="DRAFT")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # 0-100, computed from answered questions vs form questions.
    completion_percentage: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=0
    )
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    citizen: Mapped["CitizenMaster"] = relationship()
    form: Mapped["FormDefinition"] = relationship(back_populates="submissions")
    answers: Mapped[list["FormAnswer"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<FormSubmission {self.submission_id} {self.status}>"


class FormAnswer(Base):
    __tablename__ = "tbl_form_answer"
    __table_args__ = (
        # One answer per question per submission; re-answering overwrites.
        UniqueConstraint("submission_id", "question_id", name="uq_submission_question"),
    )

    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_form_submission.submission_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_form_question.question_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Typed value columns — exactly one (or answer_json for composite types)
    # is populated depending on the question's data_type.
    answer_text: Mapped[str | None] = mapped_column(Text)
    answer_number: Mapped[int | None]
    answer_decimal: Mapped[float | None] = mapped_column(Numeric(20, 4))
    answer_boolean: Mapped[bool | None] = mapped_column(Boolean)
    answer_date: Mapped[date | None] = mapped_column(Date)
    # For multi_choice arrays, location coordinates, and other composite values.
    answer_json: Mapped[dict | None] = mapped_column(JSONB)
    # USER_INPUT | DOCUMENT | API | SYSTEM_DERIVED | ADMIN_VERIFIED
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="USER_INPUT")
    # 0.0-1.0 — only meaningful for non-USER_INPUT sources.
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    submission: Mapped["FormSubmission"] = relationship(back_populates="answers")
    question: Mapped["FormQuestion"] = relationship(back_populates="answers")
    # Facts derived from this answer (viewonly: provenance rows are managed
    # from the fact side). One answer may feed several facts.
    provenance_records: Mapped[list["ProfileFactProvenance"]] = relationship(  # type: ignore[name-defined]
        back_populates="form_answer", viewonly=True
    )
