"""
Tests for Phase 5 Task 1: Tri-State Eligibility Evaluation.
Verifies Kleene tri-state logic across PASS, FAIL, UNKNOWN,
decisive short-circuits, deterministic missing_critical_facts,
and recommendation partitioning.
"""

import uuid
from datetime import date
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.citizen import CitizenMaster, DemographicProfile, FinancialProfile, LocationProfile
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from app.models.auth import UserAccount, UserRole
from app.services.eligibility_engine import EligibilityEngine
from app.repositories.assessment_repository import AssessmentRepository
from app.api.v1.recommendations import get_citizen_recommendations


def _make_rule(param: str, op: str, req: str, desc: str | None = None) -> SchemeEligibilityRule:
    return SchemeEligibilityRule(
        parameter_name=param,
        operator=op,
        required_value=req,
        rule_description=desc or f"{param} {op} {req}",
    )


def test_all_pass_and_group():
    """When all required rules pass, scheme is ELIGIBLE and overall_result is True."""
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1985, 6, 15),
    )
    citizen.financial_profile = FinancialProfile(land_holding_size=1.5, annual_income=120000.0)

    scheme = SchemeMaster(scheme_name="Farmer Support Scheme", group_combining_operator="AND")
    group = SchemeRuleGroup(group_name="Main", intra_group_operator="AND")
    group.rules = [
        _make_rule("citizen_type", "==", "FARMER", "Must be farmer"),
        _make_rule("land_holding_size", "<=", "2.0", "Land holding <= 2 ha"),
        _make_rule("annual_income", "<=", "200000", "Annual income <= 2 Lakh"),
    ]
    scheme.rule_groups = [group]

    overall, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert overall is True
    assert details["eligibility_status"] == "ELIGIBLE"
    assert details["overall_result"] is True
    assert details["missing_critical_facts"] == []
    assert details["failed_rules"] == []
    assert len(details["matched_rules"]) == 3
    assert "meets all criteria" in reason


def test_decisive_failure_in_and_group_with_missing_fact():
    """
    Decisive disqualification: If a decisive rule fails in an AND group,
    the result is NOT_ELIGIBLE even if another rule evaluates a missing fact (UNKNOWN).
    """
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="STUDENT",  # Fails FARMER
        date_of_birth=date(2000, 1, 1),
    )
    # Financial profile is None, so annual_income is missing (None)
    citizen.financial_profile = None

    scheme = SchemeMaster(scheme_name="Farmer Grant", group_combining_operator="AND")
    group = SchemeRuleGroup(group_name="Criteria", intra_group_operator="AND")
    group.rules = [
        _make_rule("citizen_type", "==", "FARMER", "Must be farmer"),  # FAIL
        _make_rule("annual_income", "<=", "150000", "Income <= 1.5 Lakh"),  # UNKNOWN
    ]
    scheme.rule_groups = [group]

    overall, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert overall is False
    assert details["eligibility_status"] == "NOT_ELIGIBLE"
    assert details["overall_result"] is False
    assert details["missing_critical_facts"] == []
    assert "Must be farmer" in details["failed_rules"]
    assert "Does not meet criteria" in reason


def test_insufficient_information_in_and_group():
    """
    When no rule fails but a required fact is missing in an AND group,
    outcome is INSUFFICIENT_INFORMATION and missing_critical_facts lists the missing fact.
    """
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1985, 1, 1),
    )
    # Financial profile missing
    citizen.financial_profile = None

    scheme = SchemeMaster(scheme_name="Farmer Welfare", group_combining_operator="AND")
    group = SchemeRuleGroup(group_name="Eligibility", intra_group_operator="AND")
    group.rules = [
        _make_rule("citizen_type", "==", "FARMER", "Must be farmer"),  # PASS
        _make_rule("annual_income", "<=", "200000", "Income <= 2 Lakh"),  # UNKNOWN
    ]
    scheme.rule_groups = [group]

    overall, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert overall is False
    assert details["eligibility_status"] == "INSUFFICIENT_INFORMATION"
    assert details["overall_result"] is False
    assert details["missing_critical_facts"] == ["annual_income"]
    assert details["failed_rules"] == []
    assert "Income <= 2 Lakh" in details["unknown_rules"][0]
    assert "Eligibility cannot be determined" in reason
    assert "annual_income" in reason


def test_multiple_missing_facts_in_and_group():
    """Multiple missing facts in an AND group are all captured in missing_critical_facts deterministically."""
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="STUDENT",
        date_of_birth=date(2004, 3, 10),
    )
    citizen.financial_profile = None
    citizen.demographic_profile = None

    scheme = SchemeMaster(scheme_name="Higher Education Fellowship", group_combining_operator="AND")
    group = SchemeRuleGroup(group_name="Criteria", intra_group_operator="AND")
    group.rules = [
        _make_rule("citizen_type", "==", "STUDENT", "Must be student"),  # PASS
        _make_rule("annual_income", "<=", "250000", "Income <= 2.5 Lakh"),  # UNKNOWN
        _make_rule("social_category", "IN", "SC,ST,OBC", "Must belong to reserved category"),  # UNKNOWN
    ]
    scheme.rule_groups = [group]

    overall, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert overall is False
    assert details["eligibility_status"] == "INSUFFICIENT_INFORMATION"
    assert details["missing_critical_facts"] == ["annual_income", "social_category"]
    assert details["failed_rules"] == []


