import pytest
from app.services.eligibility_engine import EligibilityEngine
from app.models.citizen import CitizenMaster, FinancialProfile
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from datetime import date

def test_pm_kisan_eligibility():
    engine = EligibilityEngine()
    
    # Mock Citizen (Farmer, eligible)
    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1980, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(
        land_holding_size=1.5,
        is_income_tax_payer=False
    )
    
    # Mock Scheme (PM-KISAN)
    scheme = SchemeMaster(
        scheme_name="PM-KISAN",
        group_combining_operator="AND",
    )
    
    group1 = SchemeRuleGroup(group_name="Farmer", intra_group_operator="AND")
    group1.rules = [
        SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="FARMER"),
        SchemeEligibilityRule(parameter_name="land_holding_size", operator="<=", required_value="2.0")
    ]
    
    group2 = SchemeRuleGroup(group_name="Exclusion", intra_group_operator="AND")
    group2.rules = [
        SchemeEligibilityRule(parameter_name="is_income_tax_payer", operator="==", required_value="false")
    ]
    
    scheme.rule_groups = [group1, group2]
    
    result, details, reason = engine.evaluate_scheme(citizen, scheme)
    
    assert result is True
    # Evaluation details metrics verification
    assert details["overall_result"] is True
    assert details["rule_match_score"] == 100.0
    assert details["total_rules"] == 3
    assert details["passed_rules_count"] == 3
    assert details["failed_rules_count"] == 0
    assert details["missing_rules_count"] == 0


def test_three_rules_two_passed_one_failed_score():
    """3 evaluated rules: 2 passed and 1 failed -> 66.7%."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1990, 5, 20),
    )
    # land_holding_size 3.0 fails rule (<= 2.0)
    citizen.financial_profile = FinancialProfile(
        land_holding_size=3.0,
        is_income_tax_payer=False,
    )

    scheme = SchemeMaster(
        scheme_name="Test Agriculture Scheme",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Criteria", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="FARMER"),  # Passed
        SchemeEligibilityRule(parameter_name="is_income_tax_payer", operator="==", required_value="false"),  # Passed
        SchemeEligibilityRule(parameter_name="land_holding_size", operator="<=", required_value="2.0"),  # Failed
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    # Strict eligibility is False
    assert result is False
    assert details["overall_result"] is False
    # Exactly 2/3 = 66.7%
    assert details["rule_match_score"] == 66.7
    assert details["total_rules"] == 3
    assert details["passed_rules_count"] == 2
    assert details["failed_rules_count"] == 1
    assert details["missing_rules_count"] == 0


def test_all_rules_passed_score():
    """All evaluated rules passed -> 100.0%."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="STUDENT",
        gender="FEMALE",
        date_of_birth=date(2005, 1, 1),
    )

    scheme = SchemeMaster(
        scheme_name="Test Scholarship",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Eligibility", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="STUDENT"),
        SchemeEligibilityRule(parameter_name="gender", operator="==", required_value="FEMALE"),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert result is True
    assert details["overall_result"] is True
    assert details["rule_match_score"] == 100.0
    assert details["total_rules"] == 2
    assert details["passed_rules_count"] == 2
    assert details["failed_rules_count"] == 0
    assert details["missing_rules_count"] == 0


def test_missing_rule_values_not_counted_as_passed():
    """Missing rule values are categorized as missing and NOT counted as passed."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2000, 1, 1),
    )
    # demographic_profile is None, so social_category and disability_status are missing (None)
    citizen.demographic_profile = None

    scheme = SchemeMaster(
        scheme_name="Special Category Scheme",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Category Rules", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="STUDENT"),  # Passed
        SchemeEligibilityRule(parameter_name="social_category", operator="==", required_value="OBC"),  # Missing
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert result is False
    assert details["overall_result"] is False
    assert details["rule_match_score"] == 50.0
    assert details["total_rules"] == 2
    assert details["passed_rules_count"] == 1
    assert details["failed_rules_count"] == 0
    assert details["missing_rules_count"] == 1

    # Check rule level evidence
    rules = details["groups"][0]["rules"]
    assert rules[0]["passed"] is True
    assert rules[0]["is_missing"] is False
    assert rules[1]["passed"] is False
    assert rules[1]["is_missing"] is True
    assert rules[1]["actual"] is None


def test_no_evaluable_rules():
    """Schemes with 0 rules produce 0.0% score without division-by-zero or false 100%."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="GENERAL",
        date_of_birth=date(1995, 1, 1),
    )

    scheme = SchemeMaster(
        scheme_name="Empty Scheme",
        group_combining_operator="AND",
    )
    scheme.rule_groups = []

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    # Empty rule groups vacuously satisfy overall_result per existing engine logic
    assert result is True
    assert details["rule_match_score"] == 0.0
    assert details["total_rules"] == 0
    assert details["passed_rules_count"] == 0
    assert details["failed_rules_count"] == 0
    assert details["missing_rules_count"] == 0


def test_and_or_rule_groups_score_and_eligibility():
    """
    Test AND / OR rule groups:
    Demonstrates that strict eligibility (Boolean) remains completely separate
    from the raw Rule Match Score (% of rules satisfied).
    """
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1985, 3, 10),
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=300000.0,
        is_bpl_card_holder=False,
    )

    # Scheme with OR group: Citizen needs EITHER BPL card OR income <= 400000
    scheme = SchemeMaster(
        scheme_name="Flexible Support Scheme",
        group_combining_operator="AND",
    )
    group1 = SchemeRuleGroup(group_name="Type", intra_group_operator="AND")
    group1.rules = [
        SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="FARMER"),  # Passed
    ]

    group2 = SchemeRuleGroup(group_name="Income or BPL", intra_group_operator="OR")
    group2.rules = [
        SchemeEligibilityRule(parameter_name="is_bpl_card_holder", operator="==", required_value="true"),  # Failed
        SchemeEligibilityRule(parameter_name="annual_income", operator="<=", required_value="400000"),  # Passed
    ]
    scheme.rule_groups = [group1, group2]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    # Eligible: Group 1 passed (AND), Group 2 passed (OR: 1 of 2 rules passed)
    assert result is True
    assert details["overall_result"] is True

    # Rule Match Score: 2 passed out of 3 total rules = 66.7%
    assert details["total_rules"] == 3
    assert details["passed_rules_count"] == 2
    assert details["failed_rules_count"] == 1
    assert details["rule_match_score"] == 66.7
