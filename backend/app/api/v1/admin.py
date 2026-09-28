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

Source/ingestion groups (Phase C) are added in a later slice of this
workstream.
"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import require_admin
from app.database import get_db
from app.models.auth import UserAccount, UserRole
from app.models.citizen import CitizenMaster
from app.models.assessment import EligibilityAssessment
from app.models.form import FormDefinition, FormQuestion
from app.models.scheme import SchemeEligibilityRule, SchemeMaster
from app.models.submission import FormAnswer, FormSubmission
from app.repositories.auth_repository import KNOWN_ROLES
from app.services.auth_service import AuthService

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
    """Update permitted scheme metadata. Rule tables are never touched here."""
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
