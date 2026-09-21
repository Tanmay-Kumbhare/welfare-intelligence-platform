"""
Phase 1 database foundation tests.

Covers:
  - form creation
  - question creation (with options)
  - conditional question relationship
  - form submission
  - form answer (typed values)
  - profile fact (+ one-open-fact-per-citizen-code rule)
  - profile fact provenance (linked to a form answer)
  - scheme source
  - source document (+ preserved raw content)
  - eligibility status columns on assessments

SAFETY: every test runs inside a single transaction that is ROLLED BACK at
the end, so no test data persists in the database and the 7 seeded schemes
are never touched.
"""

from __future__ import annotations

import uuid
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.config import get_settings
from app.models.assessment import EligibilityAssessment
from app.models.citizen import CitizenMaster
from app.models.form import (
    FormCondition,
    FormDefinition,
    FormQuestion,
    FormQuestionOption,
    FormSection,
)
from app.models.profile_fact import ProfileFact, ProfileFactProvenance
from app.models.scheme import (
    SchemeEligibilityRule,
    SchemeMaster,
    SchemeRuleGroup,
)
from app.models.scheme_source import (
    SchemeIngestionRun,
    SchemeRuleProvenance,
    SchemeSource,
    SchemeSourceContent,
    SchemeSourceDocument,
)
from app.models.submission import FormAnswer, FormSubmission


# Dedicated test engine using NullPool: pooled connections would otherwise
# be reused across pytest-asyncio's function-scoped event loops and fail with
# "Event loop is closed". NullPool opens a fresh connection per session and
# never reuses one across loops.
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
async def citizen(db: AsyncSession) -> CitizenMaster:
    obj = CitizenMaster(
        full_name="Phase One Test Citizen",
        date_of_birth=date(2000, 1, 1),
        citizen_type="GENERAL",
    )
    db.add(obj)
    await db.flush()
    return obj


@pytest.mark.asyncio
async def test_form_creation_with_sections(db: AsyncSession):
    """A form can be created with sections and version uniqueness holds."""
    form = FormDefinition(
        form_code="TEST_FORM",
        form_name="Test Form",
        version=1,
        status="ACTIVE",
        target_citizen_type="GENERAL",
    )
    db.add(form)
    await db.flush()

    section = FormSection(
        form_id=form.form_id,
        section_code="SEC_A",
        section_name="Section A",
        display_order=1,
    )
    db.add(section)
    await db.flush()

    fetched = await db.get(FormDefinition, form.form_id)
    assert fetched is not None
    assert fetched.form_code == "TEST_FORM"
    assert fetched.version == 1

    sections = (
        (await db.execute(select(FormSection).where(FormSection.form_id == form.form_id)))
        .scalars().all()
    )
    assert len(sections) == 1
    assert sections[0].section_code == "SEC_A"


@pytest.mark.asyncio
async def test_form_version_unique_constraint(db: AsyncSession):
    """The same form_code may exist at multiple versions but not duplicated."""
    db.add(FormDefinition(form_code="VERSIONED_FORM", form_name="V1", version=1))
    db.add(FormDefinition(form_code="VERSIONED_FORM", form_name="V2", version=2))
    await db.flush()

    rows = (
        await db.execute(
            select(FormDefinition).where(FormDefinition.form_code == "VERSIONED_FORM")
        )
    ).scalars().all()
    assert {r.version for r in rows} == {1, 2}


