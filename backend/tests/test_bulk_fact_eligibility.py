"""
Comprehensive verification of the Check Eligibility flow, bulk fact loading,
and Redis cache invalidation.
"""

from __future__ import annotations

import uuid
from datetime import date
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.cache import cache, citizen_facts_key, citizen_key, eligibility_result_key, invalidate_citizen
from app.models.citizen import CitizenMaster, DemographicProfile, FinancialProfile, LocationProfile
from app.models.profile_fact import ProfileFact
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from app.repositories.profile_repository import ProfileRepository
from app.services.eligibility_engine import EligibilityEngine


@pytest.mark.asyncio
async def test_bulk_fact_loader_redis_caching():
    """Test load_all_active_facts loads from DB once and caches in Redis."""
    cid = uuid.uuid4()
    facts_key = citizen_facts_key(cid)

    # Clear any leftover cache for this test id
    await cache.delete(facts_key)

    # 1. Mock DB returning rows
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [
        ("AGE", "22"),
        ("GENDER", "MALE"),
        ("EDUCATION_LEVEL", "UNDERGRADUATE"),
        ("ANNUAL_INCOME", "150000.0"),
        ("TENTH_PERCENTAGE", "85.5"),
    ]
    db.execute.return_value = mock_result

    repo = ProfileRepository(db)

    # First call: executes DB query and populates cache
    facts1 = await repo.load_all_active_facts(cid)
    assert db.execute.call_count == 1
    assert facts1["AGE"] == "22"
    assert facts1["GENDER"] == "MALE"
    assert facts1["EDUCATION_LEVEL"] == "UNDERGRADUATE"

    # Second call: served directly from Redis cache without hitting DB
    facts2 = await repo.load_all_active_facts(cid)
    assert db.execute.call_count == 1  # Still 1, no second SQL query!
    assert facts2 == facts1

    # Invalidate citizen
    await invalidate_citizen(cid)

    # Third call after invalidation: queries DB again
    facts3 = await repo.load_all_active_facts(cid)
    assert db.execute.call_count == 2
    assert facts3 == facts1


@pytest.mark.asyncio
async def test_eligibility_engine_uses_bulk_facts_dict():
    """Verify EligibilityEngine evaluates scheme rules against the in-memory facts dict."""
    engine = EligibilityEngine()

    citizen = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Rajesh Patil",
        date_of_birth=date(2000, 1, 1),
        gender="MALE",
        citizen_type="STUDENT",
        demographic_profile=DemographicProfile(social_category="OPEN"),
        financial_profile=FinancialProfile(annual_income=200000.0, is_bpl_card_holder=False),
        location_profile=LocationProfile(state="Maharashtra", area_type="URBAN"),
    )

    scheme = SchemeMaster(
        scheme_id=uuid.uuid4(),
        scheme_name="Higher Education Merit Scholarship",
        group_combining_operator="AND",
        status="ACTIVE",
    )

    group = SchemeRuleGroup(
        group_id=uuid.uuid4(),
        group_name="Academic & Income Criteria",
        intra_group_operator="AND",
    )

    rule1 = SchemeEligibilityRule(
        rule_id=uuid.uuid4(),
        parameter_name="tenth_percentage",
        operator=">=",
        required_value="80.0",
        rule_description="10th percentage must be at least 80%",
    )

    rule2 = SchemeEligibilityRule(
        rule_id=uuid.uuid4(),
        parameter_name="annual_income",
        operator="<=",
        required_value="300000",
        rule_description="Annual income <= 3,00,000",
    )

    rule3 = SchemeEligibilityRule(
        rule_id=uuid.uuid4(),
        parameter_name="state",
        operator="==",
        required_value="Maharashtra",
        rule_description="Resident of Maharashtra",
    )

    group.rules = [rule1, rule2, rule3]
    scheme.rule_groups = [group]

    # Preloaded in-memory bulk facts dict
    facts_dict = {
        "AGE": "24",
        "GENDER": "MALE",
        "TENTH_PERCENTAGE": "88.5",
        "ANNUAL_INCOME": "200000.0",
        "STATE": "Maharashtra",
    }

    # Evaluate using bulk facts dictionary
    overall, details, reason = engine.evaluate_scheme(citizen, scheme, facts_dict=facts_dict)

    assert overall is True
    assert "meets all criteria" in reason
    assert len(details["groups"][0]["rules"]) == 3
    for r in details["groups"][0]["rules"]:
        assert r["passed"] is True


@pytest.mark.asyncio
async def test_cache_invalidation_hook():
    """Verify invalidate_citizen clears profile, facts, and eligibility entries."""
    cid = uuid.uuid4()
    p_key = citizen_key(cid)
    f_key = citizen_facts_key(cid)
    e_key = eligibility_result_key(cid, version=1)

    await cache.set(p_key, {"name": "Test Citizen"}, ttl=60)
    await cache.set(f_key, {"AGE": "25"}, ttl=60)
    await cache.set(e_key, [{"eligible": True}], ttl=60)

    assert await cache.get(p_key) is not None
    assert await cache.get(f_key) is not None
    assert await cache.get(e_key) is not None

    await invalidate_citizen(cid)

    assert await cache.get(p_key) is None
    assert await cache.get(f_key) is None
    assert await cache.get(e_key) is None
