"""
Admin API routes.

Every route in this router depends on require_admin (backend-authoritative
authorization). The frontend AdminGate is UX only.

Groups:
  GET   /admin/stats                      overview counts + recent activity
  GET   /admin/users                      user list (never exposes credentials)
  PATCH /admin/users/{user_id}/roles      add/remove ADMIN
  GET   /admin/schemes                    scheme list with rule counts
  PATCH /admin/schemes/{scheme_id}        metadata-only edit (rules read-only)
  GET   /admin/submissions                submission monitoring list
  GET   /admin/submissions/{id}           read-only detail with answers
  PATCH /admin/citizens/{citizen_id}/verification   PENDING/VERIFIED
  GET/POST/PATCH /admin/sources[...]      source registry CRUD
  POST  /admin/sources/{id}/fetch         manual ingestion (raw snapshot)
  GET   /admin/ingestion-runs[/{id}]      run monitoring + snapshot viewer
  GET   /admin/schemes/{id}/rules-with-provenance   rules + citations
  GET   /admin/provenance/schemes/{id}/latest-document-sentences  scheme's latest snapshot sentences
  GET   /admin/provenance/documents/{id}/sentences  browse/search sentences
  POST  /admin/provenance/rules/{id}/link           cite a source sentence
  DELETE /admin/provenance/rules/{id}/links/{pid}   remove a citation
  POST  /admin/provenance/rules/{id}/links/{pid}/verify   verify citation
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_admin
from app.cache import cache, invalidate_schemes, invalidate_form
from app.database import get_db
from app.models.auth import UserAccount, UserRole
from app.models.citizen import CitizenMaster
from app.models.assessment import EligibilityAssessment
from app.models.form import FormDefinition, FormQuestion
from app.models.scheme import SchemeEligibilityRule, SchemeMaster
from app.models.submission import FormAnswer, FormSubmission
from app.models.scheme_source import (
    SCHEME_SOURCE_TYPES,
    SchemeIngestionRun,
    SchemeSource,
    SchemeSourceContent,
    SchemeSourceDocument,
)
from app.repositories.auth_repository import KNOWN_ROLES
from app.services.auth_service import AuthService
from app.services.ingestion_service import IngestionError, run_manual_fetch
from app.services.rule_provenance_service import ProvenanceError, RuleProvenanceService

router = APIRouter(dependencies=[Depends(require_admin)])


# ------------------------------------------------------------------
# Overview
# ------------------------------------------------------------------


@router.get("/stats")
async def admin_stats(db: AsyncSession = Depends(get_db)) -> Any:
    """Headline counts + short recent-activity feed for the overview page."""
    async def count(model):
        result = await db.execute(select(func.count()).select_from(model))
        return result.scalar_one()

    users = await count(UserAccount)
    citizens = await count(CitizenMaster)
    schemes = await count(SchemeMaster)
    submissions = await count(FormSubmission)
    assessments = await count(EligibilityAssessment)

    recent_users = await db.execute(
        select(UserAccount.email, UserAccount.created_at)
        .order_by(UserAccount.created_at.desc())
        .limit(5)
    )
    recent_registrations = [
        {"email": row.email, "created_at": row.created_at}
        for row in recent_users.all()
    ]

    return {
        "counts": {
            "users": users,
            "citizens": citizens,
            "schemes": schemes,
            "submissions": submissions,
            "assessments": assessments,
        },
        "recent_registrations": recent_registrations,
    }


# ------------------------------------------------------------------
# Users
# ------------------------------------------------------------------


class UserOut(BaseModel):
    user_id: uuid.UUID
    email: str
    roles: list[str]
    created_at: Any
    citizen_id: uuid.UUID | None = None


class RolesUpdate(BaseModel):
    roles: list[str]


@router.get("/users", response_model=list[UserOut])
async def admin_list_users(
    search: str | None = None,
    role: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List user accounts with roles. Never exposes password hashes or tokens."""
    query = (
        select(UserAccount, UserRole.role)
        .outerjoin(UserRole, UserRole.user_id == UserAccount.user_id)
        .order_by(UserAccount.created_at.desc())
        .limit(200)
    )
    if search:
        query = query.where(UserAccount.email.ilike(f"%{search}%"))

    result = await db.execute(query)
    rows = result.all()

    by_user: dict[uuid.UUID, UserOut] = {}
    for user, role in rows:
        entry = by_user.setdefault(
            user.user_id,
            UserOut(
                user_id=user.user_id,
                email=user.email,
                roles=[],
                created_at=user.created_at,
            ),
        )
        if role:
            entry.roles.append(role)

    if role:
        by_user = {uid: u for uid, u in by_user.items() if role in u.roles}

    # Link citizen profiles where they exist.
    for entry in by_user.values():
        citizen_result = await db.execute(
            select(CitizenMaster.citizen_id).where(
                CitizenMaster.owning_user_id == entry.user_id
            )
        )
        entry.citizen_id = citizen_result.scalar_one_or_none()

    return list(by_user.values())


