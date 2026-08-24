"""
Eligibility Engine.
Evaluates deterministic rules against citizen profiles.
Produces full evaluation details for explainability.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Tuple

from app.models.citizen import CitizenMaster
from app.models.scheme import SchemeMaster, SchemeEligibilityRule

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

    def _resolve_parameter(self, citizen: CitizenMaster, parameter_name: str) -> Any:
        """Map parameter names to actual DB column values."""
        if parameter_name == "age":
            # Compute age dynamically
            today = date.today()
            dob = citizen.date_of_birth
            return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        
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
            return citizen.financial_profile.employment_status if citizen.financial_profile else None
            
        elif parameter_name == "social_category":
            return citizen.demographic_profile.social_category if citizen.demographic_profile else None
            
        elif parameter_name == "education_level":
            return citizen.demographic_profile.education_level if citizen.demographic_profile else None
            
        elif parameter_name == "disability_status":
            return citizen.demographic_profile.disability_status if citizen.demographic_profile else "NONE"
            
        elif parameter_name == "area_type":
            return citizen.location_profile.area_type if citizen.location_profile else None
            
        elif parameter_name == "state":
            return citizen.location_profile.state if citizen.location_profile else None
            
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
