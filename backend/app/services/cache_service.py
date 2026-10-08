"""
Dedicated Redis Cache Service for VidyaSetu.

Provides async Redis caching with:
  - Cache-aside read/write helpers
  - JSON serialization for Pydantic models, dicts, lists, UUIDs, datetimes
  - Graceful Redis connection failure handling (bypasses cache to PostgreSQL)
  - Structured logging for cache hits, misses, sets, and invalidations
  - Centralized key builders and invalidation hooks
"""

import asyncio
import json
import logging
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from enum import Enum
from typing import Any, Awaitable, Callable, Optional, Sequence

import redis.asyncio as aioredis
from pydantic import BaseModel

from app.config import get_settings

logger = logging.getLogger(__name__)

# Key prefixes following the project specification
PREFIX = "vidyasetu"
KEY_SCHEMES_LIST = f"{PREFIX}:schemes:list"
KEY_FORMS_LIST_PREFIX = f"{PREFIX}:forms:list"
PREFIX_SCHEMES = f"{PREFIX}:schemes:"
PREFIX_FORMS = f"{PREFIX}:forms:"
PREFIX_CITIZENS = f"{PREFIX}:citizens:"
PREFIX_CITIZEN_FACTS = f"{PREFIX}:citizen_facts:"
PREFIX_ELIGIBILITY = f"{PREFIX}:eligibility:"


class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder supporting Pydantic models, UUIDs, dates, decimals, and enums."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, BaseModel):
            return obj.model_dump(mode="json")
        if isinstance(obj, uuid.UUID):
            return str(obj)
        if isinstance(obj, (datetime, date, time)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        if isinstance(obj, Enum):
            return obj.value
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        return super().default(obj)


def _serialize(value: Any) -> str:
    return json.dumps(value, cls=JSONEncoder)


def _deserialize(payload: str) -> Any:
    return json.loads(payload)


class RedisCacheService:
    """Async Redis cache service with graceful degradation and metric tracking."""

    def __init__(self) -> None:
        self._client: Optional[aioredis.Redis] = None
        self._pool: Optional[aioredis.ConnectionPool] = None
        self._hits = 0
        self._misses = 0
        self._errors = 0

    @property
    def enabled(self) -> bool:
        try:
            settings = get_settings()
            return bool(getattr(settings, "REDIS_CACHE_ENABLED", True) and getattr(settings, "CACHE_ENABLED", True))
        except Exception:
            return True

    @property
    def redis_url(self) -> str:
        try:
            return str(getattr(get_settings(), "REDIS_URL", "redis://localhost:6379/0"))
        except Exception:
            return "redis://localhost:6379/0"

    async def get_client(self) -> Optional[aioredis.Redis]:
        """Lazy-initialize or return existing Redis client with connection pool."""
        if not self.enabled:
            return None
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None

        if self._client is not None and getattr(self, "_loop", None) == current_loop:
            return self._client
        try:
            self._pool = aioredis.ConnectionPool.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=20,
                socket_connect_timeout=2.0,
                socket_timeout=2.0,
            )
            self._client = aioredis.Redis(connection_pool=self._pool)
            self._loop = current_loop
            return self._client
        except Exception as exc:
            self._errors += 1
            logger.warning("Failed to initialize Redis connection: %s (bypassing cache)", exc)
            return None

    async def close(self) -> None:
        """Close connection pool cleanly during application shutdown."""
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception as exc:
                logger.warning("Error closing Redis client: %s", exc)
            self._client = None
        if self._pool is not None:
            try:
                await self._pool.disconnect()
            except Exception as exc:
                logger.warning("Error closing Redis pool: %s", exc)
            self._pool = None

    async def get(self, key: str) -> Optional[Any]:
        """
        Fetch deserialized value from Redis.
        Returns None on cache miss, expiry, Redis failure, or if cache is disabled.
        """
        if not self.enabled:
            return None
        try:
            client = await self.get_client()
            if client is None:
                return None
            raw = await client.get(key)
            if raw is None:
                self._misses += 1
                logger.info("CACHE MISS key=%s", key)
                return None
            self._hits += 1
            logger.info("CACHE HIT  key=%s", key)
            return _deserialize(raw)
        except Exception as exc:
            self._errors += 1
            logger.warning("Redis cache error on GET key=%s: %s (bypassing cache)", key, exc)
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """
        Store serialized JSON value in Redis with TTL.
        Returns True on success, False on failure.
        """
        if not self.enabled:
            return False
        try:
            client = await self.get_client()
            if client is None:
                return False
            if ttl is None:
                try:
                    ttl = int(get_settings().CACHE_TTL_SECONDS)
                except Exception:
                    ttl = 300
            if ttl <= 0:
                return False
            payload = _serialize(value)
            await client.set(key, payload, ex=ttl)
            logger.info("CACHE SET  key=%s ttl=%s", key, ttl)
            return True
        except Exception as exc:
            self._errors += 1
            logger.warning("Redis cache error on SET key=%s: %s (bypassing cache)", key, exc)
            return False

    async def delete(self, key: str) -> bool:
        """Delete single key from Redis."""
        try:
            client = await self.get_client()
            if client is None:
                return False
            count = await client.delete(key)
            if count > 0:
                logger.info("CACHE INVALIDATE key=%s", key)
            return count > 0
        except Exception as exc:
            self._errors += 1
            logger.warning("Redis cache error on DELETE key=%s: %s", key, exc)
            return False

    async def delete_prefix(self, prefix: str) -> int:
        """Delete all keys matching the prefix via scan_iter."""
        try:
            client = await self.get_client()
            if client is None:
                return 0
            keys = []
            async for k in client.scan_iter(match=f"{prefix}*"):
                keys.append(k)
            if not keys:
                return 0
            count = await client.delete(*keys)
            logger.info("CACHE INVALIDATE_PREFIX prefix=%s removed=%s", prefix, count)
            return count
        except Exception as exc:
            self._errors += 1
            logger.warning("Redis cache error on DELETE_PREFIX prefix=%s: %s", prefix, exc)
            return 0

    async def clear_all(self) -> int:
        """Clear all vidyasetu cache keys."""
        return await self.delete_prefix(f"{PREFIX}:")

    async def health(self) -> dict[str, Any]:
        """Diagnostic health check for Redis connectivity."""
        try:
            client = await self.get_client()
            if client is None:
                return {"status": "unavailable", "reason": "Client initialization failed"}
            pong = await client.ping()
            return {
                "status": "connected" if pong else "unreachable",
                "ping": "PONG" if pong else str(pong),
                "url": self.redis_url,
                "hits": self._hits,
                "misses": self._misses,
                "errors": self._errors,
            }
        except Exception as exc:
            return {
                "status": "unavailable",
                "reason": str(exc),
                "url": self.redis_url,
                "hits": self._hits,
                "misses": self._misses,
                "errors": self._errors,
            }

    async def stats(self) -> dict[str, Any]:
        """Cache hit/miss/keys summary."""
        keys = []
        try:
            client = await self.get_client()
            if client is not None:
                async for k in client.scan_iter(match=f"{PREFIX}:*"):
                    keys.append(k)
        except Exception:
            pass
        return {
            "hits": self._hits,
            "misses": self._misses,
            "errors": self._errors,
            "entries": len(keys),
            "keys": sorted(keys),
        }

    async def get_or_set(
        self,
        key: str,
        fetch_fn: Callable[[], Awaitable[Any]],
        ttl: Optional[int] = None,
    ) -> Any:
        """Cache-aside helper: returns cached value or computes and caches it."""
        cached = await self.get(key)
        if cached is not None:
            return cached
        result = await fetch_fn()
        if result is not None:
            await self.set(key, result, ttl=ttl)
        return result


