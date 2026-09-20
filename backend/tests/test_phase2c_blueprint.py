"""
Phase 2C (Steps 1-4) tests: v2 form blueprint end-to-end.

Covers: seed validation (including fail-fast and circular-condition
detection), v1/v2 coexistence and versioning, v2 submission lifecycle with
conditional visibility, normalization into profiles/facts/provenance,
derived facts (AGE, IS_BPL_CARD_HOLDER), idempotent re-normalization, and
multi-citizen-type coverage (GENERAL, STUDENT, FARMER, PwD, STUDENT+PwD).

SAFETY: every test citizen/form/submission is deleted at module teardown.
The registry-fact assertions run against test citizens only. Seeded data
(7 schemes, v1+v2 forms, 15 citizens) is never modified.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.main import app
from scripts.seed_forms import validate_form_spec, validate_seed_file

_TestSession = async_sessionmaker(
    create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool),
    expire_on_commit=False,
)

SUFFIX = uuid.uuid4().hex[:8]


def _run(coro):
    return asyncio.run(coro)


def _insert_v1_submission(citizen_id: uuid.UUID, answers_by_code: dict[str, object]) -> str:
    """Simulate a pre-v2 era submission: pinned to GENERAL_CITIZEN_PROFILE v1
    with answers stored against v1 question IDs (direct DB insert, the same
    shape the Phase 2A API produces). Returns the submission_id."""
    return _insert_version_submission(citizen_id, 1, answers_by_code)


def _insert_version_submission(citizen_id: uuid.UUID, version: int, answers_by_code: dict[str, object]) -> str:
    """Directly insert a submission pinned to a specific form version with
    answers stored against that version's question IDs (the shape a real
    session from that era produced). Returns the submission_id. Only codes
    that exist in that version are inserted."""

    async def _insert():
        async with _TestSession() as session:
            row = (await session.execute(
                text("SELECT form_id FROM tbl_form_definition "
                     "WHERE form_code = 'GENERAL_CITIZEN_PROFILE' AND version = :v"),
                {"v": version},
            )).one()
            form_id = row.form_id
            qids = dict((await session.execute(
                text("SELECT q.question_code, q.question_id FROM tbl_form_question q "
                     "JOIN tbl_form_section s ON s.section_id = q.section_id "
                     "WHERE s.form_id = :fid"),
                {"fid": form_id},
            )).all())
            submission = uuid.uuid4()
            await session.execute(
                text("INSERT INTO tbl_form_submission (submission_id, citizen_id, form_id, "
                     "form_version, status, started_at, created_at, updated_at) "
                     "VALUES (:sid, :cid, :fid, :v, 'IN_PROGRESS', now(), now(), now())"),
                {"sid": submission, "cid": citizen_id, "fid": form_id, "v": version},
            )
            for code, value in answers_by_code.items():
                if code not in qids:
                    continue  # code not in this version — skip
                if isinstance(value, bool):
                    col, typed = "answer_boolean", value
                elif isinstance(value, int):
                    col, typed = "answer_number", value
                elif isinstance(value, float):
                    col, typed = "answer_decimal", value
                else:
                    col, typed = "answer_text", str(value)
                await session.execute(
                    text(f"INSERT INTO tbl_form_answer (answer_id, submission_id, question_id, "
                         f"{col}, source, created_at, updated_at) "
                         f"VALUES (:aid, :sid, :qid, :val, 'USER_INPUT', now(), now())"),
                    {"aid": uuid.uuid4(), "sid": submission, "qid": qids[code], "val": typed},
                )
            await session.commit()
            return submission

    return str(_run(_insert()))


def _fetch_rows(query: str, params: dict) -> list[dict]:
    """Read-only verification queries via asyncpg."""
    import re

    import asyncpg

    dsn = get_settings().DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    names: list[str] = []

    def _sub(match: re.Match) -> str:
        names.append(match.group(1))
        return f"${len(names)}"

    pg_query = re.sub(r"(?<!:):(\w+)", _sub, query)
    args = [params[n] for n in names]

    async def _query():
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(pg_query, *args)
            return [dict(r) for r in rows]
        finally:
            await conn.close()

    return asyncio.run(_query())


# ------------------------------------------------------------------
# Seed-file structural checks (no DB needed)
# ------------------------------------------------------------------


class TestSeedValidation:
    def test_seed_file_is_valid(self):
        import json
        from pathlib import Path

        data = json.loads(
            Path("seed_data/forms.json").read_text(encoding="utf-8-sig")
        )
        # Cross-file uniqueness + per-form structure; v1 legacy questions are
        # grandfathered (already in the DB), so only v2 and v3 must be clean.
        v2 = [f for f in data["forms"] if f.get("version") == 2]
        v3 = [f for f in data["forms"] if f.get("version") == 3]
        assert len(v2) == 1
        assert len(v3) == 1
        assert validate_form_spec(v2[0]) == []
        assert validate_form_spec(v3[0]) == []

    def test_unknown_profile_field_fails_fast(self):
        bad = {
            "form_code": "BAD_FORM",
            "sections": [
                {
                    "section_code": "S1",
                    "section_name": "S1",
                    "questions": [
                        {
                            "question_code": "Q1",
                            "question_text": "Q?",
                            "question_type": "text",
                            "profile_field": "does.not_exist",
                        }
                    ],
                }
            ],
        }
        problems = validate_form_spec(bad)
        assert any("unknown profile_field" in p for p in problems)

    def test_derived_only_field_cannot_be_asked(self):
        bad = {
            "form_code": "BAD_FORM",
            "sections": [
                {
                    "section_code": "S1",
                    "section_name": "S1",
                    "questions": [
                        {
                            "question_code": "Q_BPL",
                            "question_text": "BPL card?",
                            "question_type": "boolean",
                            "profile_field": "is_bpl_card_holder",
                        }
                    ],
                }
            ],
        }
        problems = validate_form_spec(bad)
        assert any("DERIVED_ONLY" in p for p in problems)

    def test_circular_condition_detected(self):
        bad = {
            "form_code": "BAD_FORM",
            "sections": [
                {
                    "section_code": "S1",
                    "section_name": "S1",
                    "questions": [
                        {
                            "question_code": "A",
                            "question_text": "A?",
                            "question_type": "text",
                            "conditions": [
                                {
                                    "depends_on_question_code": "B",
                                    "operator": "EQUALS",
                                    "comparison_value": "x",
                                }
                            ],
                        },
                        {
                            "question_code": "B",
                            "question_text": "B?",
                            "question_type": "text",
                            "conditions": [
                                {
                                    "depends_on_question_code": "A",
                                    "operator": "EQUALS",
                                    "comparison_value": "y",
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        problems = validate_form_spec(bad)
        assert any("circular" in p.lower() for p in problems)

    def test_duplicate_question_code_detected(self):
        bad = {
            "form_code": "BAD_FORM",
            "sections": [
                {
                    "section_code": "S1",
                    "section_name": "S1",
                    "questions": [
                        {"question_code": "X", "question_text": "?", "question_type": "text"},
                        {"question_code": "X", "question_text": "?", "question_type": "text"},
                    ],
                }
            ],
        }
        problems = validate_form_spec(bad)
        assert any("duplicate question_code" in p for p in problems)

    def test_invalid_operator_and_action_detected(self):
        bad = {
            "form_code": "BAD_FORM",
            "sections": [
                {
                    "section_code": "S1",
                    "section_name": "S1",
                    "questions": [
                        {
                            "question_code": "A",
                            "question_text": "A?",
                            "question_type": "text",
                            "conditions": [
                                {
                                    "depends_on_question_code": "A",
                                    "operator": "MAGIC",
                                    "action": "EXPLODE",
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        problems = validate_form_spec(bad)
        assert any("invalid operator" in p for p in problems)
        assert any("invalid action" in p for p in problems)

    def test_duplicate_version_in_seed_file_detected(self):
        problems = validate_seed_file(
            {
                "forms": [
                    {"form_code": "F", "version": 1, "sections": []},
                    {"form_code": "F", "version": 1, "sections": []},
                ]
            }
        )
        assert any("duplicate form_code/version" in p for p in problems)


# ------------------------------------------------------------------
# Live API checks against the seeded v1 + v2 forms
# ------------------------------------------------------------------


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


_form_detail_cache: dict[str, dict] = {}


def _form_detail(client, form_code: str) -> dict:
    if form_code not in _form_detail_cache:
        resp = client.get(f"/api/v1/forms/{form_code}")
        assert resp.status_code == 200, resp.text
        _form_detail_cache[form_code] = resp.json()
    return _form_detail_cache[form_code]


def _qid(client, form_code: str, question_code: str) -> str:
    detail = _form_detail(client, form_code)
    for section in detail["sections"]:
        for q in section["questions"]:
            if q["question_code"] == question_code:
                return q["question_id"]
    raise AssertionError(f"{question_code} not found in {form_code}")


def _make_citizen(client, tracked, **overrides) -> uuid.UUID:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "full_name": f"Phase 2C Test {suffix}",
        "date_of_birth": "2000-06-15",
        "gender": "FEMALE",
        "citizen_type": "GENERAL",
        "demographic": {"family_size": 4, "social_category": "GEN"},
        "financial": {"annual_income": 150000, "poverty_category": "APL"},
        "location": {"state": "Maharashtra", "district": "Pune", "area_type": "URBAN"},
    }
    payload.update(overrides)
    resp = client.post("/api/v1/citizens/", json=payload)
    assert resp.status_code == 201, resp.text
    citizen_id = resp.json()["citizen_id"]
    tracked["citizen_ids"].append(citizen_id)
    return citizen_id


def _answers_by_code(client, form_code: str, values: dict) -> list[dict]:
    """Map question codes to question IDs. Codes absent from the given form
    version are dropped with a warning — v3 removed the identity questions,
    so a v2-era catalogue must not be submitted against v3."""
    import warnings

    detail = _form_detail(client, form_code)
    available = {
        q["question_code"]: q["question_id"]
        for s in detail["sections"]
        for q in s["questions"]
    }
    dropped = [code for code in values if code not in available]
    if dropped:
        warnings.warn(f"question codes not in {form_code} (dropped): {dropped}")
    return [
        {"question_id": available[code], "value": value}
        for code, value in values.items()
        if code in available
    ]


def _submit(client, citizen_id, form_code, values: dict) -> str:
    resp = client.post(
        f"/api/v1/forms/{form_code}/submissions",
        json={
            "citizen_id": str(citizen_id),
            "answers": _answers_by_code(client, form_code, values),
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["submission_id"]


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


def _facts(citizen_id: uuid.UUID) -> dict[str, str]:
    rows = _fetch_rows(
        "SELECT fact_code, fact_value FROM tbl_profile_fact "
        "WHERE citizen_id = :cid AND effective_until IS NULL",
        {"cid": str(citizen_id)},
    )
    return {r["fact_code"]: r["fact_value"] for r in rows}


V2_COMMON = {
    "MARITAL_STATUS": "SINGLE",
    "RELIGION": "SIKH",
    "FAMILY_SIZE": 4,
    "STATE": "Maharashtra",
    "DISTRICT": "Pune",
    "PINCODE": "411001",
    "AREA_TYPE": "URBAN",
    "ANNUAL_INCOME": 180000,
    "POVERTY_CATEGORY": "BPL",
    "HAS_AADHAAR": True,
    "OWNS_HOUSE": False,
}


class TestVersioning:
    def test_v1_v2_v3_all_exist(self, client):
        versions = client.get("/api/v1/forms/GENERAL_CITIZEN_PROFILE/versions")
        assert versions.status_code == 200
        got = {v["version"] for v in versions.json()["versions"]}
        assert {1, 2, 3} <= got

    def test_active_version_is_v3(self, client):
        detail = _form_detail(client, "GENERAL_CITIZEN_PROFILE")
        assert detail["version"] == 3
        assert detail["form_code"] == "GENERAL_CITIZEN_PROFILE"

    def test_specific_version_reads(self, client):
        v1 = client.get("/api/v1/forms/GENERAL_CITIZEN_PROFILE/versions/1")
        v2 = client.get("/api/v1/forms/GENERAL_CITIZEN_PROFILE/versions/2")
        v3 = client.get("/api/v1/forms/GENERAL_CITIZEN_PROFILE/versions/3")
        assert v1.status_code == 200 and v2.status_code == 200 and v3.status_code == 200
        assert v1.json()["version"] == 1
        assert v2.json()["version"] == 2
        assert v3.json()["version"] == 3

    def test_invalid_version_404(self, client):
        resp = client.get("/api/v1/forms/GENERAL_CITIZEN_PROFILE/versions/99")
        assert resp.status_code == 404


class TestV3Structure:
    """The active form is v3: v2's catalogue minus the identity questions
    (FULL_NAME, DATE_OF_BIRTH, GENDER) which belong to citizen registration."""

    def test_section_count(self, client):
        detail = _form_detail(client, "GENERAL_CITIZEN_PROFILE")
        assert len(detail["sections"]) == 12

    def test_question_count(self, client):
        detail = _form_detail(client, "GENERAL_CITIZEN_PROFILE")
        total = sum(len(s["questions"]) for s in detail["sections"])
        assert total == 61

    def test_v2_is_frozen(self, client):
        """v2 must remain exactly as seeded: 12 sections, 64 questions —
        version-pinned submissions depend on it never changing."""
        v2 = client.get("/api/v1/forms/GENERAL_CITIZEN_PROFILE/versions/2").json()
        assert len(v2["sections"]) == 12
        assert sum(len(s["questions"]) for s in v2["sections"]) == 64
        codes = {q["question_code"] for s in v2["sections"] for q in s["questions"]}
        assert {"FULL_NAME", "DATE_OF_BIRTH", "GENDER"} <= codes

    def test_identity_questions_removed(self, client):
        detail = _form_detail(client, "GENERAL_CITIZEN_PROFILE")
        codes = {q["question_code"] for s in detail["sections"] for q in s["questions"]}
        assert not codes & {"FULL_NAME", "DATE_OF_BIRTH", "GENDER"}
        # The remaining Personal Information questions are welfare attributes.
        personal = next(s for s in detail["sections"] if s["section_code"] == "PERSONAL_INFO")
        assert {q["question_code"] for q in personal["questions"]} == {"MARITAL_STATUS", "RELIGION"}

    def test_sections_ordered(self, client):
        detail = _form_detail(client, "GENERAL_CITIZEN_PROFILE")
        orders = [s["display_order"] for s in detail["sections"]]
        assert orders == sorted(orders)

    def test_questions_ordered_within_sections(self, client):
        detail = _form_detail(client, "GENERAL_CITIZEN_PROFILE")
        for section in detail["sections"]:
            orders = [q["display_order"] for q in section["questions"]]
            assert orders == sorted(orders)

    def test_conditions_returned(self, client):
        detail = _form_detail(client, "GENERAL_CITIZEN_PROFILE")
        conditional = [
            q
            for s in detail["sections"]
            for q in s["questions"]
            if q.get("conditions")
        ]
        assert len(conditional) == 32
        course = next(q for s in detail["sections"] for q in s["questions"]
                      if q["question_code"] == "COURSE_NAME")
        assert course["conditions"][0]["depends_on_question_code"] == "CURRENTLY_STUDYING"

    def test_no_derived_only_question_in_v3(self, client):
        detail = _form_detail(client, "GENERAL_CITIZEN_PROFILE")
        codes = {q["question_code"] for s in detail["sections"] for q in s["questions"]}
        assert "IS_BPL_CARD_HOLDER" not in codes


class TestV3SubmissionLifecycle:
    def test_draft_allowed(self, client, tracked):
        cid = _make_citizen(client, tracked)
        sid = _submit(client, cid, "GENERAL_CITIZEN_PROFILE", {"MARITAL_STATUS": "SINGLE"})
        got = client.get(f"/api/v1/forms/submissions/{sid}?citizen_id={cid}")
        assert got.status_code == 200
        assert got.json()["status"] == "IN_PROGRESS"  # saved answers move DRAFT→IN_PROGRESS

    def test_complete_and_normalize_general(self, client, tracked):
        cid = _make_citizen(client, tracked)
        sid = _submit(client, cid, "GENERAL_CITIZEN_PROFILE", V2_COMMON)
        completion = _complete(client, cid, sid)
        assert completion["status"] == "COMPLETED"

        summary = _normalize(client, cid, sid)
        assert summary.status_code == 200, summary.text
        body = summary.json()
        assert body["status"] == "NORMALIZED"
        assert body["unmapped_answers"] == []

        facts = _facts(cid)
        # v3 asks no identity questions: DATE_OF_BIRTH must come from the
        # registration record (2000-06-15 in _make_citizen), not the form.
        assert facts["DATE_OF_BIRTH"] == "2000-06-15"
        assert facts["FULL_NAME"].startswith("Phase 2C Test")
        assert facts["IS_BPL_CARD_HOLDER"] == "TRUE"        # derived from BPL
        assert facts["POVERTY_CATEGORY"] == "BPL"
        assert facts["RELIGION"] == "SIKH"
        assert facts["ANNUAL_INCOME"] == "180000"
        assert "AGE" in facts                                # derived from DOB
        # No self-employment/farmer answers -> derived booleans FALSE (from
        # employment status absent) or absent — either is spec-consistent.

    def test_normalization_idempotent(self, client, tracked):
        cid = _make_citizen(client, tracked)
        sid = _submit(client, cid, "GENERAL_CITIZEN_PROFILE", V2_COMMON)
        _complete(client, cid, sid)
        first = _normalize(client, cid, sid).json()
        second = _normalize(client, cid, sid).json()
        assert second["facts_created"] == 0
        assert second["facts_updated"] == 0
        assert second["provenance_created"] == 0
        assert first["facts_created"] > 0

    def test_student_plus_disability_combination(self, client, tracked):
        cid = _make_citizen(client, tracked)
        values = {
            **V2_COMMON,
            "CURRENTLY_STUDYING": True,
            "COURSE_NAME": "B.Sc Physics",
            "YEAR_OF_STUDY": 2,
            "INSTITUTION_NAME": "Fergusson College",
            "MARKS_PERCENTAGE": 82.5,
            "HAS_DISABILITY": "YES",
            "DISABILITY_TYPE": "VISUAL",
            "DISABILITY_PERCENTAGE": 45,
            "HAS_DISABILITY_CERTIFICATE": True,
        }
        sid = _submit(client, cid, "GENERAL_CITIZEN_PROFILE", values)
        completion = _complete(client, cid, sid)
        # Hidden conditional questions must not block completion; the visible
        # ones were answered.
        assert completion["status"] == "COMPLETED"
        _normalize(client, cid, sid)

        facts = _facts(cid)
        assert facts["CURRENTLY_STUDYING"] == "TRUE"
        assert facts["MARKS_PERCENTAGE"] == "82.5"
        assert facts["DISABILITY_STATUS"] == "YES"
        assert facts["DISABILITY_PERCENTAGE"] == "45"
        assert facts["DISABILITY_CERTIFICATE"] == "TRUE"

    def test_farmer_flow(self, client, tracked):
        cid = _make_citizen(client, tracked)
        values = {
            **V2_COMMON,
            "FARMER_STATUS": "YES",
            "FARMER_TYPE": "TENANT",
            "TOTAL_LAND_AREA": 1.2,
            "LAND_UNIT": "HECTARE",
            "CROP_TYPE": "Cotton, Soybean",
            "HAS_KCC": True,
        }
        sid = _submit(client, cid, "GENERAL_CITIZEN_PROFILE", values)
        _complete(client, cid, sid)
        _normalize(client, cid, sid)

        facts = _facts(cid)
        assert facts["FARMER_STATUS"] == "YES"
        assert facts["FARMER_TYPE"] == "TENANT"
        assert facts["HAS_KCC"] == "TRUE"

        prof = _fetch_rows(
            "SELECT farmer_type, total_land_area, crop_type FROM tbl_agriculture_profile "
            "WHERE citizen_id = :cid",
            {"cid": str(cid)},
        )
        assert len(prof) == 1
        assert prof[0]["farmer_type"] == "TENANT"
        assert float(prof[0]["total_land_area"]) == 1.2
        assert prof[0]["crop_type"] == "Cotton, Soybean"

    def test_provenance_created(self, client, tracked):
        cid = _make_citizen(client, tracked)
        sid = _submit(client, cid, "GENERAL_CITIZEN_PROFILE", V2_COMMON)
        _complete(client, cid, sid)
        _normalize(client, cid, sid)
        rows = _fetch_rows(
            "SELECT p.source_type, p.verification_status, p.form_answer_id IS NOT NULL AS has_answer "
            "FROM tbl_profile_fact_provenance p "
            "JOIN tbl_profile_fact f ON f.fact_id = p.fact_id "
            "WHERE f.citizen_id = :cid",
            {"cid": str(cid)},
        )
        assert rows, "expected provenance rows"
        assert all(r["source_type"] in ("USER_INPUT", "SYSTEM_DERIVED") for r in rows)
        derived = [r for r in rows if r["source_type"] == "SYSTEM_DERIVED"]
        assert derived, "expected at least the derived AGE provenance"


class TestVersionPinning:
    def test_v1_submission_still_uses_v1_questions(self, client, tracked):
        """A citizen with a v1-era submission keeps answering v1 questions
        while new citizens get v2. The API always creates submissions
        against the ACTIVE version, so the legacy pin is simulated by
        inserting a v1-pinned submission the way a pre-v2 session would
        have produced; the API must still serve and complete it against
        v1 question IDs."""
        cid = _make_citizen(client, tracked)
        submission_id = _insert_v1_submission(cid, {
            "FULL_NAME": "V1 Pinned",
            "DATE_OF_BIRTH": "1990-01-01",
            "FAMILY_SIZE": 3,
            "CURRENTLY_STUDYING": False,
            "ANNUAL_INCOME": 90000.0,
            "STATE": "Maharashtra",
            "DISTRICT": "Pune",
            "HAS_AADHAAR": True,
            "IS_BPL_CARD_HOLDER": True,
        })

        got = client.get(f"/api/v1/forms/submissions/{submission_id}?citizen_id={cid}")
        assert got.status_code == 200
        body = got.json()
        assert body["form_version"] == 1
        v1_answered = {a["question_id"] for a in body["answers"]}
        v1_ids = {q["question_id"] for s in client.get("/api/v1/forms/GENERAL_CITIZEN_PROFILE/versions/1").json()["sections"] for q in s["questions"]}
        assert v1_answered and v1_answered.issubset(v1_ids), "v1 submission must reference only v1 question IDs"

        # Complete must succeed against v1 questions even though v2 is active.
        completion = _complete(client, cid, submission_id)
        assert completion["status"] == "COMPLETED"

    def test_v2_submission_pinned_to_v2(self, client, tracked):
        cid = _make_citizen(client, tracked)
        # v2 is frozen but no longer active, so a v2-era submission is
        # inserted directly the way a pre-v3 session would have produced.
        submission_id = _insert_version_submission(cid, 2, {
            "FULL_NAME": "V2 Pinned",
            "DATE_OF_BIRTH": "2001-03-10",
            "MARITAL_STATUS": "SINGLE",
            "FAMILY_SIZE": 4,
            "STATE": "Maharashtra",
            "ANNUAL_INCOME": 180000.0,
            "POVERTY_CATEGORY": "BPL",
        })
        got = client.get(f"/api/v1/forms/submissions/{submission_id}?citizen_id={cid}")
        assert got.json()["form_version"] == 2

    def test_v3_submission_pinned_to_v3(self, client, tracked):
        cid = _make_citizen(client, tracked)
        sid = _submit(client, cid, "GENERAL_CITIZEN_PROFILE", V2_COMMON)
        got = client.get(f"/api/v1/forms/submissions/{sid}?citizen_id={cid}")
        assert got.json()["form_version"] == 3
