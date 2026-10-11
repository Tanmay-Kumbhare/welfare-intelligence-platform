"""Pydantic v2 schemas for Profile Conflict and Stale Fact Auditor (Phase 6)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class FactSourceEvidence(BaseModel):
    """Evidence metadata for a specific fact observation or record."""
    source_type: str
    source_reference: Optional[str] = None
    value: Any = None
    verified: bool = False
    confidence: Optional[float] = None
    observed_at: Optional[datetime] = None


class ProfileAuditIssue(BaseModel):
    """
    An audited issue for a profile fact or attribute.
    Categorized into: CONFIRMED_CONFLICT, POSSIBLE_CONFLICT, STALE_FACT, MISSING_INFORMATION.
    """
    model_config = ConfigDict(from_attributes=True)

    issue_type: str  # "CONFIRMED_CONFLICT", "POSSIBLE_CONFLICT", "STALE_FACT", "MISSING_INFORMATION"
    attribute_name: str
    attribute_label: str
    current_value: Any = None
    conflicting_value: Any = None
    severity: str = "MEDIUM"  # "HIGH", "MEDIUM", "LOW"
    description: str
    explanation: str
    sources: List[FactSourceEvidence] = []
    affected_schemes: List[str] = []
    recommended_action: str


class ProfileAuditSummary(BaseModel):
    """Summary counts and health score for the profile audit."""
    total_issues: int
    confirmed_conflicts_count: int
    possible_conflicts_count: int
    stale_facts_count: int
    missing_information_count: int
    is_healthy: bool
    summary_message: str


class ProfileAuditResponse(BaseModel):
    """Complete audit response for a citizen profile."""
    citizen_id: uuid.UUID
    audited_at: datetime
    summary: ProfileAuditSummary
    issues: List[ProfileAuditIssue]
