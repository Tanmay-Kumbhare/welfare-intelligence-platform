"""
Eligibility Engine.
Evaluates deterministic rules against citizen profiles.
Produces full evaluation details for explainability.
"""

from __future__ import annotations

import logging
from typing import Any, Tuple

from app.models.citizen import CitizenMaster
from app.models.scheme import SchemeMaster, SchemeEligibilityRule
from app.utils.date_calc import calculate_age

logger = logging.getLogger(__name__)


class EligibilityEngine:
    """Core rule evaluation engine."""

    def evaluate_scheme(
        self, citizen: CitizenMaster, scheme: SchemeMaster
    ) -> Tuple[bool, dict[str, Any], str]:
        """
        Evaluate a single scheme for a citizen.
        Returns: (overall_result, evaluation_details_jsonb, reason)
        """
        group_results = []
        scheme_passed = True  # Will be recalculated

        for group in scheme.rule_groups:
            rule_results = []
            
            for rule in group.rules:
                actual_value = self._resolve_parameter(citizen, rule.parameter_name)
                passed = self._apply_operator(actual_value, rule.operator, rule.required_value)

                rule_results.append({
                    "parameter": rule.parameter_name,
                    "actual": actual_value,
                    "operator": rule.operator,
                    "required": rule.required_value,
                    "passed": passed,
                    "description": rule.rule_description,
                })

            if group.intra_group_operator.upper() == "AND":
                group_passed = all(r["passed"] for r in rule_results) if rule_results else True
            else:  # OR
                group_passed = any(r["passed"] for r in rule_results) if rule_results else True

            group_results.append({
                "group_name": group.group_name,
                "intra_group_operator": group.intra_group_operator,
                "group_passed": group_passed,
                "rules": rule_results,
            })

        if scheme.group_combining_operator.upper() == "AND":
            overall_result = all(g["group_passed"] for g in group_results) if group_results else True
        else:  # OR
            overall_result = any(g["group_passed"] for g in group_results) if group_results else True

        evaluation_details = {
            "overall_result": overall_result,
            "group_combining_operator": scheme.group_combining_operator,
            "groups": group_results,
        }

        if overall_result:
            reason = f"Citizen meets all criteria for {scheme.scheme_name}."
        else:
            failed_rules = []
            for g in group_results:
                for r in g["rules"]:
                    if not r["passed"]:
                        failed_rules.append(r["description"] or r["parameter"])
            reason = f"Does not meet criteria: {', '.join(failed_rules)}"

        return overall_result, evaluation_details, reason

    def _fact_value(self, citizen: CitizenMaster, fact_code: str) -> str | None:
        """Open profile-fact value for a code (fact layer = canonical store
        the normalization pipeline writes). None when never answered."""
        for fact in (getattr(citizen, "profile_facts", None) or []):
            if fact.fact_code == fact_code and fact.effective_until is None:
                return fact.fact_value
        return None

    def _resolve_parameter(self, citizen: CitizenMaster, parameter_name: str) -> Any:
        """Map parameter names to actual DB column values."""
        if parameter_name == "age":
            # Canonical source: the normalized AGE profile fact (derived from
            # the citizen-submitted DATE_OF_BIRTH by normalization). Falls
            # back to identity-record DOB + calculate_age only for citizens
            # who have never completed a form (no fact layer yet).
            facts = getattr(citizen, "profile_facts", None) or []
            for fact in facts:
                if fact.fact_code == "AGE" and fact.effective_until is None:
                    try:
                        return int(fact.fact_value)
                    except (TypeError, ValueError):
                        break
            dob = citizen.date_of_birth
            if dob is None:
                return None
            return calculate_age(dob)
        
        elif parameter_name == "gender":
            return citizen.gender
        
        elif parameter_name == "citizen_type":
            return citizen.citizen_type
            
        elif parameter_name == "annual_income":
            return float(citizen.financial_profile.annual_income) if citizen.financial_profile and citizen.financial_profile.annual_income is not None else 0.0
            
        elif parameter_name == "poverty_category":
            return citizen.financial_profile.poverty_category if citizen.financial_profile else None
            
        elif parameter_name == "land_holding_size":
            return float(citizen.financial_profile.land_holding_size) if citizen.financial_profile and citizen.financial_profile.land_holding_size is not None else 0.0
            
        elif parameter_name == "is_bpl_card_holder":
            return citizen.financial_profile.is_bpl_card_holder if citizen.financial_profile else False
            
        elif parameter_name == "is_income_tax_payer":
            return citizen.financial_profile.is_income_tax_payer if citizen.financial_profile else False
            
        elif parameter_name == "employment_status":
            # Fact layer first (the canonical post-normalization store the
            # registry writes), then the legacy V1 financial-profile column.
            fact_value = self._fact_value(citizen, "EMPLOYMENT_STATUS")
            if fact_value is not None:
                return fact_value
            return citizen.financial_profile.employment_status if citizen.financial_profile else None
            
        elif parameter_name == "social_category":
            return citizen.demographic_profile.social_category if citizen.demographic_profile else None
            
        elif parameter_name == "education_level":
            # Fact layer first: the v3 form writes education answers to the
            # EDUCATION_LEVEL fact; the old demographic_profile.education_level
            # column is empty for citizens who only used the form.
            fact_value = self._fact_value(citizen, "EDUCATION_LEVEL")
            if fact_value is not None:
                return fact_value
            return citizen.demographic_profile.education_level if citizen.demographic_profile else None
            
        elif parameter_name == "disability_status":
            # Fact layer first. The v3 form's HAS_DISABILITY answer stores
            # YES/NO/PENDING; map deterministically to the canonical values
            # scheme rules compare against (NONE = no disability).
            fact_value = self._fact_value(citizen, "DISABILITY_STATUS")
            if fact_value == "YES":
                return "PHYSICALLY_DISABLED"
            if fact_value == "NO":
                return "NONE"
            if fact_value == "PENDING":
                return "PENDING"
            return citizen.demographic_profile.disability_status if citizen.demographic_profile else "NONE"
            
        elif parameter_name == "area_type":
            return citizen.location_profile.area_type if citizen.location_profile else None

        elif parameter_name == "state":
            return citizen.location_profile.state if citizen.location_profile else None

        # ------------------------------------------------------------------
        # Academic-record parameters (read from the open profile-fact layer;
        # facts are the canonical store for exact 10th/12th marks and
        # percentile. Additive branch — existing parameter logic unchanged.
        # ------------------------------------------------------------------
        elif parameter_name in (
            "tenth_percentage", "twelfth_percentage", "twelfth_percentile",
            "livestock_cattle_count", "livestock_poultry_count",
        ):
            fact_code_map = {
                "tenth_percentage": "TENTH_PERCENTAGE",
                "twelfth_percentage": "TWELFTH_PERCENTAGE",
                "twelfth_percentile": "TWELFTH_PERCENTILE",
                "livestock_cattle_count": "LIVESTOCK_CATTLE_COUNT",
                "livestock_poultry_count": "LIVESTOCK_POULTRY_COUNT",
            }
            wanted = fact_code_map[parameter_name]
            for fact in (getattr(citizen, "profile_facts", None) or []):
                if fact.fact_code == wanted and fact.effective_until is None:
                    try:
                        return float(fact.fact_value)
                    except (TypeError, ValueError):
                        break
            return None  # never answered — rule fails with "not provided"

        else:
            logger.warning(f"Unknown parameter_name: {parameter_name}")
            return None

    def _apply_operator(self, actual: Any, operator: str, required: str) -> bool:
        """Apply comparison operator after coercing types."""
        if actual is None:
            return False

        # Coerce required value to actual value's type
        coerced_required: Any = required
        try:
            if isinstance(actual, bool):
                coerced_required = required.lower() in ("true", "1", "yes")
            elif isinstance(actual, int):
                coerced_required = int(float(required))
            elif isinstance(actual, float):
                coerced_required = float(required)
        except ValueError:
            return False

        # IN operator handles a comma-separated list of strings
        if operator == "IN":
            req_list = [x.strip() for x in required.split(",")]
            return str(actual) in req_list
            
        # Standard comparisons
        if operator == "==":
            return actual == coerced_required
        elif operator == "!=":
            return actual != coerced_required
        elif operator == "<":
            return actual < coerced_required
        elif operator == "<=":
            return actual <= coerced_required
        elif operator == ">":
            return actual > coerced_required
        elif operator == ">=":
            return actual >= coerced_required
            
        return False
