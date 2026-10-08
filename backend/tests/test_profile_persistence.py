"""
Tests for citizen profile canonical data persistence, atomic fact sync, and completeness logic.
"""

import uuid
from datetime import date
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.citizen import CitizenMaster, DemographicProfile, FinancialProfile, LocationProfile
from app.models.education_record import EducationRecord
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from app.repositories.citizen_repository import CitizenRepository
from app.schemas.citizen import (
    CitizenCreate,
    CitizenUpdate,
    DemographicProfileCreate,
    FinancialProfileCreate,
    LocationProfileCreate,
)
from app.services.citizen_service import CitizenService, compute_profile_completeness
from app.services.eligibility_engine import EligibilityEngine
from app.services.profile_sync_service import ProfileSyncService


@pytest.mark.asyncio
async def test_full_profile_crud_persists_canonical_tables_and_facts(db: AsyncSession):
    """Verify PUT /citizens/{id} atomically updates all canonical profile tables and synchronizes facts."""
    citizen_repo = CitizenRepository(db)
    service = CitizenService(db)

    # 1. Register a new citizen
    initial_data = CitizenCreate(
        full_name="Hemant Kumar",
        date_of_birth=date(1998, 5, 20),
        gender="MALE",
        mobile_number="9876543210",
        email_id="hemant@example.com",
        citizen_type="STUDENT",
        profile_types=["STUDENT"],
        demographic=DemographicProfileCreate(
            education_level="UNDERGRADUATE",
            occupation="Student",
            family_size=4,
            marital_status="SINGLE",
            social_category="OBC",
            disability_status="NONE",
            type_specific_metadata={"student_hostel_status": "HOSTELLER"},
        ),
        financial=FinancialProfileCreate(
            annual_income=180000.0,
            employment_status="STUDENT",
            income_source="Family",
            poverty_category="APL",
            land_holding_size=1.5,
            is_bpl_card_holder=False,
            is_income_tax_payer=False,
        ),
        location=LocationProfileCreate(
            address_line_1="Flat 101, Green View",
            address_line_2="MG Road",
            state="Maharashtra",
            district="Pune",
            village_city="Pune",
            pincode="411001",
            area_type="URBAN",
            same_as_permanent=True,
        ),
    )

    registered = await service.register_citizen(initial_data)
    cid = registered.citizen_id
    assert registered.full_name == "Hemant Kumar"
    assert registered.demographic.social_category == "OBC"
    assert registered.financial.annual_income == 180000.0
    assert registered.location.pincode == "411001"

    # 2. Update multiple fields from different sections
    update_data = CitizenUpdate(
        full_name="Hemant Kumar Lakhane",
        date_of_birth=date(1998, 5, 20),
        gender="MALE",
        mobile_number="9876543210",
        email_id="hemant@example.com",
        citizen_type="STUDENT",
        profile_types=["STUDENT", "FARMER"],
        demographic=DemographicProfileCreate(
            education_level="GRADUATE",
            occupation="Researcher",
            family_size=5,
            marital_status="MARRIED",
            social_category="OBC",
            disability_status="NONE",
            type_specific_metadata={"student_hostel_status": "DAY_SCHOLAR"},
        ),
        financial=FinancialProfileCreate(
            annual_income=220000.0,
            employment_status="SELF_EMPLOYED",
            income_source="Agriculture & Freelance",
            poverty_category="APL",
            land_holding_size=2.5,
            is_bpl_card_holder=False,
            is_income_tax_payer=False,
        ),
        location=LocationProfileCreate(
            address_line_1="Building B, Sunshine Colony",
            address_line_2="Near Shivaji Park",
            state="Maharashtra",
            district="Nagpur",
            village_city="Nagpur",
            pincode="440001",
            area_type="URBAN",
            same_as_permanent=True,
        ),
    )

    updated_response = await service.update_citizen(cid, update_data)
    assert updated_response is not None
    assert updated_response.full_name == "Hemant Kumar Lakhane"
    assert updated_response.demographic.family_size == 5
    assert updated_response.demographic.occupation == "Researcher"
    assert updated_response.financial.annual_income == 220000.0
    assert updated_response.financial.land_holding_size == 2.5
    assert updated_response.location.district == "Nagpur"
    assert updated_response.location.pincode == "440001"

    # 3. Fresh GET from repository / API service
    fresh_get = await service.get_citizen(cid)
    assert fresh_get is not None
    assert fresh_get.full_name == "Hemant Kumar Lakhane"
    assert fresh_get.demographic.family_size == 5
    assert fresh_get.financial.annual_income == 220000.0
    assert fresh_get.financial.employment_status == "SELF_EMPLOYED"
    assert fresh_get.location.pincode == "440001"
    assert fresh_get.location.state == "Maharashtra"

    # 4. Verify canonical database rows directly
    citizen_db = await citizen_repo.get_by_id(cid)
    assert citizen_db.full_name == "Hemant Kumar Lakhane"
    assert citizen_db.demographic_profile.family_size == 5
    assert citizen_db.demographic_profile.occupation == "Researcher"
    assert float(citizen_db.financial_profile.annual_income) == 220000.0
    assert float(citizen_db.financial_profile.land_holding_size) == 2.5
    assert citizen_db.location_profile.district == "Nagpur"
    assert citizen_db.location_profile.pincode == "440001"

    # 5. Verify synchronized profile facts
    sync_service = ProfileSyncService(db)
    facts = await sync_service.profiles.load_all_active_facts(cid)
    assert facts.get("FULL_NAME") == "Hemant Kumar Lakhane"
    assert facts.get("ANNUAL_INCOME") == "220000"
    assert facts.get("LAND_HOLDING") == "2.5"
    assert facts.get("FAMILY_SIZE") == "5"
    assert facts.get("SOCIAL_CATEGORY") == "OBC"
    assert facts.get("STATE") == "Maharashtra"
    assert facts.get("PINCODE") == "440001"
    assert facts.get("DISTRICT") == "Nagpur"


