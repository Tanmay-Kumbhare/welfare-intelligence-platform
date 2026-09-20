"""
Domain profile ORM models.

Tables (all citizen-scoped, additive to the existing V1 profiles):
  - tbl_education_profile    Student / scholarship fields
  - tbl_employment_profile   Work and income fields
  - tbl_family_member        Structured family members (not just family_size)
  - tbl_agriculture_profile  Farmer and land fields
  - tbl_disability_profile   Disability details (no raw sensitive numbers)
  - tbl_asset_profile        Asset-based eligibility inputs

Design rule: these are the CANONICAL normalized records for their domains.
tbl_profile_fact mirrors selected values for the interoperability layer;
it does not replace these tables.

Extensibility: every domain table carries an optional extension_metadata
JSONB column so genuinely-new attributes can be stored without a migration
and promoted to real columns later once their meaning stabilizes.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.orm import relationship as sa_relationship
from sqlalchemy.sql import func

from app.database import Base

if TYPE_CHECKING:  # pragma: no cover
    from app.models.citizen import CitizenMaster


class EducationProfile(Base):
    __tablename__ = "tbl_education_profile"
    __table_args__ = (
        # One current education record per citizen; future history via new rows.
        UniqueConstraint("citizen_id", name="uq_education_citizen"),
    )

    education_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # e.g. PRIMARY | SECONDARY | HIGHER_SECONDARY | GRADUATE | POST_GRADUATE
    education_level: Mapped[str | None] = mapped_column(String(50))
    institution_name: Mapped[str | None] = mapped_column(String(255))
    # GOVERNMENT | PRIVATE | AIDED | OTHER
    institution_type: Mapped[str | None] = mapped_column(String(50))
    course_name: Mapped[str | None] = mapped_column(String(255))
    # DIPLOMA | UG | PG | VOCATIONAL | OTHER
    course_type: Mapped[str | None] = mapped_column(String(50))
    year_of_study: Mapped[int | None] = mapped_column(Integer)
    # e.g. "2026-27"
    academic_year: Mapped[str | None] = mapped_column(String(20))
    marks_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2))
    annual_fee: Mapped[float | None] = mapped_column(Numeric(12, 2))
    # HOSTELLER | DAY_SCHOLAR | NONE
    hostel_status: Mapped[str | None] = mapped_column(String(20))
    scholarship_currently_received: Mapped[bool | None] = mapped_column(Boolean)
    extension_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    citizen: Mapped["CitizenMaster"] = sa_relationship()

    def __repr__(self) -> str:
        return f"<EducationProfile {self.citizen_id} {self.education_level}>"


class EmploymentProfile(Base):
    __tablename__ = "tbl_employment_profile"
    __table_args__ = (
        UniqueConstraint("citizen_id", name="uq_employment_citizen"),
    )

    employment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # EMPLOYED | UNEMPLOYED | SELF_EMPLOYED | STUDENT | RETIRED
    employment_status: Mapped[str | None] = mapped_column(String(30))
    occupation: Mapped[str | None] = mapped_column(String(100))
    # PERMANENT | CONTRACT | CASUAL | OTHER
    employment_type: Mapped[str | None] = mapped_column(String(30))
    # GOVERNMENT | PRIVATE | COOPERATIVE | NGO | HOUSEHOLD | OTHER
    employer_type: Mapped[str | None] = mapped_column(String(30))
    employer_name: Mapped[str | None] = mapped_column(String(255))
    monthly_income: Mapped[float | None] = mapped_column(Numeric(12, 2))
    annual_income: Mapped[float | None] = mapped_column(Numeric(15, 2))
    # FORMAL | INFORMAL | AGRICULTURE | OTHER
    work_sector: Mapped[str | None] = mapped_column(String(30))
    self_employed: Mapped[bool | None] = mapped_column(Boolean)
    extension_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    citizen: Mapped["CitizenMaster"] = sa_relationship()

    def __repr__(self) -> str:
        return f"<EmploymentProfile {self.citizen_id} {self.employment_status}>"


class FamilyMember(Base):
    __tablename__ = "tbl_family_member"

    family_member_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # SELF | SPOUSE | SON | DAUGHTER | FATHER | MOTHER | OTHER
    relationship: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str | None] = mapped_column(String(255))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    # STUDYING | COMPLETED | ILLITERATE | OTHER
    education_status: Mapped[str | None] = mapped_column(String(50))
    occupation: Mapped[str | None] = mapped_column(String(100))
    income: Mapped[float | None] = mapped_column(Numeric(12, 2))
    dependent_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    # NONE | PHYSICALLY_DISABLED | VISUALLY_IMPAIRED | HEARING_IMPAIRED | OTHER
    disability_status: Mapped[str | None] = mapped_column(String(30), default="NONE")
    extension_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    citizen: Mapped["CitizenMaster"] = sa_relationship()

    def __repr__(self) -> str:
        return f"<FamilyMember {self.citizen_id} {self.relationship}>"


class AgricultureProfile(Base):
    __tablename__ = "tbl_agriculture_profile"
    __table_args__ = (
        UniqueConstraint("citizen_id", name="uq_agriculture_citizen"),
    )

    agriculture_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # YES | NO | MARGINAL | SMALL | OTHER
    farmer_status: Mapped[str | None] = mapped_column(String(30))
    # OWNER | TENANT | SHARECROPPER | OTHER
    farmer_type: Mapped[str | None] = mapped_column(String(30))
    # OWNED | LEASED | BOTH | NONE
    land_ownership_status: Mapped[str | None] = mapped_column(String(30))
    total_land_area: Mapped[float | None] = mapped_column(Numeric(10, 2))
    cultivated_land_area: Mapped[float | None] = mapped_column(Numeric(10, 2))
    irrigated_land_area: Mapped[float | None] = mapped_column(Numeric(10, 2))
    # HECTARE | ACRE | BIGHA | GUNTHA
    land_unit: Mapped[str | None] = mapped_column(String(15), default="HECTARE")
    crop_type: Mapped[str | None] = mapped_column(String(100))
    # KHARIF | RABI | ZAYAD | WHOLE_YEAR
    season: Mapped[str | None] = mapped_column(String(20))
    tenant_farmer: Mapped[bool | None] = mapped_column(Boolean)
    sharecropper: Mapped[bool | None] = mapped_column(Boolean)
    agricultural_income: Mapped[float | None] = mapped_column(Numeric(15, 2))
    extension_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    citizen: Mapped["CitizenMaster"] = sa_relationship()

    def __repr__(self) -> str:
        return f"<AgricultureProfile {self.citizen_id} {self.farmer_status}>"


class DisabilityProfile(Base):
    __tablename__ = "tbl_disability_profile"
    __table_args__ = (
        UniqueConstraint("citizen_id", name="uq_disability_citizen"),
    )

    disability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # YES | NO | PENDING
    disability_status: Mapped[str | None] = mapped_column(String(20))
    # PHYSICAL | VISUAL | HEARING | INTELLECTUAL | MULTIPLE | OTHER
    disability_type: Mapped[str | None] = mapped_column(String(50))
    disability_percentage: Mapped[float | None] = mapped_column(Numeric(5, 2))
    certificate_available: Mapped[bool | None] = mapped_column(Boolean)
    # Store ONLY a salted hash of the certificate number, never the raw value.
    certificate_number_hash: Mapped[str | None] = mapped_column(String(128))
    extension_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    citizen: Mapped["CitizenMaster"] = sa_relationship()

    def __repr__(self) -> str:
        return f"<DisabilityProfile {self.citizen_id} {self.disability_status}>"


class AssetProfile(Base):
    __tablename__ = "tbl_asset_profile"

    asset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # LAND | HOUSE | VEHICLE | LIVESTOCK | EQUIPMENT | OTHER
    asset_type: Mapped[str | None] = mapped_column(String(50))
    # OWNED | JOINT | LEASED | NONE
    ownership_status: Mapped[str | None] = mapped_column(String(30))
    estimated_value: Mapped[float | None] = mapped_column(Numeric(15, 2))
    extension_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    citizen: Mapped["CitizenMaster"] = sa_relationship()

    def __repr__(self) -> str:
        return f"<AssetProfile {self.citizen_id} {self.asset_type}>"
