"""
Admin eligibility-rule management backend tests.

Covers the RuleAdminService and the /api/v1/admin/schemes/{id}/rule-groups,
/rules, and /group-combining-operator endpoints:
  - authorization: no token -> 401; authenticated non-admin -> 403;
    admin -> full CRUD (require_admin dependency, no second mechanism)
  - group/rule CRUD over HTTP + service level, incl. invalid scheme/group
  - validation of the frozen engine vocabulary (parameters, operators,
    value typing, missing values, group operator, failure stage code)
  - mandatory-condition semantics via the REAL eligibility engine: every
    rule is a hard gate; a passing high-priority rule never overrides a
    failing mandatory one; AND/OR semantics at group and scheme level
  - referential safety: provenance-bearing rules/groups refuse deletion
  - cache: rule/group mutations invalidate the affected scheme's cached
    citizen-facing data; the next eligibility evaluation sees the new rule

SAFETY: service-level tests run inside a rolled-back transaction. The HTTP
tests create real rows and delete them in finally blocks; no seeded scheme,
citizen, or source is ever modified.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from datetime import date
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.auth import UserAccount, UserSession, UserRole
from app.models.citizen import CitizenMaster, FinancialProfile
from app.models.scheme import (
    SchemeEligibilityRule,
    SchemeMaster,
    SchemeRuleGroup,
)
from app.models.scheme_source import (
    SchemeRuleProvenance,
    SchemeSource,
    SchemeSourceDocument,
)
from app.repositories.citizen_repository import CitizenRepository
from app.services.eligibility_engine import EligibilityEngine
from app.services.rule_admin_service import (
    ELIGIBILITY_RULE_OPERATORS,
    ELIGIBILITY_RULE_PARAMETERS,
    FAILURE_STAGE_CODES,
    GROUP_OPERATORS,
    RuleAdminError,
    RuleAdminService,
)

# NullPool: fresh connection per session (pytest-asyncio uses function-scoped
# event loops; pooled connections would die with "Event loop is closed").
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


def _run(coro):
    return asyncio.run(coro)


# ----------------------------------------------------------------------
# Vocabulary sanity (frozen contract consumed by the eligibility engine)
# ----------------------------------------------------------------------


def test_rule_vocabularies_match_engine():
    """Every operator the engine implements and every parameter it resolves
    is covered by the frozen vocabularies."""
    assert set(ELIGIBILITY_RULE_OPERATORS) == {"<", "<=", ">", ">=", "==", "!=", "IN"}
    assert set(ELIGIBILITY_RULE_PARAMETERS) == {
        # every branch of EligibilityEngine._resolve_parameter
        "age",
        "gender",
        "citizen_type",
        "annual_income",
        "poverty_category",
        "land_holding_size",
        "is_bpl_card_holder",
        "is_income_tax_payer",
        "employment_status",
        "social_category",
        "education_level",
        "disability_status",
        "area_type",
        "state",
        "tenth_percentage",
        "twelfth_percentage",
        "twelfth_percentile",
        "livestock_cattle_count",
        "livestock_poultry_count",
    }
    assert set(GROUP_OPERATORS) == {"AND", "OR"}
    assert set(FAILURE_STAGE_CODES) == {
        "S0_ELIGIBILITY",
        "S1_DOCUMENT_DISCREPANCY",
        "S2_DOMICILE_MISMATCH",
    }


def test_scheme_service_update_cannot_change_group_combining_operator():
    """The generic scheme PATCH stays operator-free — the operator is only
    administered through the explicit rule-management endpoint (or at
    scheme-create time)."""
    from app.services.scheme_admin_service import SchemeAdminService

    update_params = inspect.signature(SchemeAdminService.update).parameters
    assert "group_combining_operator" not in update_params
    assert "group_combining_operator" in inspect.signature(
        SchemeAdminService.create
    ).parameters
    assert "operator" in inspect.signature(
        RuleAdminService.set_group_combining_operator
    ).parameters
    assert "group_combining_operator" not in inspect.signature(
        RuleAdminService.update_rule
    ).parameters


# ----------------------------------------------------------------------
# Service-level CRUD + validation (rolled back)
# ----------------------------------------------------------------------


def _mk_scheme(session) -> SchemeMaster:
    scheme = SchemeMaster(
        scheme_name=f"RuleAdmin {uuid.uuid4().hex[:8]}",
        scheme_category="EDUCATION",
        status="ACTIVE",
    )
    session.add(scheme)
    return scheme


@pytest.mark.asyncio
async def test_group_crud_roundtrip(db: AsyncSession):
    service = RuleAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()

    group = await service.create_group(
        scheme.scheme_id, group_name="Income", intra_group_operator="OR", group_priority=2
    )
    await db.flush()
    assert group.scheme_id == scheme.scheme_id
    assert group.group_priority == 2

    fetched = await service.get_group(scheme.scheme_id, group.group_id)
    assert fetched.group_name == "Income"
    assert len(fetched.rules) == 0

    updated = await service.update_group(
        scheme.scheme_id, group.group_id, group_name="Income v2", group_priority=5
    )
    assert updated.group_name == "Income v2"
    assert updated.group_priority == 5
    assert updated.intra_group_operator == "OR"  # untouched field preserved

    await service.delete_group(scheme.scheme_id, group.group_id)
    remaining = await service.list_groups(scheme.scheme_id)
    assert all(g.group_id != group.group_id for g in remaining)


@pytest.mark.asyncio
async def test_group_validation_rejects(db: AsyncSession):
    service = RuleAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()
    group = await service.create_group(scheme.scheme_id, group_name="Base")
    await db.flush()

    with pytest.raises(RuleAdminError) as exc:
        await service.create_group(scheme.scheme_id, group_name="   ")
    assert exc.value.status_code == 400

    with pytest.raises(RuleAdminError) as exc:
        await service.create_group(scheme.scheme_id, group_name="x" * 101)
    assert exc.value.status_code == 400

    with pytest.raises(RuleAdminError) as exc:
        await service.create_group(
            scheme.scheme_id, group_name="X", intra_group_operator="XOR"
        )
    assert exc.value.status_code == 400

    with pytest.raises(RuleAdminError) as exc:
        await service.update_group(
            scheme.scheme_id, group.group_id, intra_group_operator="NOT"
        )
    assert exc.value.status_code == 400

    # Unknown scheme / foreign group
    with pytest.raises(RuleAdminError) as exc:
        await service.create_group(uuid.uuid4(), group_name="Orphan")
    assert exc.value.status_code == 404

    with pytest.raises(RuleAdminError) as exc:
        await service.get_group(scheme.scheme_id, uuid.uuid4())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_rule_belongs_to_its_scheme_only(db: AsyncSession):
    """A group from scheme B is NOT a valid group for a rule of scheme A."""
    service = RuleAdminService(db)
    scheme_a = _mk_scheme(db)
    scheme_b = _mk_scheme(db)
    await db.flush()
    group_b = await service.create_group(scheme_b.scheme_id, group_name="B Group")
    await db.flush()

    with pytest.raises(RuleAdminError) as exc:
        await service.create_rule(
            scheme_a.scheme_id,
            group_id=group_b.group_id,
            parameter_name="age",
            operator=">=",
            required_value="18",
        )
    assert exc.value.status_code == 404
    assert "this scheme" in exc.value.detail


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("parameter_name", "favourite_colour"),  # invented field
        ("parameter_name", "AGE"),  # case-sensitive engine branch
        ("operator", "==="),  # invented operator
    ],
)
async def test_rule_field_and_operator_validation_rejects(db, field, value):
    service = RuleAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()
    group = await service.create_group(scheme.scheme_id, group_name="G")
    await db.flush()
    payload = {
        "group_id": group.group_id,
        "parameter_name": "age",
        "operator": ">=",
        "required_value": "18",
    }
    payload[field] = value
    with pytest.raises(RuleAdminError) as exc:
        await service.create_rule(scheme.scheme_id, **payload)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_rule_one_char_operator_is_accepted(db: AsyncSession):
    service = RuleAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()
    group = await service.create_group(scheme.scheme_id, group_name="G")
    await db.flush()
    rule = await service.create_rule(
        scheme.scheme_id,
        group_id=group.group_id,
        parameter_name="age",
        operator=">",
        required_value="60",
    )
    assert rule.operator == ">"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "parameter_name,operator,required_value",
    [
        ("age", ">=", ""),  # missing value
        ("age", ">=", "   "),  # whitespace-only value
        ("age", ">=", "not-a-number"),  # numeric parameter, bad value
        ("age", "==", "eighteen"),  # numeric parameter, non-numeric equality
        ("annual_income", "<=", "1,00,000"),  # INR formatting, not a number
        ("is_bpl_card_holder", "==", "MAYBE"),  # non-boolean value
        ("is_bpl_card_holder", ">=", "true"),  # ordering is meaningless on booleans
        ("gender", "IN", "FEMALE,,OTHER"),  # empty IN item
        ("social_category", "IN", ",,"),  # IN with nothing
    ],
)
async def test_rule_value_validation_rejects(db, parameter_name, operator, required_value):
    service = RuleAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()
    group = await service.create_group(scheme.scheme_id, group_name="G")
    await db.flush()
    with pytest.raises(RuleAdminError) as exc:
        await service.create_rule(
            scheme.scheme_id,
            group_id=group.group_id,
            parameter_name=parameter_name,
            operator=operator,
            required_value=required_value,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_rule_missing_required_value_rejected(db: AsyncSession):
    service = RuleAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()
    group = await service.create_group(scheme.scheme_id, group_name="G")
    await db.flush()
    with pytest.raises(RuleAdminError) as exc:
        await service.create_rule(
            scheme.scheme_id,
            group_id=group.group_id,
            parameter_name="age",
            operator=">=",
            required_value=None,  # required_value missing
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_rule_failure_stage_code_vocabulary(db: AsyncSession):
    service = RuleAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()
    group = await service.create_group(scheme.scheme_id, group_name="G")
    await db.flush()

    ok = await service.create_rule(
        scheme.scheme_id,
        group_id=group.group_id,
        parameter_name="state",
        operator="==",
        required_value="Maharashtra",
        failure_stage_code="S2_DOMICILE_MISMATCH",
    )
    assert ok.failure_stage_code == "S2_DOMICILE_MISMATCH"

    with pytest.raises(RuleAdminError) as exc:
        await service.create_rule(
            scheme.scheme_id,
            group_id=group.group_id,
            parameter_name="state",
            operator="==",
            required_value="Maharashtra",
            failure_stage_code="S9_INVENTED",
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_rule_update_validates_effective_triple(db: AsyncSession):
    """A partial update cannot leave an invalid rule behind: validation runs
    against the NEW-or-EXISTING parameter/operator/value combination."""
    service = RuleAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()
    group = await service.create_group(scheme.scheme_id, group_name="G")
    rule = await service.create_rule(
        scheme.scheme_id,
        group_id=group.group_id,
        parameter_name="age",
        operator="==",
        required_value="18",
    )
    await db.flush()

    # Switch parameter to a boolean with the existing numeric value -> reject
    with pytest.raises(RuleAdminError) as exc:
        await service.update_rule(
            scheme.scheme_id, rule.rule_id, parameter_name="is_bpl_card_holder"
        )
    assert exc.value.status_code == 400

    # Switch operator to >= with existing value '18' -> valid, value kept
    updated = await service.update_rule(
        scheme.scheme_id, rule.rule_id, operator=">="
    )
    assert updated.operator == ">="
    assert updated.required_value == "18"
    assert updated.parameter_name == "age"

    # Bad new value with unchanged parameter -> reject
    with pytest.raises(RuleAdminError) as exc:
        await service.update_rule(
            scheme.scheme_id, rule.rule_id, required_value="abc"
        )
    assert exc.value.status_code == 400

    # Moving to another scheme's group is rejected
    other_scheme = _mk_scheme(db)
    await db.flush()
    other_group = await service.create_group(other_scheme.scheme_id, group_name="OG")
    await db.flush()
    with pytest.raises(RuleAdminError) as exc:
        await service.update_rule(
            scheme.scheme_id, rule.rule_id, group_id=other_group.group_id
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_set_group_combining_operator(db: AsyncSession):
    service = RuleAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()

    changed = await service.set_group_combining_operator(scheme.scheme_id, " OR ")
    assert changed.group_combining_operator == "OR"

    with pytest.raises(RuleAdminError) as exc:
        await service.set_group_combining_operator(scheme.scheme_id, "XOR")
    assert exc.value.status_code == 400

    with pytest.raises(RuleAdminError) as exc:
        await service.set_group_combining_operator(uuid.uuid4(), "AND")
    assert exc.value.status_code == 404


# ----------------------------------------------------------------------
# Eligibility-engine semantics (pure; mirrors test_eligibility_engine.py)
# ----------------------------------------------------------------------


def _engine_citizen(age_years: int, citizen_type: str):
    return CitizenMaster(
        full_name="Engine Probe",
        citizen_type=citizen_type,
        date_of_birth=date(2026 - age_years, 1, 1),
    )


def _engine_scheme(intra: str, rules: list[tuple[str, str, str]], combining: str = "AND"):
    scheme = SchemeMaster(scheme_name="Probe", group_combining_operator=combining)
    group = SchemeRuleGroup(group_name="Mixed", intra_group_operator=intra)
    group.rules = [
        SchemeEligibilityRule(parameter_name=p, operator=o, required_value=v)
        for p, o, v in rules
    ]
    scheme.rule_groups = [group]
    return scheme


def test_mandatory_rule_passes():
    engine = EligibilityEngine()
    # rule: age >= 18 (hard gate); citizen age 25 -> condition passes
    citizen = _engine_citizen(25, "STUDENT")
    scheme = _engine_scheme("AND", [("age", ">=", "18")])
    result, details, reason = engine.evaluate_scheme(citizen, scheme)
    assert result is True
    assert details["groups"][0]["group_passed"] is True
    assert reason.startswith("Citizen meets all criteria")


def test_mandatory_rule_fails_blocks_eligibility():
    engine = EligibilityEngine()
    # rule: age >= 18; citizen 16 -> the hard gate fails -> NOT eligible
    citizen = _engine_citizen(16, "STUDENT")
    scheme = _engine_scheme("AND", [("age", ">=", "18")])
    result, details, reason = engine.evaluate_scheme(citizen, scheme)
    assert result is False
    assert details["groups"][0]["group_passed"] is False
    assert "age" in reason.lower()


def test_multiple_mandatory_conditions_all_must_hold():
    engine = EligibilityEngine()

    def two_group_scheme():
        scheme = SchemeMaster(scheme_name="Probe", group_combining_operator="AND")
        g1 = SchemeRuleGroup(group_name="Age", intra_group_operator="AND")
        g1.rules = [
            SchemeEligibilityRule(parameter_name="age", operator=">=", required_value="18")
        ]
        g2 = SchemeRuleGroup(group_name="Type", intra_group_operator="AND")
        g2.rules = [
            SchemeEligibilityRule(parameter_name="citizen_type", operator="==", required_value="FARMER")
        ]
        scheme.rule_groups = [g1, g2]
        return scheme

    citizen = _engine_citizen(25, "STUDENT")  # age passes, type fails
    result, details, _ = engine.evaluate_scheme(citizen, two_group_scheme())
    assert result is False  # AND of groups: every mandatory group must hold
    assert details["groups"][0]["group_passed"] is True
    assert details["groups"][1]["group_passed"] is False

    result, _, _ = engine.evaluate_scheme(_engine_citizen(25, "FARMER"), two_group_scheme())
    assert result is True


def test_rules_within_group_and_or():
    engine = EligibilityEngine()
    rules = [("age", ">=", "18"), ("citizen_type", "==", "FARMER")]
    citizen = _engine_citizen(25, "STUDENT")  # age passes, type fails

    result, _, _ = engine.evaluate_scheme(citizen, _engine_scheme("AND", rules))
    assert result is False

    result, details, _ = engine.evaluate_scheme(citizen, _engine_scheme("OR", rules))
    assert result is True
    assert details["groups"][0]["intra_group_operator"] == "OR"


def test_scheme_level_group_combining_operator_or():
    engine = EligibilityEngine()
    citizen = _engine_citizen(25, "STUDENT")

    def two_group_scheme(combining: str):
        scheme = SchemeMaster(
            scheme_name="Probe", group_combining_operator=combining
        )
        g1 = SchemeRuleGroup(group_name="Age", intra_group_operator="AND")
        g1.rules = [
            SchemeEligibilityRule(parameter_name="age", operator=">=", required_value="18")
        ]
        g2 = SchemeRuleGroup(group_name="FarmerOnly", intra_group_operator="AND")
        g2.rules = [
            SchemeEligibilityRule(
                parameter_name="citizen_type", operator="==", required_value="FARMER"
            )
        ]
        scheme.rule_groups = [g1, g2]
        return scheme

    result, details, _ = engine.evaluate_scheme(citizen, two_group_scheme("OR"))
    assert result is True  # OR: one passing group is enough
    assert details["group_combining_operator"] == "OR"

    result, details, _ = engine.evaluate_scheme(citizen, two_group_scheme("AND"))
    assert result is False  # AND: the failing group blocks eligibility
    assert details["group_combining_operator"] == "AND"


def test_passing_higher_priority_rule_never_overrides_mandatory_failure():
    """There is no ranking/weight layer in the eligibility path: a passing
    rule — even ordered BEFORE the failing one — can never rescue a failed
    mandatory condition."""
    engine = EligibilityEngine()
    citizen = CitizenMaster(
        full_name="Engine Probe",
        citizen_type="STUDENT",
        date_of_birth=date(2026 - 16, 1, 1),  # 16 -> the age gate fails
    )

    def mixed_scheme():
        scheme = SchemeMaster(scheme_name="Probe", group_combining_operator="AND")
        group = SchemeRuleGroup(group_name="Mixed", intra_group_operator="AND")
        rule_type = SchemeEligibilityRule(
            parameter_name="citizen_type",
            operator="==",
            required_value="STUDENT",
            rule_priority=1,  # passes AND is evaluated FIRST
        )
        rule_age = SchemeEligibilityRule(
            parameter_name="age",
            operator=">=",
            required_value="18",
            rule_priority=2,  # FAILS
        )
        group.rules = [rule_type, rule_age]
        scheme.rule_groups = [group]
        return scheme

    result, details, _ = engine.evaluate_scheme(citizen, mixed_scheme())
    assert result is False
    rule_results = details["groups"][0]["rules"]
    assert rule_results[0]["passed"] is True
    assert rule_results[1]["passed"] is False
    assert details["groups"][0]["group_passed"] is False


# ----------------------------------------------------------------------
# HTTP layer (real rows, cleaned up in finally)
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.database import engine
    from app.main import app

    with TestClient(app) as c:
        yield c
    _run(engine.dispose())


def _make_user_with_role(role: str | None) -> dict:
    """Create a throwaway user (+ optional role + session); return state."""
    from app.repositories.auth_repository import AuthRepository

    email = f"rule.admin.test.{uuid.uuid4().hex[:8]}@example.com"
    state: dict = {}

    async def make():
        async with _TestSession() as s:
            user = UserAccount(email=email, provider="LOCAL", password_hash="x")
            s.add(user)
            await s.flush()
            if role:
                s.add(UserRole(user_id=user.user_id, role=role))
            repo = AuthRepository(s)
            token = uuid.uuid4().hex + uuid.uuid4().hex
            await repo.create_session(user.user_id, token, ttl_hours=1)
            await s.commit()
            state["user_id"] = user.user_id
            state["token"] = token

    _run(make())
    return state


def _cleanup_user(state: dict) -> None:
    async def cleanup():
        async with _TestSession() as s:
            await s.execute(
                delete(UserSession).where(UserSession.user_id == state["user_id"])
            )
            await s.execute(
                delete(UserRole).where(UserRole.user_id == state["user_id"])
            )
            await s.execute(
                delete(UserAccount).where(UserAccount.user_id == state["user_id"])
            )
            await s.commit()

    _run(cleanup())


@pytest.fixture(scope="module")
def admin_token() -> str:
    state = _make_user_with_role("ADMIN")
    yield state["token"]
    _cleanup_user(state)


@pytest.fixture(scope="module")
def non_admin_token() -> str:
    state = _make_user_with_role(None)
    yield state["token"]
    _cleanup_user(state)


async def _delete_scheme_full(scheme_id) -> None:
    """Remove a test scheme plus everything potentially attached to it."""
    async with _TestSession() as s:
        rule_ids = (
            (
                await s.execute(
                    select(SchemeEligibilityRule.rule_id).where(
                        SchemeEligibilityRule.scheme_id == scheme_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if rule_ids:
            await s.execute(
                delete(SchemeRuleProvenance).where(
                    SchemeRuleProvenance.rule_id.in_(rule_ids)
                )
            )
        doc_rows = (
            (
                await s.execute(
                    select(SchemeSourceDocument.source_id).where(
                        SchemeSourceDocument.scheme_id == scheme_id
                    )
                )
            )
            .scalars()
            .all()
        )
        await s.execute(
            delete(SchemeSourceDocument).where(
                SchemeSourceDocument.scheme_id == scheme_id
            )
        )
        for source_id in doc_rows:
            await s.execute(
                delete(SchemeSource).where(SchemeSource.source_id == source_id)
            )
        await s.execute(delete(SchemeMaster).where(SchemeMaster.scheme_id == scheme_id))
        await s.commit()


@pytest.fixture()
def scheme_id(client, admin_token: str):
    """Create a throwaway scheme through the admin API; clean on teardown."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/api/v1/admin/schemes",
        headers=headers,
        json={
            "scheme_name": f"Rule Admin Test {uuid.uuid4().hex[:8]}",
            "scheme_category": "EDUCATION",
            "status": "ACTIVE",
        },
    )
    assert resp.status_code == 201, resp.text
    sid = resp.json()["scheme_id"]
    yield sid
    _run(_delete_scheme_full(sid))


