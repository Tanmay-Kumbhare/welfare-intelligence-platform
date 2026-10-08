import pytest
from datetime import date
from app.services.eligibility_engine import EligibilityEngine
from app.models.citizen import CitizenMaster, FinancialProfile, DemographicProfile, LocationProfile
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule


def test_weighted_match_score_calculation():
    """Verify deterministic weighted rule-match scoring formula: sum(passed_weights)/sum(total_weights)*100."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2002, 1, 1), # Age ~24
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=180000.0,
    )
    citizen.demographic_profile = DemographicProfile(
        social_category="GENERAL",
    )

    scheme = SchemeMaster(
        scheme_name="Higher Education Scholarship",
        group_combining_operator="AND",
    )

    group = SchemeRuleGroup(group_name="Eligibility", intra_group_operator="AND")
    # age weight = 15, annual_income weight = 25, social_category weight = 25
    group.rules = [
        SchemeEligibilityRule(parameter_name="age", operator=">=", required_value="18", rule_description="Age >= 18"),
        SchemeEligibilityRule(parameter_name="annual_income", operator="<=", required_value="250000", rule_description="Income <= 2.5L"),
        SchemeEligibilityRule(parameter_name="social_category", operator="==", required_value="OBC", rule_description="Category OBC"),
    ]
    scheme.rule_groups = [group]

    # Partial match: age (15, pass), income (25, pass), category (25, fail) -> 40/65 = 62%
    result, details, reason = engine.evaluate_scheme(citizen, scheme)
    assert result is False  # Mandatory hard gate: fails because social_category != OBC
    assert details["total_rules"] == 3
    assert details["passed_rules"] == 2
    assert details["total_weight"] == 65
    assert details["passed_weight"] == 40
    assert details["match_score"] == 62
    assert "Age >= 18" in details["matched_rules"]
    assert "Income <= 2.5L" in details["matched_rules"]
    assert "Category OBC" in details["failed_rules"]

    # Full match: change category to OBC -> 65/65 = 100%
    citizen.demographic_profile.social_category = "OBC"
    result_full, details_full, reason_full = engine.evaluate_scheme(citizen, scheme)
    assert result_full is True
    assert details_full["total_rules"] == 3
    assert details_full["passed_rules"] == 3
    assert details_full["total_weight"] == 65
    assert details_full["passed_weight"] == 65
    assert details_full["match_score"] == 100
    assert len(details_full["matched_rules"]) == 3
    assert len(details_full["failed_rules"]) == 0


def test_mandatory_rule_failure_is_hard_gate():
    """Verify that mandatory rule failure strictly results in overall_result=False regardless of score."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2000, 1, 1),
    )
    # Income 5L exceeds threshold of 2.5L
    citizen.financial_profile = FinancialProfile(annual_income=500000.0)
    citizen.demographic_profile = DemographicProfile(social_category="OBC")
    citizen.location_profile = LocationProfile(state="Maharashtra")

    scheme = SchemeMaster(
        scheme_name="State Merit Scholarship",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="MandatoryCriteria", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="annual_income", operator="<=", required_value="250000", rule_description="Income <= 2.5L"),
        SchemeEligibilityRule(parameter_name="social_category", operator="==", required_value="OBC", rule_description="OBC Category"),
        SchemeEligibilityRule(parameter_name="state", operator="==", required_value="Maharashtra", rule_description="State Maharashtra"),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)
    # 2 out of 3 rules match (OBC weight 25 + State weight 10 = 35 / 60 = 58%), but overall is strictly False
    assert result is False
    assert details["match_score"] == 58
    assert "Income <= 2.5L" in details["failed_rules"]


def test_custom_rule_weights():
    """Verify that explicitly configured rule weights are honored."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2000, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(annual_income=150000.0)

    scheme = SchemeMaster(
        scheme_name="Custom Weighted Scheme",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="G1", intra_group_operator="AND")
    rule1 = SchemeEligibilityRule(parameter_name="annual_income", operator="<=", required_value="200000", rule_description="Income <= 2L")
    rule1.weight = 80  # Custom weight 80

    rule2 = SchemeEligibilityRule(parameter_name="age", operator="<=", required_value="20", rule_description="Age <= 20")
    rule2.weight = 20  # Custom weight 20

    group.rules = [rule1, rule2]
    scheme.rule_groups = [group]

    # Citizen passes rule1 (weight 80) and fails rule2 (age ~26 > 20)
    result, details, _ = engine.evaluate_scheme(citizen, scheme)
    assert details["total_weight"] == 100
    assert details["passed_weight"] == 80
    assert details["match_score"] == 80


def test_deterministic_consistency():
    """Verify repeated evaluation produces the exact same score with 0 drift."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2000, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(annual_income=200000.0)

    scheme = SchemeMaster(
        scheme_name="Deterministic Test",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="G1", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="annual_income", operator="<=", required_value="250000", rule_description="Income check"),
    ]
    scheme.rule_groups = [group]

    scores = []
    for _ in range(10):
        result, details, _ = engine.evaluate_scheme(citizen, scheme)
        scores.append(details["match_score"])

    assert all(s == 100 for s in scores)


def test_non_eligible_scheme_receives_score_and_failed_mandatory_rules():
    """Verify that non-eligible schemes also receive accurate match scores and track failed mandatory rules."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2002, 1, 1), # Age ~24
    )
    citizen.financial_profile = FinancialProfile(annual_income=300000.0) # Fails <= 2.5L
    citizen.demographic_profile = DemographicProfile(social_category="OBC") # Passes OBC
    citizen.location_profile = LocationProfile(state="Maharashtra") # Passes Maharashtra

    scheme = SchemeMaster(
        scheme_name="Higher Education State Scholarship",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="CoreCriteria", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="annual_income", operator="<=", required_value="250000", rule_description="Income <= 2.5L"), # wt 25 (fail)
        SchemeEligibilityRule(parameter_name="social_category", operator="==", required_value="OBC", rule_description="OBC Category"), # wt 25 (pass)
        SchemeEligibilityRule(parameter_name="state", operator="==", required_value="Maharashtra", rule_description="State Maharashtra"), # wt 10 (pass)
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    # 35 / 60 = 58% Rule Match Score
    assert result is False
    assert details["match_score"] == 58
    assert "Income <= 2.5L" in details["failed_mandatory_rules"]
    assert "OBC Category" in details["matched_rules"]
