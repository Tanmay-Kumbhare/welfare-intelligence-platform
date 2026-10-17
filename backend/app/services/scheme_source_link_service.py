"""
Scheme source-document association service — links EXISTING source snapshot
documents (tbl_scheme_source_document) to schemes.

The association mechanism ALREADY EXISTS: `SchemeSourceDocument.scheme_id`
(nullable FK, ondelete SET NULL) is set by `run_manual_fetch(scheme_id=...)`
during ingestion and read by the provenance flow
(`app.services.rule_provenance_service` resolves a scheme's citation
sentences from the documents explicitly linked to it). What was missing is
admin control AFTER a snapshot exists: a discovery fetch creates documents
possibly before a scheme row does, and snapshots can be re-classified.

So this service only administers the EXISTING association column — no new
table, no second source system, and it never copies provenance/content.
Linking is idempotent; unlinking requires the snapshot to actually belong to
the given scheme so an admin cannot silently detach another scheme's
evidence.

Transactions: flush-only — commit/rollback belong to the get_db lifecycle.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheme import SchemeMaster
from app.models.scheme_source import SchemeSourceDocument


class SchemeSourceLinkError(Exception):
    """Raised by the scheme source-link service; HTTP status + detail."""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


class SchemeSourceLinkService:
    """Admin-controlled scheme association for existing source documents."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _require_scheme(self, scheme_id: uuid.UUID) -> SchemeMaster:
        scheme = await self.db.get(SchemeMaster, scheme_id)
        if scheme is None:
            raise SchemeSourceLinkError("Scheme not found", 404)
        return scheme

    async def _require_document(
        self, source_document_id: uuid.UUID
    ) -> SchemeSourceDocument:
        document = await self.db.get(SchemeSourceDocument, source_document_id)
        if document is None:
            raise SchemeSourceLinkError("Source document not found", 404)
        return document

    async def list_for_scheme(
        self, scheme_id: uuid.UUID
    ) -> list[SchemeSourceDocument]:
        """Snapshots explicitly linked to the scheme, newest first. This is
        the association the provenance flow reads (latest document first)."""
        await self._require_scheme(scheme_id)
        result = await self.db.execute(
            select(SchemeSourceDocument)
            .where(SchemeSourceDocument.scheme_id == scheme_id)
            .order_by(SchemeSourceDocument.created_at.desc())
        )
        return list(result.scalars().all())

    async def link(
        self, scheme_id: uuid.UUID, source_document_id: uuid.UUID
    ) -> SchemeSourceDocument:
        """Associate an existing source document with the scheme (idempotent)."""
        await self._require_scheme(scheme_id)
        document = await self._require_document(source_document_id)
        if document.scheme_id != scheme_id:
            document.scheme_id = scheme_id
            await self.db.flush()
        return document

    async def unlink(
        self, scheme_id: uuid.UUID, source_document_id: uuid.UUID
    ) -> SchemeSourceDocument:
        """Detach a source document from the scheme (back to unassociated —
        the state documents live in right after a discovery fetch).

        The snapshot itself is NEVER deleted: it may carry ingestion history,
        content, and rule provenance citations, so only the association
        column is cleared. Refused (404) unless the snapshot is currently
        linked to THIS scheme, so another scheme's evidence can never be
        silently detached through this path."""
        await self._require_scheme(scheme_id)
        document = await self._require_document(source_document_id)
        if document.scheme_id != scheme_id:
            raise SchemeSourceLinkError(
                "Source document is not linked to this scheme", 404
            )
        document.scheme_id = None
        await self.db.flush()
        return document
