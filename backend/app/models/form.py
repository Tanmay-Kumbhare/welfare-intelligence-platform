"""
Dynamic form definition ORM models.

Tables:
  - tbl_form_definition        A citizen-facing form (e.g. GENERAL_CITIZEN_PROFILE)
  - tbl_form_section           Ordered sections within a form
  - tbl_form_question          Individual questions within a section
  - tbl_form_question_option   Answer options for choice/dropdown questions
  - tbl_form_condition         Conditional display rules between questions

Versioning model:
  A form may exist at multiple versions. Each version row is a separate
  tbl_form_definition row sharing the same form_code, with an increasing
  version number and its own status. No version assumptions are hardcoded
  here — versions are plain integers with a unique (form_code, version)
  constraint, so new versions are purely data-driven.

Question types supported (stored as free strings, validated at the API layer
later — deliberately not a DB enum so new types can be added without DDL):
  text | number | decimal | date | boolean | single_choice | multi_choice |
  dropdown | file | location
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:  # pragma: no cover
    from app.models.submission import FormAnswer, FormSubmission

# Canonical question_type values. Kept in one place for reference and tests;
# the DB stores them as plain strings on purpose.
QUESTION_TYPES = (
    "text",
    "number",
    "decimal",
    "date",
    "boolean",
    "single_choice",
    "multi_choice",
    "dropdown",
    "file",
    "location",
)


class FormDefinition(Base):
    __tablename__ = "tbl_form_definition"
    __table_args__ = (
        # One row per (form_code, version): new versions are new rows.
        UniqueConstraint("form_code", "version", name="uq_form_code_version"),
    )

    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Stable logical identifier shared by all versions, e.g. GENERAL_CITIZEN_PROFILE
    form_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    form_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    # FARMER | STUDENT | SENIOR | GENERAL — mirrors tbl_citizen_master.citizen_type
    target_citizen_type: Mapped[str | None] = mapped_column(String(20))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # DRAFT | ACTIVE | RETIRED
    status: Mapped[str] = mapped_column(String(20), default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list["FormSection"]] = relationship(
        back_populates="form",
        cascade="all, delete-orphan",
        order_by="FormSection.display_order",
    )
    submissions: Mapped[list["FormSubmission"]] = relationship(  # type: ignore[name-defined]
        back_populates="form"
    )

    def __repr__(self) -> str:
        return f"<FormDefinition {self.form_code} v{self.version} {self.status}>"


class FormSection(Base):
    __tablename__ = "tbl_form_section"
    __table_args__ = (
        UniqueConstraint("form_id", "section_code", name="uq_form_section_code"),
    )

    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    form_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_form_definition.form_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    section_code: Mapped[str] = mapped_column(String(100), nullable=False)
    section_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # ACTIVE | INACTIVE
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    form: Mapped[FormDefinition] = relationship(back_populates="sections")
    questions: Mapped[list["FormQuestion"]] = relationship(
        back_populates="section",
        cascade="all, delete-orphan",
        order_by="FormQuestion.display_order",
    )


class FormQuestion(Base):
    __tablename__ = "tbl_form_question"

    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_form_section.section_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(String(500), nullable=False)
    # See QUESTION_TYPES in this module's docstring.
    question_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Logical storage type of the answer: STRING | INTEGER | DECIMAL | BOOLEAN | DATE | JSON
    data_type: Mapped[str] = mapped_column(String(20), nullable=False, default="STRING")
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # Canonical profile mapping hint, e.g. annual_income, date_of_birth, social_category.
    # Drives future normalization into tbl_profile_fact; nullable for informational
    # questions that never become facts.
    profile_field: Mapped[str | None] = mapped_column(String(100))
    # JSONB validation spec, e.g. {"min": 0, "max": 120} or {"pattern": "^\\d{6}$"}.
    # Kept as JSON so validators can evolve without DDL.
    validation_rule: Mapped[dict | None] = mapped_column(JSONB)
    help_text: Mapped[str | None] = mapped_column(Text)
    placeholder: Mapped[str | None] = mapped_column(String(255))
    # ACTIVE | INACTIVE
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    section: Mapped[FormSection] = relationship(back_populates="questions")
    options: Mapped[list["FormQuestionOption"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="FormQuestionOption.display_order",
    )
    # Conditions where this question is the one being shown/hidden
    conditions: Mapped[list["FormCondition"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        foreign_keys="FormCondition.question_id",
    )
    # Conditions where this question is the dependency (its answer drives others)
    dependent_conditions: Mapped[list["FormCondition"]] = relationship(
        back_populates="depends_on_question",
        cascade="all, delete-orphan",
        foreign_keys="FormCondition.depends_on_question_id",
    )
    answers: Mapped[list["FormAnswer"]] = relationship(  # type: ignore[name-defined]
        back_populates="question"
    )


class FormQuestionOption(Base):
    __tablename__ = "tbl_form_question_option"
    __table_args__ = (
        UniqueConstraint("question_id", "option_code", name="uq_question_option_code"),
    )

    option_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_form_question.question_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    option_code: Mapped[str] = mapped_column(String(100), nullable=False)
    option_label: Mapped[str] = mapped_column(String(255), nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # ACTIVE | INACTIVE
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")

    question: Mapped[FormQuestion] = relationship(back_populates="options")


class FormCondition(Base):
    """
    Conditional display rule: show/hide/require `question_id` depending on the
    answer given to `depends_on_question_id`.

    Example: question "Which course are you studying?" is shown only when
    "Are you currently studying?" == YES:
      depends_on_question_id = <studying question>
      operator = EQUALS
      comparison_value = YES
      action = SHOW

    Deliberately a simple row-per-condition model, not a rules engine.
    """

    __tablename__ = "tbl_form_condition"

    condition_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Question whose visibility/requirement is affected
    question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_form_question.question_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Question whose answer drives the condition
    depends_on_question_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_form_question.question_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # EQUALS | NOT_EQUALS | GREATER_THAN | LESS_THAN | GREATER_THAN_OR_EQUAL |
    # LESS_THAN_OR_EQUAL | IN | NOT_IN | IS_EMPTY | IS_NOT_EMPTY
    operator: Mapped[str] = mapped_column(String(30), nullable=False)
    # String form of the compared value; comma-separated for IN/NOT_IN.
    comparison_value: Mapped[str | None] = mapped_column(String(255))
    # SHOW | HIDE | REQUIRE
    action: Mapped[str] = mapped_column(String(20), nullable=False, default="SHOW")
    # Logical grouping of multiple conditions on the same question:
    # all rows sharing a condition_group are ANDed; different groups are ORed.
    condition_group: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    question: Mapped[FormQuestion] = relationship(
        back_populates="conditions", foreign_keys=[question_id]
    )
    depends_on_question: Mapped[FormQuestion] = relationship(
        back_populates="dependent_conditions", foreign_keys=[depends_on_question_id]
    )
