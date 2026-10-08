"""
Pydantic schemas for repeatable education records.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class EducationRecordBase(BaseModel):
    # 10TH_SSC | 12TH_HSC | DIPLOMA | ITI | UNDERGRADUATE | POSTGRADUATE | PHD | OTHER
    level: str = Field(..., min_length=2, max_length=50)
    details: dict[str, Any] = Field(default_factory=dict)
    is_current: bool = False
    passing_year: Optional[int] = None
    percentage: Optional[float] = None


class EducationRecordCreate(EducationRecordBase):
    pass


class EducationRecordUpdate(BaseModel):
    level: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    is_current: Optional[bool] = None
    passing_year: Optional[int] = None
    percentage: Optional[float] = None


class EducationRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    record_id: uuid.UUID
    citizen_id: uuid.UUID
    level: str
    details: dict[str, Any] = Field(default_factory=dict)
    is_current: bool
    passing_year: Optional[int] = None
    percentage: Optional[float] = None
    created_at: datetime
    updated_at: datetime
