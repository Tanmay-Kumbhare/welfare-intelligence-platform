"""
Scheme admin service — controlled admin CRUD over the scheme catalogue.

Complements the existing read-oriented SchemeService: this layer owns the
*write* paths (create / update / archive / restore / delete) so every
mutation is validated server-side, ownership/authorization stays in the
admin router's require_admin dependency, and the reference-data cache is
invalidated by the calling route after a successful change.

Scope (deliberate, per the task breakdown):
  - Scheme master fields only. Rule groups / eligibility rules / required
    documents are NOT editable here; a scheme is created without rules and
    rule management is a separate, reviewed step.
  - Deletion is reference-aware: a scheme referenced by assessments,
    source documents, or rule provenance is never hard-deleted (history
    and provenance must survive); admins are pointed to archive instead.

Transactions: the service only flushes; the request's get_db() dependency
commits on success and rolls back on exception. No nested transactions.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assessment import EligibilityAssessment
from app.models.scheme import SchemeDocumentMaster, SchemeEligibilityRule, SchemeMaster
from app.models.scheme_source import SchemeRuleProvenance, SchemeSourceDocument

# ------------------------------------------------------------------
# Frozen vocabularies (match tbl_scheme_master column comments / seeds)
# ------------------------------------------------------------------

SCHEME_CATEGORIES = (
    "AGRICULTURE",
    "EDUCATION",
    "HEALTHCARE",
    "HOUSING",
    "PENSION",
    "ENERGY",
    "EMPLOYMENT",
)

# EXPIRED is derived state (e.g. window end passed) — admins may not set it directly.
SCHEME_STATUSES = ("ACTIVE", "INACTIVE", "EXPIRED")

# Persona tag for filtered discovery on the citizen side.
SCHEME_PERSONAS = ("FARMER", "STUDENT", "SENIOR", "GENERAL")

# Where the scheme record came from. Rows created through this admin API
# are manually curated records, so MANUAL_SEED is the honest default —
# government provenance must never be fabricated.
SCHEME_SOURCE_TYPES = (
    "MANUAL_SEED",
    "GOVERNMENT_API",
    "GOVERNMENT_WEBSITE",
    "GOVERNMENT_PORTAL",
    "GOVERNMENT_PDF",
    "OTHER_AUTHORIZED_SOURCE",
)

APPLICATION_WINDOW_TYPES = (
    "FRESH_APPLICATION",
    "RENEWAL",
    "BOTH",
    "CONTINUOUS",
    "WINDOW_BASED",
)

# How the scheme's rule groups combine. Consumed by the eligibility engine,
# so it is validated strictly. Editable only at create time — changing it on
# an existing scheme changes eligibility outcomes and belongs to the
# (future) reviewed rule-management workflow.
RULE_GROUP_OPERATORS = ("AND", "OR")


class SchemeAdminError(Exception):
    """Raised by the scheme admin service; carries an HTTP status + detail."""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SchemeAdminService:
    """Validated admin CRUD over tbl_scheme_master (flush-only)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _require_name(name: str | None) -> str:
        if name is None:
            raise SchemeAdminError("scheme_name is required", 400)
        name = name.strip()
        if not name:
            raise SchemeAdminError("scheme_name must not be empty", 400)
        if len(name) > 255:
            raise SchemeAdminError("scheme_name must be at most 255 characters", 400)
        return name

    @staticmethod
    def _enum(field: str, value: str, allowed: tuple[str, ...]) -> str:
        if value not in allowed:
            raise SchemeAdminError(
                f"{field} must be one of: {', '.join(allowed)}", 400
            )
        return value

    @staticmethod
    def _url(field: str, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        if not value.lower().startswith(("http://", "https://")):
            raise SchemeAdminError(f"{field} must be an absolute http(s) URL", 400)
        if len(value) > 500:
            raise SchemeAdminError(f"{field} must be at most 500 characters", 400)
        return value

    async def _validate_dates(
        self,
        *,
        start_date: date | None,
        end_date: date | None,
        scheme: SchemeMaster | None = None,
    ) -> None:
        """Reject an application window that ends before it starts.

        When only one bound is supplied on update, the missing side is read
        from the existing row so the pair is still consistent.
        """
        effective_start = start_date
        effective_end = end_date
        if scheme is not None and effective_start is None:
            effective_start = scheme.start_date
        if scheme is not None and effective_end is None:
            effective_end = scheme.end_date
        if effective_start and effective_end and effective_end < effective_start:
            raise SchemeAdminError("end_date must not be before start_date", 400)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    async def get(self, scheme_id: uuid.UUID) -> SchemeMaster:
        """Eager scheme load for read paths (groups + rules + documents)."""
        from app.repositories.scheme_repository import SchemeRepository

        scheme = await SchemeRepository(self.db).get_by_id(scheme_id)
        if scheme is None:
            raise SchemeAdminError("Scheme not found", 404)
        return scheme

    async def list(self) -> list[dict]:
        """Scheme catalogue with rule/document counts for the admin table.

        Two grouped-count queries + one scheme query; no per-scheme N+1.
        """
        schemes = (
            (await self.db.execute(select(SchemeMaster).order_by(SchemeMaster.scheme_name)))
            .scalars()
            .all()
        )
        rule_counts = dict(
            await self._grouped_counts(SchemeEligibilityRule, SchemeEligibilityRule.rule_id)
        )
        doc_counts = dict(
            await self._grouped_counts(SchemeDocumentMaster, SchemeDocumentMaster.document_id)
        )
        return [
            {
                "scheme_id": scheme.scheme_id,
                "scheme_name": scheme.scheme_name,
                "department_name": scheme.department_name,
                "scheme_category": scheme.scheme_category,
                "description": scheme.description,
                "benefit_description": scheme.benefit_description,
                "status": scheme.status,
                "official_source_url": scheme.official_source_url,
                "application_url": scheme.application_url,
                "target_persona": scheme.target_persona,
                "rule_count": rule_counts.get(scheme.scheme_id, 0),
                "document_count": doc_counts.get(scheme.scheme_id, 0),
            }
            for scheme in schemes
        ]

    async def _grouped_counts(self, model, count_column):
        result = await self.db.execute(
            select(model.scheme_id, func.count(count_column)).group_by(model.scheme_id)
        )
        return result.all()

    async def _scalar_count(self, model, scheme_id: uuid.UUID) -> int:
        result = await self.db.execute(
            select(func.count()).select_from(model).where(model.scheme_id == scheme_id)
        )
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    async def create(
        self,
        *,
        scheme_name: str,
        department_name: str | None = None,
        scheme_category: str | None = None,
        description: str | None = None,
        benefit_description: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        status: str = "ACTIVE",
        official_source_url: str | None = None,
        application_url: str | None = None,
        group_combining_operator: str = "AND",
        target_persona: str | None = None,
        official_scheme_identifier: str | None = None,
        source_type: str | None = None,
        source_name: str | None = None,
        source_url: str | None = None,
        application_window_type: str | None = None,
    ) -> SchemeMaster:
        name = self._require_name(scheme_name)
        await self._validate_dates(start_date=start_date, end_date=end_date)
        status = self._enum(
            "status", status, ("ACTIVE", "INACTIVE")
        )  # EXPIRED is derived state, never set by an admin
        if scheme_category is not None:
            scheme_category = self._enum(
                "scheme_category", scheme_category, SCHEME_CATEGORIES
            )
        if target_persona is not None:
            target_persona = self._enum("target_persona", target_persona, SCHEME_PERSONAS)
        group_combining_operator = self._enum(
            "group_combining_operator",
            group_combining_operator.upper() if isinstance(group_combining_operator, str) else group_combining_operator,
            RULE_GROUP_OPERATORS,
        )
        if source_type is not None:
            source_type = self._enum("source_type", source_type, SCHEME_SOURCE_TYPES)
        if application_window_type is not None:
            application_window_type = self._enum(
                "application_window_type",
                application_window_type,
                APPLICATION_WINDOW_TYPES,
            )

        scheme = SchemeMaster(
            scheme_name=name,
            department_name=(department_name or None),
            scheme_category=scheme_category,
            description=description,
            benefit_description=benefit_description,
            start_date=start_date,
            end_date=end_date,
            status=status,
            official_source_url=self._url("official_source_url", official_source_url),
            application_url=self._url("application_url", application_url),
            group_combining_operator=group_combining_operator,
            target_persona=target_persona,
            official_scheme_identifier=official_scheme_identifier,
            source_type=source_type or "MANUAL_SEED",
            source_name=source_name,
            source_url=self._url("source_url", source_url),
            application_window_type=application_window_type,
            scheme_version=1,
            # No verification claim on creation: last_verified_at must only
            # be set by an admin after actually verifying against official
            # sources — via the explicit verify() / POST /verify endpoint
            # (the only place both verification fields are set together).
            # Never fabricated here.
        )
        self.db.add(scheme)
        await self.db.flush()
        return scheme

    async def update(
        self,
        scheme_id: uuid.UUID,
        *,  # all optional; only supplied fields change
        scheme_name: str | None = None,
        department_name: str | None = None,
        scheme_category: str | None = None,
        description: str | None = None,
        benefit_description: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        status: str | None = None,
        official_source_url: str | None = None,
        application_url: str | None = None,
        target_persona: str | None = None,
        official_scheme_identifier: str | None = None,
        source_type: str | None = None,
        source_name: str | None = None,
        source_url: str | None = None,
        application_window_type: str | None = None,
        last_verified_at: date | None = None,
    ) -> SchemeMaster:
        """Metadata-only update of an existing scheme.

        Validation happens against the NEW value before it is applied, and
        date consistency is checked against the effective (new-or-existing)
        pair. group_combining_operator is intentionally not editable here.
        last_verified_at is applied only when the caller supplies it
        explicitly (never implicitly by an edit); the canonical verification
        record — setting last_verified_at_ts as well — remains verify().
        """
        scheme = await self.get(scheme_id)

        if scheme_name is not None:
            scheme.scheme_name = self._require_name(scheme_name)
        if status is not None:
            scheme.status = self._enum("status", status, ("ACTIVE", "INACTIVE"))
        if scheme_category is not None:
            scheme.scheme_category = self._enum(
                "scheme_category", scheme_category, SCHEME_CATEGORIES
            )
        if target_persona is not None:
            scheme.target_persona = self._enum(
                "target_persona", target_persona, SCHEME_PERSONAS
            )
        if source_type is not None:
            scheme.source_type = self._enum("source_type", source_type, SCHEME_SOURCE_TYPES)
        if application_window_type is not None:
            scheme.application_window_type = self._enum(
                "application_window_type",
                application_window_type,
                APPLICATION_WINDOW_TYPES,
            )

        for field, value in (
            ("department_name", department_name),
            ("description", description),
            ("benefit_description", benefit_description),
            ("start_date", start_date),
            ("end_date", end_date),
            ("official_source_url", self._url("official_source_url", official_source_url)),
            ("application_url", self._url("application_url", application_url)),
            ("source_name", source_name),
            ("source_url", self._url("source_url", source_url)),
            ("official_scheme_identifier", official_scheme_identifier),
            ("last_verified_at", last_verified_at),
        ):
            if value is not None:
                setattr(scheme, field, value)

        await self._validate_dates(
            start_date=start_date, end_date=end_date, scheme=scheme
        )

        # Canonical revision metadata. scheme_version stays untouched:
        # version-numbering semantics belong to the published-versions phase.
        scheme.last_updated_at = _utcnow()

        await self.db.flush()
        return scheme

    async def verify(
        self, scheme_id: uuid.UUID, *, verified_on: date
    ) -> SchemeMaster:
        """Record an explicit verification of the scheme's rules/metadata
        against official sources.

        Deliberately separate from update(): an admin may edit metadata a
        hundred times without verifying anything — editing NEVER updates the
        verification fields. This endpoint is the only place both
        verification fields are set together:
          - last_verified_at     (V1 date column, human-readable)
          - last_verified_at_ts  (canonical timestamp of the verification)
        A future date is refused — that would be a false claim.
        """
        scheme = await self.get(scheme_id)
        if verified_on > date.today():
            raise SchemeAdminError(
                "verified_on must not be a future date", 400
            )
        scheme.last_verified_at = verified_on
        scheme.last_verified_at_ts = _utcnow()
        scheme.last_updated_at = _utcnow()
        await self.db.flush()
        return scheme

    async def archive(self, scheme_id: uuid.UUID) -> SchemeMaster:
        """Deactivate (status=INACTIVE). Idempotent; never touches history."""
        scheme = await self.get(scheme_id)
        scheme.status = "INACTIVE"
        scheme.last_updated_at = _utcnow()
        await self.db.flush()
        return scheme

    async def restore(self, scheme_id: uuid.UUID) -> SchemeMaster:
        """Reactivate (status=ACTIVE). Idempotent."""
        scheme = await self.get(scheme_id)
        scheme.status = "ACTIVE"
        scheme.last_updated_at = _utcnow()
        await self.db.flush()
        return scheme

    async def delete(self, scheme_id: uuid.UUID) -> None:
        """Hard delete — ONLY when the scheme is genuinely unreferenced.

        Refused (409) when any of the following exists, because removing the
        scheme would silently destroy citizen-facing history or provenance:
          - tbl_eligibility_assessment rows (assessments cascade away)
          - linked tbl_scheme_source_document rows (FSK SET NULL would
            silently unlink the scheme from its source evidence)
          - tbl_scheme_rule_provenance rows (they cascade away with the
            scheme's rules, losing rule→source citations)
        Otherwise rule groups, rules, and required-document rows cascade
        cleanly (all FK ondelete=CASCADE) and the row is deleted.
        """
        scheme = await self.db.get(SchemeMaster, scheme_id)
        if scheme is None:
            raise SchemeAdminError("Scheme not found", 404)

        assessments = await self._scalar_count(EligibilityAssessment, scheme_id)
        if assessments:
            raise SchemeAdminError(
                "Scheme is referenced by assessment history; archive it instead",
                409,
            )

        if await self._scalar_count(SchemeSourceDocument, scheme_id):
            raise SchemeAdminError(
                "Scheme is linked to source documents; archive it instead",
                409,
            )

        rule_ids = (
            await self.db.execute(
                select(SchemeEligibilityRule.rule_id).where(
                    SchemeEligibilityRule.scheme_id == scheme_id
                )
            )
        ).scalars().all()
        if rule_ids:
            provenance = await self.db.execute(
                select(func.count())
                .select_from(SchemeRuleProvenance)
                .where(SchemeRuleProvenance.rule_id.in_(rule_ids))
            )
            if provenance.scalar_one():
                raise SchemeAdminError(
                    "Scheme rules have source provenance; archive it instead",
                    409,
                )

        await self.db.delete(scheme)
        await self.db.flush()
