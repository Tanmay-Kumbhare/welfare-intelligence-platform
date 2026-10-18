import pytest
from app.services.eligibility_engine import EligibilityEngine
from app.models.citizen import CitizenMaster, FinancialProfile, DemographicProfile
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
    """Schemes with 0 rules produce 0.0% score and are never marked confirmed eligible."""
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

    # Empty rule groups must never evaluate to confirmed eligible
    assert result is False
    assert details["overall_result"] is False
    assert details["rule_match_score"] == 0.0
    assert details["total_rules"] == 0
    assert details["passed_rules_count"] == 0
    assert details["failed_rules_count"] == 0
    assert details["missing_rules_count"] == 0
    assert "No valid eligibility criteria defined" in reason


def test_empty_rule_group_never_confirmed_eligible():
    """A scheme containing rule groups with no rules must not evaluate to True."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="GENERAL",
        date_of_birth=date(1995, 1, 1),
    )

    scheme = SchemeMaster(
        scheme_name="Empty Group Scheme",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Empty Group", intra_group_operator="AND")
    group.rules = []
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert result is False
    assert details["overall_result"] is False
    assert details["groups"][0]["group_passed"] is False
    assert details["rule_match_score"] == 0.0
    assert details["total_rules"] == 0


def test_missing_annual_income_fails_ceiling_rule():
    """Missing annual income resolves to None, fails <= ceiling rule, and records as missing."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2002, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(annual_income=None)

    scheme = SchemeMaster(
        scheme_name="Scholarship With Income Cap",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Income Criteria", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="annual_income", operator="<=", required_value="250000"),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert result is False
    assert details["overall_result"] is False
    assert details["missing_rules_count"] == 1
    assert details["passed_rules_count"] == 0
    assert details["rule_match_score"] == 0.0
    rule_evidence = details["groups"][0]["rules"][0]
    assert rule_evidence["actual"] is None
    assert rule_evidence["is_missing"] is True
    assert rule_evidence["passed"] is False


def test_valid_zero_income_passes_ceiling_rule():
    """Valid zero income (0.0) is preserved as non-missing and satisfies <= ceiling rule."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2002, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(annual_income=0.0)

    scheme = SchemeMaster(
        scheme_name="Scholarship With Income Cap",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Income Criteria", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="annual_income", operator="<=", required_value="250000"),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert result is True
    assert details["overall_result"] is True
    assert details["passed_rules_count"] == 1
    assert details["missing_rules_count"] == 0
    assert details["rule_match_score"] == 100.0
    rule_evidence = details["groups"][0]["rules"][0]
    assert rule_evidence["actual"] == 0.0
    assert rule_evidence["is_missing"] is False
    assert rule_evidence["passed"] is True


def test_missing_land_holding_fails_ceiling_rule():
    """Missing land holding size resolves to None, fails <= rule, and is marked missing."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1980, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(land_holding_size=None)

    scheme = SchemeMaster(
        scheme_name="Farmer Land Scheme",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Land", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="land_holding_size", operator="<=", required_value="2.0"),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert result is False
    assert details["overall_result"] is False
    assert details["missing_rules_count"] == 1
    rule_evidence = details["groups"][0]["rules"][0]
    assert rule_evidence["actual"] is None
    assert rule_evidence["is_missing"] is True
    assert rule_evidence["passed"] is False


def test_valid_zero_land_holding_passes_ceiling_rule():
    """Valid zero land holding (0.0) is preserved as non-missing and passes <= ceiling."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1980, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(land_holding_size=0.0)

    scheme = SchemeMaster(
        scheme_name="Farmer Land Scheme",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Land", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="land_holding_size", operator="<=", required_value="2.0"),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert result is True
    assert details["overall_result"] is True
    rule_evidence = details["groups"][0]["rules"][0]
    assert rule_evidence["actual"] == 0.0
    assert rule_evidence["is_missing"] is False
    assert rule_evidence["passed"] is True


def test_unknown_tax_payer_status_fails_exclusion_check():
    """Unknown tax-payer status (financial_profile None or is_income_tax_payer None) fails rule."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1980, 1, 1),
    )
    citizen.financial_profile = None

    scheme = SchemeMaster(
        scheme_name="PM-KISAN Exclusion",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Tax Exclusion", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="is_income_tax_payer", operator="==", required_value="false"),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert result is False
    assert details["overall_result"] is False
    assert details["missing_rules_count"] == 1
    rule_evidence = details["groups"][0]["rules"][0]
    assert rule_evidence["actual"] is None
    assert rule_evidence["is_missing"] is True
    assert rule_evidence["passed"] is False


def test_explicit_false_tax_payer_status_passes_exclusion_check():
    """Explicitly recorded False is_income_tax_payer passes the '== false' exclusion check."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1980, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(is_income_tax_payer=False)

    scheme = SchemeMaster(
        scheme_name="PM-KISAN Exclusion",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Tax Exclusion", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="is_income_tax_payer", operator="==", required_value="false"),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert result is True
    assert details["overall_result"] is True
    rule_evidence = details["groups"][0]["rules"][0]
    assert rule_evidence["actual"] is False
    assert rule_evidence["is_missing"] is False
    assert rule_evidence["passed"] is True


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


def test_employed_adult_cannot_qualify_for_scholarship_requiring_student_status():
    """An employed adult with completed education fails a scholarship requiring current student status."""
    engine = EligibilityEngine()

    adult = CitizenMaster(
        citizen_type="GENERAL",
        date_of_birth=date(1985, 5, 10),
    )
    adult.demographic_profile = DemographicProfile(
        education_level="GRADUATE",
        social_category="SC",
    )
    adult.financial_profile = FinancialProfile(
        annual_income=180000.0,
        employment_status="EMPLOYED",
    )

    scheme = SchemeMaster(
        scheme_name="NSP Post-Matric Scholarship for SC Students",
        target_persona="STUDENT",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Academic & Category Criteria", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(
            parameter_name="currently_studying",
            operator="==",
            required_value="true",
            rule_description="Must be currently enrolled and studying in a recognized course",
        ),
        SchemeEligibilityRule(
            parameter_name="social_category",
            operator="==",
            required_value="SC",
            rule_description="Must belong to Scheduled Caste category",
        ),
        SchemeEligibilityRule(
            parameter_name="education_level",
            operator="IN",
            required_value="SECONDARY,HIGHER_SECONDARY,GRADUATE,POST_GRADUATE",
            rule_description="Must be enrolled in post-matriculation courses",
        ),
        SchemeEligibilityRule(
            parameter_name="annual_income",
            operator="<=",
            required_value="250000",
            rule_description="Family annual income must not exceed Rs.2,50,000",
        ),
    ]
    scheme.rule_groups = [group]

    # Evaluate with fact layer indicating adult is NOT currently studying
    facts_dict = {"CURRENTLY_STUDYING": "FALSE", "EDUCATION_LEVEL": "GRADUATE", "SOCIAL_CATEGORY": "SC", "ANNUAL_INCOME": "180000"}
    result, details, reason = engine.evaluate_scheme(adult, scheme, facts_dict=facts_dict)

    assert result is False
    assert details["overall_result"] is False
    assert details["passed_rules_count"] == 3
    assert details["failed_rules_count"] == 1
    assert details["rule_match_score"] == 75.0
    failed_rule = next(r for r in details["groups"][0]["rules"] if not r["passed"])
    assert failed_rule["parameter"] == "currently_studying"
    assert failed_rule["actual"] is False
    assert failed_rule["passed"] is False


def test_valid_current_student_qualifies_for_scholarship():
    """A valid current student with matching criteria qualifies for the scholarship."""
    engine = EligibilityEngine()

    student = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2004, 3, 15),
    )
    student.demographic_profile = DemographicProfile(
        education_level="HIGHER_SECONDARY",
        social_category="SC",
    )
    student.financial_profile = FinancialProfile(
        annual_income=120000.0,
        employment_status="STUDENT",
    )

    scheme = SchemeMaster(
        scheme_name="NSP Post-Matric Scholarship for SC Students",
        target_persona="STUDENT",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Academic & Category Criteria", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(
            parameter_name="currently_studying",
            operator="==",
            required_value="true",
            rule_description="Must be currently enrolled and studying in a recognized course",
        ),
        SchemeEligibilityRule(
            parameter_name="social_category",
            operator="==",
            required_value="SC",
            rule_description="Must belong to Scheduled Caste category",
        ),
        SchemeEligibilityRule(
            parameter_name="education_level",
            operator="IN",
            required_value="SECONDARY,HIGHER_SECONDARY,GRADUATE,POST_GRADUATE",
            rule_description="Must be enrolled in post-matriculation courses",
        ),
        SchemeEligibilityRule(
            parameter_name="annual_income",
            operator="<=",
            required_value="250000",
            rule_description="Family annual income must not exceed Rs.2,50,000",
        ),
    ]
    scheme.rule_groups = [group]

    facts_dict = {"CURRENTLY_STUDYING": "TRUE", "EDUCATION_LEVEL": "HIGHER_SECONDARY", "SOCIAL_CATEGORY": "SC", "ANNUAL_INCOME": "120000"}
    result, details, reason = engine.evaluate_scheme(student, scheme, facts_dict=facts_dict)

    assert result is True
    assert details["overall_result"] is True
    assert details["passed_rules_count"] == 4
    assert details["failed_rules_count"] == 0
    assert details["rule_match_score"] == 100.0
    assert "meets all criteria" in reason


def test_missing_current_enrollment_fails_and_is_not_confirmed_eligible():
    """Missing current enrollment information is not treated as confirmed eligibility."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_type="GENERAL",
        date_of_birth=date(2003, 7, 20),
    )
    citizen.demographic_profile = DemographicProfile(
        education_level="HIGHER_SECONDARY",
        social_category="SC",
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=120000.0,
        employment_status=None,
    )

    scheme = SchemeMaster(
        scheme_name="NSP Post-Matric Scholarship for SC Students",
        target_persona="STUDENT",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Academic & Category Criteria", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(
            parameter_name="currently_studying",
            operator="==",
            required_value="true",
            rule_description="Must be currently enrolled and studying in a recognized course",
        ),
    ]
    scheme.rule_groups = [group]

    # No CURRENTLY_STUDYING fact, no student profile
    facts_dict = {}
    result, details, reason = engine.evaluate_scheme(citizen, scheme, facts_dict=facts_dict)

    assert result is False
    assert details["overall_result"] is False
    assert details["missing_rules_count"] == 1
    assert details["passed_rules_count"] == 0
    assert details["rule_match_score"] == 0.0
    rule_evidence = details["groups"][0]["rules"][0]
    assert rule_evidence["actual"] is None
    assert rule_evidence["is_missing"] is True
    assert rule_evidence["status"] == "UNKNOWN"
    assert rule_evidence["passed"] is False
    assert any("(Not provided)" in r for r in details["unknown_rules"])


