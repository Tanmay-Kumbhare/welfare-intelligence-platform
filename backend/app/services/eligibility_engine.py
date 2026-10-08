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
        self,
        citizen: CitizenMaster,
        scheme: SchemeMaster,
        facts_dict: dict[str, Any] | None = None,
    ) -> Tuple[bool, dict[str, Any], str]:
        """
        Evaluate a single scheme for a citizen.
        Accepts optional preloaded facts_dict for O(1) bulk fact resolution.
        Returns: (overall_result, evaluation_details_jsonb, reason)
        """
        group_results = []
        total_rules = 0
        passed_rules_count = 0
        failed_rules_count = 0
        missing_rules_count = 0

        for group in scheme.rule_groups:
            rule_results = []
            
            for rule in group.rules:
                actual_value = self._resolve_parameter(citizen, rule.parameter_name, facts_dict=facts_dict)
                is_missing = actual_value is None
                passed = self._apply_operator(actual_value, rule.operator, rule.required_value)

                total_rules += 1
                if passed:
                    passed_rules_count += 1
                elif is_missing:
                    missing_rules_count += 1
                else:
                    failed_rules_count += 1

                rule_results.append({
                    "parameter": rule.parameter_name,
                    "actual": actual_value,
                    "operator": rule.operator,
                    "required": rule.required_value,
                    "passed": passed,
                    "is_missing": is_missing,
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

        # Rule Match Score calculation:
        # Range: 0.0 to 100.0 rounded to 1 decimal place.
        # Denominator: total_rules evaluated for this scheme.
        # Numerator: passed_rules_count.
        # Missing values are NOT counted as passed.
        # When a scheme has 0 rules: rule_match_score is 0.0 to avoid division by zero or misleading 100%.
        rule_match_score = (
            round((passed_rules_count / total_rules) * 100.0, 1)
            if total_rules > 0
            else 0.0
        )

        evaluation_details = {
            "overall_result": overall_result,
            "group_combining_operator": scheme.group_combining_operator,
            "rule_match_score": rule_match_score,
            "total_rules": total_rules,
            "passed_rules_count": passed_rules_count,
            "failed_rules_count": failed_rules_count,
            "missing_rules_count": missing_rules_count,
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

    def _fact_value(
        self, citizen: CitizenMaster, fact_code: str, facts_dict: dict[str, Any] | None = None
    ) -> str | None:
        """Open profile-fact value for a code (fact layer = canonical store
        the normalization pipeline writes). None when never answered."""
        if facts_dict is not None:
            return facts_dict.get(fact_code)
        for fact in (getattr(citizen, "profile_facts", None) or []):
            if fact.fact_code == fact_code and fact.effective_until is None:
                return fact.fact_value
        return None

    def _resolve_parameter(
        self, citizen: CitizenMaster, parameter_name: str, facts_dict: dict[str, Any] | None = None
    ) -> Any:
        """Map parameter names to actual DB column or bulk fact values."""
        if parameter_name == "age":
            # Canonical source: normalized AGE fact
            age_val = self._fact_value(citizen, "AGE", facts_dict=facts_dict)
            if age_val is not None:
                try:
                    return int(age_val)
                except (TypeError, ValueError):
                    pass
            dob = citizen.date_of_birth
            if dob is None:
                return None
            return calculate_age(dob)
        
        elif parameter_name == "gender":
            gen_val = self._fact_value(citizen, "GENDER", facts_dict=facts_dict)
            return gen_val if gen_val is not None else citizen.gender
        
        elif parameter_name == "citizen_type":
            return citizen.citizen_type
            
        elif parameter_name == "annual_income":
            inc_val = self._fact_value(citizen, "ANNUAL_INCOME", facts_dict=facts_dict)
            if inc_val is not None:
                try:
                    return float(inc_val)
                except (TypeError, ValueError):
                    pass
            return float(citizen.financial_profile.annual_income) if citizen.financial_profile and citizen.financial_profile.annual_income is not None else 0.0
            
        elif parameter_name == "poverty_category":
            pov_val = self._fact_value(citizen, "POVERTY_CATEGORY", facts_dict=facts_dict)
            if pov_val is not None:
                return pov_val
            return citizen.financial_profile.poverty_category if citizen.financial_profile else None
            
        elif parameter_name == "land_holding_size":
            land_val = self._fact_value(citizen, "LAND_HOLDING_SIZE", facts_dict=facts_dict)
            if land_val is not None:
                try:
                    return float(land_val)
                except (TypeError, ValueError):
                    pass
            return float(citizen.financial_profile.land_holding_size) if citizen.financial_profile and citizen.financial_profile.land_holding_size is not None else 0.0
            
        elif parameter_name == "is_bpl_card_holder":
            bpl_val = self._fact_value(citizen, "IS_BPL_CARD_HOLDER", facts_dict=facts_dict)
            if bpl_val is not None:
                return bpl_val in ("True", "true", "1", "YES", True)
            return citizen.financial_profile.is_bpl_card_holder if citizen.financial_profile else False
            
        elif parameter_name == "is_income_tax_payer":
            tax_val = self._fact_value(citizen, "IS_INCOME_TAX_PAYER", facts_dict=facts_dict)
            if tax_val is not None:
                return tax_val in ("True", "true", "1", "YES", True)
            return citizen.financial_profile.is_income_tax_payer if citizen.financial_profile else False
            
        elif parameter_name == "employment_status":
            fact_value = self._fact_value(citizen, "EMPLOYMENT_STATUS", facts_dict=facts_dict)
            if fact_value is not None:
                return fact_value
            return citizen.financial_profile.employment_status if citizen.financial_profile else None
            
        elif parameter_name == "social_category":
            soc_val = self._fact_value(citizen, "SOCIAL_CATEGORY", facts_dict=facts_dict)
            if soc_val is not None:
                return soc_val
            return citizen.demographic_profile.social_category if citizen.demographic_profile else None
            
        elif parameter_name == "education_level":
            fact_value = self._fact_value(citizen, "EDUCATION_LEVEL", facts_dict=facts_dict)
            if fact_value is not None:
                return fact_value
            return citizen.demographic_profile.education_level if citizen.demographic_profile else None
            
        elif parameter_name == "disability_status":
            fact_value = self._fact_value(citizen, "DISABILITY_STATUS", facts_dict=facts_dict)
            if fact_value == "YES":
                return "PHYSICALLY_DISABLED"
            if fact_value == "NO":
                return "NONE"
            if fact_value == "PENDING":
                return "PENDING"
            return citizen.demographic_profile.disability_status if citizen.demographic_profile else "NONE"
            
        elif parameter_name == "area_type":
            area_val = self._fact_value(citizen, "AREA_TYPE", facts_dict=facts_dict)
            if area_val is not None:
                return area_val
            return citizen.location_profile.area_type if citizen.location_profile else None

        elif parameter_name == "state":
            state_val = self._fact_value(citizen, "STATE", facts_dict=facts_dict)
            if state_val is not None:
                return state_val
            return citizen.location_profile.state if citizen.location_profile else None

        # ------------------------------------------------------------------
        # Academic-record parameters (read from the open profile-fact layer;
        # facts are the canonical store for exact 10th/12th marks, current
        # degree, CGPA, etc.). Additive branch — existing logic unchanged.
        # ------------------------------------------------------------------
        elif parameter_name in (
            "tenth_percentage", "twelfth_percentage", "twelfth_percentile",
            "graduation_percentage", "graduation_cgpa",
            "livestock_cattle_count", "livestock_poultry_count",
        ):
            fact_code_map = {
                "tenth_percentage": "TENTH_PERCENTAGE",
                "twelfth_percentage": "TWELFTH_PERCENTAGE",
                "twelfth_percentile": "TWELFTH_PERCENTILE",
                "graduation_percentage": "GRADUATION_PERCENTAGE",
                "graduation_cgpa": "GRADUATION_CGPA",
                "livestock_cattle_count": "LIVESTOCK_CATTLE_COUNT",
                "livestock_poultry_count": "LIVESTOCK_POULTRY_COUNT",
            }
            wanted = fact_code_map[parameter_name]
            val = self._fact_value(citizen, wanted, facts_dict=facts_dict)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    pass
            return None  # never answered — rule fails with "not provided"

        elif parameter_name in (
            "current_education_level", "current_degree", "current_branch",
            "current_year", "current_semester", "highest_education_level",
        ):
            fact_code_map = {
                "current_education_level": "CURRENT_EDUCATION_LEVEL",
                "current_degree": "CURRENT_DEGREE",
                "current_branch": "CURRENT_BRANCH",
                "current_year": "CURRENT_YEAR",
                "current_semester": "CURRENT_SEMESTER",
                "highest_education_level": "HIGHEST_EDUCATION_LEVEL",
            }
            wanted = fact_code_map[parameter_name]
            return self._fact_value(citizen, wanted, facts_dict=facts_dict)

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