# Singleton instance
cache_service = RedisCacheService()


# ----------------------------------------------------------------------
# Canonical Key Builders
# ----------------------------------------------------------------------

def schemes_all_key() -> str:
    return KEY_SCHEMES_LIST


def scheme_detail_key(scheme_id: uuid.UUID | str) -> str:
    return f"{PREFIX_SCHEMES}{scheme_id}"


def scheme_rules_key(scheme_id: uuid.UUID | str) -> str:
    return f"{PREFIX_SCHEMES}rules:{scheme_id}"


def forms_list_key(target_citizen_type: Optional[str] = None) -> str:
    return f"{KEY_FORMS_LIST_PREFIX}:{target_citizen_type or 'all'}"


def form_active_key(form_code: str) -> str:
    return f"{PREFIX_FORMS}{form_code}"


def citizen_key(citizen_id: uuid.UUID | str) -> str:
    return f"{PREFIX_CITIZENS}{citizen_id}"


def citizen_facts_key(citizen_id: uuid.UUID | str) -> str:
    return f"{PREFIX_CITIZEN_FACTS}{citizen_id}"


def eligibility_result_key(citizen_id: uuid.UUID | str, version: int | str = 1) -> str:
    return f"{PREFIX_ELIGIBILITY}{citizen_id}:{version}"


# ----------------------------------------------------------------------
# Cache Invalidation Hooks
# ----------------------------------------------------------------------

async def invalidate_schemes() -> int:
    """Invalidate scheme list and all scheme detail/rules cache keys."""
    return await cache_service.delete_prefix(PREFIX_SCHEMES)


async def invalidate_form(form_code: Optional[str] = None) -> int:
    """Invalidate active form definition or all form keys."""
    if form_code:
        deleted = await cache_service.delete(form_active_key(form_code))
        list_deleted = await cache_service.delete_prefix(KEY_FORMS_LIST_PREFIX)
        return (1 if deleted else 0) + list_deleted
    return await cache_service.delete_prefix(PREFIX_FORMS)


async def invalidate_citizen_facts(citizen_id: uuid.UUID | str) -> int:
    """Invalidate cached profile facts for a citizen."""
    deleted = await cache_service.delete(citizen_facts_key(citizen_id))
    return 1 if deleted else 0


async def invalidate_citizen(citizen_id: uuid.UUID | str) -> int:
    """
    Invalidate all cached data for a citizen:
    - Profile cache (vidyasetu:citizens:{id})
    - Facts cache (vidyasetu:citizen_facts:{id})
    - Eligibility results cache (vidyasetu:eligibility:{id}:*)
    """
    del_profile = await cache_service.delete(citizen_key(citizen_id))
    del_facts = await cache_service.delete(citizen_facts_key(citizen_id))
    del_elig = await cache_service.delete_prefix(f"{PREFIX_ELIGIBILITY}{citizen_id}")
    return (1 if del_profile else 0) + (1 if del_facts else 0) + del_elig

