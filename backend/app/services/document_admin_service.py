"""
Document admin service — validated admin CRUD over the EXISTING required
documents (tbl_scheme_document_master).

Reuses the table the citizen flows already consume: citizen-facing scheme
detail (app.schemas.scheme.SchemeDetailResponse.documents) and the
recommendation document checklist (app.api.v1.recommendations). No second
requirement system, no invented document categories: the vocabulary below is
exactly the set the seeds and the model comments already use.

MANDATORY/OPTIONAL: the existing model supports it
(tbl_scheme_document_master.mandatory_flag) and the citizen recommendation
flow already honours it — a mandatory document missing/invalid blocks the
recommendation status; an optional one never does. The admin layer simply
admins that existing flag.

DELETION SAFETY: nothing persisted references a required-document row.
(tbl_eligibility_assessment stores missing-document evidence as a JSONB
SNAPSHOT inside evaluation_details, not as FKs; tbl_citizen_document rows
carry their own requirement_type strings, not document_id FKs.) A requirement
therefore hard-deletes safely; history keeps its meaning.
There is no status/is_active column on this table — archive/deactivate is
modeled simply by deleting a requirement (list is revised wholesale), matching
how the seed and the recommendation reader treat the table.

Transactions: flush-only — commit/rollback belong to the get_db lifecycle,
matching SchemeAdminService / RuleAdminService.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheme import SchemeDocumentMaster, SchemeMaster

# ------------------------------------------------------------------
# Frozen vocabulary — exactly the document types the existing system
# already uses (backend/seed_data/schemes.json + schemes_extended.json
# and the model comment listing).
# ------------------------------------------------------------------

REQUIRED_DOCUMENT_TYPES = (
    "AADHAAR",
    "BANK_PASSBOOK",
    "BPL_CARD",
    "CASTE_CERTIFICATE",
    "DISABILITY_CERTIFICATE",
    "DOMICILE_CERTIFICATE",
    "INCOME_CERTIFICATE",
    "LAND_RECORD",
    "MARKSHEET",
    "PHOTOGRAPH",
    "RATION_CARD",
    "VOTER_ID",
)

_MAX_DESCRIPTION = 2000  # Text column; a sanity cap against block dumps


class DocumentAdminError(Exception):
    """Raised by the document admin service; carries an HTTP status + detail."""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class DocumentAdminService:
    """Validated admin CRUD over a scheme's required documents (flush-only)."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_type(document_type: str | None) -> str:
        if document_type is None:
            raise DocumentAdminError("document_type is required", 400)
        if document_type not in REQUIRED_DOCUMENT_TYPES:
            raise DocumentAdminError(
                f"document_type must be one of: "
                f"{', '.join(REQUIRED_DOCUMENT_TYPES)}",
                400,
            )
        return document_type

    @staticmethod
    def _validate_description(
        description: str | None,
    ) -> str | None:
        if description is None:
            return None
        description = description.strip()
        if not description:
            return None
        if len(description) > _MAX_DESCRIPTION:
            raise DocumentAdminError(
                f"description must be at most {_MAX_DESCRIPTION} characters",
                400,
            )
        return description

    async def _require_scheme(self, scheme_id: uuid.UUID) -> SchemeMaster:
        scheme = await self.db.get(SchemeMaster, scheme_id)
        if scheme is None:
            raise DocumentAdminError("Scheme not found", 404)
        return scheme

    async def _require_unique(
        self,
        scheme_id: uuid.UUID,
        document_type: str,
        *,
        exclude_document_id: uuid.UUID | None = None,
    ) -> None:
        """One requirement per (scheme, document_type). Duplicate rows would
        make the citizen document checklist ambiguous, so they are refused
        (409) at the application layer — matching the ResourceService
        duplicate discipline, without inventing a DB constraint."""
        existing = (
            await self.db.execute(
                select(SchemeDocumentMaster.document_id).where(
                    SchemeDocumentMaster.scheme_id == scheme_id,
                    SchemeDocumentMaster.document_type == document_type,
                )
            )
        ).scalars().all()
        conflicting = [
            document_id
            for document_id in existing
            if document_id != exclude_document_id
        ]
        if conflicting:
            raise DocumentAdminError(
                f"A '{document_type}' requirement already exists for this "
                f"scheme",
                409,
            )

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def list_documents(self, scheme_id: uuid.UUID) -> list[SchemeDocumentMaster]:
        await self._require_scheme(scheme_id)
        result = await self.db.execute(
            select(SchemeDocumentMaster)
            .where(SchemeDocumentMaster.scheme_id == scheme_id)
            .order_by(SchemeDocumentMaster.document_type)
        )
        return list(result.scalars().all())

    async def get_document(
        self, scheme_id: uuid.UUID, document_id: uuid.UUID
    ) -> SchemeDocumentMaster:
        await self._require_scheme(scheme_id)
        document = await self.db.get(SchemeDocumentMaster, document_id)
        if document is None or document.scheme_id != scheme_id:
            raise DocumentAdminError(
                "Required document not found for this scheme", 404
            )
        return document

    async def create_document(
        self,
        scheme_id: uuid.UUID,
        *,
        document_type: str,
        mandatory_flag: bool = True,
        description: str | None = None,
    ) -> SchemeDocumentMaster:
        await self._require_scheme(scheme_id)
        document_type = self._validate_type(document_type)
        if not isinstance(mandatory_flag, bool):
            raise DocumentAdminError("mandatory_flag must be a boolean", 400)
        await self._require_unique(scheme_id, document_type)

        document = SchemeDocumentMaster(
            scheme_id=scheme_id,
            document_type=document_type,
            mandatory_flag=mandatory_flag,
            description=self._validate_description(description),
        )
        self.db.add(document)
        await self.db.flush()
        return document

    async def update_document(
        self,
        scheme_id: uuid.UUID,
        document_id: uuid.UUID,
        *,
        document_type: str | None = None,
        mandatory_flag: bool | None = None,
        description: str | None = None,
    ) -> SchemeDocumentMaster:
        """Edit a requirement. All fields optional; only supplied change.
        Uniqueness is checked against the (scheme, NEW type) pair excluding
        the row itself on update."""
        document = await self.get_document(scheme_id, document_id)

        if document_type is not None:
            document_type = self._validate_type(document_type)
            if document_type != document.document_type:
                await self._require_unique(
                    scheme_id,
                    document_type,
                    exclude_document_id=document.document_id,
                )
        if mandatory_flag is not None:
            if not isinstance(mandatory_flag, bool):
                raise DocumentAdminError("mandatory_flag must be a boolean", 400)
        if description is not None:
            description = self._validate_description(description)

        if document_type is not None:
            document.document_type = document_type
        if mandatory_flag is not None:
            document.mandatory_flag = mandatory_flag
        if description is not None:
            document.description = description

        await self.db.flush()
        return document

    async def delete_document(
        self, scheme_id: uuid.UUID, document_id: uuid.UUID
    ) -> None:
        """Hard delete a requirement row.

        Safe by reference inspection: no persisted record keys on a
        required-document row (assessment evidence is a JSONB snapshot;
        citizen uploads carry their own type strings), so nothing of
        historical meaning is destroyed. Deleting a mandatory requirement
        naturally stops it appearing on the citizen checklist going forward.
        """
        document = await self.get_document(scheme_id, document_id)
        await self.db.delete(document)
        await self.db.flush()
