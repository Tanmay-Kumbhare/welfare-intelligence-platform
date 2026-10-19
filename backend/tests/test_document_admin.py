"""
Admin required-document, source-association, and verification backend tests.

Covers the DocumentAdminService, SchemeSourceLinkService, the
SchemeAdminService.verify method, and the matching /api/v1/admin endpoints:
  - authorization: no token -> 401; authenticated non-admin -> 403;
    admin -> full CRUD (same require_admin dependency, no second mechanism)
  - required-document CRUD over HTTP + service level, incl. invalid scheme,
    invalid type (frozen vocabulary), duplicate requirement (409)
  - scheme <-> source-document association: link/unlink of the EXISTING
    SchemeSourceDocument.scheme_id column (no new table); unlink refused for
    a document belonging to another scheme
  - verification metadata: explicit verify endpoint sets last_verified_at +
    last_verified_at_ts; ordinary metadata edits never change them; no
    future dates; invalid formats rejected
  - cache: document/verify mutations invalidate the affected scheme's
    citizen-facing data, unrelated keyspaces untouched; source-document
    association (not citizen-catalogue data) deliberately invalidates nothing
  - referential safety: no persisted record references a required-document
    row (assessment evidence is a JSONB snapshot) so hard delete is safe;
    unlinked source documents keep their snapshots + provenance

SAFETY: service-level tests run inside a rolled-back transaction. The HTTP
tests create real rows and delete them in finally/teardown; no seeded
scheme, citizen, or source is ever modified.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date, timedelta
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.auth import UserAccount, UserSession, UserRole
from app.models.scheme import SchemeDocumentMaster, SchemeMaster
from app.models.scheme_source import (
    SchemeIngestionRun,
    SchemeSource,
    SchemeSourceContent,
    SchemeSourceDocument,
)
from app.services.document_admin_service import (
    DocumentAdminError,
    DocumentAdminService,
    REQUIRED_DOCUMENT_TYPES,
)
from app.services.scheme_admin_service import SchemeAdminError, SchemeAdminService
from app.services.scheme_source_link_service import (
    SchemeSourceLinkError,
    SchemeSourceLinkService,
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
# Vocabulary sanity (the frozen list — exactly what seeds/model overflowed)
# ----------------------------------------------------------------------


def test_required_document_types_frozen_vocabulary():
    assert set(REQUIRED_DOCUMENT_TYPES) == {
        "AADHAAR",
        "BANK_PASSBOOK",
        "BPL_CARD",
        "CASTE_CERTIFICATE",
        "DISABILITY_CERTIFICATE",
        "DOMICILE_CERTIFICATE",
        "INCOME_CERTIFICATE",
        "LAND_RECORD",
        "MARKSHEET",
        "PHOTOGRAPH",
        "RATION_CARD",
        "VOTER_ID",
    }


# ----------------------------------------------------------------------
# Service-level document CRUD (rolled back)
# ----------------------------------------------------------------------


def _mk_scheme(session) -> SchemeMaster:
    scheme = SchemeMaster(
        scheme_name=f"DocAdmin {uuid.uuid4().hex[:8]}",
        scheme_category="EDUCATION",
        status="ACTIVE",
    )
    session.add(scheme)
    return scheme


@pytest.mark.asyncio
async def test_document_crud_roundtrip(db):
    service = DocumentAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()

    created = await service.create_document(
        scheme.scheme_id,
        document_type="AADHAAR",
        mandatory_flag=False,
        description="Identity verification",
    )
    await db.flush()
    assert created.document_type == "AADHAAR"
    assert created.mandatory_flag is False
    assert created.description == "Identity verification"

    fetched = await service.get_document(scheme.scheme_id, created.document_id)
    assert fetched.document_id == created.document_id

    listed = await service.list_documents(scheme.scheme_id)
    assert [d.document_id for d in listed] == [created.document_id]

    updated = await service.update_document(
        scheme.scheme_id,
        created.document_id,
        mandatory_flag=True,
        description="Updated",
    )
    assert updated.mandatory_flag is True
    assert updated.document_type == "AADHAAR"  # untouched field preserved

    await service.delete_document(scheme.scheme_id, created.document_id)
    assert await service.list_documents(scheme.scheme_id) == []


@pytest.mark.asyncio
async def test_document_validation_rejects(db):
    service = DocumentAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()

    # invalid scheme
    with pytest.raises(DocumentAdminError) as exc:
        await service.create_document(
            uuid.uuid4(), document_type="AADHAAR"
        )
    assert exc.value.status_code == 404

    # invalid / missing document type (no invented categories)
    for bad_type in ("PASSPORT", "aadhaar", "", None):
        with pytest.raises(DocumentAdminError) as exc:
            await service.create_document(scheme.scheme_id, document_type=bad_type)
        assert exc.value.status_code == 400

    # non-boolean mandatory flag
    with pytest.raises(DocumentAdminError) as exc:
        await service.create_document(
            scheme.scheme_id, document_type="AADHAAR", mandatory_flag="yes"
        )
    assert exc.value.status_code == 400

    # over-long description
    with pytest.raises(DocumentAdminError) as exc:
        await service.create_document(
            scheme.scheme_id, document_type="AADHAAR", description="x" * 2001
        )
    assert exc.value.status_code == 400

    # duplicate requirement
    created = await service.create_document(
        scheme.scheme_id, document_type="MARKSHEET"
    )
    await db.flush()
    with pytest.raises(DocumentAdminError) as exc:
        await service.create_document(scheme.scheme_id, document_type="MARKSHEET")
    assert exc.value.status_code == 409

    # duplicate on update (renaming onto another row's type)
    other = await service.create_document(
        scheme.scheme_id, document_type="VOTER_ID"
    )
    await db.flush()
    with pytest.raises(DocumentAdminError) as exc:
        await service.update_document(
            scheme.scheme_id, other.document_id, document_type="MARKSHEET"
        )
    assert exc.value.status_code == 409

    # renaming onto ITSELF is fine (no self-conflict)
    ok = await service.update_document(
        scheme.scheme_id, created.document_id, document_type="MARKSHEET"
    )
    assert ok.document_type == "MARKSHEET"

    # unknown document / foreign scheme
    with pytest.raises(DocumentAdminError) as exc:
        await service.get_document(scheme.scheme_id, uuid.uuid4())
    assert exc.value.status_code == 404

    scheme_b = _mk_scheme(db)
    await db.flush()
    with pytest.raises(DocumentAdminError) as exc:
        await service.get_document(scheme_b.scheme_id, created.document_id)
    assert exc.value.status_code == 404


# ----------------------------------------------------------------------
# Service-level source-document association (rolled back)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_source_document_link_roundtrip(db):
    link_service = SchemeSourceLinkService(db)
    scheme_a = _mk_scheme(db)
    scheme_b = _mk_scheme(db)
    await db.flush()

    source = SchemeSource(
        source_name=f"Link Test Src {uuid.uuid4().hex[:8]}",
        source_type="GOVERNMENT_WEBSITE",
        base_url="https://linkprobe.maharashtra.gov.in/",
    )
    db.add(source)
    await db.flush()
    document = SchemeSourceDocument(
        source_id=source.source_id,
        document_name="Discovery page",
        document_url="https://linkprobe.maharashtra.gov.in/p.pdf",
        document_type="GUIDELINE",
        content_hash="2" * 64,
    )
    db.add(document)
    await db.flush()  # scheme_id stays NULL — the post-discovery state

    assert await link_service.list_for_scheme(scheme_a.scheme_id) == []

    linked = await link_service.link(scheme_a.scheme_id, document.source_document_id)
    assert linked.scheme_id == scheme_a.scheme_id
    assert (await link_service.list_for_scheme(scheme_a.scheme_id)) == [document]

    # idempotent re-link
    again = await link_service.link(scheme_a.scheme_id, document.source_document_id)
    assert again.scheme_id == scheme_a.scheme_id

    # unlink refuses a scheme the document does NOT belong to (404)
    with pytest.raises(SchemeSourceLinkError) as exc:
        await link_service.unlink(scheme_b.scheme_id, document.source_document_id)
    assert exc.value.status_code == 404
    assert document.scheme_id == scheme_a.scheme_id  # untouched

    unlinked = await link_service.unlink(scheme_a.scheme_id, document.source_document_id)
    assert unlinked.scheme_id is None
    assert await link_service.list_for_scheme(scheme_a.scheme_id) == []
    # The snapshot itself survives unlinking (only the association cleared)
    assert document.document_name == "Discovery page"

    # re-association with another scheme works
    moved = await link_service.link(scheme_b.scheme_id, document.source_document_id)
    assert moved.scheme_id == scheme_b.scheme_id

    # errors: unknown scheme / unknown document
    with pytest.raises(SchemeSourceLinkError) as exc:
        await link_service.link(uuid.uuid4(), document.source_document_id)
    assert exc.value.status_code == 404
    with pytest.raises(SchemeSourceLinkError) as exc:
        await link_service.link(scheme_a.scheme_id, uuid.uuid4())
    assert exc.value.status_code == 404


# ----------------------------------------------------------------------
# Service-level verification metadata (rolled back)
# ----------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_sets_both_fields_and_metadata_edit_does_not(db):
    service = SchemeAdminService(db)
    scheme = _mk_scheme(db)
    await db.flush()

    # Reflect the real convention (verify via the service on a fresh scheme):
    # initial state has no verification claim.
    assert scheme.last_verified_at is None
    assert scheme.last_verified_at_ts is None

    verified_on = date.today() - timedelta(days=7)
    verified = await service.verify(scheme.scheme_id, verified_on=verified_on)
    await db.flush()
    assert verified.last_verified_at == verified_on
    assert verified.last_verified_at_ts is not None
    verified_ts = verified.last_verified_at_ts

    # An ordinary metadata edit changes NEITHER verification field.
    await service.update(scheme.scheme_id, description="text edit only")
    await db.flush()
    refetched = await service.get(scheme.scheme_id)
    assert refetched.last_verified_at == verified_on
    assert refetched.last_verified_at_ts == verified_ts

    # Updating to a NEW explicit date moves it (admin-driven, not automatic).
    new_date = date.today() - timedelta(days=1)
    again = await service.verify(scheme.scheme_id, verified_on=new_date)
    assert again.last_verified_at == new_date
    assert again.last_verified_at_ts is not None

    # Future dates are refused — that would be a false claim.
    with pytest.raises(SchemeAdminError) as exc:
        await service.verify(
            scheme.scheme_id, verified_on=date.today() + timedelta(days=30)
        )
    assert exc.value.status_code == 400

    with pytest.raises(SchemeAdminError) as exc:
        await service.verify(uuid.uuid4(), verified_on=new_date)
    assert exc.value.status_code == 404


# ----------------------------------------------------------------------
# HTTP layer (real rows, cleaned up in finally/teardown)
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

    email = f"doc.admin.test.{uuid.uuid4().hex[:8]}@example.com"
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
                delete(SchemeSourceContent).where(
                    SchemeSourceContent.source_document_id.in_(
                        select(SchemeSourceDocument.source_document_id).where(
                            SchemeSourceDocument.source_id == source_id
                        )
                    )
                )
            )
            await s.execute(
                delete(SchemeIngestionRun).where(
                    SchemeIngestionRun.source_id == source_id
                )
            )
            await s.execute(
                delete(SchemeSource).where(SchemeSource.source_id == source_id)
            )
        await s.execute(
            delete(SchemeDocumentMaster).where(
                SchemeDocumentMaster.scheme_id == scheme_id
            )
        )
        await s.execute(
            delete(SchemeMaster).where(SchemeMaster.scheme_id == scheme_id)
        )
        await s.commit()


@pytest.fixture()
def scheme_id(client, admin_token: str):
    """Create a throwaway scheme through the admin API; clean on teardown."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    resp = client.post(
        "/api/v1/admin/schemes",
        headers=headers,
        json={
            "scheme_name": f"Doc Admin Test {uuid.uuid4().hex[:8]}",
            "scheme_category": "EDUCATION",
            "status": "ACTIVE",
        },
    )
    assert resp.status_code == 201, resp.text
    sid = resp.json()["scheme_id"]
    yield sid
    _run(_delete_scheme_full(sid))