def test_rule_admin_endpoints_require_authentication(client):
    """No token -> 401 on every new rule-admin route."""
    sid = str(uuid.uuid4())
    gid = str(uuid.uuid4())
    rid = str(uuid.uuid4())
    routes = [
        ("get", f"/api/v1/admin/schemes/{sid}/rule-groups", None),
        ("post", f"/api/v1/admin/schemes/{sid}/rule-groups", {"group_name": "G"}),
        ("get", f"/api/v1/admin/schemes/{sid}/rule-groups/{gid}", None),
        ("patch", f"/api/v1/admin/schemes/{sid}/rule-groups/{gid}", {"group_name": "G"}),
        ("delete", f"/api/v1/admin/schemes/{sid}/rule-groups/{gid}", None),
        (
            "patch",
            f"/api/v1/admin/schemes/{sid}/group-combining-operator",
            {"group_combining_operator": "OR"},
        ),
        ("get", f"/api/v1/admin/schemes/{sid}/rules", None),
        (
            "post",
            f"/api/v1/admin/schemes/{sid}/rules",
            {"group_id": gid, "parameter_name": "age", "operator": ">=", "required_value": "18"},
        ),
        ("get", f"/api/v1/admin/schemes/{sid}/rules/{rid}", None),
        ("patch", f"/api/v1/admin/schemes/{sid}/rules/{rid}", {"required_value": "21"}),
        ("delete", f"/api/v1/admin/schemes/{sid}/rules/{rid}", None),
    ]
    for method, path, body in routes:
        if body is None:
            response = getattr(client, method)(path)
        else:
            response = getattr(client, method)(path, json=body)
        assert response.status_code == 401, (method, path, response.status_code)