def test_seeding_persists_target_persona():
    """Verify that scheme seeding logic creates SchemeMaster instances with target_persona preserved."""
    import json
    from pathlib import Path

    seed_path = Path("seed_data/schemes.json")
    with open(seed_path, encoding="utf-8") as f:
        data = json.load(f)

    schemes_data = data.get("schemes", [])
    student_scheme = next((s for s in schemes_data if s.get("target_persona") == "STUDENT"), None)
    assert student_scheme is not None
    assert student_scheme["target_persona"] == "STUDENT"

    scheme = SchemeMaster(
        scheme_name=student_scheme["scheme_name"],
        department_name=student_scheme.get("department_name"),
        scheme_category=student_scheme.get("scheme_category"),
        description=student_scheme.get("description"),
        benefit_description=student_scheme.get("benefit_description"),
        status=student_scheme.get("status", "ACTIVE"),
        official_source_url=student_scheme.get("official_source_url"),
        application_url=student_scheme.get("application_url"),
        group_combining_operator=student_scheme.get("group_combining_operator", "AND"),
        target_persona=student_scheme.get("target_persona"),
    )

    assert scheme.target_persona == "STUDENT"
    assert scheme.scheme_name == student_scheme["scheme_name"]

    extended_path = Path("seed_data/schemes_extended.json")
    with open(extended_path, encoding="utf-8") as f:
        ext_data = json.load(f)

    all_student_schemes = [
        s for s in (schemes_data + ext_data.get("schemes", []))
        if s.get("target_persona") == "STUDENT"
    ]
    assert len(all_student_schemes) == 14
    for s in all_student_schemes:
        first_group_rules = [r["parameter_name"] for r in s["rule_groups"][0]["rules"]]
        assert "currently_studying" in first_group_rules


