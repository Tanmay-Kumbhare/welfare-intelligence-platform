"""
Citizen domain ORM models.

Tables:
  - tbl_citizen_master        Identity and contact
  - tbl_demographic_profile   Social, family, and type-specific metadata
  - tbl_financial_profile     Income, poverty, land holding
  - tbl_location_profile      State, district, area type
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class CitizenMaster(Base):
    __tablename__ = "tbl_citizen_master"

    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    gender: Mapped[str | None] = mapped_column(String(20))
    mobile_number: Mapped[str | None] = mapped_column(String(15))
    email_id: Mapped[str | None] = mapped_column(String(255))
    # FARMER | STUDENT | SENIOR | GENERAL
    citizen_type: Mapped[str] = mapped_column(String(20), nullable=False)
    registration_date: Mapped[date] = mapped_column(Date, server_default=func.current_date())
    # PENDING | VERIFIED
    verification_status: Mapped[str] = mapped_column(String(20), default="PENDING")

    # Relationships
    demographic_profile: Mapped["DemographicProfile | None"] = relationship(
        back_populates="citizen", uselist=False, cascade="all, delete-orphan"
    )
    financial_profile: Mapped["FinancialProfile | None"] = relationship(
        back_populates="citizen", uselist=False, cascade="all, delete-orphan"
    )
    location_profile: Mapped["LocationProfile | None"] = relationship(
        back_populates="citizen", uselist=False, cascade="all, delete-orphan"
    )
    assessments: Mapped[list["EligibilityAssessment"]] = relationship(  # type: ignore[name-defined]
        back_populates="citizen", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<CitizenMaster {self.citizen_id} {self.full_name}>"


class DemographicProfile(Base):
    __tablename__ = "tbl_demographic_profile"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # ILLITERATE | PRIMARY | SECONDARY | HIGHER_SECONDARY | GRADUATE | POST_GRADUATE
    education_level: Mapped[str | None] = mapped_column(String(50))
    occupation: Mapped[str | None] = mapped_column(String(100))
    family_size: Mapped[int | None] = mapped_column(Integer)
    # SINGLE | MARRIED | WIDOWED | DIVORCED
    marital_status: Mapped[str | None] = mapped_column(String(30))
    # GEN | OBC | SC | ST
    social_category: Mapped[str | None] = mapped_column(String(10))
    # NONE | PHYSICALLY_DISABLED | VISUALLY_IMPAIRED | HEARING_IMPAIRED | OTHER
    disability_status: Mapped[str] = mapped_column(String(30), default="NONE")
    # Stores non-rule informational fields per citizen type.
    # FARMER: {"crop_type": "Kharif", "irrigation_source": "Borewell", "land_ownership": "Owned"}
    # STUDENT: {"institution_name": "...", "course": "...", "current_year": "2nd Year"}
    # SENIOR: {"pension_received": false, "primary_caregiver": "Son"}
    # The eligibility engine NEVER reads this field.
    type_specific_metadata: Mapped[dict | None] = mapped_column(JSONB)

    citizen: Mapped["CitizenMaster"] = relationship(back_populates="demographic_profile")


class FinancialProfile(Base):
    __tablename__ = "tbl_financial_profile"

    financial_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    # Annual income in INR
    annual_income: Mapped[float | None] = mapped_column(Numeric(15, 2))
    # EMPLOYED | UNEMPLOYED | SELF_EMPLOYED | FARMER | STUDENT | RETIRED
    employment_status: Mapped[str | None] = mapped_column(String(30))
    income_source: Mapped[str | None] = mapped_column(String(100))
    # APL | BPL | AAY
    poverty_category: Mapped[str | None] = mapped_column(String(10))
    # Land holding in HECTARES (PM-KISAN threshold: <= 2.0 ha)
    land_holding_size: Mapped[float | None] = mapped_column(Numeric(8, 2))
    # Explicit BPL card flag — many schemes key off this directly
    is_bpl_card_holder: Mapped[bool] = mapped_column(Boolean, default=False)
    # Income tax payer exclusion flag — used in PM-KISAN and similar
    is_income_tax_payer: Mapped[bool] = mapped_column(Boolean, default=False)

    citizen: Mapped["CitizenMaster"] = relationship(back_populates="financial_profile")


class LocationProfile(Base):
    __tablename__ = "tbl_location_profile"

    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    citizen_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tbl_citizen_master.citizen_id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    state: Mapped[str | None] = mapped_column(String(100))
    district: Mapped[str | None] = mapped_column(String(100))
    village_city: Mapped[str | None] = mapped_column(String(150))
    # RURAL | URBAN | SEMI_URBAN — used in PMAY-G rule
    area_type: Mapped[str | None] = mapped_column(String(15))

    citizen: Mapped["CitizenMaster"] = relationship(back_populates="location_profile")


# Deferred import to avoid circular reference
from app.models.assessment import EligibilityAssessment  # noqa: E402, F401
