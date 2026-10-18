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


DEFAULT_PARAMETER_WEIGHTS: dict[str, int] = {
    # Income (25)
    "annual_income": 25,
    "poverty_category": 25,
    "is_bpl_card_holder": 25,
    "is_income_tax_payer": 25,
    # Social Category (25)
    "social_category": 25,
    "caste_category": 25,
    # Education (20)
    "education_level": 20,
    "academic_percentage": 20,
    "marksheet_percentage": 20,
    "academic_cgpa": 20,
    "course": 20,
    "branch": 20,
    "admission_type": 20,
    # Persona / Citizen Type (20)
    "citizen_type": 20,
    # Age (15)
    "age": 15,
    # Location (10)
    "state": 10,
    "area_type": 10,
    "district": 10,
    # Other criteria: 5
    "employment_status": 5,
    "disability_status": 5,
    "land_holding_size": 15,
}


def get_rule_weight(rule: SchemeEligibilityRule) -> int:
    """Return configured rule weight or fallback to standard category default."""
    custom_weight = getattr(rule, "weight", None)
    if custom_weight is not None and isinstance(custom_weight, (int, float)) and custom_weight > 0:
        return int(custom_weight)
    param = (getattr(rule, "parameter_name", "") or "").lower()
    return DEFAULT_PARAMETER_WEIGHTS.get(param, 5)


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
        passed_rules = 0
        total_weight = 0
        passed_weight = 0
        matched_rules = []
        failed_rules = []
        unknown_rules = []
        failed_mandatory_rules = []

        for group in scheme.rule_groups:
            rule_results = []
            
            for rule in group.rules:
                total_rules += 1
                rule_w = get_rule_weight(rule)
                total_weight += rule_w

                if facts_dict is not None:
                    try:
                        actual_value = self._resolve_parameter(citizen, rule.parameter_name, facts_dict=facts_dict)
                    except TypeError:
                        actual_value = self._resolve_parameter(citizen, rule.parameter_name)
                else:
                    actual_value = self._resolve_parameter(citizen, rule.parameter_name)
                is_missing = actual_value is None
                passed = self._apply_operator(actual_value, rule.operator, rule.required_value)
                desc = rule.rule_description or rule.parameter_name

                if passed:
                    passed_rules += 1
                    passed_rules_count += 1
                    passed_weight += rule_w
                    matched_rules.append(desc)
                    status_str = "PASS"
                elif is_missing:
                    missing_rules_count += 1
                    desc_unknown = f"{desc} (Not provided)"
                    unknown_rules.append(desc_unknown)
                    failed_rules.append(desc_unknown)
                    status_str = "UNKNOWN"
                else:
                    failed_rules_count += 1
                    failed_rules.append(desc)
                    status_str = "FAIL"

                rule_results.append({
                    "parameter": rule.parameter_name,
                    "actual": actual_value,
                    "operator": rule.operator,
                    "required": rule.required_value,
                    "passed": passed,
                    "is_missing": is_missing,
                    "status": status_str,
                    "description": rule.rule_description,
                    "weight": rule_w,
                })

            if group.intra_group_operator.upper() == "AND":
                group_passed = all(r["passed"] for r in rule_results) if rule_results else False
            else:  # OR
                group_passed = any(r["passed"] for r in rule_results) if rule_results else False

            if not group_passed:
                for r in rule_results:
                    if not r["passed"]:
                        failed_mandatory_rules.append(r["description"] or r["parameter"])

            group_results.append({
                "group_name": group.group_name,
                "intra_group_operator": group.intra_group_operator,
                "group_passed": group_passed,
                "rules": rule_results,
            })

        if scheme.group_combining_operator.upper() == "AND":
            overall_result = all(g["group_passed"] for g in group_results) if (group_results and total_rules > 0) else False
        else:  # OR
            overall_result = any(g["group_passed"] for g in group_results) if (group_results and total_rules > 0) else False

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
        if total_weight > 0:
            match_score = round((passed_weight / total_weight) * 100)
        else:
            match_score = 100 if overall_result else 0

        evaluation_details = {
            "overall_result": overall_result,
            "match_score": match_score,
            "total_rules": total_rules,
            "passed_rules": passed_rules,
            "total_weight": total_weight,
            "passed_weight": passed_weight,
            "matched_rules": matched_rules,
            "failed_rules": failed_rules,
            "unknown_rules": unknown_rules,
            "failed_mandatory_rules": failed_mandatory_rules,
            "group_combining_operator": scheme.group_combining_operator,
            "rule_match_score": rule_match_score,
            "passed_rules_count": passed_rules_count,
            "failed_rules_count": failed_rules_count,
            "missing_rules_count": missing_rules_count,
            "groups": group_results,
        }

        if overall_result:
            reason = f"Citizen meets all criteria for {scheme.scheme_name}."
        else:
            if failed_rules:
                reason = f"Does not meet criteria: {', '.join(failed_rules)}"
            else:
                reason = f"No valid eligibility criteria defined for {scheme.scheme_name}."

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

    @staticmethod
    def _parse_bool_value(val: Any) -> bool | None:
        """Parse truthy and falsy values robustly; return None if missing or invalid."""
        if isinstance(val, bool):
            return val
        if val is not None:
            s = str(val).strip().upper()
            if s in ("TRUE", "1", "YES"):
                return True
            if s in ("FALSE", "0", "NO"):
                return False
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
            if citizen.financial_profile and citizen.financial_profile.annual_income is not None:
                try:
                    return float(citizen.financial_profile.annual_income)
                except (TypeError, ValueError):
                    pass
            return None
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
            if citizen.financial_profile and citizen.financial_profile.land_holding_size is not None:
                try:
                    return float(citizen.financial_profile.land_holding_size)
                except (TypeError, ValueError):
                    pass
            return None

        elif parameter_name == "is_bpl_card_holder":
            bpl_val = self._fact_value(citizen, "IS_BPL_CARD_HOLDER", facts_dict=facts_dict)
            parsed_bool = self._parse_bool_value(bpl_val)
            if parsed_bool is not None:
                return parsed_bool
            if citizen.financial_profile and citizen.financial_profile.is_bpl_card_holder is not None:
                profile_bool = self._parse_bool_value(citizen.financial_profile.is_bpl_card_holder)
                if profile_bool is not None:
                    return profile_bool
            return None

        elif parameter_name == "is_income_tax_payer":
            tax_val = self._fact_value(citizen, "IS_INCOME_TAX_PAYER", facts_dict=facts_dict)
            parsed_bool = self._parse_bool_value(tax_val)
            if parsed_bool is not None:
                return parsed_bool
            if citizen.financial_profile and citizen.financial_profile.is_income_tax_payer is not None:
                profile_bool = self._parse_bool_value(citizen.financial_profile.is_income_tax_payer)
                if profile_bool is not None:
                    return profile_bool
            return None
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
            if fact_value is not None:
                return fact_value
            return citizen.demographic_profile.disability_status if citizen.demographic_profile else None
            
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
