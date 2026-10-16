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
  GET   /admin/schemes/{id}/rule-groups[...]       scheme rule groups (read)
  POST/PATCH/DELETE /admin/schemes/{id}/rule-groups[...]  group management
  GET   /admin/schemes/{id}/rules[...]             scheme rules (read)
  POST/PATCH/DELETE /admin/schemes/{id}/rules[...]  rule management
  PATCH /admin/schemes/{id}/group-combining-operator  explicit AND<->OR change
  GET/POST /admin/schemes/{id}/documents[...]      required-document CRUD
  PATCH/DELETE /admin/schemes/{id}/documents/{id}  required-document edit/remove
  GET/PUT/DELETE /admin/schemes/{id}/source-documents[...]  source-doc link/unlink
  POST  /admin/schemes/{id}/verify                 record last-verified date
  GET   /admin/provenance/schemes/{id}/latest-document-sentences  scheme's latest snapshot sentences
  GET   /admin/provenance/documents/{id}/sentences  browse/search sentences
  POST  /admin/provenance/rules/{id}/link           cite a source sentence
  DELETE /admin/provenance/rules/{id}/links/{pid}   remove a citation
  POST  /admin/provenance/rules/{id}/links/{pid}/verify   verify citation
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any, Optional

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
from app.models.scheme import (
    SchemeDocumentMaster,
    SchemeEligibilityRule,
    SchemeMaster,
    SchemeRuleGroup,
)
from app.models.submission import FormAnswer, FormSubmission
from app.models.scheme_source import (
    RESOURCE_STATUSES,
    RESOURCE_TYPES,
    SCHEME_SOURCE_TYPES,
    SchemeIngestionRun,
    SchemeSource,
    SchemeSourceContent,
    SchemeSourceDocument,
    SchemeSourceResource,
)
from app.repositories.auth_repository import KNOWN_ROLES
from app.services.auth_service import AuthService
from app.services.document_admin_service import (
    DocumentAdminError,
    DocumentAdminService,
)
from app.services.ingestion_service import IngestionError, run_manual_fetch
from app.services.resource_service import ResourceError, ResourceService
from app.services.rule_admin_service import RuleAdminError, RuleAdminService
from app.services.rule_provenance_service import ProvenanceError, RuleProvenanceService
from app.services.scheme_admin_service import SchemeAdminError, SchemeAdminService
from app.services.scheme_source_link_service import (
    SchemeSourceLinkError,
    SchemeSourceLinkService,
)

router = APIRouter(dependencies=[Depends(require_admin)])


# ------------------------------------------------------------------
# Overview
# ------------------------------------------------------------------


@router.get("/stats")
async def admin_stats(db: AsyncSession = Depends(get_db)) -> Any:
    """Headline counts + short recent-activity feed for the overview page."""
    import logging
    logger = logging.getLogger(__name__)
    try:
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
    except Exception as exc:
        logger.exception("admin_stats failed")
        raise HTTPException(status_code=500, detail=f"admin_stats error: {exc}")


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
    # Additive count for the admin table; existing consumers are unaffected.
    document_count: int = 0


class SchemeUpdate(BaseModel):
    """Metadata-only update. Eligibility rules / rule groups are intentionally
    NOT editable here; required documents are not touched either.

    All fields optional — only supplied fields change.
    """
    scheme_name: str | None = None
    department_name: str | None = None
    scheme_category: str | None = None  # AGRICULTURE|EDUCATION|... (validated)
    description: str | None = None
    benefit_description: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    # ACTIVE|INACTIVE only — EXPIRED is derived state, never set directly.
    status: str | None = None
    official_source_url: str | None = None
    application_url: str | None = None
    target_persona: str | None = None
    official_scheme_identifier: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    application_window_type: str | None = None
    # Date eligibility rules were last verified against official sources.
    # Only set this when the admin has actually verified — never fabricated.
    last_verified_at: str | None = None


@router.get("/schemes", response_model=list[SchemeOut])
async def admin_list_schemes(db: AsyncSession = Depends(get_db)) -> Any:
    """Full scheme catalogue (active AND inactive) for the admin table, with
    rule and document counts per scheme. Rule contents stay read-only here
    (admin rule view: GET /schemes/{id}/rules-with-provenance)."""
    return await SchemeAdminService(db).list()