def test_rule_admin_endpoints_reject_non_admin(client, non_admin_token: str):
    """Authenticated non-admin -> 403 on every new rule-admin route."""
    headers = {"Authorization": f"Bearer {non_admin_token}"}
    sid = str(uuid.uuid4())
    gid = str(uuid.uuid4())
    rid = str(uuid.uuid4())
    routes = [
        ("get", f"/api/v1/admin/schemes/{sid}/rule-groups", None),
        ("post", f"/api/v1/admin/schemes/{sid}/rule-groups", {"group_name": "G"}),
        ("patch", f"/api/v1/admin/schemes/{sid}/rule-groups/{gid}", {"group_name": "G"}),
        ("delete", f"/api/v1/admin/schemes/{sid}/rule-groups/{gid}", None),
        (
            "patch",
            f"/api/v1/admin/schemes/{sid}/group-combining-operator",
            {"group_combining_operator": "OR"},
        ),
        ("get", f"/api/v1/admin/schemes/{sid}/rules", None),
        (
            "post",
            f"/api/v1/admin/schemes/{sid}/rules",
            {"group_id": gid, "parameter_name": "age", "operator": ">=", "required_value": "18"},
        ),
        ("patch", f"/api/v1/admin/schemes/{sid}/rules/{rid}", {"required_value": "21"}),
        ("delete", f"/api/v1/admin/schemes/{sid}/rules/{rid}", None),
    ]
    for method, path, body in routes:
        if body is None:
            response = getattr(client, method)(path, headers=headers)
        else:
            response = getattr(client, method)(path, headers=headers, json=body)
        assert response.status_code == 403, (method, path, response.status_code)


