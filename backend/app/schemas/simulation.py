"""Pydantic v2 schemas for what-if eligibility simulation (Phase 5)."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.assessment import RecommendationItem
from app.services.gap_analysis_service import SchemeGapAnalysis


class SimulationInput(BaseModel):
    """
    Hypothetical profile overrides submitted by a citizen for simulation.
    All attributes are optional and none are ever persisted.
    """
    model_config = ConfigDict(extra="ignore")

    # Financial
    annual_income: Optional[float] = Field(None, ge=0)
    land_holding_size: Optional[float] = Field(None, ge=0)
    is_income_tax_payer: Optional[bool] = None
    is_bpl_card_holder: Optional[bool] = None
    employment_status: Optional[str] = None
    poverty_category: Optional[str] = None

    # Demographic & Identity
    age: Optional[int] = Field(None, ge=0, le=150)
    gender: Optional[str] = None
    citizen_type: Optional[str] = None
    social_category: Optional[str] = None
    education_level: Optional[str] = None
    disability_status: Optional[str] = None

    # Location
    state: Optional[str] = None
    area_type: Optional[str] = None

    # Academic & Livestock
    tenth_percentage: Optional[float] = Field(None, ge=0, le=100)
    twelfth_percentage: Optional[float] = Field(None, ge=0, le=100)
    twelfth_percentile: Optional[float] = Field(None, ge=0, le=100)
    livestock_cattle_count: Optional[float] = Field(None, ge=0)
    livestock_poultry_count: Optional[float] = Field(None, ge=0)


class ConditionDelta(BaseModel):
    """Details on how a single eligibility condition changed under simulation."""
    parameter: str
    parameter_label: str
    rule_description: Optional[str] = None
    baseline_value: Any = None
    simulated_value: Any = None
    baseline_passed: bool
    simulated_passed: bool
    status: str  # IMPROVED, WORSENED, UNCHANGED


class SchemeSimulationResult(BaseModel):
    """Simulation outcome and comparative delta for a single scheme."""
    model_config = ConfigDict(from_attributes=True)

    scheme_id: uuid.UUID
    scheme_name: str
    department_name: Optional[str] = None
    scheme_category: Optional[str] = None
    target_persona: Optional[str] = None

    # Baseline vs Simulated outcomes
    baseline_eligible: bool
    simulated_eligible: bool
    baseline_match_score: Optional[float] = None
    simulated_match_score: Optional[float] = None

    # Outcome classification: BECAME_ELIGIBLE, BECAME_INELIGIBLE, SCORE_IMPROVED, SCORE_DECREASED, UNCHANGED
    outcome_change: str
    summary_explanation: str

    # Condition differences
    changed_conditions: List[ConditionDelta] = []
    gap_analysis: Optional[SchemeGapAnalysis] = None


class SimulationResponse(BaseModel):
    """Overall response for a citizen's what-if eligibility simulation."""
    citizen_id: uuid.UUID
    hypothetical_inputs: Dict[str, Any]
    total_schemes_evaluated: int
    newly_eligible_count: int
    newly_ineligible_count: int
    unaltered_eligible_count: int
    improved_score_count: int
    overall_summary: str
    simulated_schemes: List[SchemeSimulationResult]
