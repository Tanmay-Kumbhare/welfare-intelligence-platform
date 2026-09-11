"""Pydantic v2 schemas for scheme domain."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class RuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    rule_id: uuid.UUID
    parameter_name: str
    operator: str
    required_value: str
    rule_description: Optional[str] = None
    rule_priority: int
    failure_stage_code: Optional[str] = None
    remedy_template: Optional[str] = None


class RuleGroupResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    group_id: uuid.UUID
    group_name: str
    intra_group_operator: str
    group_priority: int
    rules: list[RuleResponse]


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    document_id: uuid.UUID
    document_type: str
    mandatory_flag: bool
    description: Optional[str] = None


class SchemeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    scheme_id: uuid.UUID
    scheme_name: str
    department_name: Optional[str] = None
    scheme_category: Optional[str] = None
    description: Optional[str] = None
    benefit_description: Optional[str] = None
    start_date: Optional[date] = None
    status: str
    official_source_url: Optional[str] = None
    application_url: Optional[str] = None
    last_verified_at: Optional[date] = None
    group_combining_operator: str
    target_persona: Optional[str] = None


class SchemeDetailResponse(SchemeResponse):
    """Full scheme detail including rule groups and documents."""
    rule_groups: list[RuleGroupResponse] = []
    documents: list[DocumentResponse] = []


# ---------------------------------------------------------------
# Structured Failure Diagnostic schemas (S0–S2)
# ---------------------------------------------------------------

class FailedRuleDetail(BaseModel):
    """Single rule that the citizen failed."""
    parameter: str
    required: str
    actual: Any
    rule_description: Optional[str] = None


class Remediation(BaseModel):
    """Actionable remediation guidance for a failed scheme."""
    action: str
    portal_link: Optional[str] = None


class EligibilityDiagnosticResponse(BaseModel):
    """
    Diagnostic payload returned for each scheme after evaluation.
    status = ELIGIBLE | INELIGIBLE
    stage_tag = None (eligible) | S0_ELIGIBILITY | S1_DOCUMENT_DISCREPANCY | S2_DOMICILE_MISMATCH
    """
    scheme_id: uuid.UUID
    scheme_name: str
    status: str
    stage_tag: Optional[str] = None
    failed_rules: list[FailedRuleDetail] = []
    remediation: Optional[Remediation] = None