@router.patch("/users/{user_id}/roles")
async def admin_update_roles(
    user_id: uuid.UUID,
    body: RolesUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Replace the user's role set with the supplied list (e.g. grant/revoke ADMIN)."""
    unknown = [r for r in body.roles if r not in KNOWN_ROLES]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown roles: {unknown}")

    target = await db.get(UserAccount, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")

    current = await db.execute(select(UserRole).where(UserRole.user_id == user_id))
    existing = {row.role: row for row in current.scalars().all()}

    for role_name, membership in existing.items():
        if role_name not in body.roles:
            await db.delete(membership)
    for role_name in body.roles:
        if role_name not in existing:
            db.add(UserRole(user_id=user_id, role=role_name))

    await db.flush()
    return {"user_id": user_id, "roles": body.roles}


# ------------------------------------------------------------------
# Schemes
# ------------------------------------------------------------------


class SchemeOut(BaseModel):
    scheme_id: uuid.UUID
    scheme_name: str
    department_name: str | None = None
    scheme_category: str | None = None
    description: str | None = None
    benefit_description: str | None = None
    status: str
    official_source_url: str | None = None
    application_url: str | None = None
    target_persona: str | None = None
    rule_count: int = 0


class SchemeUpdate(BaseModel):
    # Metadata-only: eligibility rules are intentionally NOT editable here.
    description: str | None = None
    benefit_description: str | None = None
    official_source_url: str | None = None
    application_url: str | None = None
    status: str | None = None


SCHEME_EDITABLE_STATUSES = ("ACTIVE", "INACTIVE")


@router.get("/schemes", response_model=list[SchemeOut])
async def admin_list_schemes(db: AsyncSession = Depends(get_db)) -> Any:
    """Scheme catalogue with a rule count per scheme. Rules themselves stay
    read-only in this phase (viewed via the public GET /schemes/{id})."""
    result = await db.execute(
        select(
            SchemeMaster,
            func.count(SchemeEligibilityRule.rule_id).label("rule_count"),
        )
        .outerjoin(SchemeEligibilityRule, SchemeEligibilityRule.scheme_id == SchemeMaster.scheme_id)
        .group_by(SchemeMaster.scheme_id)
        .order_by(SchemeMaster.scheme_name)
    )

    schemes: list[SchemeOut] = []
    for scheme, rule_count in result.all():
        schemes.append(
            SchemeOut(
                scheme_id=scheme.scheme_id,
                scheme_name=scheme.scheme_name,
                department_name=scheme.department_name,
                scheme_category=scheme.scheme_category,
                description=scheme.description,
                benefit_description=scheme.benefit_description,
                status=scheme.status,
                official_source_url=scheme.official_source_url,
                application_url=scheme.application_url,
                target_persona=scheme.target_persona,
                rule_count=rule_count,
            )
        )
    return schemes


@router.patch("/schemes/{scheme_id}", response_model=SchemeOut)
async def admin_update_scheme(
    scheme_id: uuid.UUID,
    body: SchemeUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update permitted scheme metadata. Rule tables are never touched here.

    Invalidates the scheme reference-data cache so citizens immediately see
    the updated metadata.
    """
    scheme = await db.get(SchemeMaster, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found")

    if body.status is not None and body.status not in SCHEME_EDITABLE_STATUSES:
        raise HTTPException(status_code=400, detail="Status must be ACTIVE or INACTIVE")

    for field in (
        "description",
        "benefit_description",
        "official_source_url",
        "application_url",
        "status",
    ):
        value = getattr(body, field)
        if value is not None:
            setattr(scheme, field, value)

    await db.flush()
    # The scheme catalogue/detail served to citizens changed.
    invalidate_schemes()

    rule_count_result = await db.execute(
        select(func.count())
        .select_from(SchemeEligibilityRule)
        .where(SchemeEligibilityRule.scheme_id == scheme_id)
    )
    return SchemeOut(
        scheme_id=scheme.scheme_id,
        scheme_name=scheme.scheme_name,
        department_name=scheme.department_name,
        scheme_category=scheme.scheme_category,
        description=scheme.description,
        benefit_description=scheme.benefit_description,
        status=scheme.status,
        official_source_url=scheme.official_source_url,
        application_url=scheme.application_url,
        target_persona=scheme.target_persona,
        rule_count=rule_count_result.scalar_one(),
    )


# ------------------------------------------------------------------
# Submissions (read-only monitoring)
# ------------------------------------------------------------------


class SubmissionOut(BaseModel):
    submission_id: uuid.UUID
    citizen_id: uuid.UUID
    citizen_name: str | None = None
    form_code: str | None = None
    form_version: int
    status: str
    completion_percentage: int
    started_at: Any
    completed_at: Any | None = None
    updated_at: Any


class AnswerOut(BaseModel):
    question_code: str | None = None
    question_text: str | None = None
    question_type: str | None = None
    value: Any = None
    source: str


class SubmissionDetailOut(BaseModel):
    submission_id: uuid.UUID
    citizen_id: uuid.UUID
    citizen_name: str | None = None
    form_code: str | None = None
    form_version: int
    status: str
    completion_percentage: int
    started_at: Any
    completed_at: Any | None = None
    updated_at: Any
    answers: list[AnswerOut] = []


@router.get("/submissions", response_model=list[SubmissionOut])
async def admin_list_submissions(
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Read-only submission monitor. No editing — answers belong to citizens."""
    query = (
        select(FormSubmission, CitizenMaster.full_name, FormDefinition.form_code)
        .join(CitizenMaster, CitizenMaster.citizen_id == FormSubmission.citizen_id)
        .join(FormDefinition, FormDefinition.form_id == FormSubmission.form_id)
        .order_by(FormSubmission.updated_at.desc())
        .limit(200)
    )
    if status:
        query = query.where(FormSubmission.status == status.upper())

    result = await db.execute(query)
    return [
        SubmissionOut(
            submission_id=sub.submission_id,
            citizen_id=sub.citizen_id,
            citizen_name=citizen_name,
            form_code=form_code,
            form_version=sub.form_version,
            status=sub.status,
            completion_percentage=sub.completion_percentage,
            started_at=sub.started_at,
            completed_at=sub.completed_at,
            updated_at=sub.updated_at,
        )
        for sub, citizen_name, form_code in result.all()
    ]


@router.get("/submissions/{submission_id}", response_model=SubmissionDetailOut)
async def admin_submission_detail(
    submission_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Read-only detail: submission → answers, with question text for context."""
    sub_result = await db.execute(
        select(FormSubmission, CitizenMaster.full_name, FormDefinition.form_code)
        .join(CitizenMaster, CitizenMaster.citizen_id == FormSubmission.citizen_id)
        .join(FormDefinition, FormDefinition.form_id == FormSubmission.form_id)
        .where(FormSubmission.submission_id == submission_id)
    )
    row = sub_result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Submission not found")
    sub, citizen_name, form_code = row

    answer_result = await db.execute(
        select(FormAnswer, FormQuestion)
        .join(FormQuestion, FormQuestion.question_id == FormAnswer.question_id)
        .where(FormAnswer.submission_id == submission_id)
        .order_by(FormQuestion.display_order)
    )

    def answer_value(answer: FormAnswer, question: FormQuestion) -> Any:
        if answer.answer_text is not None:
            return answer.answer_text
        if answer.answer_number is not None:
            return answer.answer_number
        if answer.answer_decimal is not None:
            return float(answer.answer_decimal)
        if answer.answer_boolean is not None:
            return answer.answer_boolean
        if answer.answer_date is not None:
            return answer.answer_date.isoformat()
        if answer.answer_json is not None:
            return answer.answer_json
        return None

    answers = [
        AnswerOut(
            question_code=question.question_code,
            question_text=question.question_text,
            question_type=question.question_type,
            value=answer_value(answer, question),
            source=answer.source,
        )
        for answer, question in answer_result.all()
    ]

    return SubmissionDetailOut(
        submission_id=sub.submission_id,
        citizen_id=sub.citizen_id,
        citizen_name=citizen_name,
        form_code=form_code,
        form_version=sub.form_version,
        status=sub.status,
        completion_percentage=sub.completion_percentage,
        started_at=sub.started_at,
        completed_at=sub.completed_at,
        updated_at=sub.updated_at,
        answers=answers,
    )


# ------------------------------------------------------------------
# Citizen verification
# ------------------------------------------------------------------


class VerificationUpdate(BaseModel):
    # PENDING | VERIFIED — matches the citizen model's canonical statuses.
    verification_status: str


@router.patch("/citizens/{citizen_id}/verification")
async def admin_update_verification(
    citizen_id: uuid.UUID,
    body: VerificationUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Set a citizen's verification status (PENDING or VERIFIED)."""
    status = body.verification_status.upper()
    if status not in ("PENDING", "VERIFIED"):
        raise HTTPException(status_code=400, detail="verification_status must be PENDING or VERIFIED")

    citizen = await db.get(CitizenMaster, citizen_id)
    if citizen is None:
        raise HTTPException(status_code=404, detail="Citizen not found")

    citizen.verification_status = status
    await db.flush()
    return {
        "citizen_id": citizen_id,
        "verification_status": status,
    }


# ------------------------------------------------------------------
# Sources (Phase C: registry)
# ------------------------------------------------------------------


class SourceCreate(BaseModel):
    source_name: str
    source_type: str
    base_url: str
    authority_name: str | None = None
    status: str = "ACTIVE"


class SourceUpdate(BaseModel):
    source_name: str | None = None
    source_type: str | None = None
    base_url: str | None = None
    authority_name: str | None = None
    status: str | None = None


class SourceOut(BaseModel):
    source_id: uuid.UUID
    source_name: str
    source_type: str
    base_url: str | None = None
    authority_name: str | None = None
    status: str
    created_at: Any
    document_count: int = 0
    last_run_status: str | None = None
    last_run_at: Any | None = None


def _require_source_type(value: str) -> str:
    if value not in SCHEME_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"source_type must be one of: {', '.join(SCHEME_SOURCE_TYPES)}",
        )
    return value


@router.get("/sources", response_model=list[SourceOut])
async def admin_list_sources(db: AsyncSession = Depends(get_db)) -> Any:
    """Source registry with document counts and the latest run outcome."""
    result = await db.execute(
        select(SchemeSource).order_by(SchemeSource.created_at.desc())
    )
    sources = result.scalars().all()

    doc_counts = await db.execute(
        select(
            SchemeSourceDocument.source_id,
            func.count(SchemeSourceDocument.source_document_id),
        )
        .group_by(SchemeSourceDocument.source_id)
    )
    doc_count_map = dict(doc_counts.all())

    last_runs = await db.execute(
        select(
            SchemeIngestionRun.source_id,
            func.max(SchemeIngestionRun.started_at),
        ).group_by(SchemeIngestionRun.source_id)
    )
    last_run_times = dict(last_runs.all())

    last_status_rows = await db.execute(select(SchemeIngestionRun))
    last_status_map: dict[uuid.UUID, SchemeIngestionRun] = {}
    for run in last_status_rows.scalars():
        previous = last_status_map.get(run.source_id)
        if previous is None or (run.started_at or run.created_at) >= (
            previous.started_at or previous.created_at
        ):
            last_status_map[run.source_id] = run

    return [
        SourceOut(
            source_id=source.source_id,
            source_name=source.source_name,
            source_type=source.source_type,
            base_url=source.base_url,
            authority_name=source.authority_name,
            status=source.status,
            created_at=source.created_at,
            document_count=doc_count_map.get(source.source_id, 0),
            last_run_status=(
                last_status_map[source.source_id].status
                if source.source_id in last_status_map
                else None
            ),
            last_run_at=last_run_times.get(source.source_id),
        )
        for source in sources
    ]


@router.post("/sources", response_model=SourceOut)
async def admin_create_source(
    body: SourceCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Register a new scheme source."""
    _require_source_type(body.source_type)
    if not body.base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="base_url must be an absolute http(s) URL")
    if body.status not in ("ACTIVE", "INACTIVE", "RETIRED"):
        raise HTTPException(status_code=400, detail="status must be ACTIVE, INACTIVE, or RETIRED")

    source = SchemeSource(
        source_name=body.source_name,
        source_type=body.source_type,
        base_url=body.base_url,
        authority_name=body.authority_name,
        status=body.status,
    )
    db.add(source)
    await db.flush()
    return SourceOut(
        source_id=source.source_id,
        source_name=source.source_name,
        source_type=source.source_type,
        base_url=source.base_url,
        authority_name=source.authority_name,
        status=source.status,
        created_at=source.created_at,
        document_count=0,
    )


@router.patch("/sources/{source_id}", response_model=SourceOut)
async def admin_update_source(
    source_id: uuid.UUID,
    body: SourceUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update a registered source (name, URL, type, authority, status)."""
    source = await db.get(SchemeSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")

    if body.source_type is not None:
        source.source_type = _require_source_type(body.source_type)
    if body.status is not None and body.status not in ("ACTIVE", "INACTIVE", "RETIRED"):
        raise HTTPException(status_code=400, detail="status must be ACTIVE, INACTIVE, or RETIRED")

    for field in ("source_name", "base_url", "authority_name", "status"):
        value = getattr(body, field)
        if value is not None:
            setattr(source, field, value)

    await db.flush()
    return SourceOut(
        source_id=source.source_id,
        source_name=source.source_name,
        source_type=source.source_type,
        base_url=source.base_url,
        authority_name=source.authority_name,
        status=source.status,
        created_at=source.created_at,
    )


# ------------------------------------------------------------------
# Manual ingestion (Phase C2)
# ------------------------------------------------------------------


@router.post("/sources/{source_id}/fetch")
async def admin_fetch_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Trigger one manual ingestion run: fetch, snapshot raw content + hash.

    Never modifies scheme or rule data — the run stops at the raw snapshot
    layer by design.
    """
    source = await db.get(SchemeSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="Source is not ACTIVE")
    if not source.base_url:
        raise HTTPException(status_code=400, detail="Source has no base_url to fetch")

    try:
        run = await run_manual_fetch(db, source)
    except IngestionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return {
        "ingestion_run_id": run.ingestion_run_id,
        "source_id": source.source_id,
        "status": run.status,
        "error_summary": run.error_summary,
        "records_created": run.records_created,
        "completed_at": run.completed_at,
    }


# ------------------------------------------------------------------
# Ingestion run monitoring (Phase C3)
# ------------------------------------------------------------------


class RunOut(BaseModel):
    ingestion_run_id: uuid.UUID
    source_id: uuid.UUID
    source_name: str | None = None
    status: str
    started_at: Any
    completed_at: Any | None = None
    records_discovered: int = 0
    records_created: int = 0
    records_failed: int = 0
    error_summary: str | None = None


class ContentOut(BaseModel):
    content_id: uuid.UUID
    content_type: str
    language: str | None = None
    processing_status: str
    retrieved_at: Any | None = None
    raw_content: str | None = None


class RunDetailOut(RunOut):
    documents: list[dict[str, Any]] = []
    contents: list[ContentOut] = []


@router.get("/ingestion-runs", response_model=list[RunOut])
async def admin_list_runs(
    source_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Ingestion run history, newest first."""
    query = (
        select(SchemeIngestionRun, SchemeSource.source_name)
        .join(SchemeSource, SchemeSource.source_id == SchemeIngestionRun.source_id)
        .order_by(SchemeIngestionRun.started_at.desc())
        .limit(100)
    )
    if source_id:
        query = query.where(SchemeIngestionRun.source_id == source_id)

    result = await db.execute(query)
    return [
        RunOut(
            ingestion_run_id=run.ingestion_run_id,
            source_id=run.source_id,
            source_name=source_name,
            status=run.status,
            started_at=run.started_at,
            completed_at=run.completed_at,
            records_discovered=run.records_discovered,
            records_created=run.records_created,
            records_failed=run.records_failed,
            error_summary=run.error_summary,
        )
        for run, source_name in result.all()
    ]


@router.get("/ingestion-runs/{run_id}", response_model=RunDetailOut)
async def admin_run_detail(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Full run detail: documents, hashes, and the raw snapshot itself."""
    row = await db.execute(
        select(SchemeIngestionRun, SchemeSource.source_name)
        .join(SchemeSource, SchemeSource.source_id == SchemeIngestionRun.source_id)
        .where(SchemeIngestionRun.ingestion_run_id == run_id)
    )
    run_row = row.first()
    if run_row is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    run, source_name = run_row

    doc_result = await db.execute(
        select(SchemeSourceDocument).where(
            SchemeSourceDocument.source_id == run.source_id
        )
    )
    documents = [
        {
            "source_document_id": doc.source_document_id,
            "document_name": doc.document_name,
            "document_url": doc.document_url,
            "version": doc.version,
            "content_hash": doc.content_hash,
            "retrieved_at": doc.retrieved_at,
            "processing_status": doc.processing_status,
        }
        for doc in doc_result.scalars().all()
    ]

    content_result = await db.execute(
        select(SchemeSourceContent)
        .join(
            SchemeSourceDocument,
            SchemeSourceDocument.source_document_id == SchemeSourceContent.source_document_id,
        )
        .where(SchemeSourceDocument.source_id == run.source_id)
        .order_by(SchemeSourceContent.retrieved_at.desc())
    )
    contents = [
        ContentOut(
            content_id=content.content_id,
            content_type=content.content_type,
            language=content.language,
            processing_status=content.processing_status,
            retrieved_at=content.retrieved_at,
            raw_content=content.raw_content,
        )
        for content in content_result.scalars().all()
    ]

    return RunDetailOut(
        ingestion_run_id=run.ingestion_run_id,
        source_id=run.source_id,
        source_name=source_name,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        records_discovered=run.records_discovered,
        records_created=run.records_created,
        records_failed=run.records_failed,
        error_summary=run.error_summary,
        documents=documents,
        contents=contents,
    )


# ------------------------------------------------------------------
# Rule provenance (snapshot → sentence → cited rule)
# ------------------------------------------------------------------


class SentenceSearchQuery(BaseModel):
    query: str | None = None


@router.get("/schemes/{scheme_id}/rules-with-provenance")
async def admin_rules_with_provenance(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Every rule of the scheme with its source citation, if linked."""
    scheme = await db.get(SchemeMaster, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found")
    service = RuleProvenanceService(db)
    return {"scheme_id": scheme_id, "rules": await service.provenance_for_scheme(scheme_id)}


@router.get("/provenance/schemes/{scheme_id}/latest-document-sentences")
async def admin_latest_document_sentences(
    scheme_id: uuid.UUID,
    query: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Sentences of the scheme's latest snapshot document (its linked
    document if any, else the newest snapshot from an ACTIVE source),
    optionally filtered by an all-terms query. Feeds the citation picker."""
    scheme = await db.get(SchemeMaster, scheme_id)
    if scheme is None:
        raise HTTPException(status_code=404, detail="Scheme not found")
    service = RuleProvenanceService(db)
    document = await service.latest_document_for_scheme(scheme_id)
    if document is None:
        raise HTTPException(
            status_code=404,
            detail="No snapshot document available. Fetch a source first.",
        )
    try:
        result = await service.document_sentences(document.source_document_id, query)
    except ProvenanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        **result,
        "document_name": document.document_name,
        "document_url": document.document_url,
        "retrieved_at": document.retrieved_at,
    }


@router.get("/provenance/documents/{source_document_id}/sentences")
async def admin_document_sentences(
    source_document_id: uuid.UUID,
    query: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Sentences extracted from a snapshot document (deterministic
    segmentation), optionally filtered by an all-terms query."""
    service = RuleProvenanceService(db)
    try:
        return await service.document_sentences(source_document_id, query)
    except ProvenanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/provenance/documents/{source_document_id}/search")
async def admin_search_document_sentences(
    source_document_id: uuid.UUID,
    body: SentenceSearchQuery,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Term-overlap search over the document's sentences (for the citation
    picker; GET with ?query= is equivalent)."""
    service = RuleProvenanceService(db)
    try:
        return await service.document_sentences(source_document_id, body.query)
    except ProvenanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc


@router.post("/provenance/rules/{rule_id}/link")
async def admin_link_rule_provenance(
    rule_id: uuid.UUID,
    body: SentenceSearchQuery,
    source_document_id: uuid.UUID,
    sentence_index: int,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Cite a snapshot sentence as the source of a rule (MANUAL, PENDING)."""
    service = RuleProvenanceService(db)
    try:
        provenance = await service.link_rule(
            rule_id, source_document_id, sentence_index
        )
    except ProvenanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "rule_provenance_id": provenance.rule_provenance_id,
        "rule_id": rule_id,
        "source_document_id": source_document_id,
        "sentence_index": sentence_index,
        "source_text": provenance.source_text,
        "verification_status": provenance.verification_status,
    }


@router.delete("/provenance/rules/{rule_id}/links/{provenance_id}")
async def admin_unlink_rule_provenance(
    rule_id: uuid.UUID,
    provenance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = RuleProvenanceService(db)
    try:
        await service.unlink_rule(rule_id, provenance_id)
    except ProvenanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {"unlinked": True, "rule_id": rule_id, "provenance_id": provenance_id}


@router.post("/provenance/rules/{rule_id}/links/{provenance_id}/verify")
async def admin_verify_rule_provenance(
    rule_id: uuid.UUID,
    provenance_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Mark a citation as admin-verified (timestamped)."""
    service = RuleProvenanceService(db)
    try:
        provenance = await service.verify_rule_link(rule_id, provenance_id)
    except ProvenanceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message) from exc
    return {
        "rule_provenance_id": provenance.rule_provenance_id,
        "verification_status": provenance.verification_status,
        "verified_at": provenance.verified_at,
    }


# ------------------------------------------------------------------
# Reference-data cache ops
# ------------------------------------------------------------------


@router.get("/cache/stats")
async def admin_cache_stats() -> Any:
    """Hit/miss/entries snapshot of the reference-data TTL cache."""
    return cache.stats()


@router.post("/cache/clear")
async def admin_cache_clear() -> Any:
    """Drop all cached reference data (schemes, forms). Next reads repopulate
    from PostgreSQL. Use after out-of-band data changes or for debugging."""
    schemes_removed = invalidate_schemes()
    forms_removed = invalidate_form()
    return {
        "cleared": True,
        "schemes_keys_removed": schemes_removed,
        "forms_keys_removed": forms_removed,
    }
