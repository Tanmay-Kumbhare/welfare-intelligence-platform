"""
Phase 2B normalization tests.

Covers: completed-submission normalization, draft rejection, profile/fact
mapping, provenance, idempotency, derived AGE, typed values, unmapped
reporting, family members, ownership, and error cases.

SAFETY: test citizens, forms, submissions, and their cascading rows are
deleted at module teardown. Facts/provenance created by tests attach to
test citizens only. Seeded data (7 schemes, dev form, 15 citizens) is
never modified.
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
from app.models.form import (
    FormCondition,
    FormDefinition,
    FormQuestion,
    FormQuestionOption,
    FormSection,
)

_TestSession = async_sessionmaker(
    create_async_engine(get_settings().DATABASE_URL, poolclass=NullPool),
    expire_on_commit=False,
)

SUFFIX = uuid.uuid4().hex[:8]
NORM_FORM = f"T2B_NORM_{SUFFIX}"
COND_FORM = f"T2B_COND_{SUFFIX}"


def _run(coro):
    return asyncio.run(coro)


# ------------------------------------------------------------------
# Form builders (profile_field values drive the registry)
# ------------------------------------------------------------------


async def _create_form(spec: dict) -> uuid.UUID:
    async with _TestSession() as session:
        form = FormDefinition(
            form_code=spec["form_code"],
            form_name=spec["form_name"],
            target_citizen_type=spec.get("target_citizen_type", "GENERAL"),
            version=spec.get("version", 1),
            status=spec.get("status", "ACTIVE"),
        )
        session.add(form)
        await session.flush()
        qid_by_code: dict[str, uuid.UUID] = {}
        for s_spec in spec["sections"]:
            section = FormSection(
                form_id=form.form_id,
                section_code=s_spec["section_code"],
                section_name=s_spec["section_name"],
                display_order=s_spec.get("display_order", 1),
            )
            session.add(section)
            await session.flush()
            for q_spec in s_spec.get("questions", []):
                question = FormQuestion(
                    section_id=section.section_id,
                    question_code=q_spec["question_code"],
                    question_text=q_spec["question_text"],
                    question_type=q_spec["question_type"],
                    data_type=q_spec.get("data_type", "STRING"),
                    required=q_spec.get("required", False),
                    display_order=q_spec.get("display_order", 1),
                    profile_field=q_spec.get("profile_field"),
                    validation_rule=q_spec.get("validation_rule"),
                )
                session.add(question)
                await session.flush()
                qid_by_code[q_spec["question_code"]] = question.question_id
                for o_spec in q_spec.get("options", []):
                    session.add(
                        FormQuestionOption(
                            question_id=question.question_id,
                            option_code=o_spec["option_code"],
                            option_label=o_spec.get("option_label", o_spec["option_code"]),
                            display_order=o_spec.get("display_order", 1),
                        )
                    )
        for s_spec in spec["sections"]:
            for q_spec in s_spec.get("questions", []):
                for c_spec in q_spec.get("conditions", []):
                    session.add(
                        FormCondition(
                            question_id=qid_by_code[q_spec["question_code"]],
                            depends_on_question_id=qid_by_code[c_spec["depends_on"]],
                            operator=c_spec["operator"],
                            comparison_value=c_spec.get("comparison_value"),
                            action=c_spec.get("action", "SHOW"),
                        )
                    )
        await session.commit()
        return form.form_id


def _norm_form_spec() -> dict:
    """Covers every canonical domain plus an unmapped question."""
    return {
        "form_code": NORM_FORM,
        "form_name": "Phase 2B Normalization Form",
        "sections": [
            {
                "section_code": "S1",
                "section_name": "S1",
                "questions": [
                    # Question with dotted mapping but a bad choice value:
                    # the answer is valid at the form layer, unmappable at
                    # normalization time (warning expected).
                    {
                        "question_code": "Q_GENDER",
                        "question_text": "Gender?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "profile_field": "demographic.gender",
                    },
                    {
                        "question_code": "Q_SOCIAL",
                        "question_text": "Social category?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "profile_field": "social_category",
                    },
                    {
                        "question_code": "Q_INCOME",
                        "question_text": "Annual income?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "profile_field": "financial.annual_income",
                    },
                    {
                        "question_code": "Q_STATE",
                        "question_text": "State?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "profile_field": "location.state",
                    },
                    {
                        "question_code": "Q_PINCODE",
                        "question_text": "Pincode?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "profile_field": "location.pincode",
                    },
                    {
                        "question_code": "Q_EDU",
                        "question_text": "Education level?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "profile_field": "education.education_level",
                    },
                    {
                        "question_code": "Q_EMP",
                        "question_text": "Employment status?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "profile_field": "employment.employment_status",
                    },
                    {
                        "question_code": "Q_FAMILY_SIZE",
                        "question_text": "Family size?",
                        "question_type": "number",
                        "data_type": "INTEGER",
                        "profile_field": "family_size",
                    },
                    {
                        "question_code": "Q_LAND",
                        "question_text": "Land holding (hectares)?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "profile_field": "land_holding_size",
                    },
                    {
                        "question_code": "Q_AADHAAR",
                        "question_text": "Has Aadhaar?",
                        "question_type": "boolean",
                        "data_type": "BOOLEAN",
                        "profile_field": "has_aadhaar",
                    },
                    {
                        "question_code": "Q_FAMILY",
                        "question_text": "Family members?",
                        "question_type": "text",
                        "data_type": "JSON",
                        "profile_field": "family_members",
                    },
                    {
                        "question_code": "Q_FAV_COLOR",
                        "question_text": "Favourite colour?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "profile_field": "favourite_colour",
                    },
                ],
            }
        ],
    }


def _conditional_norm_spec() -> dict:
    """DOB-driven conditional: Q_DOB feeds AGE derivation; Q_SPORT is
    shown only when Q_PLAYS_SPORT = YES (hidden required never blocks)."""
    return {
        "form_code": COND_FORM,
        "form_name": "Phase 2B Conditional Norm Form",
        "sections": [
            {
                "section_code": "S1",
                "section_name": "S1",
                "questions": [
                    {
                        "question_code": "Q_DOB",
                        "question_text": "Date of birth?",
                        "question_type": "date",
                        "data_type": "DATE",
                        "profile_field": "demographic.date_of_birth",
                    },
                    {
                        "question_code": "Q_PLAYS_SPORT",
                        "question_text": "Do you play sports?",
                        "question_type": "boolean",
                        "data_type": "BOOLEAN",
                        "required": True,
                    },
                    {
                        "question_code": "Q_SPORT",
                        "question_text": "Which sport?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "required": True,
                        "profile_field": "favourite_sport",
                        "conditions": [
                            {
                                "depends_on": "Q_PLAYS_SPORT",
                                "operator": "EQUALS",
                                "comparison_value": "YES",
                                "action": "SHOW",
                            }
                        ],
                    },
                ],
            }
        ],
    }


# ------------------------------------------------------------------
# Fixtures and helpers
# ------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def tracked():
    registry = {"citizen_ids": [], "form_ids": []}
    yield registry

    async def _cleanup():
        async with _TestSession() as session:
            if registry["citizen_ids"]:
                await session.execute(
                    text("DELETE FROM tbl_citizen_master WHERE citizen_id = ANY(:ids)"),
                    {"ids": registry["citizen_ids"]},
                )
            if registry["form_ids"]:
                await session.execute(
                    text("DELETE FROM tbl_form_definition WHERE form_id = ANY(:ids)"),
                    {"ids": registry["form_ids"]},
                )
            await session.commit()

    _run(_cleanup())


@pytest.fixture(scope="module", autouse=True)
def forms_env(client, tracked):
    tracked["form_ids"].append(_run(_create_form(_norm_form_spec())))
    tracked["form_ids"].append(_run(_create_form(_conditional_norm_spec())))


def _make_citizen(client, tracked, **overrides) -> uuid.UUID:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "full_name": f"Phase 2B Test {suffix}",
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


def _qid(client, form_code, question_code) -> uuid.UUID:
    detail = client.get(f"/api/v1/forms/{form_code}").json()
    for section in detail["sections"]:
        for q in section["questions"]:
            if q["question_code"] == question_code:
                return uuid.UUID(q["question_id"])
    raise AssertionError(f"{question_code} not found in {form_code}")


def _start_submission(client, citizen_id, form_code, answers=None) -> str:
    resp = client.post(
        f"/api/v1/forms/{form_code}/submissions",
        json={
            "citizen_id": str(citizen_id),
            "answers": answers or [],
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["submission_id"]


def _save(client, citizen_id, submission_id, answers) -> None:
    resp = client.put(
        f"/api/v1/forms/submissions/{submission_id}",
        json={"citizen_id": str(citizen_id), "answers": answers},
    )
    assert resp.status_code == 200, resp.text


def _complete(client, citizen_id, submission_id) -> None:
    resp = client.post(
        f"/api/v1/forms/submissions/{submission_id}/complete",
        json={"citizen_id": str(citizen_id)},
    )
    assert resp.status_code == 200, resp.text


def _normalize(client, citizen_id, submission_id):
    return client.post(
        f"/api/v1/forms/submissions/{submission_id}/normalize",
        json={"citizen_id": str(citizen_id)},
    )


def _completed_norm_submission(client, tracked, answers_by_code: dict) -> tuple[uuid.UUID, str]:
    """Create a citizen, fill the normalization form, complete it."""
    citizen_id = _make_citizen(client, tracked)
    answers = []
    for code, value in answers_by_code.items():
        answers.append({"question_id": str(_qid(client, NORM_FORM, code)), "value": value})
    sid = _start_submission(client, citizen_id, NORM_FORM, answers)
    _complete(client, citizen_id, sid)
    return citizen_id, sid


def _fetch_rows(query: str, params: dict) -> list[dict]:
    """Read-only verification queries via asyncpg (the installed driver).
    Converts SQLAlchemy-style :name placeholders to asyncpg $N positions."""
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
# Tests
# ------------------------------------------------------------------


class TestNormalizationHappyPath:
    def test_1_3_4_completed_submission_normalizes(self, client, tracked):
        citizen_id, sid = _completed_norm_submission(
            client,
            tracked,
            {
                "Q_GENDER": "MALE",
                "Q_SOCIAL": "OBC",
                "Q_INCOME": "₹2,40,000",
                "Q_STATE": "Maharashtra",
                "Q_PINCODE": "411001",
                "Q_EDU": "GRADUATE",
                "Q_EMP": "EMPLOYED",
                "Q_FAMILY_SIZE": 5,
                "Q_LAND": "1.5",
                "Q_AADHAAR": True,
            },
        )
        resp = _normalize(client, citizen_id, sid)
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["submission_id"] == str(sid)
        assert body["citizen_id"] == str(citizen_id)
        assert body["status"] == "NORMALIZED"
        assert set(body["profiles_updated"]) == {
            "demographic", "financial", "location", "education", "employment",
        }
        assert body["facts_created"] >= 8
        assert body["unmapped_answers"] == []

        # Facts: typed, deterministic
        facts = _fetch_rows(
            "SELECT fact_code, fact_value, data_type, source, verified FROM tbl_profile_fact "
            "WHERE citizen_id = :cid AND effective_until IS NULL",
            {"cid": citizen_id},
        )
        by_code = {f["fact_code"]: f for f in facts}
        assert by_code["ANNUAL_INCOME"]["fact_value"] == "240000"
        assert by_code["ANNUAL_INCOME"]["data_type"] == "DECIMAL"
        assert by_code["SOCIAL_CATEGORY"]["fact_value"] == "OBC"
        assert by_code["STATE"]["fact_value"] == "Maharashtra"
        assert by_code["PINCODE"]["fact_value"] == "411001"
        assert by_code["HAS_AADHAAR"]["data_type"] == "BOOLEAN"
        assert by_code["HAS_AADHAAR"]["fact_value"] == "TRUE"
        assert by_code["FAMILY_SIZE"]["fact_value"] == "5"
        assert by_code["FAMILY_SIZE"]["data_type"] == "INTEGER"
        assert by_code["LAND_HOLDING"]["fact_value"] == "1.5"

        # Domain profiles actually written
        fin = _fetch_rows(
            "SELECT annual_income, land_holding_size FROM tbl_financial_profile WHERE citizen_id = :cid",
            {"cid": citizen_id},
        )[0]
        assert float(fin["annual_income"]) == 240000.0
        assert float(fin["land_holding_size"]) == 1.5

        demo = _fetch_rows(
            "SELECT social_category, family_size FROM tbl_demographic_profile WHERE citizen_id = :cid",
            {"cid": citizen_id},
        )[0]
        assert demo["social_category"] == "OBC"
        assert demo["family_size"] == 5

        loc = _fetch_rows(
            "SELECT state FROM tbl_location_profile WHERE citizen_id = :cid",
            {"cid": citizen_id},
        )[0]
        assert loc["state"] == "Maharashtra"

    def test_5_provenance_created(self, client, tracked):
        citizen_id, sid = _completed_norm_submission(
            client, tracked, {"Q_STATE": "Karnataka", "Q_PINCODE": "560001"}
        )
        _normalize(client, citizen_id, sid)
        prov = _fetch_rows(
            """
            SELECT p.source_type, p.source_reference, p.form_answer_id,
                   p.verification_status
            FROM tbl_profile_fact_provenance p
            JOIN tbl_profile_fact f ON f.fact_id = p.fact_id
            WHERE f.citizen_id = :cid AND f.fact_code = 'STATE'
            """,
            {"cid": citizen_id},
        )
        assert len(prov) == 1
        assert prov[0]["source_type"] == "USER_INPUT"
        assert prov[0]["source_reference"] == f"FORM_SUBMISSION:{sid}"
        assert prov[0]["form_answer_id"] is not None
        assert prov[0]["verification_status"] == "PENDING"

    def test_7_derived_age(self, client, tracked):
        # Use the conditional form for DOB → AGE.
        citizen_id2 = _make_citizen(client, tracked)
        answers = [
            {"question_id": str(_qid(client, COND_FORM, "Q_DOB")), "value": "2005-05-10"},
            {"question_id": str(_qid(client, COND_FORM, "Q_PLAYS_SPORT")), "value": False},
        ]
        sid2 = _start_submission(client, citizen_id2, COND_FORM, answers)
        _complete(client, citizen_id2, sid2)
        resp = _normalize(client, citizen_id2, sid2)
        assert resp.status_code == 200
        facts = _fetch_rows(
            "SELECT fact_code, fact_value, data_type, source FROM tbl_profile_fact "
            "WHERE citizen_id = :cid AND effective_until IS NULL",
            {"cid": citizen_id2},
        )
        by_code = {f["fact_code"]: f for f in facts}
        assert "DATE_OF_BIRTH" in by_code
        assert by_code["DATE_OF_BIRTH"]["source"] == "USER_INPUT"
        assert by_code["DATE_OF_BIRTH"]["data_type"] == "DATE"
        assert by_code["DATE_OF_BIRTH"]["fact_value"] == "2005-05-10"
        assert "AGE" in by_code
        assert by_code["AGE"]["data_type"] == "INTEGER"
        assert by_code["AGE"]["source"] == "SYSTEM_DERIVED"
        expected_age = _expected_age("2005-05-10")
        assert by_code["AGE"]["fact_value"] == str(expected_age)

    def test_9_unmapped_answer_reported(self, client, tracked):
        citizen_id, sid = _completed_norm_submission(
            client, tracked, {"Q_FAV_COLOR": "Blue"}
        )
        resp = _normalize(client, citizen_id, sid)
        assert resp.status_code == 200
        body = resp.json()
        unmapped = body["unmapped_answers"]
        assert len(unmapped) == 1
        assert unmapped[0]["question_code"] == "Q_FAV_COLOR"
        assert unmapped[0]["profile_field"] == "favourite_colour"
        assert "reason" in unmapped[0]
        # Nothing was silently stored
        facts = _fetch_rows(
            "SELECT fact_code FROM tbl_profile_fact WHERE citizen_id = :cid",
            {"cid": citizen_id},
        )
        assert all(f["fact_code"] != "FAVOURITE_COLOUR" for f in facts)

    def test_10_invalid_mapping_rejected_with_warning(self, client, tracked):
        citizen_id, sid = _completed_norm_submission(
            client, tracked, {"Q_GENDER": "HELICOPTER"}
        )
        resp = _normalize(client, citizen_id, sid)
        assert resp.status_code == 200
        body = resp.json()
        assert any("Q_GENDER" in w for w in body["warnings"])
        facts = _fetch_rows(
            "SELECT fact_code FROM tbl_profile_fact WHERE citizen_id = :cid",
            {"cid": citizen_id},
        )
        assert all(f["fact_code"] != "GENDER" for f in facts)

    def test_11_family_members(self, client, tracked):
        family = [
            {"relationship": "SPOUSE", "name": "Sunita", "date_of_birth": "1998-03-03",
             "dependent_flag": True, "income": "₹1,20,000"},
            {"relationship": "SON", "name": "Aarav", "date_of_birth": "2020-01-01",
             "dependent_flag": True},
        ]
        citizen_id, sid = _completed_norm_submission(
            client, tracked, {"Q_FAMILY": family}
        )
        resp = _normalize(client, citizen_id, sid)
        assert resp.status_code == 200
        body = resp.json()
        assert body["family_members_created"] == 2
        assert "family_member" in body["profiles_updated"]

        members = _fetch_rows(
            "SELECT relationship, name, income, dependent_flag FROM tbl_family_member "
            "WHERE citizen_id = :cid ORDER BY relationship",
            {"cid": citizen_id},
        )
        assert len(members) == 2
        by_rel = {m["relationship"]: m for m in members}
        assert by_rel["SPOUSE"]["name"] == "Sunita"
        assert float(by_rel["SPOUSE"]["income"]) == 120000.0  # deterministic parse
        assert by_rel["SPOUSE"]["dependent_flag"] is True
        assert by_rel["SON"]["name"] == "Aarav"

    def test_14_normalization_response_shape(self, client, tracked):
        citizen_id, sid = _completed_norm_submission(
            client, tracked, {"Q_STATE": "Gujarat", "Q_PINCODE": "380001"}
        )
        resp = _normalize(client, citizen_id, sid)
        body = resp.json()
        for key in (
            "submission_id", "citizen_id", "status", "form_code", "form_version",
            "profiles_updated", "facts_created", "facts_updated", "facts_derived",
            "provenance_created", "family_members_created", "family_members_updated",
            "unmapped_answers", "warnings",
        ):
            assert key in body
        assert body["form_code"] == NORM_FORM
        assert body["form_version"] == 1


class TestIdempotency:
    def test_6_repeat_normalization_idempotent(self, client, tracked):
        citizen_id, sid = _completed_norm_submission(
            client, tracked,
            {
                "Q_STATE": "Rajasthan", "Q_PINCODE": "302001",
                "Q_INCOME": "200000", "Q_FAMILY_SIZE": 3,
                "Q_FAMILY": [{"relationship": "MOTHER", "name": "Kamla"}],
            },
        )
        first = _normalize(client, citizen_id, sid).json()
        assert first["facts_created"] >= 3
        assert first["family_members_created"] == 1

        second = _normalize(client, citizen_id, sid).json()
        assert second["status"] == "NORMALIZED"
        assert second["facts_created"] == 0
        assert second["facts_updated"] == 0
        assert second["facts_derived"] == 0
        assert second["provenance_created"] == 0
        assert second["family_members_created"] == 0
        assert second["family_members_updated"] == 0

        counts = _fetch_rows(
            """
            SELECT
              (SELECT COUNT(*) FROM tbl_profile_fact WHERE citizen_id = :cid) AS facts,
              (SELECT COUNT(*) FROM tbl_profile_fact_provenance p
                 JOIN tbl_profile_fact f ON f.fact_id = p.fact_id
                 WHERE f.citizen_id = :cid) AS provenance,
              (SELECT COUNT(*) FROM tbl_family_member WHERE citizen_id = :cid) AS members
            """,
            {"cid": citizen_id},
        )[0]
        assert counts["facts"] == first["facts_created"] + first["facts_derived"]
        assert counts["provenance"] == first["provenance_created"]
        assert counts["members"] == 1


class TestValueSemantics:
    def test_8_typed_values_remain_typed(self, client, tracked):
        citizen_id, sid = _completed_norm_submission(
            client, tracked,
            {"Q_INCOME": "250000.75", "Q_FAMILY_SIZE": 6, "Q_AADHAAR": False},
        )
        _normalize(client, citizen_id, sid)
        facts = _fetch_rows(
            "SELECT fact_code, fact_value, data_type FROM tbl_profile_fact "
            "WHERE citizen_id = :cid AND effective_until IS NULL",
            {"cid": citizen_id},
        )
        by_code = {f["fact_code"]: f for f in facts}
        assert by_code["ANNUAL_INCOME"]["fact_value"] == "250000.75"
        assert by_code["ANNUAL_INCOME"]["data_type"] == "DECIMAL"
        assert by_code["FAMILY_SIZE"]["fact_value"] == "6"
        assert by_code["FAMILY_SIZE"]["data_type"] == "INTEGER"
        assert by_code["HAS_AADHAAR"]["fact_value"] == "FALSE"

    def test_verified_fact_not_overwritten(self, client, tracked):
        from datetime import date

        citizen_id, sid = _completed_norm_submission(
            client, tracked, {"Q_INCOME": "999999"}
        )
        # First normalization creates the fact from user input.
        assert _normalize(client, citizen_id, sid).status_code == 200
        # Then a document source verifies a different value (500000).
        async def _seed_verified():
            async with _TestSession() as session:
                row = (
                    await session.execute(text(
                        "SELECT fact_id FROM tbl_profile_fact WHERE citizen_id = :cid "
                        "AND fact_code = 'ANNUAL_INCOME' AND effective_until IS NULL"
                    ), {"cid": citizen_id})
                ).scalar_one()
                await session.execute(text(
                    "UPDATE tbl_profile_fact SET fact_value = '500000', verified = TRUE, "
                    "source = 'DOCUMENT' WHERE fact_id = :fid"
                ), {"fid": row})
                await session.commit()

        _run(_seed_verified())
        resp = _normalize(client, citizen_id, sid)
        assert resp.status_code == 200
        body = resp.json()
        assert any("ANNUAL_INCOME" in w for w in body["warnings"])

        fact = _fetch_rows(
            "SELECT fact_value, verified FROM tbl_profile_fact "
            "WHERE citizen_id = :cid AND fact_code = 'ANNUAL_INCOME' AND effective_until IS NULL",
            {"cid": citizen_id},
        )[0]
        assert fact["fact_value"] == "500000"
        assert fact["verified"] is True


class TestErrors:
    def test_2_draft_rejected(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        sid = _start_submission(client, citizen_id, NORM_FORM, [])
        resp = _normalize(client, citizen_id, sid)
        assert resp.status_code == 409
        assert "COMPLETED" in resp.json()["detail"]["message"]

    def test_12_ownership(self, client, tracked):
        owner = _make_citizen(client, tracked)
        other = _make_citizen(client, tracked)
        sid = _completed_norm_submission(
            client, tracked, {"Q_STATE": "Goa", "Q_PINCODE": "403001"}
        )[1]
        # owner is the creator; other citizen must be rejected.
        resp = _normalize(client, other, sid)
        assert resp.status_code == 403

    def test_13_missing_submission(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        resp = _normalize(client, citizen_id, str(uuid.uuid4()))
        assert resp.status_code == 404


def _expected_age(dob_iso: str) -> int:
    from datetime import date

    dob = date.fromisoformat(dob_iso)
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