def test_generic_scheme_patch_cannot_change_group_operator(
    client, admin_token: str, scheme_id
):
    """The generic scheme PATCH cannot edit the group combining operator:
    an inline attempt leaves the operator unchanged (only the dedicated
    rule-management endpoint accepts it)."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.patch(
        f"/api/v1/admin/schemes/{scheme_id}",
        headers=headers,
        json={"group_combining_operator": "OR"},
    )
    assert r.status_code == 200  # FastAPI drops unknown fields silently
    r = client.get(f"/api/v1/admin/schemes/{scheme_id}", headers=headers)
    assert r.json()["group_combining_operator"] == "AND"  # unchanged by PATCH


def test_group_and_rule_crud_lifecycle_over_http(client, admin_token: str, scheme_id):
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = f"/api/v1/admin/schemes/{scheme_id}"

    # --- create group ---
    r = client.post(
        f"{base}/rule-groups",
        headers=headers,
        json={"group_name": "Age Rules", "intra_group_operator": "AND", "group_priority": 1},
    )
    assert r.status_code == 201, r.text
    group = r.json()
    gid = group["group_id"]
    assert group["intra_group_operator"] == "AND"
    assert group["rules"] == []

    # --- create rule in group ---
    r = client.post(
        f"{base}/rules",
        headers=headers,
        json={
            "group_id": gid,
            "parameter_name": "age",
            "operator": ">=",
            "required_value": "18",
            "rule_description": "Must be 18 or older",
            "rule_priority": 1,
        },
    )
    assert r.status_code == 201, r.text
    rule = r.json()
    rid = rule["rule_id"]
    assert rule["scheme_id"] == scheme_id
    assert rule["group_id"] == gid

    # --- nested listing shows the rule under its group ---
    r = client.get(f"{base}/rule-groups", headers=headers)
    assert r.status_code == 200
    groups = r.json()
    assert len(groups) == 1 and groups[0]["group_id"] == gid
    assert len(groups[0]["rules"]) == 1
    assert groups[0]["rules"][0]["parameter_name"] == "age"

    # --- flat rule listing + single get ---
    r = client.get(f"{base}/rules", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1
    r = client.get(f"{base}/rules/{rid}", headers=headers)
    assert r.status_code == 200 and r.json()["required_value"] == "18"

    # --- patch group (operator change) ---
    r = client.patch(
        f"{base}/rule-groups/{gid}", headers=headers, json={"intra_group_operator": "OR"}
    )
    assert r.status_code == 200 and r.json()["intra_group_operator"] == "OR"

    # --- patch rule ---
    r = client.patch(
        f"{base}/rules/{rid}",
        headers=headers,
        json={"required_value": "21", "rule_description": "21+"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["required_value"] == "21"
    assert r.json()["operator"] == ">="

    # --- invalid scheme / group / rule ids -> 404 ---
    r = client.get(f"/api/v1/admin/schemes/{uuid.uuid4()}/rule-groups", headers=headers)
    assert r.status_code == 404
    r = client.get(f"{base}/rules/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404
    r = client.get(f"{base}/rule-groups/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404

    # --- delete rule then group (group is empty afterwards) ---
    r = client.delete(f"{base}/rules/{rid}", headers=headers)
    assert r.status_code == 200
    r = client.delete(f"{base}/rule-groups/{gid}", headers=headers)
    assert r.status_code == 200
    r = client.get(f"{base}/rules", headers=headers)
    assert r.json() == []


def test_rule_validation_over_http(client, admin_token: str, scheme_id):
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = f"/api/v1/admin/schemes/{scheme_id}"
    r = client.post(f"{base}/rule-groups", headers=headers, json={"group_name": "V"})
    gid = r.json()["group_id"]

    bad_bodies = [
        # invalid field
        {"group_id": gid, "parameter_name": "colour", "operator": ">=", "required_value": "1"},
        # invalid operator
        {"group_id": gid, "parameter_name": "age", "operator": "===", "required_value": "18"},
        # missing/empty value
        {"group_id": gid, "parameter_name": "age", "operator": ">=", "required_value": ""},
        # invalid value type/format for a numeric parameter
        {"group_id": gid, "parameter_name": "age", "operator": ">=", "required_value": "eighteen"},
        # invalid boolean value (stands in for an invalid mandatory flag/type)
        {"group_id": gid, "parameter_name": "is_bpl_card_holder", "operator": "==", "required_value": "MAYBE"},
        # invalid IN list
        {"group_id": gid, "parameter_name": "gender", "operator": "IN", "required_value": "F,,M"},
    ]
    for body in bad_bodies:
        r = client.post(f"{base}/rules", headers=headers, json=body)
        assert r.status_code == 400, (body, r.status_code, r.text)

    # invalid group ASSOCIATION: the group exists but belongs to no scheme
    # here -> 404, not 400 (service semantics; also must not create a rule)
    r = client.post(
        f"{base}/rules",
        headers=headers,
        json={
            "group_id": str(uuid.uuid4()),
            "parameter_name": "age",
            "operator": ">=",
            "required_value": "18",
        },
    )
    assert r.status_code == 404, r.text
    assert client.get(f"{base}/rules", headers=headers).json() == []

    # invalid group operator
    r = client.post(
        f"{base}/rule-groups",
        headers=headers,
        json={"group_name": "X", "intra_group_operator": "XOR"},
    )
    assert r.status_code == 400

    # invalid scheme-level group combining operator
    r = client.patch(
        f"{base}/group-combining-operator",
        headers=headers,
        json={"group_combining_operator": "MAYBE"},
    )
    assert r.status_code == 400


def test_group_combining_operator_administration_over_http(
    client, admin_token: str, scheme_id
):
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = f"/api/v1/admin/schemes/{scheme_id}"

    r = client.post(f"{base}/rule-groups", headers=headers, json={"group_name": "G1"})
    gid = r.json()["group_id"]
    client.post(
        f"{base}/rules",
        headers=headers,
        json={"group_id": gid, "parameter_name": "age", "operator": ">=", "required_value": "18"},
    )

    # Explicit operator switch is validated...
    r = client.patch(
        f"{base}/group-combining-operator",
        headers=headers,
        json={"group_combining_operator": "OR"},
    )
    assert r.status_code == 200, r.text
    # ...and visible in admin scheme detail
    r = client.get(f"/api/v1/admin/schemes/{scheme_id}", headers=headers)
    assert r.json()["group_combining_operator"] == "OR"

    # Switch back — fully reversible
    r = client.patch(
        f"{base}/group-combining-operator",
        headers=headers,
        json={"group_combining_operator": "AND"},
    )
    assert r.status_code == 200


def test_delete_protects_provenance_bearing_rule_and_group(client, admin_token: str):
    """A rule with source provenance is refused by BOTH the rule-delete and
    the group-delete endpoints (409). Once unlinked, deletion succeeds."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/admin/schemes",
        headers=headers,
        json={"scheme_name": f"Provenance Probe {uuid.uuid4().hex[:8]}", "status": "ACTIVE"},
    )
    assert r.status_code == 201, r.text
    sid = r.json()["scheme_id"]
    rid = None
    try:
        r = client.post(
            f"/api/v1/admin/schemes/{sid}/rule-groups", headers=headers, json={"group_name": "G"}
        )
        gid = r.json()["group_id"]
        r = client.post(
            f"/api/v1/admin/schemes/{sid}/rules",
            headers=headers,
            json={"group_id": gid, "parameter_name": "age", "operator": ">=", "required_value": "18"},
        )
        rid = r.json()["rule_id"]

        async def add_provenance():
            async with _TestSession() as s:
                source = SchemeSource(
                    source_name=f"Prov Src {uuid.uuid4().hex[:8]}",
                    source_type="GOVERNMENT_WEBSITE",
                    base_url="https://probe.maharashtra.gov.in/",
                    status="ACTIVE",
                )
                s.add(source)
                await s.flush()
                doc = SchemeSourceDocument(
                    scheme_id=sid,
                    source_id=source.source_id,
                    document_name="Guidelines",
                    document_url="https://probe.maharashtra.gov.in/g.pdf",
                    document_type="GUIDELINE",
                    content_hash="1" * 64,
                )
                s.add(doc)
                await s.flush()
                s.add(
                    SchemeRuleProvenance(
                        rule_id=rid,
                        source_document_id=doc.source_document_id,
                    )
                )
                await s.commit()

        _run(add_provenance())

        r = client.delete(f"/api/v1/admin/schemes/{sid}/rules/{rid}", headers=headers)
        assert r.status_code == 409, r.text
        assert "provenance" in r.json()["detail"].lower()

        r = client.delete(f"/api/v1/admin/schemes/{sid}/rule-groups/{gid}", headers=headers)
        assert r.status_code == 409, r.text

        # Untouched by the refused deletions
        r = client.get(f"/api/v1/admin/schemes/{sid}/rules/{rid}", headers=headers)
        assert r.status_code == 200

        # Unlink the provenance -> deletion becomes safe
        async def unlink():
            async with _TestSession() as s:
                await s.execute(
                    delete(SchemeRuleProvenance).where(SchemeRuleProvenance.rule_id == rid)
                )
                await s.commit()

        _run(unlink())
        r = client.delete(f"/api/v1/admin/schemes/{sid}/rules/{rid}", headers=headers)
        assert r.status_code == 200, r.text
        rid = None  # already gone; provenance cleanup will find nothing
    finally:
        _run(_delete_scheme_full(sid))