def test_document_endpoints_require_authentication(client):
    sid = str(uuid.uuid4())
    did = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    routes = [
        ("get", f"/api/v1/admin/schemes/{sid}/documents", None),
        (
            "post",
            f"/api/v1/admin/schemes/{sid}/documents",
            {"document_type": "AADHAAR"},
        ),
        ("get", f"/api/v1/admin/schemes/{sid}/documents/{doc_id}", None),
        (
            "patch",
            f"/api/v1/admin/schemes/{sid}/documents/{doc_id}",
            {"mandatory_flag": False},
        ),
        ("delete", f"/api/v1/admin/schemes/{sid}/documents/{doc_id}", None),
        ("get", f"/api/v1/admin/schemes/{sid}/source-documents", None),
        ("put", f"/api/v1/admin/schemes/{sid}/source-documents/{did}", None),
        ("delete", f"/api/v1/admin/schemes/{sid}/source-documents/{did}", None),
        ("post", f"/api/v1/admin/schemes/{sid}/verify", {"verified_on": "2026-01-01"}),
    ]
    for method, path, body in routes:
        if body is None:
            response = getattr(client, method)(path)
        else:
            response = getattr(client, method)(path, json=body)
        assert response.status_code == 401, (method, path, response.status_code)


def test_document_endpoints_reject_non_admin(client, non_admin_token: str):
    headers = {"Authorization": f"Bearer {non_admin_token}"}
    sid = str(uuid.uuid4())
    did = str(uuid.uuid4())
    doc_id = str(uuid.uuid4())
    routes = [
        ("get", f"/api/v1/admin/schemes/{sid}/documents", None),
        (
            "post",
            f"/api/v1/admin/schemes/{sid}/documents",
            {"document_type": "AADHAAR"},
        ),
        (
            "patch",
            f"/api/v1/admin/schemes/{sid}/documents/{doc_id}",
            {"mandatory_flag": False},
        ),
        ("delete", f"/api/v1/admin/schemes/{sid}/documents/{doc_id}", None),
        ("get", f"/api/v1/admin/schemes/{sid}/source-documents", None),
        ("put", f"/api/v1/admin/schemes/{sid}/source-documents/{did}", None),
        ("delete", f"/api/v1/admin/schemes/{sid}/source-documents/{did}", None),
        ("post", f"/api/v1/admin/schemes/{sid}/verify", {"verified_on": "2026-01-01"}),
    ]
    for method, path, body in routes:
        if body is None:
            response = getattr(client, method)(path, headers=headers)
        else:
            response = getattr(client, method)(path, headers=headers, json=body)
        assert response.status_code == 403, (method, path, response.status_code)


