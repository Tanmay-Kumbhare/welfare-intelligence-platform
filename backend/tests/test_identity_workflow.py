"""
Identity-workflow regression tests (post-Phase-2C identity fix).

Regression coverage for the reported bug: a citizen who registers via the
identity gate, then answers the welfare form, must flow through the whole
lifecycle as ONE citizen — no "Submission belongs to another citizen" error,
no second citizen record, and no re-asking of identity questions.

Architecture under test:
  - ONE authoritative identity: POST /citizens/ (tbl_citizen_master).
  - citizen_id is the only ownership key on every form/submission endpoint.
  - GENERAL_CITIZEN_PROFILE v3 (active) collects NO identity questions;
    identity facts (FULL_NAME / DATE_OF_BIRTH) are seeded from registration
    during normalization when absent, keeping the AGE derivation chain intact.
  - v1/v2 version-pinned submissions remain fully functional.

SAFETY: every test citizen is deleted at module teardown (cascades to
submissions, answers, facts, provenance, profiles). Seeded data is
never modified.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.main import app

_TestSession = async_sessionmaker(
    create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool),
    expire_on_commit=False,
)

SUFFIX = uuid.uuid4().hex[:8]

FORM = "GENERAL_CITIZEN_PROFILE"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def tracked():
    registry = {"citizen_ids": []}
    yield registry

    async def _cleanup():
        async with _TestSession() as session:
            if registry["citizen_ids"]:
                await session.execute(
                    text("DELETE FROM tbl_citizen_master WHERE citizen_id = ANY(:ids)"),
                    {"ids": registry["citizen_ids"]},
                )
            await session.commit()

    _run(_cleanup())


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _register(client, tracked, **overrides) -> dict:
    """Create a citizen the way the frontend identity gate does; returns the
    registration response body (citizen_id included)."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "full_name": f"Identity Test {suffix}",
        "date_of_birth": "2001-03-15",
        "gender": "FEMALE",
        "citizen_type": "GENERAL",
        "demographic": {"disability_status": "NONE"},
        "financial": {"is_bpl_card_holder": False, "is_income_tax_payer": False},
        "location": {},
    }
    payload.update(overrides)
    resp = client.post("/api/v1/citizens/", json=payload)
    assert resp.status_code == 201, resp.text
    body = resp.json()
    tracked["citizen_ids"].append(body["citizen_id"])
    return body


def _qid(client, code: str, form_version: int | None = None) -> str:
    """Question ID from the active form (or a specific version)."""
    url = f"/api/v1/forms/{FORM}"
    if form_version is not None:
        url = f"/api/v1/forms/{FORM}/versions/{form_version}"
    for section in client.get(url).json()["sections"]:
        for q in section["questions"]:
            if q["question_code"] == code:
                return q["question_id"]
    raise AssertionError(f"{code} not found in {FORM}")