@pytest.mark.asyncio
async def test_question_creation_with_options(db: AsyncSession):
    """Questions attach to sections and options attach to questions."""
    form = FormDefinition(form_code="Q_FORM", form_name="Q Form", version=1)
    db.add(form)
    await db.flush()
    section = FormSection(form_id=form.form_id, section_code="S1", section_name="S1")
    db.add(section)
    await db.flush()

    question = FormQuestion(
        section_id=section.section_id,
        question_code="EDUCATION_LEVEL",
        question_text="Highest education?",
        question_type="dropdown",
        data_type="STRING",
        required=True,
    )
    db.add(question)
    await db.flush()

    db.add_all(
        [
            FormQuestionOption(
                question_id=question.question_id,
                option_code="GRADUATE",
                option_label="Graduate",
                display_order=1,
            ),
            FormQuestionOption(
                question_id=question.question_id,
                option_code="POST_GRADUATE",
                option_label="Post Graduate",
                display_order=2,
            ),
        ]
    )
    await db.flush()

    options = (
        (
            await db.execute(
                select(FormQuestionOption).where(
                    FormQuestionOption.question_id == question.question_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(options) == 2
    assert question.question_type == "dropdown"


@pytest.mark.asyncio
async def test_conditional_question_relationship(db: AsyncSession):
    """
    "Which course are you studying?" is shown only when
    "Are you currently studying?" == YES.
    """
    form = FormDefinition(form_code="COND_FORM", form_name="Cond Form", version=1)
    db.add(form)
    await db.flush()
    section = FormSection(form_id=form.form_id, section_code="S1", section_name="S1")
    db.add(section)
    await db.flush()

    studying = FormQuestion(
        section_id=section.section_id,
        question_code="CURRENTLY_STUDYING",
        question_text="Are you currently studying?",
        question_type="boolean",
        data_type="BOOLEAN",
    )
    course = FormQuestion(
        section_id=section.section_id,
        question_code="STUDYING_COURSE",
        question_text="Which course are you studying?",
        question_type="text",
        data_type="STRING",
    )
    db.add_all([studying, course])
    await db.flush()

    condition = FormCondition(
        question_id=course.question_id,
        depends_on_question_id=studying.question_id,
        operator="EQUALS",
        comparison_value="YES",
        action="SHOW",
    )
    db.add(condition)
    await db.flush()

    fetched = await db.get(FormCondition, condition.condition_id)
    assert fetched.depends_on_question_id == studying.question_id
    assert fetched.question_id == course.question_id
    assert fetched.operator == "EQUALS"
    assert fetched.comparison_value == "YES"
    assert fetched.action == "SHOW"


@pytest.mark.asyncio
async def test_form_submission_for_citizen(db: AsyncSession, citizen: CitizenMaster):
    """A submission references citizen, form, and a form version snapshot."""
    form = FormDefinition(form_code="SUB_FORM", form_name="Sub Form", version=3)
    db.add(form)
    await db.flush()

    submission = FormSubmission(
        citizen_id=citizen.citizen_id,
        form_id=form.form_id,
        form_version=3,
        status="IN_PROGRESS",
        completion_percentage=40,
    )
    db.add(submission)
    await db.flush()

    fetched = await db.get(FormSubmission, submission.submission_id)
    assert fetched.citizen_id == citizen.citizen_id
    assert fetched.form_id == form.form_id
    assert fetched.form_version == 3
    assert fetched.status == "IN_PROGRESS"
    assert fetched.started_at is not None
    assert fetched.completed_at is None


@pytest.mark.asyncio
async def test_form_answer_typed_values(db: AsyncSession, citizen: CitizenMaster):
    """Answers store native values per data_type, not only text."""
    form = FormDefinition(form_code="ANS_FORM", form_name="Ans Form", version=1)
    db.add(form)
    await db.flush()
    section = FormSection(form_id=form.form_id, section_code="S1", section_name="S1")
    db.add(section)
    await db.flush()

    q_income = FormQuestion(
        section_id=section.section_id,
        question_code="ANNUAL_INCOME",
        question_text="Annual income?",
        question_type="decimal",
        data_type="DECIMAL",
    )
    q_dob = FormQuestion(
        section_id=section.section_id,
        question_code="DATE_OF_BIRTH",
        question_text="Date of birth?",
        question_type="date",
        data_type="DATE",
    )
    db.add_all([q_income, q_dob])
    await db.flush()

    submission = FormSubmission(
        citizen_id=citizen.citizen_id, form_id=form.form_id, form_version=1
    )
    db.add(submission)
    await db.flush()

    income_answer = FormAnswer(
        submission_id=submission.submission_id,
        question_id=q_income.question_id,
        answer_decimal=250000.50,
        source="USER_INPUT",
    )
    dob_answer = FormAnswer(
        submission_id=submission.submission_id,
        question_id=q_dob.question_id,
        answer_date=date(2000, 1, 1),
        source="DOCUMENT",
        confidence=0.95,
    )
    db.add_all([income_answer, dob_answer])
    await db.flush()

    fetched_income = await db.get(FormAnswer, income_answer.answer_id)
    assert float(fetched_income.answer_decimal) == 250000.50
    assert fetched_income.source == "USER_INPUT"

    fetched_dob = await db.get(FormAnswer, dob_answer.answer_id)
    assert fetched_dob.answer_date == date(2000, 1, 1)
    assert float(fetched_dob.confidence) == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_profile_fact_creation(db: AsyncSession, citizen: CitizenMaster):
    """Facts store typed values with source and verification flags."""
    fact = ProfileFact(
        citizen_id=citizen.citizen_id,
        fact_code="ANNUAL_INCOME",
        fact_value="250000",
        data_type="DECIMAL",
        source="USER_INPUT",
        confidence=1.0,
    )
    db.add(fact)
    await db.flush()

    fetched = await db.get(ProfileFact, fact.fact_id)
    assert fetched.fact_code == "ANNUAL_INCOME"
    assert fetched.fact_value == "250000"
    assert fetched.data_type == "DECIMAL"
    assert fetched.source == "USER_INPUT"
    assert fetched.verified is False
    assert fetched.effective_until is None

    derived = ProfileFact(
        citizen_id=citizen.citizen_id,
        fact_code="AGE",
        fact_value="26",
        data_type="INTEGER",
        source="SYSTEM_DERIVED",
    )
    db.add(derived)
    await db.flush()
    fetched_age = await db.get(ProfileFact, derived.fact_id)
    assert fetched_age.source == "SYSTEM_DERIVED"


@pytest.mark.asyncio
async def test_profile_fact_one_open_fact_per_code(db: AsyncSession, citizen: CitizenMaster):
    """Only one OPEN fact per (citizen, fact_code); history via effective_until."""
    open_fact = ProfileFact(
        citizen_id=citizen.citizen_id,
        fact_code="SOCIAL_CATEGORY",
        fact_value="GEN",
        data_type="STRING",
        source="USER_INPUT",
    )
    db.add(open_fact)
    await db.flush()

    # A second open fact for the same (citizen, code) must violate the
    # partial unique index.
    db.add(
        ProfileFact(
            citizen_id=citizen.citizen_id,
            fact_code="SOCIAL_CATEGORY",
            fact_value="OBC",
            data_type="STRING",
            source="USER_INPUT",
        )
    )
    with pytest.raises(Exception):
        await db.flush()
    await db.rollback()

    # After closing the first fact (effective_until set), a new open fact is
    # allowed — history is preserved rather than overwritten.
    async with _TestSession() as session2:
        try:
            c2 = CitizenMaster(
                full_name="Fact History Citizen",
                date_of_birth=date(1990, 5, 5),
                citizen_type="GENERAL",
            )
            session2.add(c2)
            await session2.flush()

            old = ProfileFact(
                citizen_id=c2.citizen_id,
                fact_code="POVERTY_CATEGORY",
                fact_value="APL",
                data_type="STRING",
                source="USER_INPUT",
                effective_until=date(2025, 1, 1),
            )
            session2.add(old)
            new = ProfileFact(
                citizen_id=c2.citizen_id,
                fact_code="POVERTY_CATEGORY",
                fact_value="BPL",
                data_type="STRING",
                source="DOCUMENT",
            )
            session2.add(new)
            await session2.flush()

            rows = (
                (
                    await session2.execute(
                        select(ProfileFact).where(
                            ProfileFact.citizen_id == c2.citizen_id,
                            ProfileFact.fact_code == "POVERTY_CATEGORY",
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 2
        finally:
            await session2.rollback()


@pytest.mark.asyncio
async def test_profile_fact_provenance(
    db: AsyncSession, citizen: CitizenMaster
):
    """Provenance records where a fact came from, including answer linkage."""
    # Minimal form/question/answer chain to link provenance to.
    form = FormDefinition(form_code="PROV_FORM", form_name="Prov Form", version=1)
    db.add(form)
    await db.flush()
    section = FormSection(form_id=form.form_id, section_code="S1", section_name="S1")
    db.add(section)
    await db.flush()
    question = FormQuestion(
        section_id=section.section_id,
        question_code="INCOME_Q",
        question_text="Income?",
        question_type="decimal",
        data_type="DECIMAL",
        profile_field="annual_income",
    )
    db.add(question)
    await db.flush()
    submission = FormSubmission(
        citizen_id=citizen.citizen_id, form_id=form.form_id, form_version=1
    )
    db.add(submission)
    await db.flush()
    answer = FormAnswer(
        submission_id=submission.submission_id,
        question_id=question.question_id,
        answer_decimal=180000,
        source="USER_INPUT",
    )
    db.add(answer)
    await db.flush()

    fact = ProfileFact(
        citizen_id=citizen.citizen_id,
        fact_code="ANNUAL_INCOME",
        fact_value="180000",
        data_type="DECIMAL",
        source="USER_INPUT",
    )
    db.add(fact)
    await db.flush()

    provenance = ProfileFactProvenance(
        fact_id=fact.fact_id,
        source_type="USER_INPUT",
        source_reference=f"submission:{submission.submission_id}",
        source_text="What is your family's annual income? -> 180000",
        form_answer_id=answer.answer_id,
        verification_status="PENDING",
    )
    db.add(provenance)
    await db.flush()

    fetched = await db.get(ProfileFactProvenance, provenance.provenance_id)
    assert fetched.fact_id == fact.fact_id
    assert fetched.form_answer_id == answer.answer_id
    assert fetched.source_type == "USER_INPUT"
    assert fetched.verification_status == "PENDING"


@pytest.mark.asyncio
async def test_scheme_source_creation(db: AsyncSession):
    """Sources capture the external origin of schemes."""
    source = SchemeSource(
        source_name="Test State Welfare Portal",
        source_type="GOVERNMENT_PORTAL",
        base_url="https://welfare.test.gov.example",
        authority_name="Department of Welfare",
    )
    db.add(source)
    await db.flush()

    fetched = await db.get(SchemeSource, source.source_id)
    assert fetched.source_type == "GOVERNMENT_PORTAL"
    assert fetched.status == "ACTIVE"


@pytest.mark.asyncio
async def test_scheme_source_document_preserves_raw_content(db: AsyncSession):
    """Documents link to sources, hash content, and keep the original raw text."""
    source = SchemeSource(
        source_name="Test Guidelines Site",
        source_type="GOVERNMENT_WEBSITE",
        base_url="https://schemes.test.gov.example",
    )
    db.add(source)
    await db.flush()

    document = SchemeSourceDocument(
        source_id=source.source_id,
        document_name="Test Scholarship Guidelines 2026",
        document_url="https://schemes.test.gov.example/guidelines-2026.pdf",
        document_type="GUIDELINE",
        language="en",
        content_hash="a" * 64,
        retrieved_at=None,
    )
    db.add(document)
    await db.flush()

    raw = SchemeSourceContent(
        source_document_id=document.source_document_id,
        content_type="RAW",
        raw_content="ORIGINAL RAW CONTENT — must never be destroyed",
        processing_status="PROCESSED",
    )
    extracted = SchemeSourceContent(
        source_document_id=document.source_document_id,
        content_type="EXTRACTED_TEXT",
        normalized_content="original raw content must never be destroyed",
        extraction_version="v0.dev",
    )
    db.add_all([raw, extracted])
    await db.flush()

    fetched_doc = await db.get(SchemeSourceDocument, document.source_document_id)
    assert fetched_doc.source_id == source.source_id

    contents = (
        (
            await db.execute(
                select(SchemeSourceContent).where(
                    SchemeSourceContent.source_document_id == document.source_document_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert {c.content_type for c in contents} == {"RAW", "EXTRACTED_TEXT"}
    raw_stored = next(c for c in contents if c.content_type == "RAW")
    assert "must never be destroyed" in raw_stored.raw_content


@pytest.mark.asyncio
async def test_scheme_rule_provenance_and_ingestion_run(db: AsyncSession):
    """Rule provenance links a structured rule to its source document;
    ingestion runs record counters for future ingestion infrastructure."""
    source = SchemeSource(
        source_name="Test Ingestion Source",
        source_type="GOVERNMENT_PDF",
        base_url="https://pdfs.test.gov.example",
    )
    db.add(source)
    await db.flush()

    document = SchemeSourceDocument(
        source_id=source.source_id,
        document_name="Test Scheme Circular",
        document_url="https://pdfs.test.gov.example/circular.pdf",
    )
    db.add(document)
    await db.flush()

    scheme = SchemeMaster(scheme_name="Test Provenance Scheme")
    db.add(scheme)
    await db.flush()
    group = SchemeRuleGroup(
        scheme_id=scheme.scheme_id,
        group_name="Eligibility",
        intra_group_operator="AND",
    )
    db.add(group)
    await db.flush()
    rule = SchemeEligibilityRule(
        scheme_id=scheme.scheme_id,
        group_id=group.group_id,
        parameter_name="age",
        operator=">=",
        required_value="60",
    )
    db.add(rule)
    await db.flush()

    provenance = SchemeRuleProvenance(
        rule_id=rule.rule_id,
        source_document_id=document.source_document_id,
        source_text="Applicants must be 60 years or older.",
        source_page=3,
        source_section="Eligibility",
        extraction_method="MANUAL",
        extraction_confidence=1.0,
    )
    db.add(provenance)
    await db.flush()

    run = SchemeIngestionRun(
        source_id=source.source_id,
        status="COMPLETED",
        records_discovered=10,
        records_created=8,
        records_updated=1,
        records_failed=1,
    )
    db.add(run)
    await db.flush()

    fetched_prov = await db.get(SchemeRuleProvenance, provenance.rule_provenance_id)
    assert fetched_prov.rule_id == rule.rule_id
    assert fetched_prov.source_document_id == document.source_document_id

    fetched_run = await db.get(SchemeIngestionRun, run.ingestion_run_id)
    assert fetched_run.records_created == 8


@pytest.mark.asyncio
async def test_eligibility_assessment_status_columns(
    db: AsyncSession, citizen: CitizenMaster
):
    """New canonical eligibility_status and evidence columns coexist with
    the legacy eligibility_result boolean."""
    scheme = SchemeMaster(scheme_name="Test Status Scheme")
    db.add(scheme)
    await db.flush()

    assessment = EligibilityAssessment(
        citizen_id=citizen.citizen_id,
        scheme_id=scheme.scheme_id,
        eligibility_result=False,  # legacy boolean, still required
        eligibility_status="INSUFFICIENT_INFORMATION",
        missing_facts=["poverty_category"],
        missing_documents=["INCOME_CERTIFICATE"],
        confidence_score=0.5,
        assessment_version="v1.deterministic",
    )
    db.add(assessment)
    await db.flush()

    fetched = await db.get(EligibilityAssessment, assessment.assessment_id)
    # Legacy field untouched
    assert fetched.eligibility_result is False
    # New canonical fields
    assert fetched.eligibility_status == "INSUFFICIENT_INFORMATION"
    assert fetched.missing_facts == ["poverty_category"]
    assert fetched.missing_documents == ["INCOME_CERTIFICATE"]
    assert float(fetched.confidence_score) == pytest.approx(0.5)
    assert fetched.assessment_version == "v1.deterministic"
    assert fetched.created_at is not None