def test_document_crud_lifecycle_over_http(client, admin_token: str, scheme_id):
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = f"/api/v1/admin/schemes/{scheme_id}"

    # create
    r = client.post(
        f"{base}/documents",
        headers=headers,
        json={"document_type": "AADHAAR", "mandatory_flag": True, "description": "ID"},
    )
    assert r.status_code == 201, r.text
    document = r.json()
    doc_id = document["document_id"]
    assert document["scheme_id"] == scheme_id
    assert document["document_type"] == "AADHAAR"

    # list + get
    r = client.get(f"{base}/documents", headers=headers)
    assert r.status_code == 200 and len(r.json()) == 1
    r = client.get(f"{base}/documents/{doc_id}", headers=headers)
    assert r.status_code == 200 and r.json()["mandatory_flag"] is True

    # patch (make optional, description edit)
    r = client.patch(
        f"{base}/documents/{doc_id}",
        headers=headers,
        json={"mandatory_flag": False, "description": "Optional now"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mandatory_flag"] is False

    # invalid type / unknown scheme / duplicate
    r = client.post(f"{base}/documents", headers=headers, json={"document_type": "PASSPORT"})
    assert r.status_code == 400
    r = client.post(
        f"/api/v1/admin/schemes/{uuid.uuid4()}/documents",
        headers=headers,
        json={"document_type": "BPL_CARD"},
    )
    assert r.status_code == 404
    r = client.post(f"{base}/documents", headers=headers, json={"document_type": "AADHAAR"})
    assert r.status_code == 409

    # delete + empty list afterwards
    r = client.delete(f"{base}/documents/{doc_id}", headers=headers)
    assert r.status_code == 200, r.text
    r = client.get(f"{base}/documents", headers=headers)
    assert r.json() == []
    r = client.delete(f"{base}/documents/{uuid.uuid4()}", headers=headers)
    assert r.status_code == 404


def test_source_document_link_lifecycle_over_http(client, admin_token: str, scheme_id):
    """Real rows: unlinked snapshot -> link -> list -> unlink -> re-link."""
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = f"/api/v1/admin/schemes/{scheme_id}"
    source_id = None
    doc_id = None

    async def make_document():
        nonlocal source_id, doc_id
        async with _TestSession() as s:
            source = SchemeSource(
                source_name=f"HTTP Link Test {uuid.uuid4().hex[:8]}",
                source_type="GOVERNMENT_WEBSITE",
                base_url="https://httplinkprobe.maharashtra.gov.in/",
            )
            s.add(source)
            await s.flush()
            doc = SchemeSourceDocument(
                source_id=source.source_id,
                document_name="HTTP discovery page",
                document_url="https://httplinkprobe.maharashtra.gov.in/p.pdf",
                document_type="GUIDELINE",
                content_hash="3" * 64,
            )
            s.add(doc)
            await s.commit()
            source_id = source.source_id
            doc_id = doc.source_document_id

    try:
        _run(make_document())

        # list starts empty
        r = client.get(f"{base}/source-documents", headers=headers)
        assert r.status_code == 200 and r.json() == []

        # link
        r = client.put(f"{base}/source-documents/{doc_id}", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["scheme_id"] == scheme_id

        # idempotent second link
        r = client.put(f"{base}/source-documents/{doc_id}", headers=headers)
        assert r.status_code == 200

        # listed, newest first
        r = client.get(f"{base}/source-documents", headers=headers)
        assert [d["source_document_id"] for d in r.json()] == [str(doc_id)]

        # unknown document / unknown scheme
        r = client.put(f"{base}/source-documents/{uuid.uuid4()}", headers=headers)
        assert r.status_code == 404
        r = client.put(
            f"/api/v1/admin/schemes/{uuid.uuid4()}/source-documents/{doc_id}",
            headers=headers,
        )
        assert r.status_code == 404

        # unlink + confirm the snapshot keeps its identity
        r = client.delete(f"{base}/source-documents/{doc_id}", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["scheme_id"] in (None, "None")
        ujson = r.json()
        assert ujson["document_name"] == "HTTP discovery page"
        r = client.get(f"{base}/source-documents", headers=headers)
        assert r.json() == []

        # unlink again -> refuses (not linked to this scheme)
        r = client.delete(f"{base}/source-documents/{doc_id}", headers=headers)
        assert r.status_code == 404
    finally:
        _run(_delete_scheme_full(scheme_id))
        async def cleanup_doc():
            async with _TestSession() as s:
                if doc_id:
                    await s.execute(
                        delete(SchemeSourceContent).where(
                            SchemeSourceContent.source_document_id == doc_id
                        )
                    )
                    await s.execute(
                        delete(SchemeSourceDocument).where(
                            SchemeSourceDocument.source_document_id == doc_id
                        )
                    )
                if source_id:
                    await s.execute(
                        delete(SchemeIngestionRun).where(
                            SchemeIngestionRun.source_id == source_id
                        )
                    )
                    await s.execute(
                        delete(SchemeSource).where(SchemeSource.source_id == source_id)
                    )
                await s.commit()
        _run(cleanup_doc())


def test_verify_over_http(client, admin_token: str, scheme_id):
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = f"/api/v1/admin/schemes/{scheme_id}"

    # no verification claim initially
    r = client.get(base, headers=headers)
    assert r.status_code == 200
    assert r.json()["last_verified_at"] is None

    # explicit verification
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    r = client.post(f"{base}/verify", headers=headers, json={"verified_on": yesterday})
    assert r.status_code == 200, r.text
    r = client.get(base, headers=headers)
    assert r.json()["last_verified_at"] == yesterday

    # an ordinary metadata edit does NOT falsely change verification state
    r = client.patch(base, headers=headers, json={"description": "metadata edit"})
    assert r.status_code == 200
    r = client.get(base, headers=headers)
    assert r.json()["last_verified_at"] == yesterday

    # invalid format
    r = client.post(f"{base}/verify", headers=headers, json={"verified_on": "01/02/2026"})
    assert r.status_code == 400
    # future date -> false claim, refused
    future = (date.today() + timedelta(days=30)).isoformat()
    r = client.post(f"{base}/verify", headers=headers, json={"verified_on": future})
    assert r.status_code == 400
    # still unchanged after refused attempts
    r = client.get(base, headers=headers)
    assert r.json()["last_verified_at"] == yesterday


def test_document_mutation_invalidates_scheme_cache(
    client, admin_token: str, scheme_id, monkeypatch
):
    invalidate_schemes = AsyncMock(return_value=1)
    monkeypatch.setattr("app.api.v1.admin.invalidate_schemes", invalidate_schemes)
    headers = {"Authorization": f"Bearer {admin_token}"}
    base = f"/api/v1/admin/schemes/{scheme_id}"

    r = client.post(
        f"{base}/documents", headers=headers, json={"document_type": "RATION_CARD"}
    )
    assert r.status_code == 201, r.text
    doc_id = r.json()["document_id"]
    invalidate_schemes.assert_awaited_once()

    r = client.patch(
        f"{base}/documents/{doc_id}", headers=headers, json={"mandatory_flag": False}
    )
    assert r.status_code == 200
    assert invalidate_schemes.await_count == 2

    r = client.delete(f"{base}/documents/{doc_id}", headers=headers)
    assert r.status_code == 200
    assert invalidate_schemes.await_count == 3

    today = date.today().isoformat()
    r = client.post(f"{base}/verify", headers=headers, json={"verified_on": today})
    assert r.status_code == 200, r.text
    assert invalidate_schemes.await_count == 4

    # FAILED mutation leaves cache + data untouched
    r = client.post(
        f"/api/v1/admin/schemes/{uuid.uuid4()}/documents",
        headers=headers,
        json={"document_type": "RATION_CARD"},
    )
    assert r.status_code == 404
    assert invalidate_schemes.await_count == 4


def test_source_document_link_does_not_invalidate_citizen_cache(
    client, admin_token: str, scheme_id, monkeypatch
):
    """Deliberate no-op: source-document associations are admin/provenance
    data, not part of the citizen scheme catalogue — no unnecessary
    invalidation of the schemes keyspace."""
    invalidate_schemes = AsyncMock(return_value=1)
    monkeypatch.setattr("app.api.v1.admin.invalidate_schemes", invalidate_schemes)
    headers = {"Authorization": f"Bearer {admin_token}"}
    source_id = None
    doc_id = None
    try:
        async def make_document():
            nonlocal source_id, doc_id
            async with _TestSession() as s:
                source = SchemeSource(
                    source_name=f"Nocache Link Test {uuid.uuid4().hex[:8]}",
                    source_type="GOVERNMENT_WEBSITE",
                    base_url="https://nocachelinkprobe.maharashtra.gov.in/",
                )
                s.add(source)
                await s.flush()
                doc = SchemeSourceDocument(
                    source_id=source.source_id,
                    document_name="Nocache p.pdf",
                    document_url="https://nocachelinkprobe.maharashtra.gov.in/p.pdf",
                    document_type="GUIDELINE",
                    content_hash="4" * 64,
                )
                s.add(doc)
                await s.commit()
                source_id = source.source_id
                doc_id = doc.source_document_id

        _run(make_document())

        r = client.put(
            f"/api/v1/admin/schemes/{scheme_id}/source-documents/{doc_id}",
            headers=headers,
        )
        assert r.status_code == 200, r.text

        r = client.delete(
            f"/api/v1/admin/schemes/{scheme_id}/source-documents/{doc_id}",
            headers=headers,
        )
        assert r.status_code == 200
        invalidate_schemes.assert_not_awaited()
    finally:
        _run(_delete_scheme_full(scheme_id))
        async def cleanup_doc():
            async with _TestSession() as s:
                if doc_id:
                    await s.execute(
                        delete(SchemeSourceContent).where(
                            SchemeSourceContent.source_document_id == doc_id
                        )
                    )
                    await s.execute(
                        delete(SchemeSourceDocument).where(
                            SchemeSourceDocument.source_document_id == doc_id
                        )
                    )
                if source_id:
                    await s.execute(
                        delete(SchemeIngestionRun).where(
                            SchemeIngestionRun.source_id == source_id
                        )
                    )
                    await s.execute(
                        delete(SchemeSource).where(SchemeSource.source_id == source_id)
                    )
                await s.commit()
        _run(cleanup_doc())
