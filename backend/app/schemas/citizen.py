"""Pydantic v2 schemas for citizen domain."""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


# ------------------------------------------------------------------
# Sub-schemas
# ------------------------------------------------------------------

class DemographicProfileCreate(BaseModel):
    education_level: Optional[str] = None
    occupation: Optional[str] = None
    family_size: Optional[int] = Field(None, ge=1, le=50)
    marital_status: Optional[str] = None
    social_category: Optional[str] = None
    disability_status: str = "NONE"
    type_specific_metadata: Optional[dict[str, Any]] = None


class FinancialProfileCreate(BaseModel):
    annual_income: Optional[float] = Field(None, ge=0)
    employment_status: Optional[str] = None
    income_source: Optional[str] = None
    poverty_category: Optional[str] = None
    land_holding_size: Optional[float] = Field(None, ge=0)
    is_bpl_card_holder: bool = False
    is_income_tax_payer: bool = False


class LocationProfileCreate(BaseModel):
    state: Optional[str] = None
    district: Optional[str] = None
    village_city: Optional[str] = None
    area_type: Optional[str] = None


# ------------------------------------------------------------------
# Request schemas
# ------------------------------------------------------------------

class CitizenCreate(BaseModel):
    """Request body for registering a new citizen with a full profile."""
    full_name: str = Field(..., min_length=2, max_length=255)
    date_of_birth: date
    gender: Optional[str] = None
    mobile_number: Optional[str] = None
    email_id: Optional[str] = None
    citizen_type: str = Field(..., pattern="^(FARMER|STUDENT|SENIOR|GENERAL)$")
    profile_types: list[str] = Field(default_factory=list)
    demographic: DemographicProfileCreate
    financial: FinancialProfileCreate
    location: LocationProfileCreate

    @field_validator("full_name")
    @classmethod
    def name_no_numbers_or_special(cls, v: str) -> str:
        v = v.strip()
        # Reject strings that contain digits or non-alphabetic/space chars.
        # Indian names may contain letters from any Unicode script, so we
        # allow Unicode letters (\w minus digits) and spaces.
        if re.search(r"[0-9@#$%^&*()+=\[\]{}<>|/\\\"'`~!]", v):
            raise ValueError(
                "Name must contain only alphabetic characters and spaces."
            )
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters.")
        return v

    @field_validator("mobile_number")
    @classmethod
    def mobile_must_be_10_digits(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v == "":
            return v
        digits_only = re.sub(r"\D", "", v)
        if len(digits_only) != 10:
            raise ValueError("Mobile number must be exactly 10 digits.")
        return digits_only

    @field_validator("email_id")
    @classmethod
    def email_id_format(cls, v: Optional[str]) -> Optional[str]:
        if v is None or v.strip() == "":
            return v
        # Basic email validation: local@domain.tld
        if not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", v.strip()):
            raise ValueError("Please enter a valid email address.")
        return v.strip()

    @field_validator("date_of_birth")
    @classmethod
    def dob_not_future(cls, v: date) -> date:
        from datetime import date as d
        if v >= d.today():
            raise ValueError("Date of birth must be in the past")
        return v

    @field_validator("profile_types")
    @classmethod
    def validate_profile_types(cls, v: list[str]) -> list[str]:
        allowed = {"STUDENT", "FARMER", "EMPLOYEE", "BUSINESS", "SENIOR_CITIZEN", "HOMEMAKER", "PWD", "OTHER"}
        for pt in v:
            if pt not in allowed:
                raise ValueError(f"Invalid profile type: {pt}")
        return v


class CitizenUpdate(CitizenCreate):
    """Validated replacement of one existing citizen and its three profiles.

    The endpoint deliberately updates the row addressed by ``citizen_id``;
    it never routes an edit through registration or identity matching.
    """


# ------------------------------------------------------------------
# Response schemas
# ------------------------------------------------------------------

class DemographicProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    profile_id: uuid.UUID
    education_level: Optional[str] = None
    occupation: Optional[str] = None
    family_size: Optional[int] = None
    marital_status: Optional[str] = None
    social_category: Optional[str] = None
    disability_status: str
    type_specific_metadata: Optional[dict[str, Any]] = None


class FinancialProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    financial_id: uuid.UUID
    annual_income: Optional[float] = None
    employment_status: Optional[str] = None
    income_source: Optional[str] = None
    poverty_category: Optional[str] = None
    land_holding_size: Optional[float] = None
    is_bpl_card_holder: bool
    is_income_tax_payer: bool


class LocationProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    location_id: uuid.UUID
    state: Optional[str] = None
    district: Optional[str] = None
    village_city: Optional[str] = None
    area_type: Optional[str] = None


class CitizenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    citizen_id: uuid.UUID
    full_name: str
    date_of_birth: date
    gender: Optional[str] = None
    mobile_number: Optional[str] = None
    email_id: Optional[str] = None
    citizen_type: str
    profile_types: list[str] = []
    registration_date: Optional[date] = None
    verification_status: str
    demographic: Optional[DemographicProfileResponse] = None
    financial: Optional[FinancialProfileResponse] = None
    location: Optional[LocationProfileResponse] = None


class FactSyncSummary(BaseModel):
    """Outcome of re-deriving profile facts after a direct profile edit.
    facts_updated: fact codes whose open value changed or was created.
    skipped_verified: codes left untouched because an admin/government
    verified fact exists and a self-reported edit cannot override it."""
    facts_updated: list[str] = []
    skipped_verified: list[str] = []


class CitizenUpdateResponse(CitizenResponse):
    """PUT /citizens/{id} response: the saved profile plus the fact-sync
    summary so the frontend can confirm eligibility data is current."""
    fact_sync: Optional[FactSyncSummary] = None
