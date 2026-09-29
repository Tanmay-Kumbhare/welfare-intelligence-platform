"""
Scheme service — orchestrates scheme operations.

Read paths are served through the reference-data TTL cache: the scheme
catalogue and scheme details are fully eager-loaded (groups + rules +
documents) and change only via reviewed admin mutations, so caching them
removes the largest repeated cost of the remote database on every page
view. Cached values are serialized Pydantic DTOs — never session-bound
ORM objects.

Cache discipline:
  - Written by: GET /schemes/, GET /schemes/{id}
  - Invalidated by: admin scheme PATCH (metadata edit) and the admin
    cache-clear endpoint. Ingestion never mutates scheme rows, so the
    fetch path needs no invalidation hook by design.
  - Any cache failure degrades silently to the database.
"""

from __future__ import annotations

import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache, scheme_detail_key, schemes_all_key
from app.models.scheme import SchemeMaster
from app.repositories.scheme_repository import SchemeRepository
from app.schemas.scheme import SchemeDetailResponse, SchemeResponse


class SchemeService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = SchemeRepository(db)

    async def get_all_schemes(self) -> Sequence[SchemeMaster | SchemeResponse]:
        cached = cache.get(schemes_all_key())
        if cached is not None:
            return cached

        schemes = await self.repo.get_all_active()
        serialized = [SchemeResponse.model_validate(s).model_dump() for s in schemes]
        cache.set(schemes_all_key(), serialized)
        return serialized

    async def get_scheme(
        self, scheme_id: uuid.UUID
    ) -> SchemeMaster | SchemeDetailResponse | None:
        cached = cache.get(scheme_detail_key(scheme_id))
        if cached is not None:
            return cached

        scheme = await self.repo.get_by_id(scheme_id)
        if scheme is not None:
            cache.set(
                scheme_detail_key(scheme_id),
                SchemeDetailResponse.model_validate(scheme).model_dump(),
            )
        return scheme
