import uuid
from datetime import date, datetime, timedelta, timezone
import pytest

from app.models.citizen import CitizenMaster, FinancialProfile, DemographicProfile, LocationProfile
from app.models.document import CitizenDocument
from app.models.profile_fact import ProfileFact
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from app.services.profile_audit_service import ProfileAuditService
from app.services.eligibility_engine import EligibilityEngine


def _create_mock_scheme(name: str, param: str, req_val: str, op: str = "<=") -> SchemeMaster:
    scheme = SchemeMaster(
        scheme_id=uuid.uuid4(),
        scheme_name=name,
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="Group 1", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name=param, operator=op, required_value=req_val, rule_description=f"{param} check")
    ]
    scheme.rule_groups = [group]
    return scheme


def test_audit_empty_profile_handled_safely():
    """Empty citizen profile without sub-profiles or facts executes safely."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Blank Citizen",
        date_of_birth=date(1995, 1, 1),
        citizen_type="GENERAL",
    )

    resp = ProfileAuditService.audit_citizen_profile(citizen)
    assert resp.citizen_id == citizen.citizen_id
    assert resp.summary.total_issues >= 1
    # Detects missing annual income as missing information
    missing_attrs = [i.attribute_name for i in resp.issues if i.issue_type == "MISSING_INFORMATION"]
    assert "annual_income" in missing_attrs


def test_audit_confirmed_conflict_income_profile_vs_verified_fact():
    """Conflict between profile annual_income (self-reported) and verified profile_fact is flagged as CONFIRMED_CONFLICT."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Income Conflict Citizen",
        date_of_birth=date(1990, 1, 1),
        citizen_type="GENERAL",
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=120000.0,
    )
    # Verified fact from document/government api reporting 450000.0
    fact = ProfileFact(
        fact_id=uuid.uuid4(),
        citizen_id=citizen.citizen_id,
        fact_code="ANNUAL_INCOME",
        fact_value="450000.0",
        data_type="DECIMAL",
        source="GOVERNMENT_API",
        verified=True,
    )
    citizen.profile_facts = [fact]

    scheme = _create_mock_scheme("Low Income Scheme", "annual_income", "200000.0")

    resp = ProfileAuditService.audit_citizen_profile(citizen, schemes=[scheme])
    assert resp.summary.confirmed_conflicts_count == 1
    issue = next(i for i in resp.issues if i.attribute_name == "annual_income")
    assert issue.issue_type == "CONFIRMED_CONFLICT"
    assert issue.severity == "HIGH"
    assert issue.current_value == "₹120000"
    assert issue.conflicting_value == "₹450000"
    assert len(issue.sources) == 2
    assert "Low Income Scheme" in issue.affected_schemes


def test_audit_possible_conflict_income_profile_vs_unverified_fact():
    """Unverified fact differing from profile is flagged as POSSIBLE_CONFLICT."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Unverified Citizen",
        date_of_birth=date(1990, 1, 1),
        citizen_type="GENERAL",
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=250000.0,
    )
    fact = ProfileFact(
        fact_id=uuid.uuid4(),
        citizen_id=citizen.citizen_id,
        fact_code="ANNUAL_INCOME",
        fact_value="350000.0",
        data_type="DECIMAL",
        source="USER_INPUT",
        verified=False,
    )
    citizen.profile_facts = [fact]

    resp = ProfileAuditService.audit_citizen_profile(citizen)
    assert resp.summary.possible_conflicts_count == 1
    issue = next(i for i in resp.issues if i.attribute_name == "annual_income")
    assert issue.issue_type == "POSSIBLE_CONFLICT"
    assert issue.severity == "MEDIUM"


def test_audit_age_vs_dob_conflict():
    """Discrepancy between calculated DOB age and stored AGE fact is detected."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="DOB Citizen",
        date_of_birth=date(2000, 1, 1),  # Age ~26
        citizen_type="STUDENT",
    )
    # Stored fact says age 18
    fact = ProfileFact(
        fact_id=uuid.uuid4(),
        citizen_id=citizen.citizen_id,
        fact_code="AGE",
        fact_value="18",
        data_type="INTEGER",
        source="USER_INPUT",
        verified=False,
    )
    citizen.profile_facts = [fact]

    resp = ProfileAuditService.audit_citizen_profile(citizen)
    issue = next(i for i in resp.issues if i.attribute_name == "age")
    assert issue.issue_type == "CONFIRMED_CONFLICT"
    assert issue.conflicting_value == 18


