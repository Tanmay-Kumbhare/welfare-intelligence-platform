"""
Resource service — Phase 3B (Task 1G).

Controlled admin CRUD for tbl_scheme_source_resource plus the frozen Task 1E
URL-normalization rules. No fetching, crawling, or ingestion here by design:
resources are pure registry metadata; snapshots are created only by the
(later) ingestion layer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scheme_source import (
    RESOURCE_STATUSES,
    RESOURCE_TYPES,
    SchemeSource,
    SchemeSourceResource,
)

# Documented session/tracking query parameters that MUST NOT participate in
# resource identity (Task 1E normalization rule 6). MahaDBT deep URLs carry
# an opaque `str=` token that rotates; a tokenized URL and its token-less
# form are the same logical resource.
SESSION_QUERY_PARAMS = ("str",)


class ResourceError(Exception):
    """Raised by the resource service; carries an HTTP status + detail."""

    def __init__(self, detail: str, status_code: int = 400):
        self.detail = detail
        self.status_code = status_code
        super().__init__(detail)


def normalize_resource_url(url: str) -> str:
    """
    Normalize a resource URL per the frozen Task 1E rules:

      1. lowercase scheme and host
      2. drop the default port (:80 for http, :443 for https)
      3. drop the fragment (#...)
      4. collapse the empty path (https://host == https://host/)
      5. strip a trailing slash on the last non-empty path segment
         (/schemes/ == /schemes)
      6. drop documented session/tracking query params (str=); preserve all
         other query components in their original order

    Deterministic: the same logical resource always produces the same string.
    """
    if not url:
        raise ResourceError("resource_url must not be empty")
    if not url.lower().startswith(("http://", "https://")):
        raise ResourceError("resource_url must be an absolute http(s) URL")

    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Rule 2: strip default ports.
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Rule 3: the fragment never reaches urlunparse below (we rebuild without
    # it), so it is dropped implicitly.

    # Rules 4-5: collapse the path's trailing slash. The root path stays "/"
    # so "https://host" and "https://host/" are both represented as "/".
    path = parsed.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Rule 6: drop documented session params, preserve everything else.
    if parsed.query:
        kept = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=True)
            if k not in SESSION_QUERY_PARAMS
        ]
        query = urlencode(kept)
    else:
        query = ""

    return urlunparse((scheme, netloc, path, "", query, ""))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ResourceService:
    """Admin-controlled CRUD over scheme source resources."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_type(resource_type: str) -> str:
        if resource_type not in RESOURCE_TYPES:
            raise ResourceError(
                f"resource_type must be one of: {', '.join(RESOURCE_TYPES)}"
            )
        return resource_type

    @staticmethod
    def _validate_status(status: str) -> str:
        if status not in RESOURCE_STATUSES:
            raise ResourceError(
                f"status must be one of: {', '.join(RESOURCE_STATUSES)}"
            )
        return status

    async def _require_source(self, source_id: uuid.UUID) -> SchemeSource:
        source = await self.db.get(SchemeSource, source_id)
        if source is None:
            raise ResourceError("Source not found", status_code=404)
        return source

    async def _require_available_url(
        self, source_id: uuid.UUID, normalized_url: str
    ) -> None:
        existing = (
            await self.db.execute(
                select(SchemeSourceResource.resource_id).where(
                    SchemeSourceResource.source_id == source_id,
                    SchemeSourceResource.resource_url == normalized_url,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise ResourceError(
                "A resource with this URL already exists for this source",
                status_code=409,
            )

    async def _require_resource(
        self, resource_id: uuid.UUID
    ) -> SchemeSourceResource:
        resource = await self.db.get(SchemeSourceResource, resource_id)
        if resource is None:
            raise ResourceError("Resource not found", status_code=404)
        return resource

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        source_id: uuid.UUID,
        *,
        resource_name: str,
        resource_url: str,
        resource_type: str,
        language: str | None = None,
        status: str = "ACTIVE",
        fetch_method: str | None = None,
        is_application_portal: bool = False,
        notes: str | None = None,
    ) -> SchemeSourceResource:
        await self._require_source(source_id)
        self._validate_type(resource_type)
        self._validate_status(status)

        normalized = normalize_resource_url(resource_url)
        await self._require_available_url(source_id, normalized)

        resource = SchemeSourceResource(
            source_id=source_id,
            resource_name=resource_name,
            resource_url=normalized,
            resource_type=resource_type,
            language=language,
            status=status,
            fetch_method=fetch_method or "HTTP_GET",
            is_application_portal=is_application_portal,
            discovered_at=_utcnow(),
            notes=notes,
        )
        self.db.add(resource)
        await self.db.flush()
        return resource

    async def get(self, resource_id: uuid.UUID) -> SchemeSourceResource:
        return await self._require_resource(resource_id)

    async def list(
        self, source_id: uuid.UUID | None = None
    ) -> list[SchemeSourceResource]:
        stmt = select(SchemeSourceResource).order_by(
            SchemeSourceResource.created_at.desc()
        )
        if source_id is not None:
            await self._require_source(source_id)
            stmt = stmt.where(SchemeSourceResource.source_id == source_id)
        return list((await self.db.execute(stmt)).scalars().all())

    async def update(
        self,
        resource_id: uuid.UUID,
        *,
        resource_name: str | None = None,
        resource_url: str | None = None,
        resource_type: str | None = None,
        language: str | None = None,
        status: str | None = None,
        fetch_method: str | None = None,
        is_application_portal: bool | None = None,
        notes: str | None = None,
    ) -> SchemeSourceResource:
        resource = await self._require_resource(resource_id)

        if resource_type is not None:
            resource.resource_type = self._validate_type(resource_type)
        if status is not None:
            resource.status = self._validate_status(status)

        if resource_url is not None:
            normalized = normalize_resource_url(resource_url)
            if normalized != resource.resource_url:
                await self._require_available_url(resource.source_id, normalized)
            resource.resource_url = normalized
            # A re-registered URL is being re-checked right now.
            resource.last_checked_at = _utcnow()

        for field in (
            "resource_name",
            "language",
            "fetch_method",
            "is_application_portal",
            "notes",
        ):
            value = locals()[field]
            if value is not None:
                setattr(resource, field, value)

        await self.db.flush()
        return resource
