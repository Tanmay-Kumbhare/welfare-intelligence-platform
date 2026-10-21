"""
What-If Eligibility Simulation Service (Phase 5).

Allows citizens to simulate hypothetical profile changes and see the resulting
impact on scheme eligibility, Rule Match Scores, and gap analysis without
persisting any changes to the database or modifying existing assessments.

Core Invariants:
1. Pure In-Memory / Zero Persistence:
   - Does not write, modify, or commit to any database table.
   - The citizen's real profile, sub-profiles, and profile facts remain strictly unchanged.
2. Reuses Deterministic Engine:
   - Reuses EligibilityEngine logic with parameter resolution proxying simulation inputs.
   - Preserves all operator comparisons, scoring rules, and deterministic invariants.
3. Comparative Explainability:
   - Compares baseline evaluation to simulated evaluation.
   - Identifies which conditions improved, worsened, or remained unchanged.
   - Explains outcomes clearly to the citizen.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.models.citizen import CitizenMaster
from app.models.scheme import SchemeMaster
from app.schemas.simulation import (
    ConditionDelta,
    SchemeSimulationResult,
    SimulationInput,
    SimulationResponse,
)
from app.services.eligibility_engine import EligibilityEngine
from app.services.gap_analysis_service import GapAnalysisService, PARAMETER_LABELS


class SimulationEligibilityEngine(EligibilityEngine):
    """
    Subclass of EligibilityEngine that resolves hypothetical overrides first,
    falling back to the citizen's real profile attributes and profile facts.
    """

    def __init__(self, overrides: Dict[str, Any], facts_dict: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.overrides = {k: v for k, v in overrides.items() if v is not None}
        self.facts_dict = facts_dict

    def _resolve_parameter(
        self, citizen: CitizenMaster, parameter_name: str, facts_dict: dict[str, Any] | None = None
    ) -> Any:
        if parameter_name in self.overrides:
            val = self.overrides[parameter_name]
            # Special normalization conversions for standard parameters
            if parameter_name in ("annual_income", "land_holding_size"):
                return float(val) if val is not None else 0.0
            if parameter_name in (
                "tenth_percentage",
                "twelfth_percentage",
                "twelfth_percentile",
                "livestock_cattle_count",
                "livestock_poultry_count",
            ):
                return float(val) if val is not None else None
            if parameter_name == "age":
                return int(val) if val is not None else None
            return val

        # Fallback to standard engine parameter resolution
        effective_facts = facts_dict if facts_dict is not None else self.facts_dict
        return super()._resolve_parameter(citizen, parameter_name, facts_dict=effective_facts)


class SimulationService:
    """Service orchestrating what-if profile simulations."""

    @staticmethod
    def simulate_citizen_eligibility(
        citizen: CitizenMaster,
        schemes: Sequence[SchemeMaster],
        simulation_input: SimulationInput,
        baseline_assessments_map: Optional[Dict[uuid.UUID, Tuple[bool, Dict[str, Any], str]]] = None,
        facts_dict: Optional[Dict[str, Any]] = None,
    ) -> SimulationResponse:
        """
        Simulate eligibility for all active schemes under hypothetical inputs.
        
        Args:
            citizen: The authenticated citizen master record.
            schemes: Sequence of active schemes with rule groups.
            simulation_input: Hypothetical profile changes.
            baseline_assessments_map: Optional pre-computed baseline (scheme_id -> (result, details, reason)).
                                      If not provided, baseline is evaluated in-memory using standard engine.
            facts_dict: Optional active profile facts mapping {fact_code: fact_value}.
                        If not provided but citizen has loaded profile_facts, they are extracted.
        """
        if facts_dict is None and getattr(citizen, "profile_facts", None):
            facts_dict = {
                f.fact_code: f.fact_value
                for f in citizen.profile_facts
                if getattr(f, "effective_until", None) is None
            }

        raw_overrides = simulation_input.model_dump(exclude_unset=True, exclude_none=True)

        standard_engine = EligibilityEngine()
        sim_engine = SimulationEligibilityEngine(raw_overrides, facts_dict=facts_dict)

        simulated_schemes: List[SchemeSimulationResult] = []
        newly_eligible_count = 0
        newly_ineligible_count = 0
        unaltered_eligible_count = 0
        improved_score_count = 0

        for scheme in schemes:
            scheme_id = scheme.scheme_id

            # 1. Baseline evaluation (from map or evaluated in-memory)
            if baseline_assessments_map and scheme_id in baseline_assessments_map:
                base_eligible, base_details, base_reason = baseline_assessments_map[scheme_id]
            else:
                base_eligible, base_details, base_reason = standard_engine.evaluate_scheme(
                    citizen, scheme, facts_dict=facts_dict
                )

            # 2. Simulated evaluation
            sim_eligible, sim_details, sim_reason = sim_engine.evaluate_scheme(
                citizen, scheme, facts_dict=facts_dict
            )

            base_score = (
                base_details.get("rule_match_score")
                if base_details and isinstance(base_details, dict)
                else None
            )
            sim_score = (
                sim_details.get("rule_match_score")
                if sim_details and isinstance(sim_details, dict)
                else None
            )

            # 3. Detect changed conditions
            changed_conditions = SimulationService._compute_condition_deltas(
                base_details=base_details,
                sim_details=sim_details,
            )

            # 4. Determine outcome change category and citizen-friendly explanation
            outcome_change, summary_explanation = SimulationService._determine_outcome_change(
                scheme_name=scheme.scheme_name,
                base_eligible=base_eligible,
                sim_eligible=sim_eligible,
                base_score=base_score,
                sim_score=sim_score,
                changed_conditions=changed_conditions,
            )

            # Tally metrics
            if not base_eligible and sim_eligible:
                newly_eligible_count += 1
            elif base_eligible and not sim_eligible:
                newly_ineligible_count += 1
            elif base_eligible and sim_eligible:
                unaltered_eligible_count += 1

            if (sim_score or 0.0) > (base_score or 0.0):
                improved_score_count += 1

            # 5. Gap analysis on simulated result
            # Prepare mock/existing documents list if present on scheme
            scheme_docs = []
            if getattr(scheme, "documents", None):
                for d in scheme.documents:
                    scheme_docs.append({
                        "document_type": d.document_type,
                        "name": getattr(d, "document_name", getattr(d, "description", None)) or d.document_type,
                        "required": getattr(d, "mandatory_flag", getattr(d, "is_mandatory", True)),
                        "status": "VALID",  # In what-if profile simulation, highlight rule gaps
                    })

            sim_gap_analysis = GapAnalysisService.analyze_gaps(
                evaluation_details=sim_details,
                scheme_documents=scheme_docs,
                eligibility_result=sim_eligible,
            )

            simulated_schemes.append(
                SchemeSimulationResult(
                    scheme_id=scheme_id,
                    scheme_name=scheme.scheme_name,
                    department_name=getattr(scheme, "department_name", None),
                    scheme_category=getattr(scheme, "scheme_category", None),
                    target_persona=getattr(scheme, "target_persona", None),
                    baseline_eligible=base_eligible,
                    simulated_eligible=sim_eligible,
                    baseline_match_score=base_score,
                    simulated_match_score=sim_score,
                    outcome_change=outcome_change,
                    summary_explanation=summary_explanation,
                    changed_conditions=changed_conditions,
                    gap_analysis=sim_gap_analysis,
                )
            )

        # Sort simulated schemes deterministically:
        # 1. Newly eligible first
        # 2. Score improvements next
        # 3. Alphabetical by scheme name
        outcome_order = {
            "BECAME_ELIGIBLE": 0,
            "SCORE_IMPROVED": 1,
            "UNCHANGED": 2,
            "SCORE_DECREASED": 3,
            "BECAME_INELIGIBLE": 4,
        }
        simulated_schemes.sort(
            key=lambda s: (
                outcome_order.get(s.outcome_change, 9),
                -(s.simulated_match_score or 0.0),
                s.scheme_name.lower(),
                str(s.scheme_id),
            )
        )

        overall_summary = SimulationService._format_overall_summary(
            newly_eligible=newly_eligible_count,
            newly_ineligible=newly_ineligible_count,
            improved_score=improved_score_count,
            total_schemes=len(schemes),
        )

        return SimulationResponse(
            citizen_id=citizen.citizen_id,
            hypothetical_inputs=raw_overrides,
            total_schemes_evaluated=len(schemes),
            newly_eligible_count=newly_eligible_count,
            newly_ineligible_count=newly_ineligible_count,
            unaltered_eligible_count=unaltered_eligible_count,
            improved_score_count=improved_score_count,
            overall_summary=overall_summary,
            simulated_schemes=simulated_schemes,
        )

    @staticmethod
    def _compute_condition_deltas(
        base_details: Optional[Dict[str, Any]],
        sim_details: Optional[Dict[str, Any]],
    ) -> List[ConditionDelta]:
        """Compares baseline rule results with simulated rule results using stable group and rule indexing."""
        deltas: List[ConditionDelta] = []
        if not base_details or not sim_details:
            return deltas

        # Index baseline rules stably by (group_index, rule_index)
        base_rules: Dict[Tuple[int, int], Dict[str, Any]] = {}
        for g_idx, bg in enumerate(base_details.get("groups", [])):
            for r_idx, br in enumerate(bg.get("rules", [])):
                base_rules[(g_idx, r_idx)] = br

        for g_idx, sg in enumerate(sim_details.get("groups", [])):
            for r_idx, sr in enumerate(sg.get("rules", [])):
                param = sr.get("parameter", "")
                desc = sr.get("description", "") or ""
                br = base_rules.get((g_idx, r_idx))

                base_val = br.get("actual") if br else None
                sim_val = sr.get("actual")
                base_passed = br.get("passed", False) if br else False
                sim_passed = sr.get("passed", False)

                # Has the condition outcome or value changed?
                if base_val != sim_val or base_passed != sim_passed:
                    if not base_passed and sim_passed:
                        status = "IMPROVED"
                    elif base_passed and not sim_passed:
                        status = "WORSENED"
                    else:
                        status = "UNCHANGED"

                    label = PARAMETER_LABELS.get(param, param.replace("_", " ").title())
                    deltas.append(
                        ConditionDelta(
                            parameter=param,
                            parameter_label=label,
                            rule_description=desc or None,
                            baseline_value=base_val,
                            simulated_value=sim_val,
                            baseline_passed=base_passed,
                            simulated_passed=sim_passed,
                            status=status,
                        )
                    )

        return deltas

    @staticmethod
    def _determine_outcome_change(
        scheme_name: str,
        base_eligible: bool,
        sim_eligible: bool,
        base_score: Optional[float],
        sim_score: Optional[float],
        changed_conditions: List[ConditionDelta],
    ) -> Tuple[str, str]:
        """Categorizes outcome change and creates user-friendly explanation."""
        b_score = base_score or 0.0
        s_score = sim_score or 0.0

        improved_params = [
            c.parameter_label for c in changed_conditions if c.status == "IMPROVED"
        ]
        worsened_params = [
            c.parameter_label for c in changed_conditions if c.status == "WORSENED"
        ]

        if not base_eligible and sim_eligible:
            outcome_change = "BECAME_ELIGIBLE"
            if improved_params:
                summary = (
                    f"You would now be eligible for {scheme_name}! "
                    f"Requirements satisfied: {', '.join(improved_params)}."
                )
            else:
                summary = f"You would now be eligible for {scheme_name} under these hypothetical values."

        elif base_eligible and not sim_eligible:
            outcome_change = "BECAME_INELIGIBLE"
            if worsened_params:
                summary = (
                    f"You would no longer qualify for {scheme_name}. "
                    f"Criteria no longer met: {', '.join(worsened_params)}."
                )
            else:
                summary = f"You would no longer qualify for {scheme_name} under these hypothetical values."

        elif s_score > b_score:
            outcome_change = "SCORE_IMPROVED"
            delta = round(s_score - b_score, 1)
            if improved_params:
                summary = (
                    f"Eligibility match score improved by {delta}% (from {b_score:.1f}% to {s_score:.1f}%). "
                    f"Satisfied: {', '.join(improved_params)}."
                )
            else:
                summary = f"Eligibility match score improved from {b_score:.1f}% to {s_score:.1f}%."

        elif s_score < b_score:
            outcome_change = "SCORE_DECREASED"
            delta = round(b_score - s_score, 1)
            if worsened_params:
                summary = (
                    f"Eligibility match score dropped by {delta}% (from {b_score:.1f}% to {s_score:.1f}%). "
                    f"Unmet: {', '.join(worsened_params)}."
                )
            else:
                summary = f"Eligibility match score dropped from {b_score:.1f}% to {s_score:.1f}%."

        else:
            outcome_change = "UNCHANGED"
            if base_eligible:
                summary = f"You remain fully eligible for {scheme_name} (match score: {s_score:.1f}%)."
            else:
                summary = f"Eligibility for {scheme_name} remains unchanged (match score: {s_score:.1f}%)."

        return outcome_change, summary

    @staticmethod
    def _format_overall_summary(
        newly_eligible: int,
        newly_ineligible: int,
        improved_score: int,
        total_schemes: int,
    ) -> str:
        """Citizen-friendly executive summary across all simulated schemes."""
        parts = []
        if newly_eligible > 0:
            parts.append(f"would qualify for {newly_eligible} additional scheme{'s' if newly_eligible > 1 else ''}")
        if newly_ineligible > 0:
            parts.append(f"would lose eligibility for {newly_ineligible} scheme{'s' if newly_ineligible > 1 else ''}")
        if improved_score > 0 and newly_eligible == 0:
            parts.append(f"would improve criteria match on {improved_score} scheme{'s' if improved_score > 1 else ''}")

        if not parts:
            return "Hypothetical changes have no net impact on your scheme eligibility or match scores."

        return "With these changes, you " + " and ".join(parts) + "."