def test_enrollment_not_inferred_from_citizen_type_or_employment_when_fact_missing():
    """Missing CURRENTLY_STUDYING fact must return None, never inferring from citizen_type or employment_status."""
    engine = EligibilityEngine()

    student_citizen = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2003, 5, 20),
    )
    student_citizen.demographic_profile = DemographicProfile(
        education_level="HIGHER_SECONDARY",
        social_category="SC",
    )
    student_citizen.financial_profile = FinancialProfile(
        annual_income=100000.0,
        employment_status="STUDENT",
    )

    # Empty facts dictionary (fact is missing)
    facts_dict = {}
    for param in ("currently_studying", "is_studying", "is_enrolled", "is_currently_enrolled"):
        assert engine._resolve_parameter(student_citizen, param, facts_dict=facts_dict) is None

    scheme = SchemeMaster(
        scheme_name="Test Scholarship",
        target_persona="STUDENT",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Enrollment Check", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(
            parameter_name="currently_studying",
            operator="==",
            required_value="true",
            rule_description="Must be currently enrolled and studying in a recognized course",
        ),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(student_citizen, scheme, facts_dict=facts_dict)
    assert result is False
    assert details["overall_result"] is False
    rule_ev = details["groups"][0]["rules"][0]
    assert rule_ev["actual"] is None
    assert rule_ev["is_missing"] is True
    assert rule_ev["status"] == "UNKNOWN"
    assert rule_ev["passed"] is False


