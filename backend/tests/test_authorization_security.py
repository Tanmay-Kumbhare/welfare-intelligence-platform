"""
Regression tests for Phase 4 Task 1: Fix Broken Object-Level Authorization (BOLA/IDOR).

Covers:
1. Unauthenticated requests to citizen-scoped endpoints return HTTP 401 with WWW-Authenticate header.
2. Cross-citizen requests (User A attempting to access/mutate Citizen B) return HTTP 403 Forbidden.
3. Authorized requests (User A accessing/mutating own Citizen A) succeed with HTTP 200/201.
4. Administrators can access citizen profiles for administrative oversight.
5. Public endpoints (schemes catalogue, forms catalogue, initial citizen registration) remain accessible without authentication.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.main import app
from app.models.citizen import CitizenMaster
from app.services.auth_service import AuthService


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(autouse=True)
def disable_cache(monkeypatch):
    from app.services.cache_service import cache_service
    async def _ret_none(*args, **kwargs):
        return None
    monkeypatch.setattr(cache_service, "get_client", _ret_none)


async def _create_test_user_and_citizen(
    db: AsyncSession,
    *,
    prefix: str,
    role: str = "CITIZEN",
) -> tuple[dict, str]:
    """Helper to register a user, link a citizen profile, and return login credentials."""
    auth_service = AuthService(db)
    suffix = uuid.uuid4().hex[:8]
    # Replace digits with letters so name is purely alphabetic
    letters = suffix.translate(str.maketrans("0123456789", "abcdefghij"))
    email = f"{prefix}_{suffix}@example.com"
    password = "SecurePassword123!"

    citizen_data = {
        "full_name": f"Citizen {letters.capitalize()}",
        "date_of_birth": "1995-06-15",
        "gender": "FEMALE",
        "email_id": email,
        "citizen_type": "GENERAL",
        "demographic": {"disability_status": "NONE"},
        "financial": {"is_bpl_card_holder": False, "is_income_tax_payer": False, "annual_income": 350000},
        "location": {"state": "Maharashtra"},
    }

    user, citizen = await auth_service.register(
        email=email,
        password=password,
        citizen_data=citizen_data,
    )
    if role != "CITIZEN":
        await auth_service.users.add_role(user.user_id, role)

    _, token, _ = await auth_service.login(email, password)
    await db.flush()

    return {
        "user_id": user.user_id,
        "citizen_id": citizen.citizen_id,
        "email": email,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }, token


@pytest.mark.asyncio
async def test_unauthenticated_requests_return_401(db: AsyncSession):
    """Unauthenticated requests must not read or modify another citizen's profile, facts, assessments, or documents."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        user_info, _ = await _create_test_user_and_citizen(db, prefix="unauth_target")
        citizen_id = str(user_info["citizen_id"])
        dummy_id = str(uuid.uuid4())

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Profile Read
            r = await client.get(f"/api/v1/citizens/{citizen_id}")
            assert r.status_code == 401
            assert "www-authenticate" in r.headers

            # 2. Profile Update
            r = await client.put(f"/api/v1/citizens/{citizen_id}", json={"full_name": "Hacked Name"})
            assert r.status_code == 401

            # 3. Education Records List
            r = await client.get(f"/api/v1/citizens/{citizen_id}/education")
            assert r.status_code == 401

            # 4. Education Records Create
            r = await client.post(
                f"/api/v1/citizens/{citizen_id}/education",
                json={"level": "UNDERGRADUATE", "details": {"degree_name": "BSc"}, "passing_year": 2020},
            )
            assert r.status_code == 401

            # 5. Education Records Update
            r = await client.put(
                f"/api/v1/citizens/{citizen_id}/education/{dummy_id}",
                json={"percentage": 85.5},
            )
            assert r.status_code == 401

            # 6. Education Records Delete
            r = await client.delete(f"/api/v1/citizens/{citizen_id}/education/{dummy_id}")
            assert r.status_code == 401

            # 7. Citizen Profile Audit
            r = await client.get(f"/api/v1/citizens/audit/{citizen_id}")
            assert r.status_code == 401

            # 8. Recommendations
            r = await client.get(f"/api/v1/recommendations/{citizen_id}")
            assert r.status_code == 401

            # 9. Eligibility Evaluation
            r = await client.post(f"/api/v1/eligibility/evaluate/{citizen_id}")
            assert r.status_code == 401

            # 10. Eligibility Simulation
            r = await client.post(f"/api/v1/eligibility/simulate/{citizen_id}", json={"overrides": {}})
            assert r.status_code == 401

            # 11. Document Requirements
            r = await client.get(f"/api/v1/documents/requirements/{citizen_id}")
            assert r.status_code == 401

            # 12. Document Upload
            r = await client.post(
                f"/api/v1/documents/upload/{citizen_id}",
                json={
                    "requirement_type": "INCOME_CERTIFICATE",
                    "filename": "income.pdf",
                    "content_type": "application/pdf",
                    "content_base64": "SGVsbG8gV29ybGQ=",
                },
            )
            assert r.status_code == 401

            # 13. Document Delete
            r = await client.delete(f"/api/v1/documents/{citizen_id}/{dummy_id}")
            assert r.status_code == 401

            # 14. Form Submission Create
            r = await client.post(
                "/api/v1/forms/GENERAL_CITIZEN_PROFILE/submissions",
                json={"citizen_id": citizen_id, "answers": []},
            )
            assert r.status_code == 401
            assert "www-authenticate" in r.headers

            # 15. Form Submission Read
            r = await client.get(
                f"/api/v1/forms/submissions/{dummy_id}",
                params={"citizen_id": citizen_id},
            )
            assert r.status_code == 401

            # 16. Form Submission Update
            r = await client.put(
                f"/api/v1/forms/submissions/{dummy_id}",
                json={"citizen_id": citizen_id, "answers": []},
            )
            assert r.status_code == 401

            # 17. Form Submission Complete
            r = await client.post(
                f"/api/v1/forms/submissions/{dummy_id}/complete",
                json={"citizen_id": citizen_id},
            )
            assert r.status_code == 401

            # 18. Form Submission Normalize
            r = await client.post(
                f"/api/v1/forms/submissions/{dummy_id}/normalize",
                json={"citizen_id": citizen_id},
            )
            assert r.status_code == 401
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_cross_citizen_access_forbidden(db: AsyncSession):
    """Authenticated User A must NOT read or modify Citizen B's data (403 Forbidden)."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        user_a, _ = await _create_test_user_and_citizen(db, prefix="user_a")
        user_b, _ = await _create_test_user_and_citizen(db, prefix="user_b")

        citizen_b_id = str(user_b["citizen_id"])
        dummy_id = str(uuid.uuid4())
        headers_a = user_a["headers"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Read another citizen's profile
            r = await client.get(f"/api/v1/citizens/{citizen_b_id}", headers=headers_a)
            assert r.status_code == 403
            assert r.json()["detail"] == "You can only access your own citizen profile"

            # 2. Modify another citizen's profile
            r = await client.put(
                f"/api/v1/citizens/{citizen_b_id}",
                headers=headers_a,
                json={
                    "full_name": "Tampered Name",
                    "date_of_birth": "1995-06-15",
                    "citizen_type": "GENERAL",
                    "demographic": {"disability_status": "NONE"},
                    "financial": {"is_bpl_card_holder": False, "is_income_tax_payer": False},
                    "location": {},
                },
            )
            assert r.status_code == 403

            # 3. List another citizen's education records
            r = await client.get(f"/api/v1/citizens/{citizen_b_id}/education", headers=headers_a)
            assert r.status_code == 403

            # 4. Add education record to another citizen
            r = await client.post(
                f"/api/v1/citizens/{citizen_b_id}/education",
                headers=headers_a,
                json={"level": "UNDERGRADUATE", "details": {"degree_name": "BSc"}, "passing_year": 2020},
            )
            assert r.status_code == 403

            # 5. Profile audit of another citizen
            r = await client.get(f"/api/v1/citizens/audit/{citizen_b_id}", headers=headers_a)
            assert r.status_code == 403

            # 6. Recommendations for another citizen
            r = await client.get(f"/api/v1/recommendations/{citizen_b_id}", headers=headers_a)
            assert r.status_code == 403

            # 7. Evaluate eligibility for another citizen
            r = await client.post(f"/api/v1/eligibility/evaluate/{citizen_b_id}", headers=headers_a)
            assert r.status_code == 403

            # 8. Simulate eligibility for another citizen
            r = await client.post(
                f"/api/v1/eligibility/simulate/{citizen_b_id}",
                headers=headers_a,
                json={"overrides": {}},
            )
            assert r.status_code == 403

            # 9. Document requirements for another citizen
            r = await client.get(f"/api/v1/documents/requirements/{citizen_b_id}", headers=headers_a)
            assert r.status_code == 403

            # 10. Upload document to another citizen
            r = await client.post(
                f"/api/v1/documents/upload/{citizen_b_id}",
                headers=headers_a,
                json={
                    "requirement_type": "INCOME_CERTIFICATE",
                    "filename": "income.pdf",
                    "content_type": "application/pdf",
                    "content_base64": "SGVsbG8gV29ybGQ=",
                },
            )
            assert r.status_code == 403

            # 11. Delete document of another citizen
            r = await client.delete(f"/api/v1/documents/{citizen_b_id}/{dummy_id}", headers=headers_a)
            assert r.status_code == 403

            # 12. Create submission for another citizen
            r = await client.post(
                "/api/v1/forms/GENERAL_CITIZEN_PROFILE/submissions",
                headers=headers_a,
                json={"citizen_id": citizen_b_id, "answers": []},
            )
            assert r.status_code == 403
            assert r.json()["detail"] == "You can only access your own citizen profile"

            # 13. Read submission of another citizen
            r = await client.get(
                f"/api/v1/forms/submissions/{dummy_id}",
                headers=headers_a,
                params={"citizen_id": citizen_b_id},
            )
            assert r.status_code == 403
            assert r.json()["detail"] == "You can only access your own citizen profile"

            # 14. Update submission of another citizen
            r = await client.put(
                f"/api/v1/forms/submissions/{dummy_id}",
                headers=headers_a,
                json={"citizen_id": citizen_b_id, "answers": []},
            )
            assert r.status_code == 403
            assert r.json()["detail"] == "You can only access your own citizen profile"

            # 15. Complete submission of another citizen
            r = await client.post(
                f"/api/v1/forms/submissions/{dummy_id}/complete",
                headers=headers_a,
                json={"citizen_id": citizen_b_id},
            )
            assert r.status_code == 403
            assert r.json()["detail"] == "You can only access your own citizen profile"

            # 16. Normalize submission of another citizen
            r = await client.post(
                f"/api/v1/forms/submissions/{dummy_id}/normalize",
                headers=headers_a,
                json={"citizen_id": citizen_b_id},
            )
            assert r.status_code == 403
            assert r.json()["detail"] == "You can only access your own citizen profile"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_authorized_own_citizen_access_allowed(db: AsyncSession):
    """Authenticated User A can access and modify their own citizen profile and documents."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        user_a, _ = await _create_test_user_and_citizen(db, prefix="owner_a")
        citizen_id = str(user_a["citizen_id"])
        headers = user_a["headers"]

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Read own profile
            r = await client.get(f"/api/v1/citizens/{citizen_id}", headers=headers)
            assert r.status_code == 200
            data = r.json()
            assert data["citizen_id"] == citizen_id
            assert data["email_id"] is not None

            # 2. Update own profile
            r = await client.put(
                f"/api/v1/citizens/{citizen_id}",
                headers=headers,
                json={
                    "full_name": "Updated Own Name",
                    "date_of_birth": "1995-06-15",
                    "gender": "FEMALE",
                    "citizen_type": "GENERAL",
                    "demographic": {"disability_status": "NONE"},
                    "financial": {"is_bpl_card_holder": False, "is_income_tax_payer": False, "annual_income": 400000},
                    "location": {"state": "Maharashtra"},
                },
            )
            assert r.status_code == 200
            assert r.json()["full_name"] == "Updated Own Name"

            # 3. Add own education record
            r = await client.post(
                f"/api/v1/citizens/{citizen_id}/education",
                headers=headers,
                json={
                    "level": "UNDERGRADUATE",
                    "details": {"degree_name": "BTech Computer Science"},
                    "passing_year": 2017,
                    "percentage": 82.5,
                },
            )
            assert r.status_code == 201
            edu_record = r.json()
            record_id = edu_record["record_id"]

            # 4. List own education records
            r = await client.get(f"/api/v1/citizens/{citizen_id}/education", headers=headers)
            assert r.status_code == 200
            records = r.json()
            assert len(records) >= 1
            assert any(rec["record_id"] == record_id for rec in records)

            # 5. Delete own education record
            r = await client.delete(
                f"/api/v1/citizens/{citizen_id}/education/{record_id}",
                headers=headers,
            )
            assert r.status_code == 200

            # 6. Read own document requirements
            r = await client.get(f"/api/v1/documents/requirements/{citizen_id}", headers=headers)
            assert r.status_code == 200

            # 7. Read own recommendations
            r = await client.get(f"/api/v1/recommendations/{citizen_id}", headers=headers)
            assert r.status_code == 200

            # 8. Simulate own eligibility
            r = await client.post(
                f"/api/v1/eligibility/simulate/{citizen_id}",
                headers=headers,
                json={"overrides": {"annual_income": 150000}},
            )
            assert r.status_code == 200

            # 9. Create own submission
            r = await client.post(
                "/api/v1/forms/GENERAL_CITIZEN_PROFILE/submissions",
                headers=headers,
                json={"citizen_id": citizen_id, "answers": []},
            )
            assert r.status_code == 201
            sub_id = r.json()["submission_id"]

            # 10. Read own submission
            r = await client.get(
                f"/api/v1/forms/submissions/{sub_id}",
                headers=headers,
                params={"citizen_id": citizen_id},
            )
            assert r.status_code == 200
            assert r.json()["submission_id"] == sub_id

            # 11. Update own submission
            r = await client.put(
                f"/api/v1/forms/submissions/{sub_id}",
                headers=headers,
                json={"citizen_id": citizen_id, "answers": []},
            )
            assert r.status_code == 200
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_user_can_access_any_citizen(db: AsyncSession):
    """Admin users are authorized to inspect citizen profiles for administrative oversight."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        admin_info, _ = await _create_test_user_and_citizen(db, prefix="admin_user", role="ADMIN")
        citizen_target, _ = await _create_test_user_and_citizen(db, prefix="target_citizen")
        target_citizen_id = str(citizen_target["citizen_id"])

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # Admin can read target citizen's profile
            r = await client.get(
                f"/api/v1/citizens/{target_citizen_id}",
                headers=admin_info["headers"],
            )
            assert r.status_code == 200
            assert r.json()["citizen_id"] == target_citizen_id

            # Admin can inspect target citizen's recommendations
            r = await client.get(
                f"/api/v1/recommendations/{target_citizen_id}",
                headers=admin_info["headers"],
            )
            assert r.status_code == 200

            # Admin can create submission for target citizen
            r = await client.post(
                "/api/v1/forms/GENERAL_CITIZEN_PROFILE/submissions",
                headers=admin_info["headers"],
                json={"citizen_id": target_citizen_id, "answers": []},
            )
            assert r.status_code == 201
            target_sub_id = r.json()["submission_id"]

            # Admin can read target citizen's submission
            r = await client.get(
                f"/api/v1/forms/submissions/{target_sub_id}",
                headers=admin_info["headers"],
                params={"citizen_id": target_citizen_id},
            )
            assert r.status_code == 200
            assert r.json()["submission_id"] == target_sub_id
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_public_endpoints_accessible_without_auth(db: AsyncSession):
    """Public scheme catalogues, forms, and anonymous initial registration remain public."""
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 1. Scheme Catalogue
            r = await client.get("/api/v1/schemes/")
            assert r.status_code == 200
            assert isinstance(r.json(), list)

            # 2. Forms Catalogue
            r = await client.get("/api/v1/forms/")
            assert r.status_code == 200

            # 3. Initial Anonymous Registration
            suffix = uuid.uuid4().hex[:8].translate(str.maketrans("0123456789", "abcdefghij"))
            reg_payload = {
                "full_name": f"Anonymous {suffix.capitalize()}",
                "date_of_birth": "1998-04-12",
                "gender": "MALE",
                "citizen_type": "GENERAL",
                "demographic": {"disability_status": "NONE"},
                "financial": {"is_bpl_card_holder": False, "is_income_tax_payer": False},
                "location": {"state": "Delhi"},
            }
            r = await client.post("/api/v1/citizens/", json=reg_payload)
            assert r.status_code == 201
            data = r.json()
            assert "citizen_id" in data
    finally:
        app.dependency_overrides.clear()
