"""
Reference-data TTL cache tests.

Covers: hit, miss, expiry, invalidation (single key + prefix), graceful
fallback when the cache backend raises, and payload identity between the
cached and uncached read paths (API contract preservation).

The cache is process-local and bounded; tests restore global state via
fixtures so the seeded demo data and other test modules are unaffected.
"""

from __future__ import annotations

import time
import uuid

import pytest

from app.cache import (
    TTLCache,
    cache,
    form_active_key,
    forms_list_key,
    invalidate_form,
    invalidate_schemes,
    scheme_detail_key,
    schemes_all_key,
)
from app.schemas.scheme import SchemeDetailResponse, SchemeResponse


# ----------------------------------------------------------------------
# Unit tests: the TTLCache primitive
# ----------------------------------------------------------------------


class TestTTLCachePrimitive:
    def test_miss_then_hit(self):
        c = TTLCache()
        assert c.get("k") is None          # miss
        c.set("k", {"a": 1}, ttl_seconds=60)
        assert c.get("k") == {"a": 1}      # hit

    def test_expiry(self):
        c = TTLCache()
        c.set("k", "v", ttl_seconds=0)     # non-positive TTL is never stored
        assert c.get("k") is None

        c.set("k", "v", ttl_seconds=1)
        # Force expiry without sleeping a full second of wall time.
        c._store["k"].expires_at = time.monotonic() - 0.01
        assert c.get("k") is None          # expired -> miss
        assert "k" not in c._store         # stale entry dropped

    def test_invalidate_single_key(self):
        c = TTLCache()
        c.set("a", 1, ttl_seconds=60)
        c.set("b", 2, ttl_seconds=60)
        c.invalidate("a")
        assert c.get("a") is None
        assert c.get("b") == 2

    def test_invalidate_prefix(self):
        c = TTLCache()
        c.set("schemes:all", 1, ttl_seconds=60)
        c.set("schemes:detail:x", 2, ttl_seconds=60)
        c.set("forms:active:CODE", 3, ttl_seconds=60)
        removed = c.invalidate_prefix("schemes:")
        assert removed == 2
        assert c.get("schemes:all") is None
        assert c.get("schemes:detail:x") is None
        assert c.get("forms:active:CODE") == 3

    def test_clear_and_stats(self):
        c = TTLCache()
        c.set("a", 1, ttl_seconds=60)
        c.get("a")
        c.get("missing")
        stats = c.stats()
        assert stats["hits"] == 1 and stats["misses"] == 1
        assert stats["entries"] == 1
        assert c.clear() == 1
        assert c.stats()["entries"] == 0

    def test_max_entries_bound(self):
        c = TTLCache()
        for i in range(1_100):
            c.set(f"k{i}", i, ttl_seconds=60)
        assert len(c._store) <= 1_000      # stays bounded
        assert c.get("k0") is None         # oldest evicted

    def test_disabled_cache_never_stores(self, monkeypatch):
        c = TTLCache()
        monkeypatch.setattr(type(c), "enabled", property(lambda self: False))
        c.set("k", "v", ttl_seconds=60)
        assert c.get("k") is None

    def test_graceful_fallback_on_internal_error(self, monkeypatch):
        """A broken backend must degrade to misses, never raise."""
        c = TTLCache()
        c.set("k", "v", ttl_seconds=60)

        class BrokenStore(dict):
            def get(self, key, default=None):
                raise RuntimeError("cache backend down")

        c._store = BrokenStore()
        assert c.get("k") is None          # error -> miss, not exception
        assert c.stats()["errors"] >= 1
        # set() must also degrade: force the eviction path to fail by breaking
        # the builtin min() the eviction uses.
        def broken_min(*args, **kwargs):
            raise RuntimeError("eviction failed")

        monkeypatch.setattr("builtins.min", broken_min)
        for i in range(1_100):  # exceed _MAX_ENTRIES to trigger eviction
            c.set(f"k{i}", i, ttl_seconds=60)
        assert c.stats()["errors"] >= 2     # swallowed, never raised

    def test_invalidate_on_broken_store_is_safe(self):
        c = TTLCache()

        class BrokenStore(dict):
            def pop(self, *a, **k):
                raise RuntimeError("boom")

            def keys(self):
                return []

        c._store = BrokenStore()
        c.invalidate("anything")                       # must not raise
        assert c.invalidate_prefix("p") == 0           # must not raise
        assert c.clear() == 0                          # must not raise


# ----------------------------------------------------------------------
# Key builders + shared invalidation helpers
# ----------------------------------------------------------------------


