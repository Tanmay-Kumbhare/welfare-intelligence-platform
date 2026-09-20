"""
Profile fact ORM models.

Tables:
  - tbl_profile_fact             Normalized fact layer between citizen data and
                                 the future eligibility engine
  - tbl_profile_fact_provenance  Where each fact came from

Design rules (from the Phase 1 spec):
  - Profile facts are an INTEROPERABILITY layer, not the source of truth.
    Canonical domain tables (education, employment, family, agriculture,
    financial, location) remain normalized.
  - fact_code examples: ANNUAL_INCOME, DATE_OF_BIRTH, AGE, SOCIAL_CATEGORY.
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
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:  # pragma: no cover
    from app.models.citizen import CitizenMaster
    from app.models.submission import FormAnswer

# Canonical fact value types.
FACT_DATA_TYPES = ("STRING", "INTEGER", "DECIMAL", "BOOLEAN", "DATE", "JSON")

# Canonical fact sources.
FACT_SOURCES = ("USER_INPUT", "DOCUMENT", "OCR", "GOVERNMENT_API", "EXTERNAL_VERIFICATION", "ADMIN_VERIFIED", "SYSTEM_DERIVED")


class ProfileFact(Base):
    __tablename__ = "tbl_profile_fact"
    __table_args__ = (
        CheckConstraint(
            "data_type IN ('STRING','INTEGER','DECIMAL','BOOLEAN','DATE','JSON')",
            name="ck_profile_fact_data_type",
        ),
        # At most one current fact per (citizen, code). History is expressed
        # via effective_from/effective_until on superseded rows if needed;
        # new rows must not collide with open rows (partial unique index below).
        Index(
            "uq_profile_fact_open",
            "citizen_id",
            "fact_code",
            unique=True,
            postgresql_where=text("effective_until IS NULL"),
        ),
    )

    fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # e.g. ANNUAL_INCOME, DATE_OF_BIRTH, AGE, SOCIAL_CATEGORY
    fact_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # Native typed value of the fact. Stored as TEXT plus data_type;
    # typed accessors convert at read time (keeps one value column for all types).
    fact_value: Mapped[str | None] = mapped_column(Text)
    data_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # USER_INPUT | DOCUMENT | OCR | GOVERNMENT_API | EXTERNAL_VERIFICATION |
    # ADMIN_VERIFIED | SYSTEM_DERIVED
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="USER_INPUT")
    # 0.0-1.0
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    citizen: Mapped["CitizenMaster"] = relationship()
    provenance_records: Mapped[list["ProfileFactProvenance"]] = relationship(
        back_populates="fact",
        cascade="all, delete-orphan",
        order_by="ProfileFactProvenance.created_at",
    )

    def __repr__(self) -> str:
        return f"<ProfileFact {self.fact_code}={self.fact_value} ({self.data_type})>"


class ProfileFactProvenance(Base):
    """Where a profile fact came from, with optional document linkage."""

    __tablename__ = "tbl_profile_fact_provenance"

    provenance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_profile_fact.fact_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # USER_INPUT | DOCUMENT | OCR | GOVERNMENT_API | EXTERNAL_VERIFICATION |
    # ADMIN_VERIFIED | SYSTEM_DERIVED
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Opaque pointer to the origin: file path, record ID, endpoint name, etc.
    source_reference: Mapped[str | None] = mapped_column(String(255))
    # Verbatim excerpt the value was taken from (for explainability).
    source_text: Mapped[str | None] = mapped_column(Text)
    # Optional links into the evidence chain.
    document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    form_answer_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_form_answer.answer_id", ondelete="SET NULL"),
    )
    # PENDING | VERIFIED | REJECTED
    verification_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    verification_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    fact: Mapped[ProfileFact] = relationship(back_populates="provenance_records")
    form_answer: Mapped["FormAnswer"] = relationship(  # type: ignore[name-defined]
        back_populates="provenance_records"
    )
