import pytest
from datetime import date
import uuid
from app.services.citizen_service import compute_profile_completeness
from app.services.eligibility_engine import EligibilityEngine
from app.models.citizen import CitizenMaster, DemographicProfile, FinancialProfile, LocationProfile
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from app.models.education_record import EducationRecord


def test_profile_completeness_identity_only_is_incomplete():
    """Verify that a citizen with only Name + DOB is marked INCOMPLETE."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Hemantkumar Lakhane",
        date_of_birth=date(2000, 1, 1),
        citizen_type="GENERAL",
    )
    status, completion, missing = compute_profile_completeness(citizen)
    assert status == "INCOMPLETE"
    assert completion < 50
    assert "Annual Income" in missing
    assert "Social Category" in missing
    assert "State / Location" in missing
    assert "Education Details" in missing


def test_profile_completeness_fully_filled():
    """Verify that a citizen with all core dimensions is marked COMPLETE."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Hemantkumar Lakhane",
        date_of_birth=date(2000, 1, 1),
        gender="MALE",
        citizen_type="STUDENT",
        profile_types=["STUDENT"],
    )
    citizen.demographic_profile = DemographicProfile(
        social_category="OBC",
        education_level="GRADUATE",
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=150000.0,
    )
    citizen.location_profile = LocationProfile(
        state="Maharashtra",
    )
    citizen.education_records = [
        EducationRecord(
            level="UNDERGRADUATE",
            details={"degree": "B.E. Computer Engineering"},
            percentage=85.0,
        )
    ]

    status, completion, missing = compute_profile_completeness(citizen)
    assert status == "COMPLETE"
    assert completion == 100
    assert len(missing) == 0


def test_missing_facts_do_not_silently_pass_rules():
    """Verify that missing income/category does NOT default to 0 or pass <= checks."""
    engine = EligibilityEngine()

    # Citizen with ONLY DOB, missing financial/demographic/location profiles
    citizen = CitizenMaster(
        citizen_type="GENERAL",
        date_of_birth=date(2000, 1, 1),
    )

    scheme = SchemeMaster(
        scheme_name="Scholarship Scheme",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="IncomeCriteria", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(
            parameter_name="annual_income",
            operator="<=",
            required_value="250000",
            rule_description="Annual income <= 2.5L",
        ),
        SchemeEligibilityRule(
            parameter_name="social_category",
            operator="==",
            required_value="OBC",
            rule_description="OBC Category",
        ),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)

    # Missing income must NOT default to 0.0 and pass!
    assert result is False
    assert details["passed_rules"] == 0
    assert details["match_score"] == 0
    assert details["eligibility_status"] == "INSUFFICIENT_INFORMATION"
    assert len(details["unknown_rules"]) == 2
    assert len(details["failed_rules"]) == 0
    assert details["missing_critical_facts"] == ["annual_income", "social_category"]
