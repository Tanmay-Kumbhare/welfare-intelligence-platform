"""
Phase 2A dynamic form API tests.

Covers form reads (list/detail/version/ordering/options/conditions), the
submission lifecycle (draft → save → complete), typed-answer validation,
conditional-question applicability, completion percentage math, and
form-version pinning.

SAFETY: all test forms/citizens are created with unique per-run names and
DELETED at module teardown (citizens first — their submissions/answers
cascade — then forms, which cascade their hierarchies). No test data
persists in the live database and the 7 seeded schemes are untouched.
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

SUFFIX = uuid.uuid4().hex[:8]  # unique per test run → deterministic cleanup

VALIDATION_FORM = f"T2A_VALIDATE_{SUFFIX}"
CONDITIONAL_FORM = f"T2A_COND_{SUFFIX}"
VERSIONED_FORM = f"T2A_VERSIONED_{SUFFIX}"
FOREIGN_FORM = f"T2A_FOREIGN_{SUFFIX}"


def _run(coro):
    """Run a setup/cleanup coroutine on its own short-lived event loop.

    Safe with NullPool: no connection ever outlives the helper's loop.
    """
    return asyncio.run(coro)


# ------------------------------------------------------------------
# Direct form builders (service-independent test data)
# ------------------------------------------------------------------


async def _create_form(spec: dict) -> uuid.UUID:
    async with _TestSession() as session:
        form = FormDefinition(
            form_code=spec["form_code"],
            form_name=spec["form_name"],
            description=spec.get("description"),
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
                status=s_spec.get("status", "ACTIVE"),
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
                            condition_group=c_spec.get("condition_group", 1),
                        )
                    )
        await session.commit()
        return form.form_id


def _validation_form_spec() -> dict:
    """One question per data_type, deliberately unordered display orders."""
    return {
        "form_code": VALIDATION_FORM,
        "form_name": "Phase 2A Validation Form",
        "sections": [
            {
                "section_code": "SEC_B",
                "section_name": "Section B",
                "display_order": 2,
                "questions": [
                    {
                        "question_code": "Q_DECIMAL",
                        "question_text": "Decimal?",
                        "question_type": "decimal",
                        "data_type": "DECIMAL",
                        "required": True,
                        "display_order": 2,
                        "validation_rule": {"min": 0},
                    },
                    {
                        "question_code": "Q_TEXT",
                        "question_text": "Text?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "required": True,
                        "display_order": 1,
                        "validation_rule": {"max_length": 50},
                    },
                ],
            },
            {
                "section_code": "SEC_A",
                "section_name": "Section A",
                "display_order": 1,
                "questions": [
                    {
                        "question_code": "Q_NUMBER",
                        "question_text": "Number?",
                        "question_type": "number",
                        "data_type": "INTEGER",
                        "required": True,
                        "display_order": 3,
                        "validation_rule": {"min": 1, "max": 30},
                    },
                    {
                        "question_code": "Q_BOOL",
                        "question_text": "Boolean?",
                        "question_type": "boolean",
                        "data_type": "BOOLEAN",
                        "required": True,
                        "display_order": 2,
                    },
                ],
            },
            {
                "section_code": "SEC_C",
                "section_name": "Section C",
                "display_order": 3,
                "questions": [
                    {
                        "question_code": "Q_DATE",
                        "question_text": "Date?",
                        "question_type": "date",
                        "data_type": "DATE",
                        "required": True,
                        "display_order": 1,
                    },
                    {
                        "question_code": "Q_CHOICE",
                        "question_text": "Choice?",
                        "question_type": "dropdown",
                        "data_type": "STRING",
                        "required": False,
                        "display_order": 2,
                        "options": [
                            {"option_code": "OPT_A", "display_order": 2},
                            {"option_code": "OPT_B", "display_order": 1},
                        ],
                    },
                    {
                        "question_code": "Q_MULTI",
                        "question_text": "Multi?",
                        "question_type": "multi_choice",
                        "data_type": "STRING",
                        "required": False,
                        "display_order": 3,
                        "options": [
                            {"option_code": "X", "display_order": 1},
                            {"option_code": "Y", "display_order": 2},
                            {"option_code": "Z", "display_order": 3},
                        ],
                    },
                    {
                        "question_code": "Q_EMAIL",
                        "question_text": "Email?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "required": False,
                        "display_order": 4,
                        "validation_rule": {"email": True},
                    },
                ],
            },
        ],
    }


def _conditional_form_spec() -> dict:
    """Q_COURSE is required but visible only when Q_STUDY == YES."""
    return {
        "form_code": CONDITIONAL_FORM,
        "form_name": "Phase 2A Conditional Form",
        "sections": [
            {
                "section_code": "S1",
                "section_name": "S1",
                "questions": [
                    {
                        "question_code": "Q_STUDY",
                        "question_text": "Studying?",
                        "question_type": "boolean",
                        "data_type": "BOOLEAN",
                        "required": True,
                    },
                    {
                        "question_code": "Q_COURSE",
                        "question_text": "Course?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "required": True,
                        "conditions": [
                            {
                                "depends_on": "Q_STUDY",
                                "operator": "EQUALS",
                                "comparison_value": "YES",
                                "action": "SHOW",
                            }
                        ],
                    },
                    {
                        "question_code": "Q_ALWAYS",
                        "question_text": "Always required?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "required": True,
                    },
                ],
            }
        ],
    }


def _versioned_spec(version: int, question_code: str) -> dict:
    return {
        "form_code": VERSIONED_FORM,
        "form_name": "Phase 2A Versioned Form",
        "version": version,
        "sections": [
            {
                "section_code": "S1",
                "section_name": "S1",
                "questions": [
                    {
                        "question_code": question_code,
                        "question_text": f"{question_code}?",
                        "question_type": "text",
                        "data_type": "STRING",
                        "required": True,
                    }
                ],
            }
        ],
    }


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def tracked():
    """Registry of rows created by this module, deleted at teardown."""
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
    """Create every test form exactly once for the whole module."""
    tracked["form_ids"].append(_run(_create_form(_validation_form_spec())))
    tracked["form_ids"].append(_run(_create_form(_conditional_form_spec())))
    tracked["form_ids"].append(_run(_create_form(_versioned_spec(1, "Q_V1"))))
    tracked["form_ids"].append(_run(_create_form(_versioned_spec(2, "Q_V2"))))


def _make_citizen(client: TestClient, tracked: dict) -> uuid.UUID:
    suffix = uuid.uuid4().hex[:8]
    resp = client.post(
        "/api/v1/citizens/",
        json={
            "full_name": f"Phase 2A Test {suffix}",
            "date_of_birth": "1995-04-04",
            "gender": "MALE",
            "citizen_type": "GENERAL",
            "demographic": {"family_size": 3, "social_category": "GEN"},
            "financial": {"annual_income": 150000, "poverty_category": "APL"},
            "location": {"state": "Maharashtra", "district": "Pune", "area_type": "URBAN"},
        },
    )
    assert resp.status_code == 201, resp.text
    citizen_id = resp.json()["citizen_id"]
    tracked["citizen_ids"].append(citizen_id)
    return citizen_id


def _qid(client: TestClient, form_code: str, question_code: str) -> uuid.UUID:
    detail = client.get(f"/api/v1/forms/{form_code}").json()
    for section in detail["sections"]:
        for q in section["questions"]:
            if q["question_code"] == question_code:
                return uuid.UUID(q["question_id"])
    raise AssertionError(f"{question_code} not found in {form_code}")


def _version_qid(client: TestClient, version: int, question_code: str) -> uuid.UUID:
    detail = client.get(f"/api/v1/forms/{VERSIONED_FORM}/versions/{version}").json()
    for section in detail["sections"]:
        for q in section["questions"]:
            if q["question_code"] == question_code:
                return uuid.UUID(q["question_id"])
    raise AssertionError(f"{question_code} not found in version {version}")


# ------------------------------------------------------------------
# FORM READ tests (17.1 – 17.9)
# ------------------------------------------------------------------


class TestFormReads:
    def test_list_active_forms(self, client):
        resp = client.get("/api/v1/forms/")
        assert resp.status_code == 200
        codes = [f["form_code"] for f in resp.json()]
        assert "GENERAL_CITIZEN_PROFILE" in codes  # seeded dev form visible

    def test_list_returns_latest_active_version_only(self, client):
        resp = client.get("/api/v1/forms/")
        versioned = [
            f for f in resp.json() if f["form_code"] == VERSIONED_FORM
        ]
        assert len(versioned) == 1
        assert versioned[0]["version"] == 2
        assert versioned[0]["status"] == "ACTIVE"

    def test_get_form_hierarchy(self, client):
        resp = client.get(f"/api/v1/forms/{VALIDATION_FORM}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["form_code"] == VALIDATION_FORM
        assert body["version"] == 1
        assert len(body["sections"]) == 3
        flat = [q for s in body["sections"] for q in s["questions"]]
        assert len(flat) == 8

    def test_get_specific_version(self, client):
        v1 = client.get(f"/api/v1/forms/{VERSIONED_FORM}/versions/1")
        assert v1.status_code == 200
        codes = [
            q["question_code"] for s in v1.json()["sections"] for q in s["questions"]
        ]
        assert codes == ["Q_V1"]

        v2 = client.get(f"/api/v1/forms/{VERSIONED_FORM}/versions/2")
        codes2 = [
            q["question_code"] for s in v2.json()["sections"] for q in s["questions"]
        ]
        assert codes2 == ["Q_V2"]

    def test_get_invalid_form(self, client):
        resp = client.get(f"/api/v1/forms/DOES_NOT_EXIST_{SUFFIX}")
        assert resp.status_code == 404
        assert resp.json()["detail"]["message"]

    def test_get_invalid_version(self, client):
        resp = client.get(f"/api/v1/forms/{VERSIONED_FORM}/versions/99")
        assert resp.status_code == 404

    def test_sections_and_questions_ordered(self, client):
        body = client.get(f"/api/v1/forms/{VALIDATION_FORM}").json()
        section_orders = [s["display_order"] for s in body["sections"]]
        assert section_orders == sorted(section_orders)
        # SEC_A (order 1) was seeded second — proves sorting is applied.
        assert [s["section_code"] for s in body["sections"]] == [
            "SEC_A", "SEC_B", "SEC_C",
        ]
        sec_b = next(s for s in body["sections"] if s["section_code"] == "SEC_B")
        q_orders = [q["display_order"] for q in sec_b["questions"]]
        assert q_orders == sorted(q_orders)

    def test_options_returned_and_ordered(self, client):
        body = client.get(f"/api/v1/forms/{VALIDATION_FORM}").json()
        choice = next(
            q for s in body["sections"] for q in s["questions"]
            if q["question_code"] == "Q_CHOICE"
        )
        assert [o["option_code"] for o in choice["options"]] == ["OPT_B", "OPT_A"]

        multi = next(
            q for s in body["sections"] for q in s["questions"]
            if q["question_code"] == "Q_MULTI"
        )
        assert [o["option_code"] for o in multi["options"]] == ["X", "Y", "Z"]

    def test_conditions_returned_with_codes(self, client):
        body = client.get(f"/api/v1/forms/{CONDITIONAL_FORM}").json()
        course = next(
            q for s in body["sections"] for q in s["questions"]
            if q["question_code"] == "Q_COURSE"
        )
        assert len(course["conditions"]) == 1
        cond = course["conditions"][0]
        assert cond["operator"] == "EQUALS"
        assert cond["comparison_value"] == "YES"
        assert cond["action"] == "SHOW"
        assert cond["depends_on_question_code"] == "Q_STUDY"

    def test_validation_metadata_exposed(self, client):
        body = client.get(f"/api/v1/forms/{VALIDATION_FORM}").json()
        number_q = next(
            q for s in body["sections"] for q in s["questions"]
            if q["question_code"] == "Q_NUMBER"
        )
        assert number_q["validation_rule"] == {"min": 1, "max": 30}
        assert number_q["required"] is True
        assert number_q["data_type"] == "INTEGER"
        assert number_q["question_type"] == "number"


# ------------------------------------------------------------------
# SUBMISSION lifecycle tests (17.10 – 17.14)
# ------------------------------------------------------------------


class TestSubmissionLifecycle:
    def _qids(self, client):
        return {
            c: _qid(client, VALIDATION_FORM, c)
            for c in ("Q_TEXT", "Q_NUMBER", "Q_BOOL", "Q_DATE")
        }

    def test_10_create_draft(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        resp = client.post(
            f"/api/v1/forms/{VALIDATION_FORM}/submissions",
            json={"citizen_id": str(citizen_id)},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "DRAFT"
        assert body["completion_percentage"] == 0
        assert body["form_version"] == 1
        assert body["applicable_questions"] == 8
        assert body["answers"] == []
        assert body["form_code"] == VALIDATION_FORM

    def test_11_save_valid_typed_answers(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        q = self._qids(client)
        sid = client.post(
            f"/api/v1/forms/{VALIDATION_FORM}/submissions",
            json={"citizen_id": str(citizen_id)},
        ).json()["submission_id"]

        resp = client.put(
            f"/api/v1/forms/submissions/{sid}",
            json={
                "citizen_id": str(citizen_id),
                "answers": [
                    {"question_id": str(q["Q_TEXT"]), "value": "Test User"},
                    {"question_id": str(q["Q_NUMBER"]), "value": 4},
                    {"question_id": str(q["Q_BOOL"]), "value": True},
                    {"question_id": str(q["Q_DATE"]), "value": "2001-02-03"},
                ],
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "IN_PROGRESS"
        by_code = {a["question_code"]: a for a in body["answers"]}
        assert by_code["Q_TEXT"]["answer_text"] == "Test User"
        assert by_code["Q_NUMBER"]["answer_number"] == 4
        assert by_code["Q_BOOL"]["answer_boolean"] is True
        assert by_code["Q_DATE"]["answer_date"] == "2001-02-03"
        # 4 of 8 applicable answered → 50%
        assert body["completion_percentage"] == 50

    def test_12_update_answer_overwrites_no_duplicates(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        q_text = _qid(client, VALIDATION_FORM, "Q_TEXT")
        sid = client.post(
            f"/api/v1/forms/{VALIDATION_FORM}/submissions",
            json={"citizen_id": str(citizen_id)},
        ).json()["submission_id"]
        client.put(
            f"/api/v1/forms/submissions/{sid}",
            json={
                "citizen_id": str(citizen_id),
                "answers": [{"question_id": str(q_text), "value": "First"}],
            },
        )
        resp = client.put(
            f"/api/v1/forms/submissions/{sid}",
            json={
                "citizen_id": str(citizen_id),
                "answers": [{"question_id": str(q_text), "value": "Second"}],
            },
        )
        assert resp.status_code == 200
        answers = resp.json()["answers"]
        assert len(answers) == 1  # one row, not two
        assert answers[0]["answer_text"] == "Second"

    def test_13_retrieve_submission(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        q_bool = _qid(client, VALIDATION_FORM, "Q_BOOL")
        sid = client.post(
            f"/api/v1/forms/{VALIDATION_FORM}/submissions",
            json={
                "citizen_id": str(citizen_id),
                "answers": [{"question_id": str(q_bool), "value": False}],
            },
        ).json()["submission_id"]

        resp = client.get(
            f"/api/v1/forms/submissions/{sid}",
            params={"citizen_id": str(citizen_id)},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["submission_id"] == sid
        assert body["form_code"] == VALIDATION_FORM
        assert body["status"] == "IN_PROGRESS"
        assert body["answers"][0]["question_code"] == "Q_BOOL"
        assert body["answers"][0]["answer_boolean"] is False

    def test_14_resume_returns_same_submission(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        q_text = _qid(client, VALIDATION_FORM, "Q_TEXT")
        first = client.post(
            f"/api/v1/forms/{VALIDATION_FORM}/submissions",
            json={
                "citizen_id": str(citizen_id),
                "answers": [{"question_id": str(q_text), "value": "Keep me"}],
            },
        ).json()
        second = client.post(
            f"/api/v1/forms/{VALIDATION_FORM}/submissions",
            json={"citizen_id": str(citizen_id)},
        ).json()
        assert second["submission_id"] == first["submission_id"]
        assert [a["question_code"] for a in second["answers"]] == ["Q_TEXT"]


# ------------------------------------------------------------------
# ANSWER VALIDATION tests (17.15 – 17.18, 17.22)
# ------------------------------------------------------------------


class TestAnswerValidation:
    @pytest.fixture()
    def ctx(self, client, tracked):
        """Fresh citizen + submission per test; one qid lookup."""
        citizen_id = _make_citizen(client, tracked)
        codes = (
            "Q_TEXT", "Q_NUMBER", "Q_BOOL", "Q_DATE",
            "Q_DECIMAL", "Q_CHOICE", "Q_MULTI", "Q_EMAIL",
        )
        qids = {c: _qid(client, VALIDATION_FORM, c) for c in codes}
        sid = client.post(
            f"/api/v1/forms/{VALIDATION_FORM}/submissions",
            json={"citizen_id": str(citizen_id)},
        ).json()["submission_id"]
        return {
            "sid": sid,
            "citizen_id": citizen_id,
            "qids": qids,
            "submission_url": f"/api/v1/forms/submissions/{sid}",
            "owner": {"citizen_id": str(citizen_id)},
        }

    def _put(self, client, ctx, pairs):
        return client.put(
            ctx["submission_url"],
            json={
                **ctx["owner"],
                "answers": [
                    {"question_id": str(qid), "value": value} for qid, value in pairs
                ],
            },
        )

    def test_15_valid_typed_answers(self, client, ctx):
        resp = self._put(
            client, ctx,
            [
                (ctx["qids"]["Q_DECIMAL"], 250000.5),
                (ctx["qids"]["Q_EMAIL"], "user@example.com"),
            ],
        )
        assert resp.status_code == 200, resp.text
        by_code = {a["question_code"]: a for a in resp.json()["answers"]}
        assert by_code["Q_DECIMAL"]["answer_decimal"] == 250000.5
        assert by_code["Q_EMAIL"]["answer_text"] == "user@example.com"

    def test_16_boolean_question_rejects_string(self, client, ctx):
        resp = self._put(client, ctx, [(ctx["qids"]["Q_BOOL"], "yes")])
        assert resp.status_code == 422
        assert "boolean" in resp.json()["detail"]["message"].lower()

    def test_16b_integer_question_rejects_fraction(self, client, ctx):
        resp = self._put(client, ctx, [(ctx["qids"]["Q_NUMBER"], 4.5)])
        assert resp.status_code == 422

    def test_16c_date_question_rejects_bad_format(self, client, ctx):
        resp = self._put(client, ctx, [(ctx["qids"]["Q_DATE"], "03-02-2001")])
        assert resp.status_code == 422

    def test_16d_numeric_min_rule_enforced(self, client, ctx):
        resp = self._put(client, ctx, [(ctx["qids"]["Q_NUMBER"], 0)])
        assert resp.status_code == 422
        assert ">=" in resp.json()["detail"]["message"]

    def test_16e_email_rule_enforced(self, client, ctx):
        resp = self._put(client, ctx, [(ctx["qids"]["Q_EMAIL"], "not-an-email")])
        assert resp.status_code == 422

    def test_16f_string_max_length_enforced(self, client, ctx):
        resp = self._put(client, ctx, [(ctx["qids"]["Q_TEXT"], "x" * 51)])
        assert resp.status_code == 422

    def test_17_invalid_option_rejected(self, client, ctx):
        resp = self._put(client, ctx, [(ctx["qids"]["Q_CHOICE"], "NOPE")])
        assert resp.status_code == 422
        assert "OPT_A" in resp.json()["detail"]["message"]

    def test_17b_invalid_multi_choice_member_rejected(self, client, ctx):
        resp = self._put(client, ctx, [(ctx["qids"]["Q_MULTI"], ["X", "W"])])
        assert resp.status_code == 422

    def test_17c_valid_multi_choice_stored_as_json(self, client, ctx):
        resp = self._put(client, ctx, [(ctx["qids"]["Q_MULTI"], ["X", "Z"])])
        assert resp.status_code == 200
        multi = next(
            a for a in resp.json()["answers"] if a["question_code"] == "Q_MULTI"
        )
        assert multi["answer_json"] == ["X", "Z"]

    def test_17d_invalid_source_rejected(self, client, ctx):
        resp = client.put(
            ctx["submission_url"],
            json={
                **ctx["owner"],
                "answers": [
                    {
                        "question_id": str(ctx["qids"]["Q_TEXT"]),
                        "value": "x",
                        "source": "TELEPATHY",
                    }
                ],
            },
        )
        assert resp.status_code == 422

    def test_18_question_from_another_form_rejected(self, client, tracked, ctx):
        # Throwaway foreign form, looked up via the API, then deleted.
        _run(_create_form({
            "form_code": FOREIGN_FORM,
            "form_name": "Foreign",
            "sections": [{
                "section_code": "S",
                "section_name": "S",
                "questions": [{
                    "question_code": "Q_FOREIGN",
                    "question_text": "Foreign?",
                    "question_type": "text",
                    "data_type": "STRING",
                }],
            }],
        }))
        foreign_form_id = None
        try:
            foreign = client.get(f"/api/v1/forms/{FOREIGN_FORM}").json()
            foreign_qid = next(
                uuid.UUID(q["question_id"])
                for s in foreign["sections"]
                for q in s["questions"]
            )
            resp = self._put(client, ctx, [(foreign_qid, "infiltrating")])
            assert resp.status_code == 422
            assert "belong" in resp.json()["detail"]["message"].lower()
        finally:
            async def _drop():
                async with _TestSession() as session:
                    await session.execute(
                        text("DELETE FROM tbl_form_definition WHERE form_code = :c"),
                        {"c": FOREIGN_FORM},
                    )
                    await session.commit()

            _run(_drop())

    def test_22_incomplete_draft_allowed(self, client, ctx):
        resp = self._put(client, ctx, [(ctx["qids"]["Q_TEXT"], "Partial")])
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "IN_PROGRESS"
        assert 0 < body["completion_percentage"] < 100

    def test_clear_saved_answer_with_null(self, client, ctx):
        self._put(client, ctx, [(ctx["qids"]["Q_TEXT"], "Temporary")])
        resp = self._put(client, ctx, [(ctx["qids"]["Q_TEXT"], None)])
        assert resp.status_code == 200
        assert all(a["question_code"] != "Q_TEXT" for a in resp.json()["answers"])


# ------------------------------------------------------------------
# COMPLETION + CONDITIONAL tests (17.19 – 17.21, 17.23 – 17.24)
# ------------------------------------------------------------------


class TestCompletionAndConditions:
    def _start(self, client, tracked):
        """Fresh citizen + editable submission per test (no resume bleed)."""
        citizen_id = _make_citizen(client, tracked)
        sid = client.post(
            f"/api/v1/forms/{CONDITIONAL_FORM}/submissions",
            json={"citizen_id": str(citizen_id)},
        ).json()["submission_id"]
        return citizen_id, sid

    def _put(self, client, citizen_id, sid, pairs):
        return client.put(
            f"/api/v1/forms/submissions/{sid}",
            json={
                "citizen_id": str(citizen_id),
                "answers": [
                    {"question_id": str(_qid(client, CONDITIONAL_FORM, code)), "value": value}
                    for code, value in pairs
                ],
            },
        )

    def _complete(self, client, citizen_id, sid):
        return client.post(
            f"/api/v1/forms/submissions/{sid}/complete",
            json={"citizen_id": str(citizen_id)},
        )

    def test_19_missing_required_listed_on_completion(self, client, tracked):
        citizen_id, sid = self._start(client, tracked)
        self._put(client, citizen_id, sid, [("Q_STUDY", False)])
        resp = self._complete(client, citizen_id, sid)
        assert resp.status_code == 422
        # Q_COURSE is hidden (Q_STUDY=NO) → only Q_ALWAYS is missing.
        assert resp.json()["detail"]["missing_required"] == ["Q_ALWAYS"]

    def test_20_hidden_conditional_required_does_not_block(self, client, tracked):
        citizen_id, sid = self._start(client, tracked)
        put = self._put(
            client, citizen_id, sid, [("Q_STUDY", False), ("Q_ALWAYS", "N/A")]
        )
        body = put.json()
        # Hidden Q_COURSE excluded from the denominator: 2/2 applicable.
        assert body["applicable_questions"] == 2
        assert body["answered_questions"] == 2
        assert body["completion_percentage"] == 100
        assert body["missing_required"] == []

        complete = self._complete(client, citizen_id, sid)
        assert complete.status_code == 200
        assert complete.json()["status"] == "COMPLETED"
        assert complete.json()["completed_at"] is not None

    def test_21_visible_conditional_required_blocks(self, client, tracked):
        citizen_id, sid = self._start(client, tracked)
        put = self._put(
            client, citizen_id, sid, [("Q_STUDY", True), ("Q_ALWAYS", "Done")]
        )
        body = put.json()
        # Q_COURSE now visible: 3 applicable, 2 answered → 67%.
        assert body["applicable_questions"] == 3
        assert body["completion_percentage"] == 67
        assert body["missing_required"] == ["Q_COURSE"]

        complete = self._complete(client, citizen_id, sid)
        assert complete.status_code == 422
        assert complete.json()["detail"]["missing_required"] == ["Q_COURSE"]

        # Answering the conditional question unblocks completion.
        self._put(client, citizen_id, sid, [("Q_COURSE", "B.Tech")])
        complete2 = self._complete(client, citizen_id, sid)
        assert complete2.status_code == 200
        assert complete2.json()["status"] == "COMPLETED"

    def test_23_completion_percentage_applicable_only(self, client, tracked):
        citizen_id, sid = self._start(client, tracked)
        put = self._put(client, citizen_id, sid, [("Q_STUDY", True)])
        # 1 of 3 applicable → 33% (not 1 of 3 hidden-adjusted).
        assert put.json()["completion_percentage"] == 33
        assert put.json()["applicable_questions"] == 3

    def test_completed_submission_not_editable(self, client, tracked):
        citizen_id, sid = self._start(client, tracked)
        self._put(client, citizen_id, sid, [("Q_STUDY", False), ("Q_ALWAYS", "Done")])
        assert self._complete(client, citizen_id, sid).status_code == 200

        put = self._put(client, citizen_id, sid, [("Q_ALWAYS", "Changed")])
        assert put.status_code == 409

        again = self._complete(client, citizen_id, sid)
        assert again.status_code == 409


# ------------------------------------------------------------------
# VERSION PINNING test (17.25)
# ------------------------------------------------------------------


class TestVersionPinning:
    def test_submission_stays_on_its_form_version(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        created = client.post(
            f"/api/v1/forms/{VERSIONED_FORM}/submissions",
            json={"citizen_id": str(citizen_id)},
        ).json()
        assert created["form_version"] == 2  # latest active version
        sid = created["submission_id"]
        q_v2 = _qid(client, VERSIONED_FORM, "Q_V2")

        # v3 of the same form_code appears after the submission started.
        v3_id = _run(_create_form(_versioned_spec(3, "Q_V3")))
        tracked["form_ids"].append(v3_id)

        # v1's question id is rejected — not part of the pinned version.
        q_v1 = _version_qid(client, 1, "Q_V1")
        put_v1 = client.put(
            f"/api/v1/forms/submissions/{sid}",
            json={
                "citizen_id": str(citizen_id),
                "answers": [{"question_id": str(q_v1), "value": "old version"}],
            },
        )
        assert put_v1.status_code == 422

        # v3's question id is rejected too.
        q_v3 = _version_qid(client, 3, "Q_V3")
        put_v3 = client.put(
            f"/api/v1/forms/submissions/{sid}",
            json={
                "citizen_id": str(citizen_id),
                "answers": [{"question_id": str(q_v3), "value": "new version"}],
            },
        )
        assert put_v3.status_code == 422

        # The pinned v2 question still saves, and version stays 2.
        put_v2 = client.put(
            f"/api/v1/forms/submissions/{sid}",
            json={
                "citizen_id": str(citizen_id),
                "answers": [{"question_id": str(q_v2), "value": "correct version"}],
            },
        )
        assert put_v2.status_code == 200
        assert put_v2.json()["form_version"] == 2


# ------------------------------------------------------------------
# SUBMISSION error handling (Part 11)
# ------------------------------------------------------------------


class TestSubmissionErrors:
    def test_submission_for_unknown_citizen(self, client):
        resp = client.post(
            f"/api/v1/forms/{VALIDATION_FORM}/submissions",
            json={"citizen_id": str(uuid.uuid4())},
        )
        assert resp.status_code == 404

    def test_submission_for_unknown_form(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        resp = client.post(
            f"/api/v1/forms/NO_SUCH_FORM_{SUFFIX}/submissions",
            json={"citizen_id": str(citizen_id)},
        )
        assert resp.status_code == 404

    def test_ownership_enforced(self, client, tracked):
        owner = _make_citizen(client, tracked)
        other = _make_citizen(client, tracked)
        sid = client.post(
            f"/api/v1/forms/{VALIDATION_FORM}/submissions",
            json={"citizen_id": str(owner)},
        ).json()["submission_id"]

        get = client.get(
            f"/api/v1/forms/submissions/{sid}", params={"citizen_id": str(other)}
        )
        assert get.status_code == 403

        put = client.put(
            f"/api/v1/forms/submissions/{sid}",
            json={"citizen_id": str(other), "answers": []},
        )
        assert put.status_code == 403

        complete = client.post(
            f"/api/v1/forms/submissions/{sid}/complete",
            json={"citizen_id": str(other)},
        )
        assert complete.status_code == 403

    def test_missing_submission_404(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        resp = client.get(
            f"/api/v1/forms/submissions/{uuid.uuid4()}",
            params={"citizen_id": str(citizen_id)},
        )
        assert resp.status_code == 404

    def test_invalid_status_via_update_rejected(self, client, tracked):
        citizen_id = _make_citizen(client, tracked)
        sid = client.post(
            f"/api/v1/forms/{VALIDATION_FORM}/submissions",
            json={"citizen_id": str(citizen_id)},
        ).json()["submission_id"]
        resp = client.put(
            f"/api/v1/forms/submissions/{sid}",
            json={"citizen_id": str(citizen_id), "status": "COMPLETED", "answers": []},
        )
        assert resp.status_code == 409
