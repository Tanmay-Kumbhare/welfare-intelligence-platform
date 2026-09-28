"""
Manual scheme-source ingestion service.

Flow (Phase 3B slice — deliberately stops at the raw snapshot layer):

    Admin triggers POST /admin/sources/{id}/fetch
        -> ingestion run (RUNNING)
        -> HTTP fetch via httpx
        -> validate response
        -> raw content snapshot (tbl_scheme_source_content, type RAW)
        -> SHA-256 content hash
        -> run COMPLETED (or FAILED with error_summary)

HARD INVARIANT: this service NEVER writes to tbl_scheme_master,
tbl_scheme_rule_group, or tbl_scheme_eligibility_rule. Candidate-rule
extraction and human review come in later phases.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheme_source import (
    SchemeIngestionRun,
    SchemeSource,
    SchemeSourceContent,
    SchemeSourceDocument,
)

# Generous but bounded: government portals can be slow, but an admin
# triggered request must never hang a worker indefinitely.
FETCH_TIMEOUT_SECONDS = 20.0
MAX_CONTENT_CHARS = 5_000_000  # ~5 MB of text; refuse absurdly large bodies

USER_AGENT = (
    "VidyaSetuIngestionBot/1.0 "
    "(welfare scheme provenance snapshots; manual admin-triggered fetch)"
)


class IngestionError(Exception):
    """Raised when a fetch cannot produce a usable raw snapshot."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _document_name_for(url: str) -> str:
    """Derive a stable human-readable document name from the fetched URL."""
    parsed = urlparse(url)
    segments = [s for s in parsed.path.split("/") if s]
    if segments:
        candidate = segments[-1]
        # Strip a trailing file extension like .html or .pdf for readability,
        # but keep names short and safe.
        if "." in candidate:
            candidate = candidate.rsplit(".", 1)[0]
        candidate = candidate[:200]
        if candidate:
            return candidate
    return parsed.netloc or "fetched-document"


async def fetch_raw_content(url: str) -> str:
    """Fetch the URL and return the response body as text, or raise."""
    if not url or not url.startswith(("http://", "https://")):
        raise IngestionError("Source URL must be an absolute http(s) URL")

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=FETCH_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT},
    ) as client:
        try:
            response = await client.get(url)
        except httpx.HTTPError as exc:
            raise IngestionError(f"Request failed: {exc}") from exc

    if response.status_code >= 400:
        raise IngestionError(f"Source responded with HTTP {response.status_code}")

    content = response.text
    if not content.strip():
        raise IngestionError("Source responded with an empty body")
    if len(content) > MAX_CONTENT_CHARS:
        raise IngestionError(
            f"Response too large to snapshot ({len(content)} chars > {MAX_CONTENT_CHARS})"
        )
    return content


async def run_manual_fetch(
    db: AsyncSession,
    source: SchemeSource,
    scheme_id: uuid.UUID | None = None,
) -> SchemeIngestionRun:
    """
    Execute one manual ingestion run against `source`.

    Creates the run row first (RUNNING), then fetches. On success stores a
    SchemeSourceDocument (versioned per (source, document_name)) plus a RAW
    SchemeSourceContent snapshot with the SHA-256 hash. On failure records
    FAILED + error_summary. Scheme/rule tables are never modified.
    """
    run = SchemeIngestionRun(source_id=source.source_id, status="RUNNING")
    db.add(run)
    await db.flush()  # assign ingestion_run_id before fetch side effects

    url = source.base_url
    try:
        content = await fetch_raw_content(url)
    except IngestionError as exc:
        run.status = "FAILED"
        run.error_summary = str(exc)
        run.completed_at = _utcnow()
        await db.flush()
        return run

    content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    document_name = _document_name_for(url)

    # Version: same document name re-fetched becomes the next version so
    # change detection (hash comparison) works across retrievals.
    max_version = await db.execute(
        select(func.max(SchemeSourceDocument.version)).where(
            SchemeSourceDocument.source_id == source.source_id,
            SchemeSourceDocument.document_name == document_name,
        )
    )
    next_version = (max_version.scalar_one() or 0) + 1
    now = _utcnow()

    document = SchemeSourceDocument(
        source_id=source.source_id,
        scheme_id=scheme_id,
        document_name=document_name,
        document_url=url,
        language="en",
        version=next_version,
        retrieved_at=now,
        content_hash=content_hash,
        # Retrieval is done; content extraction (future phase) stays PENDING.
        processing_status="PROCESSED",
    )
    db.add(document)
    await db.flush()  # assign source_document_id

    db.add(
        SchemeSourceContent(
            source_document_id=document.source_document_id,
            content_type="RAW",
            raw_content=content,
            language="en",
            # Raw bytes are preserved verbatim; extraction is a later phase.
            processing_status="PENDING",
            extraction_version="raw-v1",
            retrieved_at=now,
        )
    )

    run.status = "COMPLETED"
    run.records_discovered = 1
    run.records_created = 1
    run.completed_at = now
    await db.flush()
    return run