def _create_submission(client, citizen_id, answers=None) -> dict:
    resp = client.post(
        f"/api/v1/forms/{FORM}/submissions",
        json={"citizen_id": str(citizen_id), "answers": answers or []},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _update(client, citizen_id, submission_id, answers) -> dict:
    resp = client.put(
        f"/api/v1/forms/submissions/{submission_id}",
        json={"citizen_id": str(citizen_id), "answers": answers},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _complete(client, citizen_id, submission_id) -> dict:
    resp = client.post(
        f"/api/v1/forms/submissions/{submission_id}/complete",
        json={"citizen_id": str(citizen_id)},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def _normalize(client, citizen_id, submission_id):
    return client.post(
        f"/api/v1/forms/submissions/{submission_id}/normalize",
        json={"citizen_id": str(citizen_id)},
    )


def _evaluate(client, citizen_id):
    resp = client.post(f"/api/v1/eligibility/evaluate/{citizen_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _facts(client_unused, citizen_id: uuid.UUID) -> dict[str, str]:
    rows = _run(_open_facts_query(citizen_id))
    return {r["fact_code"]: r["fact_value"] for r in rows}


async def _open_facts_query(citizen_id: uuid.UUID):
    async with _TestSession() as session:
        rows = (await session.execute(
            text("SELECT fact_code, fact_value FROM tbl_profile_fact "
                 "WHERE citizen_id = :cid AND effective_until IS NULL"),
            {"cid": str(citizen_id)},
        )).mappings().all()
    return rows


def _welfare_answers(client) -> list[dict]:
    """A minimal welfare answer set against v3 (no identity questions).
    Covers every v3 required question so a submission can be completed."""
    return [
        {"question_id": _qid(client, "MARITAL_STATUS"), "value": "SINGLE"},
        {"question_id": _qid(client, "FAMILY_SIZE"), "value": 4},
        {"question_id": _qid(client, "STATE"), "value": "Maharashtra"},
        {"question_id": _qid(client, "DISTRICT"), "value": "Pune"},
        {"question_id": _qid(client, "PINCODE"), "value": "411001"},
        {"question_id": _qid(client, "AREA_TYPE"), "value": "URBAN"},
        {"question_id": _qid(client, "ANNUAL_INCOME"), "value": 180000},
        {"question_id": _qid(client, "POVERTY_CATEGORY"), "value": "BPL"},
        {"question_id": _qid(client, "HAS_AADHAAR"), "value": True},
    ]


# ------------------------------------------------------------------
# The reported bug, end to end
# ------------------------------------------------------------------


class TestReportedBugRegression:
    def test_register_store_id_complete_flow_no_ownership_error(self, client, tracked):
        """The exact reported scenario: register → keep citizen_id → load
        form → submission → save → complete → normalize → evaluate — all
        under ONE citizen_id with no 'different user' error anywhere."""
        citizen = _register(client, tracked)
        citizen_id = citizen["citizen_id"]

        # The frontend stores this id (localStorage) and sends it everywhere.
        form = client.get(f"/api/v1/forms/{FORM}")
        assert form.status_code == 200
        assert form.json()["version"] == 3

        draft = _create_submission(client, citizen_id)
        assert draft["citizen_id"] == citizen_id

        _update(client, citizen_id, draft["submission_id"], _welfare_answers(client))
        completed = _complete(client, citizen_id, draft["submission_id"])
        assert completed["status"] == "COMPLETED"

        summary = _normalize(client, citizen_id, draft["submission_id"])
        assert summary.status_code == 200, summary.text

        assessments = _evaluate(client, citizen_id)
        assert len(assessments) == 7  # all seeded schemes evaluated

    def test_welfare_form_has_no_identity_questions(self, client):
        codes = {
            q["question_code"]
            for s in client.get(f"/api/v1/forms/{FORM}").json()["sections"]
            for q in s["questions"]
        }
        assert not codes & {"FULL_NAME", "DATE_OF_BIRTH", "GENDER"}

    def test_identity_facts_compete_the_chain(self, client, tracked):
        """After a v3-only flow, normalization still produces FULL_NAME,
        DATE_OF_BIRTH and the derived AGE — sourced from registration."""
        citizen = _register(client, tracked, date_of_birth="2001-03-15")
        citizen_id = citizen["citizen_id"]
        draft = _create_submission(client, citizen_id)
        _update(client, citizen_id, draft["submission_id"], _welfare_answers(client))
        _complete(client, citizen_id, draft["submission_id"])
        assert _normalize(client, citizen_id, draft["submission_id"]).status_code == 200

        facts = _facts(client, citizen_id)
        assert facts["FULL_NAME"] == citizen["full_name"]
        assert facts["DATE_OF_BIRTH"] == "2001-03-15"
        # Derived AGE consistent with the canonical calculator.
        from app.utils.date_calc import calculate_age
        from datetime import date

        expected = calculate_age(date(2001, 3, 15))
        assert facts["AGE"] == str(expected)

    def test_engine_age_matches_fact_after_v3_flow(self, client, tracked):
        """AGE fact and eligibility-engine age agree for the same citizen."""
        from datetime import date

        from app.utils.date_calc import calculate_age

        citizen = _register(client, tracked, date_of_birth="2001-03-15")
        citizen_id = citizen["citizen_id"]
        draft = _create_submission(client, citizen_id)
        _update(client, citizen_id, draft["submission_id"], _welfare_answers(client))
        _complete(client, citizen_id, draft["submission_id"])
        _normalize(client, citizen_id, draft["submission_id"])
        assessments = _evaluate(client, citizen_id)

        expected = str(calculate_age(date(2001, 3, 15)))
        for assessment in assessments:
            for group in assessment["evaluation_details"]["groups"]:
                for rule in group["rules"]:
                    if rule["parameter"] == "age":
                        assert str(rule["actual"]) == expected

    def test_no_second_citizen_created_by_form_flow(self, client, tracked):
        """Submitting the welfare form must never create another citizen row."""
        before = _count_citizens_named(client, tracked)
        citizen = _register(client, tracked)
        citizen_id = citizen["citizen_id"]
        draft = _create_submission(client, citizen_id)
        _update(client, citizen_id, draft["submission_id"], _welfare_answers(client))
        _complete(client, citizen_id, draft["submission_id"])
        _normalize(client, citizen_id, draft["submission_id"])
        after = _count_citizens_named(client, tracked)
        # Exactly one new citizen (the registration), nothing from the form flow.
        assert after == before + 1


async def _count_citizens_query() -> int:
    async with _TestSession() as session:
        return (await session.execute(
            text("SELECT COUNT(*) FROM tbl_citizen_master")
        )).scalar_one()


def _count_citizens_named(client, tracked) -> int:
    return _run(_count_citizens_query())


# ------------------------------------------------------------------
# Ownership and identity edges
# ------------------------------------------------------------------


class TestOwnership:
    def test_same_citizen_resumes_draft(self, client, tracked):
        citizen_id = _register(client, tracked)["citizen_id"]
        first = _create_submission(client, citizen_id)
        _update(client, citizen_id, first["submission_id"], _welfare_answers(client)[:2])

        # A later page load re-POSTs; resume must return the same submission.
        resume = _create_submission(client, citizen_id)
        assert resume["submission_id"] == first["submission_id"]
        assert resume["completion_percentage"] > 0

    def test_different_citizen_cannot_access_submission(self, client, tracked):
        owner = _register(client, tracked)["citizen_id"]
        other = _register(client, tracked)["citizen_id"]
        draft = _create_submission(client, owner)

        got = client.get(f"/api/v1/forms/submissions/{draft['submission_id']}?citizen_id={other}")
        assert got.status_code == 403
        assert "another citizen" in got.json()["detail"]["message"]

        put = client.put(
            f"/api/v1/forms/submissions/{draft['submission_id']}",
            json={"citizen_id": other, "answers": _welfare_answers(client)},
        )
        assert put.status_code == 403

        complete = client.post(
            f"/api/v1/forms/submissions/{draft['submission_id']}/complete",
            json={"citizen_id": other},
        )
        assert complete.status_code == 403

        normalize = _normalize(client, other, draft["submission_id"])
        assert normalize.status_code == 403

    def test_missing_citizen_id_fails_cleanly(self, client, tracked):
        owner = _register(client, tracked)["citizen_id"]
        draft = _create_submission(client, owner)

        got = client.get(f"/api/v1/forms/submissions/{draft['submission_id']}")
        assert got.status_code == 422

        put = client.put(
            f"/api/v1/forms/submissions/{draft['submission_id']}",
            json={"answers": []},
        )
        assert put.status_code == 422

        complete = client.post(
            f"/api/v1/forms/submissions/{draft['submission_id']}/complete",
            json={},
        )
        assert complete.status_code == 422

    def test_unknown_citizen_rejected_on_submission_create(self, client):
        resp = client.post(
            f"/api/v1/forms/{FORM}/submissions",
            json={"citizen_id": str(uuid.uuid4()), "answers": []},
        )
        assert resp.status_code == 404

    def test_repeated_registration_creates_distinct_citizens_no_collision(
        self, client, tracked
    ):
        """Re-registering the same person data creates a new, independent
        citizen (no name/DOB matching, no silent merge) — ownership stays
        citizen_id-based; both records work independently."""
        a = _register(client, tracked)
        b = _register(
            client, tracked,
            full_name=a["full_name"], date_of_birth=a["date_of_birth"],
        )
        assert a["citizen_id"] != b["citizen_id"]

        # Both citizens run their own independent (draft) submissions.
        answers = _welfare_answers(client)
        for citizen_id in (a["citizen_id"], b["citizen_id"]):
            draft = _create_submission(client, citizen_id)
            assert draft["citizen_id"] == citizen_id
            updated = _update(client, citizen_id, draft["submission_id"], answers[:3])
            assert updated["citizen_id"] == citizen_id

    def test_malformed_citizen_id_is_422_not_500(self, client):
        resp = client.post(
            f"/api/v1/forms/{FORM}/submissions",
            json={"citizen_id": "not-a-uuid", "answers": []},
        )
        assert resp.status_code == 422


# ------------------------------------------------------------------
# Versioning compatibility
# ------------------------------------------------------------------


class TestVersionCompatibility:
    def test_v1_pinned_submission_completes_and_normalizes(self, client, tracked):
        """A pre-v3 (v1-pinned) submission still works end to end, including
        normalization — identity questions in v1 answers remain valid."""
        citizen_id = _register(client, tracked)["citizen_id"]

        async def _insert():
            async with _TestSession() as session:
                form_id = (await session.execute(
                    text("SELECT form_id FROM tbl_form_definition "
                         "WHERE form_code = :fc AND version = 1"),
                    {"fc": FORM},
                )).scalar_one()
                qids = dict((await session.execute(
                    text("SELECT q.question_code, q.question_id FROM tbl_form_question q "
                         "JOIN tbl_form_section s ON s.section_id = q.section_id "
                         "WHERE s.form_id = :fid"),
                    {"fid": form_id},
                )).all())
                sid = uuid.uuid4()
                await session.execute(
                    text("INSERT INTO tbl_form_submission (submission_id, citizen_id, form_id, "
                         "form_version, status, started_at, created_at, updated_at) "
                         "VALUES (:sid, :cid, :fid, 1, 'IN_PROGRESS', now(), now(), now())"),
                    {"sid": sid, "cid": str(citizen_id), "fid": form_id},
                )
                # All v1 required questions (CURRENTLY_STUDYING is required in v1,
                # unlike v2) with per-type typed answer columns.
                answers = {
                    "FULL_NAME": "V1 Citizen",
                    "DATE_OF_BIRTH": date(1990, 1, 1),
                    "FAMILY_SIZE": 3,
                    "STATE": "Maharashtra",
                    "DISTRICT": "Pune",
                    "ANNUAL_INCOME": Decimal("240000"),
                    "CURRENTLY_STUDYING": False,
                    "HAS_AADHAAR": True,
                }
                for code, value in answers.items():
                    if isinstance(value, bool):
                        col, typed = "answer_boolean", value
                    elif isinstance(value, Decimal):
                        col, typed = "answer_decimal", value
                    elif isinstance(value, date):
                        col, typed = "answer_date", value
                    elif isinstance(value, int):
                        col, typed = "answer_number", value
                    else:
                        col, typed = "answer_text", str(value)
                    await session.execute(
                        text(f"INSERT INTO tbl_form_answer (answer_id, submission_id, question_id, "
                             f"{col}, source, created_at, updated_at) "
                             f"VALUES (:aid, :sid, :qid, :val, 'USER_INPUT', now(), now())"),
                        {"aid": uuid.uuid4(), "sid": sid, "qid": qids[code], "val": typed},
                    )
                await session.commit()
                return sid

        sid = str(_run(_insert()))
        completed = _complete(client, citizen_id, sid)
        assert completed["status"] == "COMPLETED"
        assert completed["form_version"] == 1
        assert _normalize(client, citizen_id, sid).status_code == 200

    def test_v2_pinned_submission_completes(self, client, tracked):
        """A pre-v3 (v2-pinned) submission still completes against v2
        questions — v2 is frozen and active-version changes never leak in."""
        citizen_id = _register(client, tracked)["citizen_id"]

        async def _insert():
            async with _TestSession() as session:
                form_id = (await session.execute(
                    text("SELECT form_id FROM tbl_form_definition "
                         "WHERE form_code = :fc AND version = 2"),
                    {"fc": FORM},
                )).scalar_one()
                qids = dict((await session.execute(
                    text("SELECT q.question_code, q.question_id FROM tbl_form_question q "
                         "JOIN tbl_form_section s ON s.section_id = q.section_id "
                         "WHERE s.form_id = :fid"),
                    {"fid": form_id},
                )).all())
                sid = uuid.uuid4()
                await session.execute(
                    text("INSERT INTO tbl_form_submission (submission_id, citizen_id, form_id, "
                         "form_version, status, started_at, created_at, updated_at) "
                         "VALUES (:sid, :cid, :fid, 2, 'IN_PROGRESS', now(), now(), now())"),
                    {"sid": sid, "cid": str(citizen_id), "fid": form_id},
                )
                # All v2 required questions with per-type typed answer columns.
                answers = {
                    "FULL_NAME": "V2 Citizen",
                    "DATE_OF_BIRTH": date(1995, 5, 5),
                    "FAMILY_SIZE": 4,
                    "STATE": "Maharashtra",
                    "DISTRICT": "Pune",
                    "ANNUAL_INCOME": Decimal("180000"),
                    "HAS_AADHAAR": True,
                    "MARITAL_STATUS": "SINGLE",
                }
                for code, value in answers.items():
                    if isinstance(value, bool):
                        col, typed = "answer_boolean", value
                    elif isinstance(value, Decimal):
                        col, typed = "answer_decimal", value
                    elif isinstance(value, date):
                        col, typed = "answer_date", value
                    elif isinstance(value, int):
                        col, typed = "answer_number", value
                    else:
                        col, typed = "answer_text", str(value)
                    await session.execute(
                        text(f"INSERT INTO tbl_form_answer (answer_id, submission_id, question_id, "
                             f"{col}, source, created_at, updated_at) "
                             f"VALUES (:aid, :sid, :qid, :val, 'USER_INPUT', now(), now())"),
                        {"aid": uuid.uuid4(), "sid": sid, "qid": qids[code], "val": typed},
                    )
                await session.commit()
                return sid

        sid = str(_run(_insert()))
        completed = _complete(client, citizen_id, sid)
        assert completed["status"] == "COMPLETED"
        assert completed["form_version"] == 2

    def test_question_from_other_version_rejected(self, client, tracked):
        """A v2 question ID (identity question removed from v3) cannot be
        answered inside a v3 submission."""
        citizen_id = _register(client, tracked)["citizen_id"]
        v2_qid = _qid(client, "FULL_NAME", form_version=2)
        resp = client.post(
            f"/api/v1/forms/{FORM}/submissions",
            json={
                "citizen_id": str(citizen_id),
                "answers": [{"question_id": v2_qid, "value": "Impostor"}],
            },
        )
        assert resp.status_code == 422
        assert "form version" in resp.json()["detail"]["message"]


# ------------------------------------------------------------------
# Age consistency preserved
# ------------------------------------------------------------------


class TestAgeConsistencyPreserved:
    def test_age_fact_matches_registration_dob(self, client, tracked):
        citizen_id = _register(client, tracked, date_of_birth="2001-03-15")["citizen_id"]
        draft = _create_submission(client, citizen_id)
        _update(client, citizen_id, draft["submission_id"], _welfare_answers(client))
        _complete(client, citizen_id, draft["submission_id"])
        _normalize(client, citizen_id, draft["submission_id"])

        facts = _facts(client, citizen_id)
        from datetime import date

        from app.utils.date_calc import calculate_age

        assert facts["DATE_OF_BIRTH"] == "2001-03-15"
        assert facts["AGE"] == str(calculate_age(date(2001, 3, 15)))

    def test_form_dob_fact_not_overwritten_by_registration(self, client, tracked):
        """A citizen with a pre-v3 form-sourced DATE_OF_BIRTH fact keeps that
        fact's value and provenance — registration only fills gaps."""
        citizen = _register(client, tracked, date_of_birth="2001-03-15")
        citizen_id = citizen["citizen_id"]

        async def _seed_fact():
            async with _TestSession() as session:
                await session.execute(
                    text("INSERT INTO tbl_profile_fact (fact_id, citizen_id, fact_code, "
                         "fact_value, data_type, source, verified, created_at, updated_at) "
                         "VALUES (:fid, :cid, 'DATE_OF_BIRTH', '1999-01-01', 'DATE', "
                         "'USER_INPUT', FALSE, now(), now())"),
                    {"fid": uuid.uuid4(), "cid": str(citizen_id)},
                )
                await session.commit()

        _run(_seed_fact())
        draft = _create_submission(client, citizen_id)
        _update(client, citizen_id, draft["submission_id"], _welfare_answers(client))
        _complete(client, citizen_id, draft["submission_id"])
        assert _normalize(client, citizen_id, draft["submission_id"]).status_code == 200

        facts = _facts(client, citizen_id)
        assert facts["DATE_OF_BIRTH"] == "1999-01-01"  # untouched
        from datetime import date

        from app.utils.date_calc import calculate_age

        assert facts["AGE"] == str(calculate_age(date(1999, 1, 1)))
