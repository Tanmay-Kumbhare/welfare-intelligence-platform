"""
Application-level TTL cache for frequently-read, slowly-changing reference
data (scheme catalogue, scheme details, form definitions).

Design constraints (deliberately minimal, production-oriented):

  - In-process: one dict per worker process. The app is currently deployed
    as a single uvicorn process; when it scales to multiple workers, swap
    this module's internals for Redis WITHOUT touching the services —
    they only use get/set/invalidate below.
  - Stores JSON-able values only (serialized Pydantic DTOs). ORM objects
    must never be put in the cache: they are session-bound and lazy-load
    illegally inside async sessions.
  - Graceful degradation: every operation swallows internal errors. If the
    cache is broken, callers transparently fall through to PostgreSQL —
    a cache outage must never take the API down.
  - TTL-based expiry with a monotonic clock, plus explicit invalidation
    hooks fired by the admin mutations that change scheme/form data.

Nothing user-specific or fast-changing is ever stored here: no sessions,
no profiles, no submissions, no assessments, no admin monitoring data.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

from app.config import get_settings

# Bounded entry count: reference data is small (tens of entries), but the
# cap guards against accidental unbounded growth if a future caller starts
# caching per-entity keys (e.g. per-citizen) that it should not.
_MAX_ENTRIES = 1_000


@dataclass
class _Entry:
    value: Any
    expires_at: float


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    errors: int = 0
    keys: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "errors": self.errors,
            "entries": len(self.keys),
            "keys": self.keys,
        }


class TTLCache:
    """Process-local TTL cache. See module docstring for the contract."""

    def __init__(self) -> None:
        self._store: dict[str, _Entry] = {}
        self._hits = 0
        self._misses = 0
        self._errors = 0

    @property
    def enabled(self) -> bool:
        try:
            return bool(get_settings().CACHE_ENABLED)
        except Exception:
            return True

    def get(self, key: str) -> Optional[Any]:
        """Cached value or None (miss/expiry/disabled/error). Never raises."""
        if not self.enabled:
            return None
        try:
            entry = self._store.get(key)
            if entry is None:
                self._misses += 1
                return None
            if time.monotonic() >= entry.expires_at:
                # Expired: treat as a miss and drop the stale entry.
                self._store.pop(key, None)
                self._misses += 1
                return None
            self._hits += 1
            return entry.value
        except Exception:
            # Any internal failure degrades to a cache miss, never an API error.
            self._errors += 1
            return None

    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Store a value with a TTL. Never raises."""
        if not self.enabled:
            return
        try:
            if ttl_seconds is None:
                ttl_seconds = int(get_settings().CACHE_TTL_SECONDS)
            if ttl_seconds <= 0:
                return
            if len(self._store) >= _MAX_ENTRIES and key not in self._store:
                # Drop the soonest-expiring entry to stay bounded.
                oldest_key = min(self._store, key=lambda k: self._store[k].expires_at)
                self._store.pop(oldest_key, None)
            self._store[key] = _Entry(
                value=value, expires_at=time.monotonic() + float(ttl_seconds)
            )
        except Exception:
            self._errors += 1

    def invalidate(self, key: str) -> int:
        """Remove one key if present. Returns 1 if it existed, else 0."""
        try:
            return 1 if self._store.pop(key, None) is not None else 0
        except Exception:
            self._errors += 1
            return 0

    def invalidate_prefix(self, prefix: str) -> int:
        """Remove every key starting with `prefix`. Returns count removed."""
        try:
            victims = [k for k in self._store if k.startswith(prefix)]
            for k in victims:
                self._store.pop(k, None)
            return len(victims)
        except Exception:
            self._errors += 1
            return 0

    def clear(self) -> int:
        """Drop everything. Returns the number of entries removed."""
        try:
            count = len(self._store)
            self._store.clear()
            return count
        except Exception:
            self._errors += 1
            return 0

    def stats(self) -> dict[str, Any]:
        try:
            return CacheStats(
                hits=self._hits,
                misses=self._misses,
                errors=self._errors,
                keys=sorted(self._store.keys()),
            ).as_dict()
        except Exception:
            return {"hits": 0, "misses": 0, "errors": 1, "entries": 0, "keys": []}


# Single process-wide instance. Import this — never instantiate per-request,
# or every request would get an empty cache.
cache = TTLCache()


# ----------------------------------------------------------------------
# Canonical key builders (services and invalidation hooks share these so a
# renamed key cannot silently break invalidation).
# ----------------------------------------------------------------------

def schemes_all_key() -> str:
    return "schemes:all"


def scheme_detail_key(scheme_id: uuid.UUID | str) -> str:
    return f"schemes:detail:{scheme_id}"


def form_active_key(form_code: str) -> str:
    return f"forms:active:{form_code}"


def forms_list_key() -> str:
    return "forms:list"


def citizen_key(citizen_id: uuid.UUID | str) -> str:
    return f"citizens:{citizen_id}"


def invalidate_schemes() -> int:
    """Called after any admin mutation of scheme metadata/rules."""
    return cache.invalidate_prefix("schemes:")


def invalidate_form(form_code: str | None = None) -> int:
    """Called after any mutation of form definitions. The forms-list key is
    parametrized by target_citizen_type, so the whole "forms:list" prefix is
    cleared rather than a single key."""
    if form_code:
        count = cache.invalidate(form_active_key(form_code))
        return count + cache.invalidate_prefix(forms_list_key())
    return cache.invalidate_prefix("forms:")


def invalidate_citizen(citizen_id: uuid.UUID | str) -> int:
    """Called whenever a citizen's profile/facts change (profile edit,
    submission normalization) so the short-TTL profile read never serves
    stale data past its write."""
    return cache.invalidate(citizen_key(citizen_id))
