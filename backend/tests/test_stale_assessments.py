"""
Regression tests for Phase 3 Task 4: Prevent stale eligibility results from appearing current.

Covers:
1. Rule and group mutations in RuleAdminService updating SchemeMaster.last_updated_at.
2. Failed mutations not falsely advancing last_updated_at.
3. Assessment upsert refreshing updated_at timestamp.
4. Detecting and flagging stale assessments when a scheme's rules change after evaluation.
5. Clearing staleness upon re-evaluation.
6. Excluding inactive, expired, and future-dated schemes from current recommendations.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.citizen import CitizenMaster
from app.models.scheme import SchemeMaster, SchemeRuleGroup, SchemeEligibilityRule
from app.models.assessment import EligibilityAssessment
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.scheme_repository import SchemeRepository
from app.schemas.assessment import RecommendationItem
from app.services.eligibility_engine import EligibilityEngine
from app.services.recommendation_service import rank_recommendations
from app.services.rule_admin_service import RuleAdminError, RuleAdminService


_test_engine = create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool)
_TestSession = async_sessionmaker(_test_engine, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    """Yield an async session whose transaction is always rolled back."""
    async with _TestSession() as session:
        try:
            yield session
        finally:
            await session.rollback()


def _mk_test_scheme(
    db: AsyncSession,
    *,
    name_suffix: str,
    status: str = "ACTIVE",
    start_date: date | None = None,
    end_date: date | None = None,
    last_updated_at: datetime | None = None,
) -> SchemeMaster:
    scheme = SchemeMaster(
        scheme_name=f"Stale Audit Scheme {name_suffix}",
        scheme_category="EDUCATION",
        status=status,
        start_date=start_date,
        end_date=end_date,
        last_updated_at=last_updated_at,
        group_combining_operator="AND",
        scheme_version=1,
    )
    db.add(scheme)
    return scheme


def _mk_test_citizen(db: AsyncSession, *, name_suffix: str) -> CitizenMaster:
    citizen = CitizenMaster(
        full_name=f"Stale Audit Citizen {name_suffix}",
        citizen_type="STUDENT",
        date_of_birth=date(2005, 5, 15),
        gender="FEMALE",
        profile_types=["STUDENT"],
    )
    db.add(citizen)
    return citizen


# ----------------------------------------------------------------------
# 1 & 2 & 3. RuleAdminService last_updated_at updates and failed mutations
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rule_and_group_mutations_update_last_updated_at(db: AsyncSession):
    """Creating, updating, and deleting groups and rules updates SchemeMaster.last_updated_at."""
    service = RuleAdminService(db)
    suffix = uuid.uuid4().hex[:8]
    scheme = _mk_test_scheme(db, name_suffix=suffix)
    await db.flush()

    assert scheme.last_updated_at is None

    # 1. create_group
    group = await service.create_group(scheme.scheme_id, group_name="Group 1")
    await db.flush()
    assert scheme.last_updated_at is not None
    t1 = scheme.last_updated_at

    # 2. update_group
    await service.update_group(scheme.scheme_id, group.group_id, group_name="Group 1 Updated")
    await db.flush()
    assert scheme.last_updated_at >= t1
    t2 = scheme.last_updated_at

    # 3. create_rule
    rule = await service.create_rule(
        scheme.scheme_id,
        group_id=group.group_id,
        parameter_name="age",
        operator=">=",
        required_value="18",
    )
    await db.flush()
    assert scheme.last_updated_at >= t2
    t3 = scheme.last_updated_at

    # 4. update_rule
    await service.update_rule(
        scheme.scheme_id,
        rule.rule_id,
        required_value="21",
    )
    await db.flush()
    assert scheme.last_updated_at >= t3
    t4 = scheme.last_updated_at

    # 5. set_group_combining_operator
    await service.set_group_combining_operator(scheme.scheme_id, "OR")
    await db.flush()
    assert scheme.last_updated_at >= t4
    t5 = scheme.last_updated_at

    # 6. delete_rule
    await service.delete_rule(scheme.scheme_id, rule.rule_id)
    await db.flush()
    assert scheme.last_updated_at >= t5
    t6 = scheme.last_updated_at

    # 7. delete_group
    await service.delete_group(scheme.scheme_id, group.group_id)
    await db.flush()
    assert scheme.last_updated_at >= t6


@pytest.mark.asyncio
async def test_failed_mutations_do_not_advance_last_updated_at(db: AsyncSession):
    """Validation errors must not falsely advance SchemeMaster.last_updated_at."""
    service = RuleAdminService(db)
    suffix = uuid.uuid4().hex[:8]
    fixed_time = datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    scheme = _mk_test_scheme(db, name_suffix=suffix, last_updated_at=fixed_time)
    await db.flush()

    # Invalid group operator
    with pytest.raises(RuleAdminError):
        await service.create_group(scheme.scheme_id, group_name="G", intra_group_operator="INVALID")
    assert scheme.last_updated_at == fixed_time

    # Invalid rule parameter
    group = await service.create_group(scheme.scheme_id, group_name="Valid Group")
    await db.flush()
    time_after_group = scheme.last_updated_at

    with pytest.raises(RuleAdminError):
        await service.create_rule(
            scheme.scheme_id,
            group_id=group.group_id,
            parameter_name="invented_param",
            operator="==",
            required_value="foo",
        )
    assert scheme.last_updated_at == time_after_group


# ----------------------------------------------------------------------
# 4. Assessment repository upsert refreshes updated_at
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_assessment_upsert_refreshes_updated_at(db: AsyncSession):
    """Upserting an existing assessment must refresh the updated_at timestamp."""
    repo = AssessmentRepository(db)
    suffix = uuid.uuid4().hex[:8]
    scheme = _mk_test_scheme(db, name_suffix=suffix)
    citizen = _mk_test_citizen(db, name_suffix=suffix)
    await db.flush()

    # Initial assessment insert
    initial = await repo.upsert_assessment(
        citizen_id=citizen.citizen_id,
        scheme_id=scheme.scheme_id,
        eligibility_result=False,
        reason="Initial failure",
        evaluation_details={"overall_result": False},
    )
    await db.flush()
    created_at = initial.created_at
    updated_at_1 = initial.updated_at
    assert created_at is not None
    assert updated_at_1 is not None

    # Upsert again with new outcome via batch upsert_assessments
    batch_result = await repo.upsert_assessments(
        [
            {
                "citizen_id": citizen.citizen_id,
                "scheme_id": scheme.scheme_id,
                "eligibility_result": True,
                "reason": "Now eligible",
                "evaluation_details": {"overall_result": True},
                "confidence_score": 1.0,
            }
        ]
    )
    await db.flush()
    second = batch_result[0]

    assert second.eligibility_result is True
    assert second.reason == "Now eligible"
    assert second.updated_at >= updated_at_1


# ----------------------------------------------------------------------
# 5 & 6. Staleness detection and re-evaluation clearing
# ----------------------------------------------------------------------


import asyncio
from sqlalchemy import func as sa_func
from app.api.v1.recommendations import get_citizen_recommendations


@pytest.mark.asyncio
async def test_stale_assessment_detected_after_rule_mutation(db: AsyncSession):
    """When a scheme's rules change after evaluation, recommendations API marks it stale, and re-evaluation naturally clears staleness."""
    repo = AssessmentRepository(db)
    rule_service = RuleAdminService(db)
    suffix = uuid.uuid4().hex[:8]

    scheme = _mk_test_scheme(db, name_suffix=suffix)
    citizen = _mk_test_citizen(db, name_suffix=suffix)
    await db.flush()

    group = await rule_service.create_group(scheme.scheme_id, group_name="G1")
    rule = await rule_service.create_rule(
        scheme.scheme_id,
        group_id=group.group_id,
        parameter_name="age",
        operator=">=",
        required_value="18",
    )
    await db.flush()

    # Initial evaluation: performed and stored at T_eval
    eval_row = await repo.upsert_assessment(
        citizen_id=citizen.citizen_id,
        scheme_id=scheme.scheme_id,
        eligibility_result=True,
        reason="Age satisfies >= 18",
        evaluation_details={"overall_result": True, "rule_match_score": 100.0},
    )
    await db.flush()

    # Backdate assessment's updated_at slightly to simulate evaluation occurring before subsequent rule edit
    eval_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    eval_row.updated_at = eval_time
    eval_row.created_at = eval_time
    await db.flush()

    # Admin modifies rule at T_rule > T_eval
    await asyncio.sleep(0.01)
    await rule_service.update_rule(scheme.scheme_id, rule.rule_id, required_value="25")
    await db.flush()

    assert scheme.last_updated_at > eval_time

    # 1. Exercise the actual recommendations API response
    api_response = await get_citizen_recommendations(
        citizen_id=citizen.citizen_id,
        db=db,
        user=None,
    )
    assert api_response.eligible_count == 1
    stale_item = api_response.eligible_schemes[0]
    assert stale_item.is_stale is True
    assert stale_item.reason == "Scheme rules changed since your last evaluation. Re-evaluation recommended."
    assert "Scheme rules changed since your last evaluation. Re-evaluation recommended." in (stale_item.recommendation_explanation or "")

    # Historical assessment records are preserved (not deleted)
    record_count = (
        await db.execute(
            select(sa_func.count())
            .select_from(EligibilityAssessment)
            .where(EligibilityAssessment.citizen_id == citizen.citizen_id)
        )
    ).scalar()
    assert record_count == 1

    # 2. Re-evaluation at T_re-eval > T_rule clears staleness naturally through repository upsert
    await asyncio.sleep(0.01)
    re_eval_row = await repo.upsert_assessment(
        citizen_id=citizen.citizen_id,
        scheme_id=scheme.scheme_id,
        eligibility_result=False,
        reason="Citizen is younger than 25",
        evaluation_details={"overall_result": False, "rule_match_score": 0.0},
    )
    await db.flush()

    # The natural updated_at timestamp from the DB upsert must now be strictly greater than scheme.last_updated_at
    assert re_eval_row.updated_at > scheme.last_updated_at

    # 3. Exercise the actual recommendations API response again after re-evaluation
    fresh_api_response = await get_citizen_recommendations(
        citizen_id=citizen.citizen_id,
        db=db,
        user=None,
    )
    assert fresh_api_response.ineligible_count == 1
    fresh_item = fresh_api_response.ineligible_schemes[0]
    assert fresh_item.is_stale is False
    assert fresh_item.reason == "Citizen is younger than 25"
    assert "Scheme rules changed since your last evaluation" not in (fresh_item.recommendation_explanation or "")


