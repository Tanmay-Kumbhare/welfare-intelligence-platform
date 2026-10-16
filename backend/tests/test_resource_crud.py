"""
Phase 3B resource model + CRUD tests (Task 1G).

Covers:
  - Task 1E URL normalization rules (unit)
  - resource create / get / list / update via the service (rolled back)
  - validation: invalid source, duplicate normalized URL, invalid type/status
  - HTTP layer: admin authorization (401 without token, 201 with admin token)
    and proof that existing Source CRUD is unaffected

SAFETY: service-level tests run inside a rolled-back transaction. The HTTP
tests create real rows (admin user + source + resource) and delete them in a
finally block, so the seeded data and other test modules are unaffected.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.auth import UserAccount, UserRole, UserSession
from app.models.scheme_source import (
    RESOURCE_TYPES,
    SchemeSource,
    SchemeSourceResource,
)
from app.services.resource_service import (
    ResourceError,
    ResourceService,
    normalize_resource_url,
)

# NullPool: fresh connection per session, avoids pytest-asyncio's
# function-scoped event loops reusing pooled connections ("Event loop is
# closed").
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


@pytest_asyncio.fixture
async def source(db: AsyncSession) -> SchemeSource:
    obj = SchemeSource(
        source_name=f"Resource Test Source {uuid.uuid4().hex[:8]}",
        source_type="GOVERNMENT_WEBSITE",
        base_url="https://example.maharashtra.gov.in/",
        authority_name="Government of Maharashtra",
        status="ACTIVE",
    )
    db.add(obj)
    await db.flush()
    return obj


# ----------------------------------------------------------------------
# Unit: Task 1E normalization rules
# ----------------------------------------------------------------------


class TestNormalizeResourceUrl:
    def test_lowercase_scheme_and_host(self):
        assert (
            normalize_resource_url("HTTPS://Krishi.Maharashtra.GOV.in/Schemes")
            == "https://krishi.maharashtra.gov.in/Schemes"
        )

    def test_default_port_removed(self):
        assert (
            normalize_resource_url("https://example.gov.in:443/a")
            == "https://example.gov.in/a"
        )
        assert (
            normalize_resource_url("http://example.gov.in:80/a")
            == "http://example.gov.in/a"
        )

    def test_fragment_removed(self):
        assert (
            normalize_resource_url("https://example.gov.in/schemes#section-2")
            == "https://example.gov.in/schemes"
        )

    def test_empty_path_collapsed(self):
        assert normalize_resource_url("https://example.gov.in") == "https://example.gov.in/"
        assert normalize_resource_url("https://example.gov.in/") == "https://example.gov.in/"

    def test_trailing_slash_collapsed(self):
        assert (
            normalize_resource_url("https://example.gov.in/schemes/")
            == "https://example.gov.in/schemes"
        )

    def test_mahadbt_session_token_removed(self):
        assert (
            normalize_resource_url(
                "https://mahadbt.maharashtra.gov.in/Farmer/SchemeData/SchemeData?str=E9DDFA703C38E51AA76CB4993576E544"
            )
            == "https://mahadbt.maharashtra.gov.in/Farmer/SchemeData/SchemeData"
        )

    def test_meaningful_query_preserved(self):
        assert (
            normalize_resource_url("https://example.gov.in/list?page=2&str=abc")
            == "https://example.gov.in/list?page=2"
        )

    def test_non_http_rejected(self):
        with pytest.raises(ResourceError):
            normalize_resource_url("ftp://example.gov.in/file")

    def test_relative_rejected(self):
        with pytest.raises(ResourceError):
            normalize_resource_url("/schemes")

    def test_deterministic_identity(self):
        a = normalize_resource_url("HTTPS://Example.gov.in:443/schemes/#top")
        b = normalize_resource_url("https://example.gov.in/schemes")
        assert a == b


# ----------------------------------------------------------------------
# Service-level CRUD (rolled back)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_and_get_resource(db: AsyncSession, source: SchemeSource):
    service = ResourceService(db)
    created = await service.create(
        source.source_id,
        resource_name="Scheme catalogue",
        resource_url="https://example.maharashtra.gov.in/schemes/",
        resource_type="CATALOGUE_PAGE",
    )
    await db.flush()

    fetched = await service.get(created.resource_id)
    assert fetched.resource_name == "Scheme catalogue"
    assert fetched.resource_url == "https://example.maharashtra.gov.in/schemes"
    assert fetched.resource_type == "CATALOGUE_PAGE"
    assert fetched.status == "ACTIVE"
    assert fetched.fetch_method == "HTTP_GET"
    assert fetched.is_application_portal is False
    assert fetched.discovered_at is not None


@pytest.mark.asyncio
async def test_list_resources_filtered_by_source(
    db: AsyncSession, source: SchemeSource
):
    service = ResourceService(db)
    await service.create(
        source.source_id,
        resource_name="Catalogue",
        resource_url="https://example.maharashtra.gov.in/schemes",
        resource_type="CATALOGUE_PAGE",
    )
    await service.create(
        source.source_id,
        resource_name="Guidelines PDF",
        resource_url="https://example.maharashtra.gov.in/docs/guidelines.pdf",
        resource_type="PDF",
    )
    await db.flush()

    all_resources = await service.list()
    assert {r.resource_type for r in all_resources} >= {"CATALOGUE_PAGE", "PDF"}

    scoped = await service.list(source.source_id)
    assert len(scoped) == 2


@pytest.mark.asyncio
async def test_update_resource_metadata_and_retire(
    db: AsyncSession, source: SchemeSource
):
    service = ResourceService(db)
    created = await service.create(
        source.source_id,
        resource_name="Old name",
        resource_url="https://example.maharashtra.gov.in/schemes",
        resource_type="SCHEME_PAGE",
    )
    await db.flush()

    updated = await service.update(
        created.resource_id, resource_name="New name", status="RETIRED"
    )
    assert updated.resource_name == "New name"
    assert updated.status == "RETIRED"


@pytest.mark.asyncio
async def test_invalid_source_id_rejected(db: AsyncSession):
    service = ResourceService(db)
    with pytest.raises(ResourceError) as exc:
        await service.create(
            uuid.uuid4(),
            resource_name="Orphan",
            resource_url="https://example.gov.in/x",
            resource_type="OTHER",
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_duplicate_normalized_url_rejected(
    db: AsyncSession, source: SchemeSource
):
    service = ResourceService(db)
    await service.create(
        source.source_id,
        resource_name="First",
        resource_url="https://example.maharashtra.gov.in/schemes",
        resource_type="CATALOGUE_PAGE",
    )
    await db.flush()

    # Same logical URL with trailing slash + uppercase host -> still duplicate.
    with pytest.raises(ResourceError) as exc:
        await service.create(
            source.source_id,
            resource_name="Second",
            resource_url="HTTPS://Example.Maharashtra.GOV.in/schemes/",
            resource_type="SCHEME_PAGE",
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_url_update_normalizes_and_rechecks(
    db: AsyncSession, source: SchemeSource
):
    service = ResourceService(db)
    created = await service.create(
        source.source_id,
        resource_name="Movable",
        resource_url="https://example.maharashtra.gov.in/a",
        resource_type="DOCUMENT_ARCHIVE",
    )
    await db.flush()

    updated = await service.update(
        created.resource_id,
        resource_url="https://example.maharashtra.gov.in/b/#top",
    )
    assert updated.resource_url == "https://example.maharashtra.gov.in/b"
    assert updated.last_checked_at is not None


@pytest.mark.asyncio
async def test_invalid_resource_type_rejected(
    db: AsyncSession, source: SchemeSource
):
    service = ResourceService(db)
    with pytest.raises(ResourceError) as exc:
        await service.create(
            source.source_id,
            resource_name="Bad type",
            resource_url="https://example.maharashtra.gov.in/x",
            resource_type="NOT_A_TYPE",
        )
    assert exc.value.status_code == 400
    assert "resource_type" in exc.value.detail


@pytest.mark.asyncio
async def test_invalid_status_rejected(db: AsyncSession, source: SchemeSource):
    service = ResourceService(db)
    with pytest.raises(ResourceError) as exc:
        await service.create(
            source.source_id,
            resource_name="Bad status",
            resource_url="https://example.maharashtra.gov.in/y",
            resource_type="OTHER",
            status="DELETED",
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_resource_type_vocabulary_is_frozen():
    """The exposed vocabulary matches the frozen Task 1E set exactly."""
    assert RESOURCE_TYPES == (
        "CATALOGUE_PAGE",
        "SCHEME_PAGE",
        "PDF",
        "APPLICATION_PORTAL",
        "API_ENDPOINT",
        "DOCUMENT_ARCHIVE",
        "OTHER",
    )


# ----------------------------------------------------------------------
# HTTP layer: admin authorization + existing Source CRUD unaffected
# (real rows, cleaned up in finally)
# ----------------------------------------------------------------------


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token() -> str:
    """Create a throwaway ADMIN user + session; delete both afterwards."""
    from app.repositories.auth_repository import AuthRepository

    email = f"resource.crud.test.{uuid.uuid4().hex[:8]}@example.com"
    state: dict = {}

    async def make():
        async with _TestSession() as s:
            user = UserAccount(email=email, provider="LOCAL", password_hash="x")
            s.add(user)
            await s.flush()
            s.add(UserRole(user_id=user.user_id, role="ADMIN"))
            repo = AuthRepository(s)
            token = uuid.uuid4().hex + uuid.uuid4().hex
            await repo.create_session(user.user_id, token, ttl_hours=1)
            await s.commit()
            state["user_id"] = user.user_id
            state["token"] = token

    _run(make())
    yield state["token"]

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


def test_admin_authorization_required(client, admin_token: str):
    """No token -> 401. The admin dependency mechanism is reused unchanged."""
    assert client.get("/api/v1/admin/resources").status_code == 401
    assert (
        client.post(
            "/api/v1/admin/sources",
            json={
                "source_name": "Should Not Exist",
                "source_type": "GOVERNMENT_WEBSITE",
                "base_url": "https://no.example.gov.in",
            },
        ).status_code
        == 401
    )


def test_resource_crud_over_http(client, admin_token: str):
    """Full create/get/list/update cycle over HTTP with an admin session."""
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Create a throwaway source through the EXISTING source CRUD (contract check).
    r = client.post(
        "/api/v1/admin/sources",
        headers=headers,
        json={
            "source_name": f"Resource HTTP Test {uuid.uuid4().hex[:8]}",
            "source_type": "GOVERNMENT_WEBSITE",
            "base_url": "https://http-test.maharashtra.gov.in/",
            "authority_name": "Government of Maharashtra",
            "status": "ACTIVE",
        },
    )
    assert r.status_code == 200, r.text
    source_id = r.json()["source_id"]

    try:
        # Create a resource under it.
        r = client.post(
            f"/api/v1/admin/sources/{source_id}/resources",
            headers=headers,
            json={
                "resource_name": "Catalogue",
                "resource_url": "https://HTTP-Test.maharashtra.gov.in/schemes/#top",
                "resource_type": "CATALOGUE_PAGE",
                "is_application_portal": False,
            },
        )
        assert r.status_code == 201, r.text
        body = r.json()
        resource_id = body["resource_id"]
        # Normalization applied before persistence.
        assert body["resource_url"] == "https://http-test.maharashtra.gov.in/schemes"

        # Get by ID.
        r = client.get(f"/api/v1/admin/resources/{resource_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["resource_name"] == "Catalogue"

        # List (scoped).
        r = client.get(
            f"/api/v1/admin/resources?source_id={source_id}", headers=headers
        )
        assert r.status_code == 200
        assert [x["resource_id"] for x in r.json()] == [resource_id]

        # Duplicate normalized URL -> 409.
        r = client.post(
            f"/api/v1/admin/sources/{source_id}/resources",
            headers=headers,
            json={
                "resource_name": "Dup",
                "resource_url": "https://http-test.maharashtra.gov.in/schemes/",
                "resource_type": "SCHEME_PAGE",
            },
        )
        assert r.status_code == 409

        # Invalid type -> 400.
        r = client.post(
            f"/api/v1/admin/sources/{source_id}/resources",
            headers=headers,
            json={
                "resource_name": "Bad",
                "resource_url": "https://http-test.maharashtra.gov.in/z",
                "resource_type": "BOGUS",
            },
        )
        assert r.status_code == 400

        # Update + retire.
        r = client.patch(
            f"/api/v1/admin/resources/{resource_id}",
            headers=headers,
            json={"resource_name": "Renamed", "status": "RETIRED"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "RETIRED"

        # Unknown resource -> 404; unknown source -> 404.
        assert (
            client.get(
                f"/api/v1/admin/resources/{uuid.uuid4()}", headers=headers
            ).status_code
            == 404
        )
        r = client.get(
            f"/api/v1/admin/resources?source_id={uuid.uuid4()}", headers=headers
        )
        assert r.status_code == 404
    finally:
        client.delete(f"/api/v1/admin/sources/{source_id}", headers=headers)


def test_existing_source_crud_unchanged(client, admin_token: str):
    """The pre-existing source CRUD contract behaves exactly as before."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    r = client.get("/api/v1/admin/sources", headers=headers)
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and len(rows) >= 4
    expected_keys = {
        "source_id",
        "source_name",
        "source_type",
        "base_url",
        "authority_name",
        "status",
        "created_at",
        "document_count",
        "last_run_status",
        "last_run_at",
    }
    assert expected_keys.issubset(rows[0].keys())