# ----------------------------------------------------------------------
# Cache: rule mutations invalidate the affected scheme's citizen-facing data
# ----------------------------------------------------------------------


def test_rule_mutation_invalidates_scheme_cache(
    client, admin_token: str, scheme_id, monkeypatch
):
    invalidate_schemes = AsyncMock(return_value=1)
    monkeypatch.setattr("app.api.v1.admin.invalidate_schemes", invalidate_schemes)
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = f"/api/v1/admin/schemes/{scheme_id}"

    r = client.post(f"{base}/rule-groups", headers=headers, json={"group_name": "Cache G"})
    assert r.status_code == 201, r.text
    gid = r.json()["group_id"]
    invalidate_schemes.assert_awaited_once()

    r = client.patch(
        f"{base}/rule-groups/{gid}", headers=headers, json={"intra_group_operator": "OR"}
    )
    assert r.status_code == 200, r.text
    assert invalidate_schemes.await_count == 2

    r = client.post(
        f"{base}/rules",
        headers=headers,
        json={"group_id": gid, "parameter_name": "age", "operator": ">=", "required_value": "18"},
    )
    assert r.status_code == 201, r.text
    rid = r.json()["rule_id"]
    assert invalidate_schemes.await_count == 3
    r = client.patch(
        f"{base}/rules/{rid}", headers=headers, json={"required_value": "21"}
    )
    assert r.status_code == 200, r.text
    assert invalidate_schemes.await_count == 4

    r = client.patch(
        f"{base}/group-combining-operator",
        headers=headers,
        json={"group_combining_operator": "OR"},
    )
    assert r.status_code == 200, r.text
    assert invalidate_schemes.await_count == 5


