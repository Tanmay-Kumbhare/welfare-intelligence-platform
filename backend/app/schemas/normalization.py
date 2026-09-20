"""Pydantic v2 schemas for the Phase 2B normalization API."""

from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class UnmappedAnswerItem(BaseModel):
    """One answer that could not be mapped to a canonical profile field."""

    question_code: str
    profile_field: Optional[str] = None
    reason: str


class NormalizationSummary(BaseModel):
    """
    Result of normalizing a completed submission.

    profiles_updated: canonical domains whose rows were written
        (demographic/financial/location/education/employment/agriculture/
        disability/family_member).
    unmapped_answers: answers with no canonical mapping — reported, never
        silently discarded.
    warnings: non-fatal issues (unparseable values, skipped family entries,
        verified-fact preservation notices).
    """

    submission_id: uuid.UUID
    citizen_id: uuid.UUID
    status: str
    form_code: Optional[str] = None
    form_version: Optional[int] = None
    profiles_updated: list[str] = []
    facts_created: int = 0
    facts_updated: int = 0
    facts_derived: int = 0
    provenance_created: int = 0
    family_members_created: int = 0
    family_members_updated: int = 0
    unmapped_answers: list[UnmappedAnswerItem] = []
    warnings: list[str] = Field(default_factory=list)


class NormalizeRequest(BaseModel):
    """Request body while authentication is not yet implemented."""

    citizen_id: uuid.UUID
