"""
Scheme domain ORM models.

Tables:
  - tbl_scheme_master            Welfare scheme catalogue
  - tbl_scheme_rule_group        Logical grouping of eligibility rules
  - tbl_scheme_eligibility_rule  Individual eligibility conditions
  - tbl_scheme_document_master   Required documents per scheme
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SchemeMaster(Base):
    __tablename__ = "tbl_scheme_master"

    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scheme_name: Mapped[str] = mapped_column(String(255), nullable=False)
    department_name: Mapped[str | None] = mapped_column(String(255))
    # AGRICULTURE | EDUCATION | HEALTHCARE | HOUSING | PENSION | ENERGY | EMPLOYMENT
    scheme_category: Mapped[str | None] = mapped_column(String(50))
    description: Mapped[str | None] = mapped_column(Text)
    # What the citizen actually receives if eligible
    benefit_description: Mapped[str | None] = mapped_column(Text)
    start_date: Mapped[date | None] = mapped_column(Date)
    # ACTIVE | INACTIVE | EXPIRED
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    # Authoritative government source URL
    official_source_url: Mapped[str | None] = mapped_column(String(500))
    # Online application portal URL
    application_url: Mapped[str | None] = mapped_column(String(500))
    # Date eligibility rules were last verified against official sources
    last_verified_at: Mapped[date | None] = mapped_column(Date)
    # AND | OR — how the scheme''s rule groups are combined
    group_combining_operator: Mapped[str] = mapped_column(String(5), default="AND")
    # FARMER | STUDENT | SENIOR | GENERAL — persona tag for filtered discovery
    target_persona: Mapped[str | None] = mapped_column(String(50), index=True)

    # ------------------------------------------------------------------
    # Phase 1: source-independent canonical fields for future ingestion.
    # Raw source content lives in tbl_scheme_source_document/_content —
    # never duplicated here. All fields nullable → existing seed rows
    # remain valid unchanged.
    # ------------------------------------------------------------------
    # Government's own identifier for the scheme (e.g. scheme code).
    official_scheme_identifier: Mapped[str | None] = mapped_column(String(100))
    # Where the scheme record came from: MANUAL_SEED | GOVERNMENT_API |
    # GOVERNMENT_WEBSITE | GOVERNMENT_PORTAL | GOVERNMENT_PDF |
    # OTHER_AUTHORIZED_SOURCE
    source_type: Mapped[str | None] = mapped_column(String(50))
    # Human-readable source name (e.g. ministry/portal name).
    source_name: Mapped[str | None] = mapped_column(String(255))
    # Canonical URL describing the scheme.
    source_url: Mapped[str | None] = mapped_column(String(500))
    # FRESH_APPLICATION | RENEWAL | BOTH | CONTINUOUS | WINDOW_BASED
    application_window_type: Mapped[str | None] = mapped_column(String(30))
    # When the application window closes (if applicable).
    end_date: Mapped[date | None] = mapped_column(Date)
    # Record version, incremented on substantive scheme revisions.
    scheme_version: Mapped[int] = mapped_column(Integer, default=1)
    last_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Overrides/extends the V1 last_verified_at date with a timestamp.
    last_verified_at_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    rule_groups: Mapped[list["SchemeRuleGroup"]] = relationship(
        back_populates="scheme",
        cascade="all, delete-orphan",
        order_by="SchemeRuleGroup.group_priority",
    )
    eligibility_rules: Mapped[list["SchemeEligibilityRule"]] = relationship(
        back_populates="scheme",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list["SchemeDocumentMaster"]] = relationship(
        back_populates="scheme",
        cascade="all, delete-orphan",
    )
    assessments: Mapped[list["EligibilityAssessment"]] = relationship(  # type: ignore[name-defined]
        back_populates="scheme",
        cascade="all, delete-orphan",
    )
    # Source documents linked to this scheme (external ingestion foundation).
    source_documents: Mapped[list["SchemeSourceDocument"]] = relationship(  # type: ignore[name-defined]
        back_populates="scheme",
        viewonly=True,
    )

    def __repr__(self) -> str:
        return f"<SchemeMaster {self.scheme_id} {self.scheme_name}>"


class SchemeRuleGroup(Base):
    __tablename__ = "tbl_scheme_rule_group"

    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_scheme_master.scheme_id", ondelete="CASCADE"),
        nullable=False,
    )
    group_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # AND | OR — how rules within this group are combined
    intra_group_operator: Mapped[str] = mapped_column(String(5), nullable=False)
    group_priority: Mapped[int] = mapped_column(Integer, default=1)

    scheme: Mapped["SchemeMaster"] = relationship(back_populates="rule_groups")
    rules: Mapped[list["SchemeEligibilityRule"]] = relationship(
        back_populates="group",
        cascade="all, delete-orphan",
        order_by="SchemeEligibilityRule.rule_priority",
    )


class SchemeEligibilityRule(Base):
    __tablename__ = "tbl_scheme_eligibility_rule"

    rule_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Denormalized FK to scheme for direct queries without joining through group
    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_scheme_master.scheme_id", ondelete="CASCADE"),
        nullable=False,
    )
    group_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_scheme_rule_group.group_id", ondelete="CASCADE"),
        nullable=False,
    )
    # Maps to a named parameter in the eligibility engine''s PARAMETER_MAP
    # Valid values: age, gender, citizen_type, annual_income, poverty_category,
    # land_holding_size, is_bpl_card_holder, is_income_tax_payer, employment_status,
    # social_category, education_level, disability_status, area_type, state
    parameter_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # Comparison operator: < | <= | > | >= | == | != | IN
    operator: Mapped[str] = mapped_column(String(5), nullable=False)
    # String representation of threshold or value.
    # For IN operator: comma-separated string, e.g. "BPL,AAY"
    required_value: Mapped[str] = mapped_column(String(255), nullable=False)
    # Human-readable explanation shown to citizen in evaluation details
    rule_description: Mapped[str | None] = mapped_column(Text)
    rule_priority: Mapped[int] = mapped_column(Integer, default=1)
    # Diagnostic stage code: S0_ELIGIBILITY | S1_DOCUMENT_DISCREPANCY | S2_DOMICILE_MISMATCH
    failure_stage_code: Mapped[str | None] = mapped_column(String(50))
    # Actionable remediation template shown to citizen on failure
    remedy_template: Mapped[str | None] = mapped_column(Text)

    scheme: Mapped["SchemeMaster"] = relationship(back_populates="eligibility_rules")
    group: Mapped["SchemeRuleGroup"] = relationship(back_populates="rules")


class SchemeDocumentMaster(Base):
    __tablename__ = "tbl_scheme_document_master"

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    scheme_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_scheme_master.scheme_id", ondelete="CASCADE"),
        nullable=False,
    )
    # AADHAAR | INCOME_CERTIFICATE | CASTE_CERTIFICATE | LAND_RECORD |
    # BANK_PASSBOOK | BPL_CARD | MARKSHEET | RATION_CARD | VOTER_ID |
    # DISABILITY_CERTIFICATE | PHOTOGRAPH | DOMICILE_CERTIFICATE
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    mandatory_flag: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[str | None] = mapped_column(Text)

    scheme: Mapped["SchemeMaster"] = relationship(back_populates="documents")


# Deferred import to avoid circular reference
from app.models.assessment import EligibilityAssessment  # noqa: E402, F401
