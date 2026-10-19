"""
Admin scheme management backend tests.

Covers the SchemeAdminService and the /api/v1/admin/schemes endpoints:
  - authorization: no token -> 401 on every mutation; authenticated
    non-admin -> 403 (require_admin dependency)
  - create / update / archive / restore / delete over HTTP
  - server-side validation failures (vocabularies, URLs, dates, name)
  - referenced-scheme deletion protection (assessments / source documents)
  - cache invalidation: an archived scheme disappears from the public list

SAFETY: service-level tests run inside a rolled-back transaction. The HTTP
tests create real rows and delete them in finally blocks, so seeded data
and other test modules are unaffected. No seeded scheme is ever modified.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import delete
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.auth import UserAccount, UserSession, UserRole
from app.models.assessment import EligibilityAssessment
from app.models.citizen import CitizenMaster
from app.models.scheme import SchemeMaster
from app.models.scheme_source import SchemeSource, SchemeSourceDocument
from app.services.scheme_admin_service import (
    APPLICATION_WINDOW_TYPES,
    SCHEME_CATEGORIES,
    SCHEME_PERSONAS,
    SCHEME_SOURCE_TYPES,
    RULE_GROUP_OPERATORS,
    SchemeAdminError,
    SchemeAdminService,
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


# ----------------------------------------------------------------------
# Vocabulary sanity (frozen contract used by the frontend later)
# ----------------------------------------------------------------------


def test_vocabularies_are_frozen():
    assert SCHEME_CATEGORIES == (
        "AGRICULTURE",
        "EDUCATION",
        "HEALTHCARE",
        "HOUSING",
        "PENSION",
        "ENERGY",
        "EMPLOYMENT",
    )
    assert SCHEME_PERSONAS == ("FARMER", "STUDENT", "SENIOR", "GENERAL")
    assert SCHEME_SOURCE_TYPES[0] == "MANUAL_SEED"
    assert set(APPLICATION_WINDOW_TYPES) == {
        "FRESH_APPLICATION",
        "RENEWAL",
        "BOTH",
        "CONTINUOUS",
        "WINDOW_BASED",
    }
    assert set(RULE_GROUP_OPERATORS) == {"AND", "OR"}


# ----------------------------------------------------------------------
# Service-level CRUD + validation (rolled back)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_scheme_defaults(db: AsyncSession):
    service = SchemeAdminService(db)
    scheme = await service.create(scheme_name="  Test Scheme Admin CRUD  ")
    await db.flush()

    assert scheme.scheme_name == "Test Scheme Admin CRUD"  # stripped
    assert scheme.status == "ACTIVE"
    assert scheme.group_combining_operator == "AND"
    assert scheme.scheme_version == 1
    # No verification/provenance claim is fabricated on create.
    assert scheme.last_verified_at is None
    assert scheme.source_type == "MANUAL_SEED"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("scheme_name", ""),  # empty
        ("scheme_name", None),  # required
        ("scheme_name", "x" * 300),  # > 255
        ("scheme_category", "GARDENING"),
        ("target_persona", "ALIEN"),
        ("status", "EXPIRED"),  # derived state, admins may not set it
        ("status", "DELETED"),
        ("group_combining_operator", "XOR"),
        ("official_source_url", "ftp://example.gov.in/scheme"),
        ("official_source_url", "not-a-url"),
        ("application_url", "javascript:alert(1)"),
        ("source_type", "GUESS"),
        ("application_window_type", "SOMETIMES"),
    ],
)
async def test_create_validation_rejects(db: AsyncSession, field, value):
    service = SchemeAdminService(db)
    base: dict = {"scheme_name": "Validation Probe"}
    base[field] = value  # for scheme_name probes this replaces the name itself
    with pytest.raises(SchemeAdminError) as exc:
        await service.create(**base)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_create_rejects_end_before_start(db: AsyncSession):
    service = SchemeAdminService(db)
    with pytest.raises(SchemeAdminError) as exc:
        await service.create(
            scheme_name="Window Probe",
            start_date=date(2030, 1, 1),
            end_date=date(2029, 1, 1),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_validates_against_existing_dates(db: AsyncSession):
    service = SchemeAdminService(db)
    scheme = await service.create(
        scheme_name="Date Pair Probe", end_date=date(2030, 1, 1)
    )
    await db.flush()

    # New start_date is after the scheme's existing end_date -> rejected.
    with pytest.raises(SchemeAdminError) as exc:
        await service.update(scheme.scheme_id, start_date=date(2031, 1, 1))
    assert exc.value.status_code == 400

    # Consistent pair passes and stamps last_updated_at.
    updated = await service.update(
        scheme.scheme_id,
        start_date=date(2029, 1, 1),
        scheme_name="Date Pair Probe v2",
    )
    assert updated.scheme_name == "Date Pair Probe v2"
    assert updated.last_updated_at is not None


@pytest.mark.asyncio
async def test_update_rejects_unknown_scheme(db: AsyncSession):
    service = SchemeAdminService(db)
    with pytest.raises(SchemeAdminError) as exc:
        await service.update(uuid.uuid4(), description="nope")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_archive_and_restore_idempotent(db: AsyncSession):
    service = SchemeAdminService(db)
    scheme = await service.create(scheme_name="Archive Probe")
    await db.flush()

    assert (await service.archive(scheme.scheme_id)).status == "INACTIVE"
    assert (await service.archive(scheme.scheme_id)).status == "INACTIVE"
    assert (await service.restore(scheme.scheme_id)).status == "ACTIVE"


@pytest.mark.asyncio
async def test_delete_unreferenced_succeeds(db: AsyncSession):
    service = SchemeAdminService(db)
    scheme = await service.create(scheme_name="Delete Probe")
    await db.flush()
    await service.delete(scheme.scheme_id)
    with pytest.raises(SchemeAdminError) as exc:
        await service.get(scheme.scheme_id)
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_create_duplicate_scheme_rejected(db: AsyncSession):
    service = SchemeAdminService(db)
    unique_name = f"Unique Scheme {uuid.uuid4().hex[:8]}"
    scheme1 = await service.create(scheme_name=unique_name)
    await db.flush()
    assert scheme1.scheme_name == unique_name

    with pytest.raises(SchemeAdminError) as exc:
        await service.create(scheme_name=unique_name)
    assert exc.value.status_code == 409
    assert f"A scheme named '{unique_name}' already exists" in exc.value.detail


@pytest.mark.asyncio
async def test_create_duplicate_case_and_whitespace_rejected(db: AsyncSession):
    service = SchemeAdminService(db)
    base_name = f"Case Whitespace Probe {uuid.uuid4().hex[:8]}"
    scheme = await service.create(scheme_name=base_name)
    await db.flush()
    assert scheme.scheme_name == base_name

    # Different casing and surrounding whitespace
    variations = [
        f"   {base_name.upper()}   ",
        f"  {base_name.lower()}  ",
        base_name.upper(),
        base_name.lower(),
    ]
    for variant in variations:
        with pytest.raises(SchemeAdminError) as exc:
            await service.create(scheme_name=variant)
        assert exc.value.status_code == 409
        assert "already exists" in exc.value.detail


@pytest.mark.asyncio
async def test_duplicate_rejection_matches_stored_scheme_with_surrounding_whitespace(
    db: AsyncSession,
):
    """If an existing database row has untrimmed whitespace, duplicate checks still detect it."""
    service = SchemeAdminService(db)
    suffix = uuid.uuid4().hex[:8]
    padded_raw_name = f"   Legacy Padded Scheme {suffix}   "
    clean_name = f"Legacy Padded Scheme {suffix}"

    # Insert directly into DB bypassing service._require_name to simulate pre-existing un-trimmed record
    legacy_scheme = SchemeMaster(
        scheme_name=padded_raw_name,
        status="ACTIVE",
        group_combining_operator="AND",
        scheme_version=1,
    )
    db.add(legacy_scheme)
    await db.flush()

    # Attempt to create with clean/trimmed name
    with pytest.raises(SchemeAdminError) as exc:
        await service.create(scheme_name=clean_name)
    assert exc.value.status_code == 409
    assert f"A scheme named '{clean_name}' already exists" in exc.value.detail

    # Attempt to create with lowercase variation
    with pytest.raises(SchemeAdminError) as exc:
        await service.create(scheme_name=clean_name.lower())
    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail

    # Attempt to rename another scheme to this name
    other_scheme = await service.create(scheme_name=f"Other Scheme {suffix}")
    await db.flush()
    with pytest.raises(SchemeAdminError) as exc:
        await service.update(other_scheme.scheme_id, scheme_name=clean_name)
    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail


@pytest.mark.asyncio
async def test_update_rename_to_existing_scheme_rejected(db: AsyncSession):
    service = SchemeAdminService(db)
    suffix = uuid.uuid4().hex[:8]
    scheme1 = await service.create(scheme_name=f"First Scheme {suffix}")
    scheme2 = await service.create(scheme_name=f"Second Scheme {suffix}")
    await db.flush()

    # Renaming scheme2 to scheme1's name (exact)
    with pytest.raises(SchemeAdminError) as exc:
        await service.update(scheme2.scheme_id, scheme_name=f"First Scheme {suffix}")
    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail

    # Renaming scheme2 to scheme1's name (case and whitespace variation)
    with pytest.raises(SchemeAdminError) as exc:
        await service.update(scheme2.scheme_id, scheme_name=f"  FIRST SCHEME {suffix}  ")
    assert exc.value.status_code == 409
    assert "already exists" in exc.value.detail


@pytest.mark.asyncio
async def test_update_other_fields_preserves_name(db: AsyncSession):
    service = SchemeAdminService(db)
    original_name = f"Preserve Name Probe {uuid.uuid4().hex[:8]}"
    scheme = await service.create(scheme_name=original_name, description="initial")
    await db.flush()

    updated = await service.update(scheme.scheme_id, description="updated description")
    assert updated.scheme_name == original_name
    assert updated.description == "updated description"


@pytest.mark.asyncio
async def test_update_retains_own_name_succeeds(db: AsyncSession):
    service = SchemeAdminService(db)
    original_name = f"Self Retain Probe {uuid.uuid4().hex[:8]}"
    scheme = await service.create(scheme_name=original_name)
    await db.flush()

    # Exact name update
    updated = await service.update(
        scheme.scheme_id, scheme_name=original_name, description="same name edit"
    )
    assert updated.scheme_name == original_name

    # Whitespace-padded own name update
    updated_ws = await service.update(
        scheme.scheme_id, scheme_name=f"  {original_name}  "
    )
    assert updated_ws.scheme_name == original_name


@pytest.mark.asyncio
async def test_duplicate_check_handles_db_error(db: AsyncSession, monkeypatch):
    service = SchemeAdminService(db)
    async def failing_execute(*args, **kwargs):
        raise SQLAlchemyError("Simulated query execution error")
    monkeypatch.setattr(db, "execute", failing_execute)

    with pytest.raises(SchemeAdminError) as exc:
        await service.create(scheme_name="Error Probe")
    assert exc.value.status_code == 500
    assert "Database error" in exc.value.detail


# ----------------------------------------------------------------------
# HTTP layer (real rows, cleaned up in finally)
# ----------------------------------------------------------------------


def _run(coro):
    return asyncio.run(coro)


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

    email = f"scheme.admin.test.{uuid.uuid4().hex[:8]}@example.com"
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


def _mk_scheme_payload(name_suffix: str) -> dict:
    return {
        "scheme_name": f"Admin Scheme Test {name_suffix}",
        "scheme_category": "EDUCATION",
        "description": "temporary admin test scheme",
        "status": "ACTIVE",
        "start_date": "2026-01-01",
        "end_date": "2030-01-01",
        "target_persona": "STUDENT",
        "application_url": "https://test-scheme.example.gov.in/apply",
    }


def test_admin_endpoints_require_authentication(client):
    """No token -> 401 on every admin scheme route."""
    for method, path, body in [
        ("get", "/api/v1/admin/schemes", None),
        ("get", f"/api/v1/admin/schemes/{uuid.uuid4()}", None),
        ("post", "/api/v1/admin/schemes", _mk_scheme_payload("anon")),
        ("patch", f"/api/v1/admin/schemes/{uuid.uuid4()}", {"description": "x"}),
        ("post", f"/api/v1/admin/schemes/{uuid.uuid4()}/archive", None),
        ("post", f"/api/v1/admin/schemes/{uuid.uuid4()}/restore", None),
        ("delete", f"/api/v1/admin/schemes/{uuid.uuid4()}", None),
    ]:
        if body is None:
            response = getattr(client, method)(path)
        else:
            response = getattr(client, method)(path, json=body)
        assert response.status_code == 401, (method, path, response.status_code)


def test_admin_endpoints_reject_non_admin(client, non_admin_token: str):
    """Authenticated non-admin -> 403 on every admin scheme route."""
    headers = {"Authorization": f"Bearer {non_admin_token}"}
    for method, path, body in [
        ("get", "/api/v1/admin/schemes", None),
        ("post", "/api/v1/admin/schemes", _mk_scheme_payload("nonadmin")),
        ("patch", f"/api/v1/admin/schemes/{uuid.uuid4()}", {"description": "x"}),
        ("post", f"/api/v1/admin/schemes/{uuid.uuid4()}/archive", None),
        ("post", f"/api/v1/admin/schemes/{uuid.uuid4()}/restore", None),
        ("delete", f"/api/v1/admin/schemes/{uuid.uuid4()}", None),
    ]:
        if body is None:
            response = getattr(client, method)(path, headers=headers)
        else:
            response = getattr(client, method)(path, headers=headers, json=body)
        assert response.status_code == 403, (method, path, response.status_code)


def test_scheme_crud_lifecycle_over_http(client, admin_token: str):
    """Create -> detail -> update -> archive -> restore -> delete."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = _mk_scheme_payload(uuid.uuid4().hex[:8])

    # --- create ---
    r = client.post("/api/v1/admin/schemes", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    created = r.json()
    scheme_id = created["scheme_id"]
    assert created["scheme_name"] == payload["scheme_name"]
    assert created["status"] == "ACTIVE"
    assert created["scheme_category"] == "EDUCATION"
    assert created["rule_count"] == 0

    try:
        # --- detail (fresh, includes full master fields) ---
        r = client.get(f"/api/v1/admin/schemes/{scheme_id}", headers=headers)
        assert r.status_code == 200, r.text
        detail = r.json()
        assert detail["scheme_id"] == scheme_id
        assert detail["source_type"] == "MANUAL_SEED"
        assert detail["start_date"].startswith("2026-01-01")
        assert detail["rule_group_count"] == 0
        assert detail["document_count"] == 0

        # --- update ---
        r = client.patch(
            f"/api/v1/admin/schemes/{scheme_id}",
            headers=headers,
            json={
                "description": "updated description",
                "end_date": "2031-06-30",  # consistent new pair
                "official_scheme_identifier": "TEST-1",
            },
        )
        assert r.status_code == 200, r.text
        assert r.json()["description"] == "updated description"

        # Last verified is accepted only as a deliberate admin claim.
        r = client.patch(
            f"/api/v1/admin/schemes/{scheme_id}",
            headers=headers,
            json={"last_verified_at": "2026-10-01"},
        )
        assert r.status_code == 200, r.text

        # --- archive (cache invalidation visible on the public list) ---
        r = client.get("/api/v1/schemes/")  # warm the citizen cache
        assert r.status_code == 200
        r = client.post(
            f"/api/v1/admin/schemes/{scheme_id}/archive", headers=headers
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "INACTIVE"
        # Archived scheme must vanish from the citizen-facing catalogue
        # (proves invalidate_schemes ran after the status change).
        r = client.get("/api/v1/schemes/")
        assert all(s["scheme_id"] != scheme_id for s in r.json())

        # --- restore ---
        r = client.post(
            f"/api/v1/admin/schemes/{scheme_id}/restore", headers=headers
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "ACTIVE"

        # --- delete (unreferenced) ---
        r = client.delete(f"/api/v1/admin/schemes/{scheme_id}", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["deleted"] is True
        assert (
            client.get(f"/api/v1/admin/schemes/{scheme_id}", headers=headers).status_code
            == 404
        )
    finally:
        client.delete(f"/api/v1/admin/schemes/{scheme_id}", headers=headers)


def test_scheme_create_validation_failures(client, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = _mk_scheme_payload("val")

    bad_bodies = [
        {**base, "scheme_name": "   "},
        {**base, "scheme_category": "GARDENING"},
        {**base, "target_persona": "ALIEN"},
        {**base, "status": "EXPIRED"},
        {**base, "group_combining_operator": "XOR"},
        {**base, "official_source_url": "ftp://example.gov.in/x"},
        {**base, "application_url": "not-a-url"},
        {**base, "source_type": "GUESS"},
        {**base, "application_window_type": "SOMETIMES"},
        {**base, "start_date": "2031-01-01", "end_date": "2030-01-01"},
        {**base, "start_date": "not-a-date"},
    ]
    for i, body in enumerate(bad_bodies):
        r = client.post("/api/v1/admin/schemes", headers=headers, json=body)
        assert r.status_code == 400, (i, r.text)


def test_scheme_update_validation_failures_and_404(client, admin_token: str):
    headers = {"Authorization": f"Bearer {admin_token}"}
    payload = _mk_scheme_payload(uuid.uuid4().hex[:8])
    r = client.post("/api/v1/admin/schemes", headers=headers, json=payload)
    assert r.status_code == 201, r.text
    scheme_id = r.json()["scheme_id"]

    try:
        for body in [
            {"status": "EXPIRED"},
            {"status": "BOGUS"},
            {"scheme_category": "GARDENING"},
            {"end_date": "2025-01-01"},  # before the existing start_date
            {"official_source_url": "gopher://x"},
            {"last_verified_at": "october"},
        ]:
            r = client.patch(
                f"/api/v1/admin/schemes/{scheme_id}", headers=headers, json=body
            )
            assert r.status_code == 400, (body, r.text)

        r = client.get(f"/api/v1/admin/schemes/{scheme_id}", headers=headers)
        assert r.status_code == 200  # none of the failed PATCHes changed it

        # Unknown ids -> 404 for every mutation.
        unknown = uuid.uuid4()
        assert (
            client.patch(
                f"/api/v1/admin/schemes/{unknown}",
                headers=headers,
                json={"description": "x"},
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/admin/schemes/{unknown}/archive", headers=headers
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/admin/schemes/{unknown}/restore", headers=headers
            ).status_code
            == 404
        )
        assert (
            client.delete(f"/api/v1/admin/schemes/{unknown}", headers=headers).status_code
            == 404
        )
    finally:
        client.delete(f"/api/v1/admin/schemes/{scheme_id}", headers=headers)


def test_delete_protects_assessment_history(client, admin_token: str):
    """A scheme referenced by an assessment is never hard-deleted (409)."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/admin/schemes", headers=headers, json=_mk_scheme_payload(uuid.uuid4().hex[:8])
    )
    assert r.status_code == 201, r.text
    scheme_id = r.json()["scheme_id"]

    created_citizen: CitizenMaster | None = None
    try:
        # Commit real reference rows (can't be inside the rolled-back `db`).
        async def make_refs():
            nonlocal created_citizen
            async with _TestSession() as s:
                created_citizen = CitizenMaster(
                    full_name="Delete Protection Probe",
                    date_of_birth=date(1995, 1, 1),
                    citizen_type="STUDENT",
                )
                s.add(created_citizen)
                await s.flush()
                s.add(
                    EligibilityAssessment(
                        citizen_id=created_citizen.citizen_id,
                        scheme_id=scheme_id,
                        eligibility_result=True,
                    )
                )
                await s.commit()

        _run(make_refs())

        r = client.delete(f"/api/v1/admin/schemes/{scheme_id}", headers=headers)
        assert r.status_code == 409, r.text
        assert "assessment" in r.json()["detail"].lower()

        # Detail still available for admins (the scheme itself is untouched).
        r = client.get(f"/api/v1/admin/schemes/{scheme_id}", headers=headers)
        assert r.status_code == 200, r.text
    finally:
        async def cleanup():
            async with _TestSession() as s:
                await s.execute(
                    delete(EligibilityAssessment).where(
                        EligibilityAssessment.scheme_id == scheme_id
                    )
                )
                if created_citizen is not None:
                    await s.execute(
                        delete(CitizenMaster).where(
                            CitizenMaster.citizen_id == created_citizen.citizen_id
                        )
                    )
                await s.execute(
                    delete(SchemeMaster).where(SchemeMaster.scheme_id == scheme_id)
                )
                await s.commit()

        _run(cleanup())


def test_delete_protects_linked_source_documents(client, admin_token: str):
    """A scheme with linked source documents is never hard-deleted (409)."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.post(
        "/api/v1/admin/schemes", headers=headers, json=_mk_scheme_payload(uuid.uuid4().hex[:8])
    )
    assert r.status_code == 201, r.text
    scheme_id = r.json()["scheme_id"]
    source_id: str | None = None

    try:
        async def make_doc():
            nonlocal source_id
            async with _TestSession() as s:
                source = SchemeSource(
                    source_name=f"Delete Protection Src {uuid.uuid4().hex[:8]}",
                    source_type="GOVERNMENT_WEBSITE",
                    base_url="https://delete-probe.maharashtra.gov.in/",
                    status="ACTIVE",
                )
                s.add(source)
                await s.flush()
                source_id = str(source.source_id)
                s.add(
                    SchemeSourceDocument(
                        scheme_id=scheme_id,
                        source_id=source.source_id,
                        document_name="Guidelines",
                        document_url="https://delete-probe.maharashtra.gov.in/g.pdf",
                        document_type="GUIDELINE",
                        content_hash="0" * 64,
                    )
                )
                await s.commit()

        _run(make_doc())

        r = client.delete(f"/api/v1/admin/schemes/{scheme_id}", headers=headers)
        assert r.status_code == 409, r.text
        assert "source document" in r.json()["detail"].lower()
    finally:
        async def cleanup():
            async with _TestSession() as s:
                if source_id:
                    await s.execute(
                        delete(SchemeSource).where(SchemeSource.source_id == source_id)
                    )
                await s.execute(
                    delete(SchemeMaster).where(SchemeMaster.scheme_id == scheme_id)
                )
                await s.commit()

        _run(cleanup())


def test_admin_list_schemes_contract(client, admin_token: str):
    """The admin list shape stays stable for the existing frontend table."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/admin/schemes", headers=headers)
    assert r.status_code == 200, r.text
    rows = r.json()
    assert isinstance(rows, list) and len(rows) >= 1  # the 7 seeded schemes
    expected_keys = {
        "scheme_id",
        "scheme_name",
        "status",
        "scheme_category",
        "rule_count",
        "document_count",
    }
    assert expected_keys.issubset(rows[0].keys())


def test_duplicate_scheme_rejected_over_http(client, admin_token: str):
    """HTTP: duplicate creation returns 409, collision rename returns 409, self-rename succeeds."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    suffix1 = uuid.uuid4().hex[:8]
    suffix2 = uuid.uuid4().hex[:8]
    payload1 = _mk_scheme_payload(suffix1)
    payload2 = _mk_scheme_payload(suffix2)

    r1 = client.post("/api/v1/admin/schemes", headers=headers, json=payload1)
    assert r1.status_code == 201, r1.text
    id1 = r1.json()["scheme_id"]

    r2 = client.post("/api/v1/admin/schemes", headers=headers, json=payload2)
    assert r2.status_code == 201, r2.text
    id2 = r2.json()["scheme_id"]

    try:
        # Duplicate create with different casing and whitespace -> 409
        dup_payload = _mk_scheme_payload(f"dup_{suffix1}")
        dup_payload["scheme_name"] = f"  {payload1['scheme_name'].lower()}  "
        r_dup = client.post("/api/v1/admin/schemes", headers=headers, json=dup_payload)
        assert r_dup.status_code == 409, r_dup.text
        assert "already exists" in r_dup.json()["detail"]

        # Rename scheme2 to scheme1's name -> 409
        r_rename_collision = client.patch(
            f"/api/v1/admin/schemes/{id2}",
            headers=headers,
            json={"scheme_name": payload1["scheme_name"].upper()},
        )
        assert r_rename_collision.status_code == 409, r_rename_collision.text

        # Update scheme1 retaining its own name -> 200
        r_self_update = client.patch(
            f"/api/v1/admin/schemes/{id1}",
            headers=headers,
            json={"scheme_name": payload1["scheme_name"], "description": "self update"},
        )
        assert r_self_update.status_code == 200, r_self_update.text

        # Update scheme1 without changing name (only description) -> 200
        r_desc_update = client.patch(
            f"/api/v1/admin/schemes/{id1}",
            headers=headers,
            json={"description": "desc only"},
        )
        assert r_desc_update.status_code == 200, r_desc_update.text
    finally:
        client.delete(f"/api/v1/admin/schemes/{id1}", headers=headers)
        client.delete(f"/api/v1/admin/schemes/{id2}", headers=headers)
