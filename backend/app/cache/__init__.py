"""
Cache package - exports the unified Redis cache service and key helpers.
Replaces the previous in-process in-memory dict cache with Redis.
"""

from app.services.cache_service import (
    RedisCacheService,
    cache_service,
    cache_service as cache,
    citizen_facts_key,
    citizen_key,
    eligibility_result_key,
    form_active_key,
    forms_list_key,
    invalidate_citizen,
    invalidate_citizen_facts,
    invalidate_form,
    invalidate_schemes,
    scheme_detail_key,
    scheme_rules_key,
    schemes_all_key,
)

# Backward-compatibility alias
TTLCache = RedisCacheService

__all__ = [
    "RedisCacheService",
    "cache_service",
    "cache",
    "citizen_facts_key",
    "citizen_key",
    "eligibility_result_key",
    "form_active_key",
    "forms_list_key",
    "invalidate_citizen",
    "invalidate_citizen_facts",
    "invalidate_form",
    "invalidate_schemes",
    "scheme_detail_key",
    "scheme_rules_key",
    "schemes_all_key",
]