def test_invalid_enrollment_fact_returns_none():
    """An invalid CURRENTLY_STUDYING fact value returns None and is treated as missing."""
    engine = EligibilityEngine()
    citizen = CitizenMaster(citizen_type="STUDENT")

    facts_dict = {"CURRENTLY_STUDYING": "MAYBE"}
    assert engine._resolve_parameter(citizen, "currently_studying", facts_dict=facts_dict) is None


def test_string_true_in_scheme_json_matches_boolean_true_and_fails_explicit_false():
    """String 'true' in scheme rule matches Boolean True and explicit False fails."""
    engine = EligibilityEngine()
    citizen = CitizenMaster(citizen_type="GENERAL")

    scheme = SchemeMaster(
        scheme_name="Test Scholarship",
        target_persona="STUDENT",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Enrollment", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(
            parameter_name="currently_studying",
            operator="==",
            required_value="true",
        ),
    ]
    scheme.rule_groups = [group]

    # Explicit True matches "true"
    result_true, details_true, _ = engine.evaluate_scheme(citizen, scheme, facts_dict={"CURRENTLY_STUDYING": "TRUE"})
    assert result_true is True
    assert details_true["groups"][0]["rules"][0]["actual"] is True
    assert details_true["groups"][0]["rules"][0]["passed"] is True

    # Explicit False fails "true"
    result_false, details_false, _ = engine.evaluate_scheme(citizen, scheme, facts_dict={"CURRENTLY_STUDYING": "FALSE"})
    assert result_false is False
    assert details_false["groups"][0]["rules"][0]["actual"] is False
    assert details_false["groups"][0]["rules"][0]["passed"] is False
    assert details_false["groups"][0]["rules"][0]["is_missing"] is False
    assert details_false["groups"][0]["rules"][0]["status"] == "FAIL"


def test_employed_adult_with_missing_enrollment_fails_scholarship():
    """An employed adult with missing CURRENTLY_STUDYING fact fails the scholarship with UNKNOWN status."""
    engine = EligibilityEngine()
    adult = CitizenMaster(
        citizen_type="GENERAL",
        date_of_birth=date(1990, 1, 1),
    )
    adult.financial_profile = FinancialProfile(
        annual_income=200000.0,
        employment_status="EMPLOYED",
    )

    scheme = SchemeMaster(
        scheme_name="Test Scholarship",
        target_persona="STUDENT",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Enrollment", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(
            parameter_name="currently_studying",
            operator="==",
            required_value="true",
        ),
    ]
    scheme.rule_groups = [group]

    result, details, _ = engine.evaluate_scheme(adult, scheme, facts_dict={})
    assert result is False
    assert details["groups"][0]["rules"][0]["actual"] is None
    assert details["groups"][0]["rules"][0]["is_missing"] is True
    assert details["groups"][0]["rules"][0]["status"] == "UNKNOWN"