@pytest.mark.asyncio
async def test_recommendations_api_http_staleness_lifecycle(db: AsyncSession):
    """Exercises the recommendations HTTP route over ASGI to verify end-to-end status, JSON serialization, and staleness flags."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app
    from app.database import get_db
    from app.api.v1.deps import get_authenticated_user, require_same_citizen
    from app.models.auth import UserAccount

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_authenticated_user] = lambda: None
    try:
        repo = AssessmentRepository(db)
        rule_service = RuleAdminService(db)
        suffix = uuid.uuid4().hex[:8]

        scheme = _mk_test_scheme(db, name_suffix=suffix)
        citizen = _mk_test_citizen(db, name_suffix=suffix)
        await db.flush()

        group = await rule_service.create_group(scheme.scheme_id, group_name="G_HTTP")
        rule = await rule_service.create_rule(
            scheme.scheme_id,
            group_id=group.group_id,
            parameter_name="age",
            operator=">=",
            required_value="18",
        )
        await db.flush()

        eval_row = await repo.upsert_assessment(
            citizen_id=citizen.citizen_id,
            scheme_id=scheme.scheme_id,
            eligibility_result=True,
            reason="Age satisfies >= 18",
            evaluation_details={"overall_result": True, "rule_match_score": 100.0},
        )
        await db.flush()

        # Simulate older evaluation
        eval_row.updated_at = datetime.now(timezone.utc) - timedelta(minutes=15)
        await db.flush()

        # Admin edits rule
        await asyncio.sleep(0.01)
        await rule_service.update_rule(scheme.scheme_id, rule.rule_id, required_value="30")
        await db.flush()

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get(f"/api/v1/recommendations/{citizen.citizen_id}")
            assert r.status_code == 200
            data = r.json()
            assert data["eligible_count"] == 1
            item = data["eligible_schemes"][0]
            assert item["is_stale"] is True
            assert item["reason"] == "Scheme rules changed since your last evaluation. Re-evaluation recommended."
            assert "Scheme rules changed since your last evaluation. Re-evaluation recommended." in (item.get("recommendation_explanation") or "")

            # Re-evaluate naturally
            await asyncio.sleep(0.01)
            await repo.upsert_assessment(
                citizen_id=citizen.citizen_id,
                scheme_id=scheme.scheme_id,
                eligibility_result=False,
                reason="Does not meet revised age >= 30",
                evaluation_details={"overall_result": False, "rule_match_score": 0.0},
            )
            await db.flush()

            # HTTP GET after re-evaluation
            r_fresh = await client.get(f"/api/v1/recommendations/{citizen.citizen_id}")
            assert r_fresh.status_code == 200
            fresh_data = r_fresh.json()
            assert fresh_data["ineligible_count"] == 1
            fresh_item = fresh_data["ineligible_schemes"][0]
            assert fresh_item["is_stale"] is False
            assert fresh_item["reason"] == "Does not meet revised age >= 30"
            assert "Scheme rules changed since your last evaluation" not in (fresh_item.get("recommendation_explanation") or "")
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_authenticated_user, None)
        app.dependency_overrides.pop(require_same_citizen, None)


# ----------------------------------------------------------------------
# 7. Inactive, expired, and future schemes excluded
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_inactive_and_outside_validity_schemes_excluded_from_recommendations(db: AsyncSession):
    """Only ACTIVE schemes currently within their validity dates are returned for recommendations."""
    repo = AssessmentRepository(db)
    suffix = uuid.uuid4().hex[:8]
    citizen = _mk_test_citizen(db, name_suffix=suffix)
    ref_date = date(2026, 6, 1)

    # 1. Active & Valid
    s_valid = _mk_test_scheme(
        db,
        name_suffix=f"valid_{suffix}",
        status="ACTIVE",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    # 2. Inactive
    s_inactive = _mk_test_scheme(
        db,
        name_suffix=f"inactive_{suffix}",
        status="INACTIVE",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 12, 31),
    )
    # 3. Expired
    s_expired = _mk_test_scheme(
        db,
        name_suffix=f"expired_{suffix}",
        status="ACTIVE",
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )
    # 4. Future-dated (not yet started)
    s_future = _mk_test_scheme(
        db,
        name_suffix=f"future_{suffix}",
        status="ACTIVE",
        start_date=date(2027, 1, 1),
        end_date=date(2027, 12, 31),
    )
    await db.flush()

    for s in (s_valid, s_inactive, s_expired, s_future):
        await repo.upsert_assessment(
            citizen_id=citizen.citizen_id,
            scheme_id=s.scheme_id,
            eligibility_result=True,
            reason="Pass",
            evaluation_details={"overall_result": True},
        )
    await db.flush()

    # Query with active_only=True and as_of=ref_date
    assessments = await repo.get_citizen_assessments(
        citizen.citizen_id, active_only=True, as_of=ref_date
    )

    returned_scheme_ids = {a.scheme_id for a in assessments}
    assert s_valid.scheme_id in returned_scheme_ids
    assert s_inactive.scheme_id not in returned_scheme_ids
    assert s_expired.scheme_id not in returned_scheme_ids
    assert s_future.scheme_id not in returned_scheme_ids
