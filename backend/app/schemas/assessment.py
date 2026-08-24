"""Pydantic v2 schemas for eligibility assessment domain."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict

from app.schemas.scheme import DocumentResponse, SchemeResponse


class RuleEvaluationDetail(BaseModel):
    """Evidence for a single rule evaluation."""
    parameter: str
    actual: Any
    operator: str
    required: str
    passed: bool
    description: Optional[str] = None


class GroupEvaluationDetail(BaseModel):
    """Evidence for a single rule group evaluation."""
    group_name: str
    intra_group_operator: str
    group_passed: bool
    rules: list[RuleEvaluationDetail]


class EvaluationDetails(BaseModel):
    """Full JSONB evaluation_details structure."""
    overall_result: bool
    group_combining_operator: str
    groups: list[GroupEvaluationDetail]


class AssessmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    assessment_id: uuid.UUID
    citizen_id: uuid.UUID
    scheme_id: uuid.UUID
    eligibility_result: bool
    reason: Optional[str] = None
    evaluation_details: Optional[dict[str, Any]] = None
    assessment_date: date


class RecommendationItem(BaseModel):
    """Single item in a citizen''s recommendations list."""
    scheme: SchemeResponse
    eligibility_result: bool
    reason: Optional[str] = None
    evaluation_details: Optional[dict[str, Any]] = None
    assessment_date: date
    documents: list[DocumentResponse] = []


class RecommendationsResponse(BaseModel):
    """Full recommendations response for a citizen."""
    citizen_id: uuid.UUID
    total_schemes_evaluated: int
    eligible_count: int
    ineligible_count: int
    eligible_schemes: list[RecommendationItem]
    ineligible_schemes: list[RecommendationItem]