class TestKeysAndInvalidationHelpers:
    def test_key_builders(self):
        sid = uuid.uuid4()
        assert schemes_all_key() == "schemes:all"
        assert scheme_detail_key(sid) == f"schemes:detail:{sid}"
        assert form_active_key("GENERAL") == "forms:active:GENERAL"
        assert forms_list_key() == "forms:list"

    def test_invalidate_schemes_prefix(self):
        cache.set(schemes_all_key(), [{"x": 1}], ttl_seconds=60)
        cache.set(scheme_detail_key("abc"), {"x": 1}, ttl_seconds=60)
        cache.set(form_active_key("F"), {"x": 1}, ttl_seconds=60)
        assert invalidate_schemes() == 2
        assert cache.get(schemes_all_key()) is None
        assert cache.get(form_active_key("F")) == {"x": 1}   # untouched
        cache.invalidate(form_active_key("F"))

    def test_invalidate_form(self):
        cache.set(form_active_key("F"), {"x": 1}, ttl_seconds=60)
        cache.set(forms_list_key() + ":all", [{"x": 1}], ttl_seconds=60)
        cache.set(schemes_all_key(), [{"x": 1}], ttl_seconds=60)
        assert invalidate_form("F") == 2
        assert cache.get(schemes_all_key()) == [{"x": 1}]    # untouched
        cache.invalidate(schemes_all_key())


# ----------------------------------------------------------------------
# Integration: services really use the cache (FastAPI TestClient against
# the real app; the DB is hit only on the miss path).
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


class TestServiceCacheIntegration:
    def test_scheme_list_hit_after_first_call(self, client):
        r1 = client.get("/api/v1/schemes/")
        assert r1.status_code == 200
        assert cache.stats()["misses"] >= 1

        r2 = client.get("/api/v1/schemes/")
        assert r2.status_code == 200
        assert r2.json() == r1.json()
        stats = cache.stats()
        assert stats["hits"] >= 1
        assert schemes_all_key() in stats["keys"]

    def test_scheme_detail_hit_and_identity(self, client):
        list_payload = client.get("/api/v1/schemes/").json()
        assert list_payload, "seeded schemes must exist for this test"
        scheme_id = list_payload[0]["scheme_id"]

        r1 = client.get(f"/api/v1/schemes/{scheme_id}")
        assert r1.status_code == 200
        detail_cached = r1.json()

        # Second read must come from cache and be identical.
        r2 = client.get(f"/api/v1/schemes/{scheme_id}")
        assert r2.json() == detail_cached
        assert scheme_detail_key(scheme_id) in cache.stats()["keys"]

        # Cached detail must deep-equal a freshly built DTO from the ORM.
        # Fresh NullPool engine inside its own event loop — the TestClient's
        # asyncpg connections belong to a different loop.
        import asyncio

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
        from sqlalchemy.pool import NullPool

        from app.config import get_settings
        from app.repositories.scheme_repository import SchemeRepository

        async def _fresh():
            engine = create_async_engine(
                get_settings().DATABASE_URL, poolclass=NullPool
            )
            try:
                session_factory = async_sessionmaker(engine, expire_on_commit=False)
                async with session_factory() as session:
                    scheme = await SchemeRepository(session).get_by_id(scheme_id)
                    # mode="json" matches what the API response carries
                    # (UUIDs stringified by the JSON encoder).
                    return SchemeDetailResponse.model_validate(scheme).model_dump(mode="json")
            finally:
                await engine.dispose()

        assert detail_cached == asyncio.run(_fresh())

    def test_form_active_hit(self, client):
        r1 = client.get("/api/v1/forms/GENERAL_CITIZEN_PROFILE")
        assert r1.status_code == 200
        payload = r1.json()

        r2 = client.get("/api/v1/forms/GENERAL_CITIZEN_PROFILE")
        assert r2.json() == payload
        assert form_active_key("GENERAL_CITIZEN_PROFILE") in cache.stats()["keys"]

    def test_invalidation_helper_clears_scheme_cache(self, client):
        # Populate
        first = client.get("/api/v1/schemes/").json()
        assert schemes_all_key() in cache.stats()["keys"]
        # Invalidate the way the admin mutation does
        invalidate_schemes()
        assert cache.get(schemes_all_key()) is None
        # Next read repopulates with identical content
        second = client.get("/api/v1/schemes/").json()
        assert second == first

    def test_disabled_cache_falls_through_to_db(self, client, monkeypatch):
        monkeypatch.setattr(type(cache), "enabled", property(lambda self: False))
        r = client.get("/api/v1/schemes/")
        assert r.status_code == 200
        assert cache.stats()["entries"] == 0            # nothing stored
        assert r.json(), "DB fallback must still serve data"