class SchemeCreate(BaseModel):
    """Create a scheme (catalogue + curated metadata only, no rules yet)."""
    scheme_name: str
    department_name: str | None = None
    scheme_category: str | None = None
    description: str | None = None
    benefit_description: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    status: str = "ACTIVE"
    official_source_url: str | None = None
    application_url: str | None = None
    group_combining_operator: str = "AND"
    target_persona: str | None = None
    official_scheme_identifier: str | None = None
    source_type: str | None = None  # defaults to MANUAL_SEED (honest provenance)
    source_name: str | None = None
    source_url: str | None = None
    application_window_type: str | None = None


class AdminSchemeDetailOut(SchemeOut):
    """Scheme detail with the full master record fields plus rule-group,
    rule, and document counts (rule/document contents are read via the
    dedicated endpoints; not duplicated here)."""
    start_date: Any | None = None
    end_date: Any | None = None
    last_verified_at: Any | None = None
    official_scheme_identifier: str | None = None
    source_type: str | None = None
    source_name: str | None = None
    source_url: str | None = None
    application_window_type: str | None = None
    group_combining_operator: str = "AND"
    scheme_version: int = 1
    last_updated_at: Any | None = None
    rule_group_count: int = 0
    document_count: int = 0


@router.patch("/schemes/{scheme_id}", response_model=SchemeOut)
async def admin_update_scheme(
    scheme_id: uuid.UUID,
    body: SchemeUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update permitted scheme metadata. Rule tables are never touched here.

    All mutable master fields are validated server-side (vocabularies,
    http(s) URLs, name, date consistency). group_combining_operator is
    intentionally NOT editable through this endpoint — changing it changes
    eligibility outcomes and belongs to the reviewed rule-management flow.
    Invalidates the scheme reference-data cache so citizens immediately see
    the updated metadata.
    """
    service = SchemeAdminService(db)
    try:
        await service.update(
            scheme_id,
            scheme_name=body.scheme_name,
            department_name=body.department_name,
            scheme_category=body.scheme_category,
            description=body.description,
            benefit_description=body.benefit_description,
            start_date=_to_date("start_date", body.start_date),
            end_date=_to_date("end_date", body.end_date),
            status=body.status,
            official_source_url=body.official_source_url,
            application_url=body.application_url,
            target_persona=body.target_persona,
            official_scheme_identifier=body.official_scheme_identifier,
            source_type=body.source_type,
            source_name=body.source_name,
            source_url=body.source_url,
            application_window_type=body.application_window_type,
            last_verified_at=_to_date("last_verified_at", body.last_verified_at),
        )
    except SchemeAdminError as exc:
        raise _scheme_admin_error(exc) from exc

    # The scheme catalogue/detail served to citizens changed.
    await invalidate_schemes()

    rule_count_result = await db.execute(
        select(func.count())
        .select_from(SchemeEligibilityRule)
        .where(SchemeEligibilityRule.scheme_id == scheme_id)
    )
    return await _scheme_out(db, scheme_id, rule_count_result.scalar_one())


# ---------------------------
# Scheme create / detail / archive / restore / delete
# (see SchemeAdminService for validation and reference protection)
# ---------------------------


def _scheme_admin_error(exc: SchemeAdminError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _to_date(field: str, value: str | None) -> Optional[date]:
    """Parse an ISO date string (YYYY-MM-DD); None passes through."""
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"{field} must be an ISO date (YYYY-MM-DD), got '{value}'",
        ) from exc


async def _scheme_out(
    db: AsyncSession, scheme_id: uuid.UUID, rule_count: int = 0
) -> SchemeOut:
    scheme = await db.get(SchemeMaster, scheme_id)
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
        rule_count=rule_count,
    )


@router.post("/schemes", response_model=SchemeOut, status_code=201)
async def admin_create_scheme(
    body: SchemeCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create a scheme. Catalogue/metadata only — the scheme is created
    WITHOUT eligibility rules/document definitions; an admin adds rules in
    the separate reviewed rule-management flow before citizens can be
    evaluated against it (an empty rule graph is never auto-eligible)."""
    service = SchemeAdminService(db)
    try:
        scheme = await service.create(
            scheme_name=body.scheme_name,
            department_name=body.department_name,
            scheme_category=body.scheme_category,
            description=body.description,
            benefit_description=body.benefit_description,
            start_date=_to_date("start_date", body.start_date),
            end_date=_to_date("end_date", body.end_date),
            status=body.status,
            official_source_url=body.official_source_url,
            application_url=body.application_url,
            group_combining_operator=body.group_combining_operator,
            target_persona=body.target_persona,
            official_scheme_identifier=body.official_scheme_identifier,
            source_type=body.source_type,
            source_name=body.source_name,
            source_url=body.source_url,
            application_window_type=body.application_window_type,
        )
    except SchemeAdminError as exc:
        raise _scheme_admin_error(exc) from exc

    await invalidate_schemes()
    return await _scheme_out(db, scheme.scheme_id, 0)


@router.get("/schemes/{scheme_id}", response_model=AdminSchemeDetailOut)
async def admin_get_scheme(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Admin detail for one scheme (any status), always read fresh — never
    from the citizen-facing reference-data cache."""
    service = SchemeAdminService(db)
    try:
        scheme = await service.get(scheme_id)
    except SchemeAdminError as exc:
        raise _scheme_admin_error(exc) from exc

    # Groups + their rules + documents are eagerly loaded by the repository;
    # count from those to avoid an async lazy-load (would raise MissingGreenlet).
    rule_group_count = len(scheme.rule_groups)
    rule_count = sum(len(group.rules) for group in scheme.rule_groups)
    document_count = len(scheme.documents)

    return AdminSchemeDetailOut(
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
        start_date=scheme.start_date,
        end_date=scheme.end_date,
        last_verified_at=scheme.last_verified_at,
        official_scheme_identifier=scheme.official_scheme_identifier,
        source_type=scheme.source_type,
        source_name=scheme.source_name,
        source_url=scheme.source_url,
        application_window_type=scheme.application_window_type,
        group_combining_operator=scheme.group_combining_operator,
        scheme_version=scheme.scheme_version,
        last_updated_at=scheme.last_updated_at,
        rule_group_count=rule_group_count,
        document_count=document_count,
    )


@router.post("/schemes/{scheme_id}/archive", response_model=SchemeOut)
async def admin_archive_scheme(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Deactivate the scheme (status -> INACTIVE). Idempotent. History,
    assessments, and provenance are never modified. Invalidates the citizen
    scheme cache (an INACTIVE scheme vanishes from citizen lists)."""
    service = SchemeAdminService(db)
    try:
        scheme = await service.archive(scheme_id)
    except SchemeAdminError as exc:
        raise _scheme_admin_error(exc) from exc
    await invalidate_schemes()
    return await _scheme_out(db, scheme.scheme_id)


@router.post("/schemes/{scheme_id}/restore", response_model=SchemeOut)
async def admin_restore_scheme(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Reactivate an archived scheme (status -> ACTIVE). Idempotent."""
    service = SchemeAdminService(db)
    try:
        scheme = await service.restore(scheme_id)
    except SchemeAdminError as exc:
        raise _scheme_admin_error(exc) from exc
    await invalidate_schemes()
    return await _scheme_out(db, scheme.scheme_id)


@router.delete("/schemes/{scheme_id}")
async def admin_delete_scheme(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Hard-delete a scheme ONLY when it is not referenced by assessments,
    source documents, or rule provenance (409 otherwise — archive instead).
    Invalidates the citizen scheme cache; a stale cached entry could offer a
    deleted scheme to citizens."""
    service = SchemeAdminService(db)
    try:
        await service.delete(scheme_id)
    except SchemeAdminError as exc:
        raise _scheme_admin_error(exc) from exc
    await invalidate_schemes()
    return {"deleted": True, "scheme_id": str(scheme_id)}


class SchemeVerify(BaseModel):
    """Explicit verification recording. Deliberately separate from the
    generic PATCH: editing scheme metadata must never silently claim the
    scheme was verified."""
    verified_on: str  # ISO date (YYYY-MM-DD)


@router.post("/schemes/{scheme_id}/verify", response_model=SchemeOut)
async def admin_verify_scheme(
    scheme_id: uuid.UUID,
    body: SchemeVerify,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Record that an admin verified the scheme's rules/metadata against
    official sources on `verified_on` (validated ISO date, not in the
    future). Sets BOTH last_verified_at and last_verified_at_ts; ordinary
    metadata edits never touch either field. Invalidates the citizen scheme
    cache (last_verified_at is shown on scheme detail)."""
    service = SchemeAdminService(db)
    try:
        scheme = await service.verify(
            scheme_id, verified_on=_to_date("verified_on", body.verified_on)
        )
    except SchemeAdminError as exc:
        raise _scheme_admin_error(exc) from exc
    await invalidate_schemes()
    return await _scheme_out(db, scheme.scheme_id)


# ------------------------------------------------------------------
# Eligibility rule groups + rules (validated write layer in
# RuleAdminService; reads here are always fresh, never cache-served)
# ------------------------------------------------------------------


class RuleOut(BaseModel):
    rule_id: uuid.UUID
    scheme_id: uuid.UUID
    group_id: uuid.UUID
    parameter_name: str
    operator: str
    required_value: str
    rule_description: str | None = None
    rule_priority: int = 1
    failure_stage_code: str | None = None
    remedy_template: str | None = None


class RuleGroupOut(BaseModel):
    group_id: uuid.UUID
    scheme_id: uuid.UUID
    group_name: str
    intra_group_operator: str
    group_priority: int
    rules: list[RuleOut] = []


class RuleGroupCreate(BaseModel):
    group_name: str
    intra_group_operator: str = "AND"
    group_priority: int = 1


class RuleGroupUpdate(BaseModel):
    """All optional; only supplied fields change."""
    group_name: str | None = None
    intra_group_operator: str | None = None
    group_priority: int | None = None


class RuleCreate(BaseModel):
    group_id: uuid.UUID
    parameter_name: str
    operator: str
    required_value: str
    rule_description: str | None = None
    rule_priority: int = 1
    failure_stage_code: str | None = None
    remedy_template: str | None = None


class RuleUpdate(BaseModel):
    """All optional; only supplied fields change."""
    group_id: uuid.UUID | None = None
    parameter_name: str | None = None
    operator: str | None = None
    required_value: str | None = None
    rule_description: str | None = None
    rule_priority: int | None = None
    failure_stage_code: str | None = None
    remedy_template: str | None = None


class GroupCombiningOperatorUpdate(BaseModel):
    """Explicit AND<->OR switch for how the scheme's rule groups combine.
    Deliberately separate from the generic scheme PATCH (material
    eligibility change)."""
    group_combining_operator: str


def _rule_admin_error(exc: RuleAdminError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _rule_out(rule) -> RuleOut:
    return RuleOut(
        rule_id=rule.rule_id,
        scheme_id=rule.scheme_id,
        group_id=rule.group_id,
        parameter_name=rule.parameter_name,
        operator=rule.operator,
        required_value=rule.required_value,
        rule_description=rule.rule_description,
        rule_priority=rule.rule_priority,
        failure_stage_code=rule.failure_stage_code,
        remedy_template=rule.remedy_template,
    )


def _group_out(group) -> RuleGroupOut:
    return RuleGroupOut(
        group_id=group.group_id,
        scheme_id=group.scheme_id,
        group_name=group.group_name,
        intra_group_operator=group.intra_group_operator,
        group_priority=group.group_priority,
        rules=[_rule_out(r) for r in group.rules],
    )


@router.get("/schemes/{scheme_id}/rule-groups", response_model=list[RuleGroupOut])
async def admin_list_rule_groups(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List the scheme's rule groups (priority-ordered) with their nested rules."""
    service = RuleAdminService(db)
    try:
        groups = await service.list_groups(scheme_id)  # scheme validated; rules eager
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    return [_group_out(g) for g in groups]


@router.get("/schemes/{scheme_id}/rule-groups/{group_id}", response_model=RuleGroupOut)
async def admin_get_rule_group(
    scheme_id: uuid.UUID,
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = RuleAdminService(db)
    try:
        group = await service.get_group(scheme_id, group_id)
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    return _group_out(group)


@router.post("/schemes/{scheme_id}/rule-groups", response_model=RuleGroupOut, status_code=201)
async def admin_create_rule_group(
    scheme_id: uuid.UUID,
    body: RuleGroupCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = RuleAdminService(db)
    try:
        group = await service.create_group(
            scheme_id,
            group_name=body.group_name,
            intra_group_operator=body.intra_group_operator,
            group_priority=body.group_priority,
        )
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    await invalidate_schemes()
    return _group_out(group)


@router.patch("/schemes/{scheme_id}/rule-groups/{group_id}", response_model=RuleGroupOut)
async def admin_update_rule_group(
    scheme_id: uuid.UUID,
    group_id: uuid.UUID,
    body: RuleGroupUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Edit a group. Changing intra_group_operator is an explicit
    eligibility-affecting change (AND <-> OR of the group's rules) —
    validated against the frozen AND|OR vocabulary."""
    service = RuleAdminService(db)
    try:
        group = await service.update_group(
            scheme_id,
            group_id,
            group_name=body.group_name,
            intra_group_operator=body.intra_group_operator,
            group_priority=body.group_priority,
        )
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    await invalidate_schemes()
    return _group_out(group)


@router.delete("/schemes/{scheme_id}/rule-groups/{group_id}")
async def admin_delete_rule_group(
    scheme_id: uuid.UUID,
    group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Hard-delete a group + its rules ONLY when none of its rules carries
    source provenance (409 otherwise — the citation chain must survive)."""
    service = RuleAdminService(db)
    try:
        await service.delete_group(scheme_id, group_id)
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    await invalidate_schemes()
    return {"deleted": True, "group_id": str(group_id)}


@router.patch("/schemes/{scheme_id}/group-combining-operator", response_model=SchemeOut)
async def admin_set_group_combining_operator(
    scheme_id: uuid.UUID,
    body: GroupCombiningOperatorUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Switch how the scheme's groups combine (AND | OR). This is a MATERIAL
    eligibility change (every group vs any group) and lives here — never in
    the generic scheme PATCH — so it is always deliberate and vocabulary-
    validated. Invalidates the citizen scheme cache immediately."""
    service = RuleAdminService(db)
    try:
        scheme = await service.set_group_combining_operator(
            scheme_id, body.group_combining_operator
        )
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    await invalidate_schemes()
    return await _scheme_out(db, scheme.scheme_id)


@router.get("/schemes/{scheme_id}/rules", response_model=list[RuleOut])
async def admin_list_rules(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = RuleAdminService(db)
    try:
        rules = await service.list_rules(scheme_id)
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    return [_rule_out(r) for r in rules]


@router.post("/schemes/{scheme_id}/rules", response_model=RuleOut, status_code=201)
async def admin_create_rule(
    scheme_id: uuid.UUID,
    body: RuleCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Create one mandatory eligibility rule inside the scheme. The rule
    becomes a hard gate the very next eligibility evaluation consumes."""
    service = RuleAdminService(db)
    try:
        rule = await service.create_rule(
            scheme_id,
            group_id=body.group_id,
            parameter_name=body.parameter_name,
            operator=body.operator,
            required_value=body.required_value,
            rule_description=body.rule_description,
            rule_priority=body.rule_priority,
            failure_stage_code=body.failure_stage_code,
            remedy_template=body.remedy_template,
        )
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    await invalidate_schemes()
    return _rule_out(rule)


@router.get("/schemes/{scheme_id}/rules/{rule_id}", response_model=RuleOut)
async def admin_get_rule(
    scheme_id: uuid.UUID,
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = RuleAdminService(db)
    try:
        rule = await service.get_rule(scheme_id, rule_id)
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    return _rule_out(rule)


@router.patch("/schemes/{scheme_id}/rules/{rule_id}", response_model=RuleOut)
async def admin_update_rule(
    scheme_id: uuid.UUID,
    rule_id: uuid.UUID,
    body: RuleUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Edit a rule. Validation runs against the EFFECTIVE (new-or-existing)
    parameter/operator/value triple, so a partial update cannot leave an
    invalid rule behind. Provenance routes are never touched."""
    service = RuleAdminService(db)
    try:
        rule = await service.update_rule(
            scheme_id,
            rule_id,
            group_id=body.group_id,
            parameter_name=body.parameter_name,
            operator=body.operator,
            required_value=body.required_value,
            rule_description=body.rule_description,
            rule_priority=body.rule_priority,
            failure_stage_code=body.failure_stage_code,
            remedy_template=body.remedy_template,
        )
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    await invalidate_schemes()
    return _rule_out(rule)


@router.delete("/schemes/{scheme_id}/rules/{rule_id}")
async def admin_delete_rule(
    scheme_id: uuid.UUID,
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Hard-delete a rule ONLY when it has no source provenance (409
    otherwise). Assessment history is unaffected: past assessments snapshot
    their evidence against the scheme."""
    service = RuleAdminService(db)
    try:
        await service.delete_rule(scheme_id, rule_id)
    except RuleAdminError as exc:
        raise _rule_admin_error(exc) from exc
    await invalidate_schemes()
    return {"deleted": True, "rule_id": str(rule_id)}


# ------------------------------------------------------------------
# Required documents (required-document admin over the EXISTING
# tbl_scheme_document_master, validated in DocumentAdminService)
# ------------------------------------------------------------------


class DocumentOut(BaseModel):
    document_id: uuid.UUID
    scheme_id: uuid.UUID
    document_type: str
    mandatory_flag: bool
    description: str | None = None


class DocumentCreate(BaseModel):
    document_type: str
    mandatory_flag: bool = True
    description: str | None = None


class DocumentUpdate(BaseModel):
    """All optional; only supplied fields change."""
    document_type: str | None = None
    mandatory_flag: bool | None = None
    description: str | None = None


def _document_admin_error(exc: DocumentAdminError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _document_out(document: SchemeDocumentMaster) -> DocumentOut:
    return DocumentOut(
        document_id=document.document_id,
        scheme_id=document.scheme_id,
        document_type=document.document_type,
        mandatory_flag=document.mandatory_flag,
        description=document.description,
    )


@router.get("/schemes/{scheme_id}/documents", response_model=list[DocumentOut])
async def admin_list_documents(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Required documents of the scheme (same records the citizen checklist
    reads). Reads are always fresh — never cache-served."""
    service = DocumentAdminService(db)
    try:
        documents = await service.list_documents(scheme_id)
    except DocumentAdminError as exc:
        raise _document_admin_error(exc) from exc
    return [_document_out(d) for d in documents]


@router.get("/schemes/{scheme_id}/documents/{document_id}", response_model=DocumentOut)
async def admin_get_document(
    scheme_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = DocumentAdminService(db)
    try:
        document = await service.get_document(scheme_id, document_id)
    except DocumentAdminError as exc:
        raise _document_admin_error(exc) from exc
    return _document_out(document)


@router.post(
    "/schemes/{scheme_id}/documents", response_model=DocumentOut, status_code=201
)
async def admin_create_document(
    scheme_id: uuid.UUID,
    body: DocumentCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Add a required-document requirement to the scheme. document_type is
    validated against the EXISTING type vocabulary (no invented categories),
    duplicates per (scheme, type) are refused. Changing the citizen-facing
    document checklist invalidates the scheme reference-data cache."""
    service = DocumentAdminService(db)
    try:
        document = await service.create_document(
            scheme_id,
            document_type=body.document_type,
            mandatory_flag=body.mandatory_flag,
            description=body.description,
        )
    except DocumentAdminError as exc:
        raise _document_admin_error(exc) from exc
    await invalidate_schemes()
    return _document_out(document)


@router.patch(
    "/schemes/{scheme_id}/documents/{document_id}", response_model=DocumentOut
)
async def admin_update_document(
    scheme_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DocumentUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = DocumentAdminService(db)
    try:
        document = await service.update_document(
            scheme_id,
            document_id,
            document_type=body.document_type,
            mandatory_flag=body.mandatory_flag,
            description=body.description,
        )
    except DocumentAdminError as exc:
        raise _document_admin_error(exc) from exc
    await invalidate_schemes()
    return _document_out(document)


@router.delete("/schemes/{scheme_id}/documents/{document_id}")
async def admin_delete_document(
    scheme_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Remove a required-document requirement (hard delete — the service
    documents why no persisted record references it). Invalidates the
    citizen scheme cache; a stale cached detail could keep demanding a
    document the scheme no longer requires."""
    service = DocumentAdminService(db)
    try:
        await service.delete_document(scheme_id, document_id)
    except DocumentAdminError as exc:
        raise _document_admin_error(exc) from exc
    await invalidate_schemes()
    return {"deleted": True, "document_id": str(document_id)}


# ------------------------------------------------------------------
# Scheme <-> source-document association (the EXISTING
# SchemeSourceDocument.scheme_id column, administered in
# SchemeSourceLinkService — no new table, no second source system)
# ------------------------------------------------------------------


class SourceDocumentOut(BaseModel):
    source_document_id: uuid.UUID
    source_id: uuid.UUID
    scheme_id: uuid.UUID | None = None
    document_name: str
    document_url: str
    document_type: str | None = None
    version: int
    processing_status: str | None = None
    retrieved_at: Any | None = None
    content_hash: str | None = None

    @classmethod
    def from_model(cls, d: SchemeSourceDocument) -> "SourceDocumentOut":
        return cls(
            source_document_id=d.source_document_id,
            source_id=d.source_id,
            scheme_id=d.scheme_id,
            document_name=d.document_name,
            document_url=d.document_url,
            document_type=d.document_type,
            version=d.version,
            processing_status=d.processing_status,
            retrieved_at=d.retrieved_at,
            content_hash=d.content_hash,
        )


def _scheme_source_link_error(
    exc: SchemeSourceLinkError,
) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get(
    "/schemes/{scheme_id}/source-documents",
    response_model=list[SourceDocumentOut],
)
async def admin_list_scheme_source_documents(
    scheme_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Source snapshot documents linked to the scheme (the association the
    provenance citation flow reads, newest first)."""
    service = SchemeSourceLinkService(db)
    try:
        documents = await service.list_for_scheme(scheme_id)
    except SchemeSourceLinkError as exc:
        raise _scheme_source_link_error(exc) from exc
    return [SourceDocumentOut.from_model(d) for d in documents]


@router.put(
    "/schemes/{scheme_id}/source-documents/{source_document_id}",
    response_model=SourceDocumentOut,
)
async def admin_link_source_document(
    scheme_id: uuid.UUID,
    source_document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Link an existing source snapshot document to the scheme (idempotent).
    Pure association — no content, provenance, or scheme data is copied or
    changed. The association is admin-only monitoring/provenance data, not
    part of the citizen scheme catalogue, so no cache invalidation here."""
    service = SchemeSourceLinkService(db)
    try:
        document = await service.link(scheme_id, source_document_id)
    except SchemeSourceLinkError as exc:
        raise _scheme_source_link_error(exc) from exc
    return SourceDocumentOut.from_model(document)


@router.delete(
    "/schemes/{scheme_id}/source-documents/{source_document_id}",
    response_model=SourceDocumentOut,
)
async def admin_unlink_source_document(
    scheme_id: uuid.UUID,
    source_document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Detach a source snapshot document from the scheme. The snapshot and
    its provenance are never deleted — only the association is cleared —
    and the call is refused unless the document is currently linked to THIS
    scheme (another scheme's evidence cannot be detached through here)."""
    service = SchemeSourceLinkService(db)
    try:
        document = await service.unlink(scheme_id, source_document_id)
    except SchemeSourceLinkError as exc:
        raise _scheme_source_link_error(exc) from exc
    return SourceDocumentOut.from_model(document)


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
# Resources (Phase 3B / Task 1G) — registry metadata only.
# No fetching/crawling: snapshots are created only by the ingestion layer.
# ------------------------------------------------------------------


class ResourceCreate(BaseModel):
    resource_name: str
    resource_url: str
    resource_type: str
    language: str | None = None
    status: str = "ACTIVE"
    is_application_portal: bool = False
    notes: str | None = None


class ResourceUpdate(BaseModel):
    resource_name: str | None = None
    resource_url: str | None = None
    resource_type: str | None = None
    language: str | None = None
    status: str | None = None
    is_application_portal: bool | None = None
    notes: str | None = None


class ResourceOut(BaseModel):
    resource_id: uuid.UUID
    source_id: uuid.UUID
    resource_name: str
    resource_url: str
    resource_type: str
    language: str | None = None
    status: str | None = None
    fetch_method: str | None = None
    is_application_portal: bool | None = None
    discovered_at: Any | None = None
    last_checked_at: Any | None = None
    notes: str | None = None
    created_at: Any

    @classmethod
    def from_model(cls, r: SchemeSourceResource) -> "ResourceOut":
        return cls(
            resource_id=r.resource_id,
            source_id=r.source_id,
            resource_name=r.resource_name,
            resource_url=r.resource_url,
            resource_type=r.resource_type,
            language=r.language,
            status=r.status,
            fetch_method=r.fetch_method,
            is_application_portal=r.is_application_portal,
            discovered_at=r.discovered_at,
            last_checked_at=r.last_checked_at,
            notes=r.notes,
            created_at=r.created_at,
        )


def _resource_error(exc: ResourceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.post(
    "/sources/{source_id}/resources",
    response_model=ResourceOut,
    status_code=201,
)
async def admin_create_resource(
    source_id: uuid.UUID,
    body: ResourceCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Register a logical resource (catalogue page, PDF, portal, ...) under a source."""
    service = ResourceService(db)
    try:
        resource = await service.create(
            source_id,
            resource_name=body.resource_name,
            resource_url=body.resource_url,
            resource_type=body.resource_type,
            language=body.language,
            status=body.status,
            is_application_portal=body.is_application_portal,
            notes=body.notes,
        )
    except ResourceError as exc:
        raise _resource_error(exc) from exc
    return ResourceOut.from_model(resource)


@router.get("/resources", response_model=list[ResourceOut])
async def admin_list_resources(
    source_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """List resources, optionally filtered to one source."""
    service = ResourceService(db)
    try:
        resources = await service.list(source_id)
    except ResourceError as exc:
        raise _resource_error(exc) from exc
    return [ResourceOut.from_model(r) for r in resources]


@router.get("/resources/{resource_id}", response_model=ResourceOut)
async def admin_get_resource(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = ResourceService(db)
    try:
        resource = await service.get(resource_id)
    except ResourceError as exc:
        raise _resource_error(exc) from exc
    return ResourceOut.from_model(resource)


@router.patch("/resources/{resource_id}", response_model=ResourceOut)
async def admin_update_resource(
    resource_id: uuid.UUID,
    body: ResourceUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Update resource metadata (name, URL, type, language, status, notes).

    Setting status=RETIRED/INACTIVE is the supported way to deactivate a
    resource; physical deletion is deliberately not exposed.
    """
    service = ResourceService(db)
    try:
        resource = await service.update(
            resource_id,
            resource_name=body.resource_name,
            resource_url=body.resource_url,
            resource_type=body.resource_type,
            language=body.language,
            status=body.status,
            is_application_portal=body.is_application_portal,
            notes=body.notes,
        )
    except ResourceError as exc:
        raise _resource_error(exc) from exc
    return ResourceOut.from_model(resource)


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
# Form Question Configuration (Placeholders & Field Metadata)
# ------------------------------------------------------------------


class FormQuestionConfigUpdate(BaseModel):
    question_text: str | None = None
    placeholder: str | None = None
    help_text: str | None = None
    required: bool | None = None


@router.patch("/forms/questions/{question_id}")
async def admin_update_form_question(
    question_id: uuid.UUID,
    data: FormQuestionConfigUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Configure a question's label, placeholder, help_text, or required flag."""
    res = await db.execute(
        select(FormQuestion).where(FormQuestion.question_id == question_id)
    )
    question = res.scalar_one_or_none()
    if not question:
        raise HTTPException(status_code=404, detail="Form question not found")

    update_dict = data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(question, field, value)

    await db.commit()
    await db.refresh(question)
    await invalidate_form()

    return {
        "question_id": question.question_id,
        "question_code": question.question_code,
        "question_text": question.question_text,
        "placeholder": question.placeholder,
        "help_text": question.help_text,
        "required": question.required,
    }


# ------------------------------------------------------------------
# Reference-data cache ops
# ------------------------------------------------------------------


@router.get("/cache/stats")
async def admin_cache_stats() -> Any:
    """Hit/miss/entries snapshot of the Redis reference-data cache."""
    return await cache.stats()


@router.post("/cache/clear")
async def admin_cache_clear() -> Any:
    """Drop all cached reference data (schemes, forms). Next reads repopulate
    from PostgreSQL. Use after out-of-band data changes or for debugging."""
    schemes_removed = await invalidate_schemes()
    forms_removed = await invalidate_form()
    return {
        "cleared": True,
        "schemes_keys_removed": schemes_removed,
        "forms_keys_removed": forms_removed,
    }