def test_failed_mutation_leaves_cache_and_data_untouched(
    client, admin_token: str, scheme_id, monkeypatch
):
    """A failed mutation neither invalidates the cache nor persists changes."""
    invalidate_schemes = AsyncMock(return_value=1)
    monkeypatch.setattr("app.api.v1.admin.invalidate_schemes", invalidate_schemes)
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = f"/api/v1/admin/schemes/{scheme_id}"

    sentinel = len(client.get(f"{base}/rules", headers=headers).json())
    r = client.post(
        f"{base}/rules",
        headers=headers,
        json={
            "group_id": str(uuid.uuid4()),  # unknown group -> 404, no side effects
            "parameter_name": "age",
            "operator": ">=",
            "required_value": "18",
        },
    )
    assert r.status_code == 404
    assert len(client.get(f"{base}/rules", headers=headers).json()) == sentinel
    invalidate_schemes.assert_not_awaited()


# ----------------------------------------------------------------------
# Engine compatibility end-to-end: the next evaluation sees the updated rule
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_next_eligibility_evaluation_sees_administered_rule(db: AsyncSession):
    """The full chain: admin-created rule -> committed graph -> the same
    scheme loader the eligibility API uses -> deterministic engine ->
    a mandatory outcome that flips exactly when the admin edits the rule."""
    service = RuleAdminService(db)
    scheme = _mk_scheme(db)  # ACTIVE — evaluation only considers active schemes
    await db.flush()
    group = await service.create_group(scheme.scheme_id, group_name="Age Gate")
    rule = await service.create_rule(
        scheme.scheme_id,
        group_id=group.group_id,
        parameter_name="age",
        operator=">=",
        required_value="18",
    )
    await db.flush()

    citizen = CitizenMaster(
        full_name="Eval Probe",
        citizen_type="STUDENT",
        date_of_birth=date(2010, 1, 1),  # 16 years old
    )
    db.add(citizen)
    await db.flush()
    citizen_id = citizen.citizen_id
    scheme_id = scheme.scheme_id

    # Commit: the repository/other sessions must see the graph like the API.
    await db.commit()

    async def evaluate():
        async with _TestSession() as s:
            loaded = (
                await s.execute(
                    select(SchemeMaster)
                    .where(SchemeMaster.scheme_id == scheme_id)
                    .options(
                        selectinload(SchemeMaster.rule_groups).selectinload(
                            SchemeRuleGroup.rules
                        )
                    )
                )
            ).scalar_one()
            citizen_loaded = await CitizenRepository(s).get_full_profile(citizen_id)
            result, details, _ = EligibilityEngine().evaluate_scheme(
                citizen_loaded, loaded
            )
            return result, details

    try:
        result_first, details_first = await evaluate()
        assert result_first is False  # 16 < 18 — mandatory gate fails
        assert details_first["overall_result"] is False

        # Admin edit: lower the age gate to 10 (service pattern, flush+commit).
        async with _TestSession() as s:
            await RuleAdminService(s).update_rule(
                scheme_id, rule.rule_id, required_value="10"
            )
            await s.commit()

        result_second, details_second = await evaluate()
        assert result_second is True  # the very next evaluation sees the NEW rule
        assert details_second["groups"][0]["group_passed"] is True

        # A second failing group under AND blocks eligibility again.
        async with _TestSession() as s:
            impossible = await RuleAdminService(s).create_group(
                scheme_id, group_name="Impossible", intra_group_operator="AND"
            )
            s.add(
                SchemeEligibilityRule(
                    scheme_id=scheme_id,
                    group_id=impossible.group_id,
                    parameter_name="age",
                    operator=">=",
                    required_value="99",
                )
            )
            await s.commit()

        result_and, _ = await evaluate()
        assert result_and is False  # AND: the new failing group blocks eligibility

        # Scheme operator OR -> passing the age gate is sufficient again.
        async with _TestSession() as s:
            await RuleAdminService(s).set_group_combining_operator(scheme_id, "OR")
            await s.commit()
        result_or, _ = await evaluate()
        assert result_or is True
    finally:
        await _delete_scheme_full(scheme_id)
        async with _TestSession() as s:
            await s.execute(
                delete(CitizenMaster).where(CitizenMaster.citizen_id == citizen_id)
            )
            await s.commit()
