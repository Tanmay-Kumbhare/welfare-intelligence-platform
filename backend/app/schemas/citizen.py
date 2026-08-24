"""Pydantic v2 schemas for citizen domain."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    demographic: DemographicProfileCreate
    financial: FinancialProfileCreate
    location: LocationProfileCreate

    @field_validator("date_of_birth")
    @classmethod
    def dob_not_future(cls, v: date) -> date:
        from datetime import date as d
        if v >= d.today():
            raise ValueError("Date of birth must be in the past")
        return v


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
    registration_date: Optional[date] = None
    verification_status: str
    demographic: Optional[DemographicProfileResponse] = None
    financial: Optional[FinancialProfileResponse] = None
    location: Optional[LocationProfileResponse] = None