@pytest.mark.asyncio
async def test_profile_completeness_gate_and_eligibility_evaluation(db: AsyncSession):
    """Verify that incomplete profile fails completeness check while complete profile passes."""
    service = CitizenService(db)
    engine = EligibilityEngine()

    # Incomplete citizen: Name, DOB, Gender only
    incomplete_data = CitizenCreate(
        full_name="Tanmay Lakhane",
        date_of_birth=date(2002, 3, 15),
        gender="MALE",
        citizen_type="GENERAL",
        demographic=DemographicProfileCreate(),
        financial=FinancialProfileCreate(),
        location=LocationProfileCreate(),
    )

    created = await service.register_citizen(incomplete_data)
    cid = created.citizen_id

    # Completeness check
    status, score, missing = compute_profile_completeness(
        await CitizenRepository(db).get_by_id(cid)
    )
    assert status == "INCOMPLETE"
    assert "Annual Income" in missing
    assert "Social Category" in missing
    assert "State / Location" in missing

    # Complete the profile
    complete_update = CitizenUpdate(
        full_name="Tanmay Lakhane",
        date_of_birth=date(2002, 3, 15),
        gender="MALE",
        citizen_type="STUDENT",
        demographic=DemographicProfileCreate(
            education_level="UNDERGRADUATE",
            social_category="OBC",
        ),
        financial=FinancialProfileCreate(
            annual_income=150000.0,
        ),
        location=LocationProfileCreate(
            state="Maharashtra",
            district="Pune",
            pincode="411001",
        ),
    )

    updated = await service.update_citizen(cid, complete_update)
    fresh_citizen = await CitizenRepository(db).get_full_profile(cid)
    status_c, score_c, missing_c = compute_profile_completeness(fresh_citizen)
    assert status_c == "COMPLETE"
    assert len(missing_c) == 0

    # Evaluate against a scheme using the full profile
    scheme = SchemeMaster(
        scheme_name="Maharashtra Post-Matric OBC Scholarship",
        group_combining_operator="AND",
    )
    group = SchemeRuleGroup(group_name="MainGroup", intra_group_operator="AND")
    group.rules = [
        SchemeEligibilityRule(parameter_name="annual_income", operator="<=", required_value="250000", rule_description="Income <= 2.5L"),
        SchemeEligibilityRule(parameter_name="social_category", operator="==", required_value="OBC", rule_description="OBC Category"),
        SchemeEligibilityRule(parameter_name="state", operator="==", required_value="Maharashtra", rule_description="State Maharashtra"),
    ]
    scheme.rule_groups = [group]

    facts_dict = await ProfileSyncService(db).profiles.load_all_active_facts(cid)
    result, details, reason = engine.evaluate_scheme(fresh_citizen, scheme, facts_dict=facts_dict)
    assert result is True
    assert details["match_score"] == 100