def test_decisive_pass_in_or_group_with_missing_fact():
    """
    In an OR group, if any rule PASSES, the group PASSES regardless of other UNKNOWN rules.
    Kleene OR: PASS OR UNKNOWN = PASS.
    """
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1990, 1, 1),
    )
    # Demographic profile is None, so disability_status is UNKNOWN
    citizen.demographic_profile = None

    scheme = SchemeMaster(scheme_name="Community Grant", group_combining_operator="AND")
    group = SchemeRuleGroup(group_name="Target Group", intra_group_operator="OR")
    group.rules = [
        _make_rule("citizen_type", "==", "FARMER", "Farmer category"),  # PASS
        _make_rule("disability_status", "!=", "NONE", "Person with disability"),  # UNKNOWN
    ]
    scheme.rule_groups = [group]

    overall, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert overall is True
    assert details["eligibility_status"] == "ELIGIBLE"
    assert details["overall_result"] is True
    assert details["missing_critical_facts"] == []


def test_all_fail_in_or_group():
    """In an OR group, if all rules FAIL, group is FAIL -> NOT_ELIGIBLE."""
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="BUSINESS",
        gender="MALE",
        date_of_birth=date(1980, 1, 1),
    )

    scheme = SchemeMaster(scheme_name="Vulnerable Persons Aid", group_combining_operator="AND")
    group = SchemeRuleGroup(group_name="Target Group", intra_group_operator="OR")
    group.rules = [
        _make_rule("citizen_type", "==", "FARMER", "Must be farmer"),  # FAIL
        _make_rule("gender", "==", "FEMALE", "Must be female"),  # FAIL
    ]
    scheme.rule_groups = [group]

    overall, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert overall is False
    assert details["eligibility_status"] == "NOT_ELIGIBLE"
    assert len(details["failed_rules"]) == 2


def test_insufficient_information_in_or_group():
    """
    In an OR group, if one rule FAILS and the other is UNKNOWN,
    the group outcome is UNKNOWN (Kleene OR: FAIL OR UNKNOWN = UNKNOWN).
    """
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="BUSINESS",  # Fails FARMER
        date_of_birth=date(1990, 1, 1),
    )
    citizen.financial_profile = None  # is_bpl_card_holder is UNKNOWN

    scheme = SchemeMaster(scheme_name="Livelihood Scheme", group_combining_operator="AND")
    group = SchemeRuleGroup(group_name="Target Group", intra_group_operator="OR")
    group.rules = [
        _make_rule("citizen_type", "==", "FARMER", "Must be farmer"),  # FAIL
        _make_rule("is_bpl_card_holder", "==", "true", "BPL Card holder"),  # UNKNOWN
    ]
    scheme.rule_groups = [group]

    overall, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert overall is False
    assert details["eligibility_status"] == "INSUFFICIENT_INFORMATION"
    assert details["missing_critical_facts"] == ["is_bpl_card_holder"]


def test_multi_group_and_of_ors():
    """
    Multi-group combination:
    Group 1 (OR): PASS or FAIL -> Group 1 is PASS.
    Group 2 (AND): PASS and UNKNOWN -> Group 2 is UNKNOWN.
    Scheme Combining (AND): PASS AND UNKNOWN = INSUFFICIENT_INFORMATION.
    """
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="STUDENT",
        gender="MALE",
        date_of_birth=date(2003, 5, 20),
    )
    citizen.financial_profile = None
    citizen.location_profile = LocationProfile(state="Maharashtra")

    scheme = SchemeMaster(scheme_name="Maharashtra Student Aid", group_combining_operator="AND")

    g1 = SchemeRuleGroup(group_name="Category", intra_group_operator="OR")
    g1.rules = [
        _make_rule("citizen_type", "==", "STUDENT", "Student"),  # PASS
        _make_rule("gender", "==", "FEMALE", "Female"),  # FAIL
    ]

    g2 = SchemeRuleGroup(group_name="Location and Income", intra_group_operator="AND")
    g2.rules = [
        _make_rule("state", "==", "Maharashtra", "Resident of Maharashtra"),  # PASS
        _make_rule("annual_income", "<=", "300000", "Income <= 3 Lakh"),  # UNKNOWN
    ]

    scheme.rule_groups = [g1, g2]

    overall, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert overall is False
    assert details["eligibility_status"] == "INSUFFICIENT_INFORMATION"
    assert details["missing_critical_facts"] == ["annual_income"]


