"""
Scheme source and ingestion ORM models.

Tables:
  - tbl_scheme_source             An external source schemes can be obtained from
  - tbl_scheme_source_document    A document retrieved from a source
  - tbl_scheme_source_content     Raw/processed content of a document
  - tbl_scheme_rule_provenance    Links an eligibility rule to its source text
  - tbl_scheme_ingestion_run      One ingestion run against a source

Phase 1 only creates the infrastructure — no actual ingestion runs happen yet.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:  # pragma: no cover
    from app.models.scheme import SchemeEligibilityRule, SchemeMaster

# Canonical source types.
SCHEME_SOURCE_TYPES = (
    "GOVERNMENT_API",
    "GOVERNMENT_WEBSITE",
    "GOVERNMENT_PORTAL",
    "GOVERNMENT_PDF",
    "OTHER_AUTHORIZED_SOURCE",
)

# Canonical content types for tbl_scheme_source_content.
CONTENT_TYPES = ("RAW", "NORMALIZED", "EXTRACTED_TEXT")

# Canonical processing statuses.
PROCESSING_STATUSES = ("PENDING", "PROCESSING", "PROCESSED", "FAILED")


class SchemeSource(Base):
    __tablename__ = "tbl_scheme_source"
    __table_args__ = (
        CheckConstraint(
            "source_type IN ('GOVERNMENT_API','GOVERNMENT_WEBSITE','GOVERNMENT_PORTAL',"
            "'GOVERNMENT_PDF','OTHER_AUTHORIZED_SOURCE')",
            name="ck_scheme_source_type",
        ),
        UniqueConstraint("source_name", name="uq_scheme_source_name"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    authority_name: Mapped[str | None] = mapped_column(String(255))
    # ACTIVE | INACTIVE | RETIRED
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    documents: Mapped[list["SchemeSourceDocument"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )
    ingestion_runs: Mapped[list["SchemeIngestionRun"]] = relationship(
        back_populates="source",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<SchemeSource {self.source_name} ({self.source_type})>"


class SchemeSourceDocument(Base):
    __tablename__ = "tbl_scheme_source_document"
    __table_args__ = (
        # Same document (by URL) may be re-retrieved as new versions;
        # uniqueness is enforced on (source, name, version) instead of URL
        # so URL changes don't duplicate logical documents.
        UniqueConstraint(
            "source_id", "document_name", "version", name="uq_source_document_version"
        ),
    )

    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Nullable: a document can be discovered before being linked to a scheme.
    scheme_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_scheme_master.scheme_id", ondelete="SET NULL"),
        index=True,
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_scheme_source.source_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_name: Mapped[str] = mapped_column(String(255), nullable=False)
    document_url: Mapped[str] = mapped_column(String(500), nullable=False)
    # GUIDELINE | NOTIFICATION | RESOLUTION | APPLICATION_FORM | OTHER
    document_type: Mapped[str | None] = mapped_column(String(50))
    # e.g. en, hi, mr
    language: Mapped[str | None] = mapped_column(String(10), default="en")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[date | None] = mapped_column(Date)
    # SHA-256 of the retrieved bytes — change detection between retrievals.
    content_hash: Mapped[str | None] = mapped_column(String(64))
    # PENDING | PROCESSING | PROCESSED | FAILED
    processing_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    source: Mapped[SchemeSource] = relationship(back_populates="documents")
    scheme: Mapped["SchemeMaster"] = relationship()
    contents: Mapped[list["SchemeSourceContent"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
    )
    rule_provenances: Mapped[list["SchemeRuleProvenance"]] = relationship(
        back_populates="source_document"
    )

    def __repr__(self) -> str:
        return f"<SchemeSourceDocument {self.document_name} v{self.version}>"


class SchemeSourceContent(Base):
    """Preserves the original raw content alongside any processed variants."""

    __tablename__ = "tbl_scheme_source_content"
    __table_args__ = (
        CheckConstraint(
            "content_type IN ('RAW','NORMALIZED','EXTRACTED_TEXT')",
            name="ck_scheme_content_type",
        ),
        UniqueConstraint(
            "source_document_id",
            "content_type",
            "language",
            name="uq_source_content_variant",
        ),
    )

    content_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_scheme_source_document.source_document_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # RAW | NORMALIZED | EXTRACTED_TEXT
    content_type: Mapped[str] = mapped_column(String(30), nullable=False)
    raw_content: Mapped[str | None] = mapped_column(Text)
    normalized_content: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(10), default="en")
    # PENDING | PROCESSING | PROCESSED | FAILED
    processing_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    # Version tag of the extraction pipeline that produced this content.
    extraction_version: Mapped[str | None] = mapped_column(String(50))
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now(), onupdate=func.now()
    )

    document: Mapped[SchemeSourceDocument] = relationship(back_populates="contents")

    def __repr__(self) -> str:
        return f"<SchemeSourceContent {self.content_id} {self.content_type}>"


class SchemeRuleProvenance(Base):
    """
    Answers: "Why does the platform believe this scheme has this eligibility rule?"

    Links a structured rule (tbl_scheme_eligibility_rule row) to the exact
    source text it was extracted from.
    """

    __tablename__ = "tbl_scheme_rule_provenance"

    rule_provenance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_scheme_eligibility_rule.rule_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "tbl_scheme_source_document.source_document_id", ondelete="RESTRICT"
        ),
        nullable=False,
        index=True,
    )
    # Exact text the rule was derived from.
    source_text: Mapped[str | None] = mapped_column(Text)
    source_page: Mapped[int | None] = mapped_column(Integer)
    source_section: Mapped[str | None] = mapped_column(String(255))
    source_reference: Mapped[str | None] = mapped_column(String(255))
    # MANUAL | NLP_RULE_BASED | LLM_ASSISTED | API_IMPORT (future values fine)
    extraction_method: Mapped[str | None] = mapped_column(String(50))
    # 0.0-1.0
    extraction_confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    # PENDING | VERIFIED | REJECTED
    verification_status: Mapped[str] = mapped_column(String(20), default="PENDING")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    rule: Mapped["SchemeEligibilityRule"] = relationship()
    source_document: Mapped[SchemeSourceDocument] = relationship(
        back_populates="rule_provenances"
    )

    def __repr__(self) -> str:
        return f"<SchemeRuleProvenance {self.rule_id} <- {self.source_document_id}>"


class SchemeIngestionRun(Base):
    """One ingestion attempt against one source. Infrastructure only for Phase 1."""

    __tablename__ = "tbl_scheme_ingestion_run"

    ingestion_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_scheme_source.source_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # RUNNING | COMPLETED | FAILED | CANCELLED
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    records_discovered: Mapped[int] = mapped_column(Integer, default=0)
    records_created: Mapped[int] = mapped_column(Integer, default=0)
    records_updated: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    error_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )

    source: Mapped[SchemeSource] = relationship(back_populates="ingestion_runs")

    def __repr__(self) -> str:
        return f"<SchemeIngestionRun {self.ingestion_run_id} {self.status}>"