def test_audit_stale_profile_facts():
    """Income fact older than 365 days is flagged as STALE_FACT."""
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    old_date = now - timedelta(days=400)

    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Stale Fact Citizen",
        date_of_birth=date(1990, 1, 1),
        citizen_type="GENERAL",
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=150000.0,
    )
    fact = ProfileFact(
        fact_id=uuid.uuid4(),
        citizen_id=citizen.citizen_id,
        fact_code="ANNUAL_INCOME",
        fact_value="150000.0",
        data_type="DECIMAL",
        source="DOCUMENT",
        verified=True,
        created_at=old_date,
        updated_at=old_date,
    )
    citizen.profile_facts = [fact]

    resp = ProfileAuditService.audit_citizen_profile(citizen, as_of=now)
    assert resp.summary.stale_facts_count == 1
    issue = next(i for i in resp.issues if i.issue_type == "STALE_FACT")
    assert issue.attribute_name == "annual_income"
    assert "400 days ago" in issue.description
    assert "exceeds recommended validity period" in issue.description


def test_audit_invalid_document_conflict():
    """Document detected as conflicting type (e.g. Identity Proof uploaded for 12th Marksheet) is flagged."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Doc Mismatch Citizen",
        date_of_birth=date(2005, 1, 1),
        citizen_type="STUDENT",
    )
    doc = CitizenDocument(
        document_id=uuid.uuid4(),
        citizen_id=citizen.citizen_id,
        requirement_type="12TH_MARKSHEET",
        original_filename="passport_photo.png",
        content_type="image/png",
        file_size=1024,
        detected_type="IDENTITY_PROOF",
        validation_status="INVALID",
        validation_message="Incorrect document type.",
        uploaded_at=datetime.now(timezone.utc),
    )

    resp = ProfileAuditService.audit_citizen_profile(citizen, documents=[doc])
    issue = next(i for i in resp.issues if i.attribute_name == "document_12th_marksheet")
    assert issue.issue_type == "CONFIRMED_CONFLICT"
    assert "passport_photo.png" in issue.description
    assert issue.conflicting_value == "Identity Proof"


def test_audit_no_persistence_or_side_effects():
    """Profile audit is strictly read-only and does not mutate any attributes or records."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Immutable Citizen",
        date_of_birth=date(1990, 5, 20),
        citizen_type="FARMER",
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=100000.0,
        land_holding_size=2.5,
    )
    fact = ProfileFact(
        fact_id=uuid.uuid4(),
        citizen_id=citizen.citizen_id,
        fact_code="ANNUAL_INCOME",
        fact_value="500000.0",
        data_type="DECIMAL",
        source="GOVERNMENT_API",
        verified=True,
    )
    citizen.profile_facts = [fact]

    # Run audit
    ProfileAuditService.audit_citizen_profile(citizen)

    # Verify zero mutations
    assert citizen.financial_profile.annual_income == 100000.0
    assert fact.fact_value == "500000.0"
    assert citizen.citizen_type == "FARMER"


def test_baseline_deterministic_eligibility_engine_untouched():
    """Baseline deterministic engine continues to evaluate accurately and untouched."""
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        citizen_type="FARMER",
        date_of_birth=date(1980, 1, 1),
    )
    citizen.financial_profile = FinancialProfile(
        land_holding_size=1.5,
        is_income_tax_payer=False,
    )
    scheme = SchemeMaster(
        scheme_id=uuid.uuid4(),
        scheme_name="PM-KISAN",
        group_combining_operator="AND",
        target_persona="FARMER",
    )
    group = SchemeRuleGroup(group_name="Farmer", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="FARMER"),
        SchemeEligibilityRule(parameter_name="land_holding_size", operator="<=", required_value="2.0"),
    ]
    scheme.rule_groups = [group]

    result, details, reason = engine.evaluate_scheme(citizen, scheme)
    assert result is True
    assert details["overall_result"] is True
    assert details["rule_match_score"] == 100.0


def test_audit_zero_income_not_flagged_as_missing():
    """Valid annual_income = 0.0 is a legitimate zero value and is NOT flagged as missing information."""
    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Zero Income Citizen",
        date_of_birth=date(1995, 1, 1),
        citizen_type="GENERAL",
    )
    citizen.financial_profile = FinancialProfile(
        annual_income=0.0,
    )
    # Demographic profile with social_category provided
    citizen.demographic_profile = DemographicProfile(
        social_category="GEN",
    )

    resp = ProfileAuditService.audit_citizen_profile(citizen)
    missing_attrs = [i.attribute_name for i in resp.issues if i.issue_type == "MISSING_INFORMATION"]
    assert "annual_income" not in missing_attrs
    assert "social_category" not in missing_attrs