def test_multi_group_decisive_failure_dominates():
    """
    Multi-group combination with AND combining operator:
    Group 1 fails decisively.
    Group 2 has unknown facts.
    Overall outcome MUST be NOT_ELIGIBLE (decisive failure dominates).
    """
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="BUSINESS",  # Fails STUDENT
        date_of_birth=date(1975, 1, 1),
    )
    citizen.financial_profile = None

    scheme = SchemeMaster(scheme_name="National Scholarship", group_combining_operator="AND")

    g1 = SchemeRuleGroup(group_name="Enrollment", intra_group_operator="AND")
    g1.rules = [
        _make_rule("citizen_type", "==", "STUDENT", "Must be student"),  # FAIL
    ]

    g2 = SchemeRuleGroup(group_name="Income", intra_group_operator="AND")
    g2.rules = [
        _make_rule("annual_income", "<=", "200000", "Income <= 2 Lakh"),  # UNKNOWN
    ]

    scheme.rule_groups = [g1, g2]

    overall, details, reason = engine.evaluate_scheme(citizen, scheme)

    assert overall is False
    assert details["eligibility_status"] == "NOT_ELIGIBLE"
    assert details["missing_critical_facts"] == []


@pytest.mark.asyncio
async def test_tri_state_database_persistence_and_recommendations_split(db: AsyncSession):
    """
    Verify end-to-end database persistence and recommendations API separation:
    1. INSUFFICIENT_INFORMATION assessment stores eligibility_status and missing_facts in DB.
    2. Recommendations API returns it in information_needed_schemes, NOT eligible or ineligible.
    """
    repo = AssessmentRepository(db)

    citizen_id = uuid.uuid4()
    admin_user = UserAccount(user_id=uuid.uuid4(), email="admin@test.gov.in")
    admin_user.roles = [UserRole(role="ADMIN")]

    # Create citizen
    citizen = CitizenMaster(
        citizen_id=citizen_id,
        full_name="Tri-State Test Citizen",
        gender="MALE",
        date_of_birth=date(1995, 1, 1),
        citizen_type="STUDENT",
    )
    db.add(citizen)

    # Create 3 schemes:
    # 1. Eligible scheme
    # 2. Ineligible scheme
    # 3. Information Needed scheme
    sch_eligible = SchemeMaster(
        scheme_id=uuid.uuid4(),
        scheme_name="Confirmed Eligible Scheme",
        status="ACTIVE",
    )
    sch_ineligible = SchemeMaster(
        scheme_id=uuid.uuid4(),
        scheme_name="Confirmed Ineligible Scheme",
        status="ACTIVE",
    )
    sch_info_needed = SchemeMaster(
        scheme_id=uuid.uuid4(),
        scheme_name="Information Needed Scheme",
        status="ACTIVE",
    )
    db.add_all([sch_eligible, sch_ineligible, sch_info_needed])
    await db.flush()

    # Persist assessments
    await repo.upsert_assessment(
        citizen_id=citizen_id,
        scheme_id=sch_eligible.scheme_id,
        eligibility_result=True,
        eligibility_status="ELIGIBLE",
        reason="Meets criteria",
        evaluation_details={"overall_result": True, "eligibility_status": "ELIGIBLE", "rule_match_score": 100.0},
    )
    await repo.upsert_assessment(
        citizen_id=citizen_id,
        scheme_id=sch_ineligible.scheme_id,
        eligibility_result=False,
        eligibility_status="NOT_ELIGIBLE",
        reason="Fails criteria",
        evaluation_details={"overall_result": False, "eligibility_status": "NOT_ELIGIBLE", "rule_match_score": 0.0},
    )
    await repo.upsert_assessment(
        citizen_id=citizen_id,
        scheme_id=sch_info_needed.scheme_id,
        eligibility_result=False,
        eligibility_status="INSUFFICIENT_INFORMATION",
        missing_facts=["annual_income"],
        reason="Eligibility cannot be determined: missing annual_income",
        evaluation_details={
            "overall_result": False,
            "eligibility_status": "INSUFFICIENT_INFORMATION",
            "missing_critical_facts": ["annual_income"],
            "rule_match_score": 50.0,
        },
    )
    await db.flush()

    # Call recommendations API
    resp = await get_citizen_recommendations(
        citizen_id=citizen_id,
        db=db,
        user=admin_user,
    )

    assert resp.total_schemes_evaluated == 3
    assert resp.eligible_count == 1
    assert resp.ineligible_count == 1
    assert resp.information_needed_count == 1

    assert len(resp.eligible_schemes) == 1
    assert resp.eligible_schemes[0].scheme.scheme_id == sch_eligible.scheme_id
    assert resp.eligible_schemes[0].eligibility_status == "ELIGIBLE"

    assert len(resp.ineligible_schemes) == 1
    assert resp.ineligible_schemes[0].scheme.scheme_id == sch_ineligible.scheme_id
    assert resp.ineligible_schemes[0].eligibility_status == "NOT_ELIGIBLE"

    assert len(resp.information_needed_schemes) == 1
    info_item = resp.information_needed_schemes[0]
    assert info_item.scheme.scheme_id == sch_info_needed.scheme_id
    assert info_item.eligibility_status == "INSUFFICIENT_INFORMATION"
    assert info_item.missing_critical_facts == ["annual_income"]
    assert info_item.eligibility_result is False
