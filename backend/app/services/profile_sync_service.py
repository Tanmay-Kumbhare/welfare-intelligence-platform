"""
Profile synchronization service.

Closes the loop the form pipeline leaves open: the citizen profile
(tbl_citizen_master + demographic/financial/location singletons) can be
edited directly (ProfilePage → PUT /citizens/{id}), but the profile-fact
layer (tbl_profile_fact) that the eligibility engine actually reads was
only ever written by normalizing a COMPLETED submission. Without this
service a direct profile edit is invisible to the engine until the user
re-submits the whole form.

Two operations, one authority:

    sync_facts_from_profile(citizen_id)
        Re-derive every fact that has a canonical column in the citizen's
        profile tables. Uses the SAME registry (profile_mapping.REGISTRY)
        and the SAME ProfileRepository as submission normalization — no
        new tables, no duplicate mapping logic, no changes to the
        eligibility engine or normalization service.

    compute_prefill(citizen_id, questions)
        For each form question with a profile_field, return the value
        stored in the citizen's profile so the welfare form can prefill
        instead of re-asking. Read-only.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.citizen import CitizenMaster
from app.repositories.profile_repository import ProfileRepository, SINGLETON_DOMAINS
from app.services.profile_mapping import (
    DERIVATION_RULES,
    ProfileField,
    canonical_fact_value,
    resolve_profile_field,
)

# Sources authoritative enough to overwrite an existing VERIFIED fact —
# same policy as normalization. A citizen's own profile edit is treated as
# self-reported (USER_INPUT); it does NOT override an admin/government
# verified fact.
_VERIFIED_SOURCES = ("ADMIN_VERIFIED", "GOVERNMENT_API", "EXTERNAL_VERIFICATION")

# Registry keys mapped onto the citizen-master identity row (no singleton
# profile row). Values are read from CitizenMaster columns.
_IDENTITY_KEYS = {
    "citizen.full_name": lambda c: c.full_name,
    "citizen.mobile_number": lambda c: c.mobile_number,
    "citizen.email_id": lambda c: c.email_id,
}

# profile_field registry keys for the identity answers the form never asks
# (set once at registration; prefill may mirror them for display-only use,
# fact sync never rewrites the identity columns themselves).
_PREFILL_IDENTITY_BARE = {
    "full_name": lambda c: c.full_name,
    "date_of_birth": lambda c: c.date_of_birth.isoformat() if c.date_of_birth else None,
    "gender": lambda c: c.gender,
    "mobile_number": lambda c: c.mobile_number,
    "email_id": lambda c: c.email_id,
}


class ProfileSyncService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.profiles = ProfileRepository(db)

    # ------------------------------------------------------------------
    # Fact re-sync (write path)
    # ------------------------------------------------------------------

    async def sync_facts_from_profile(self, citizen_id: uuid.UUID) -> dict[str, Any]:
        """
        Re-derive profile facts from the citizen's profile tables.

        Only fact_codes whose registry entry has a canonical `column` are
        synced — exactly the values a direct profile edit can change. Facts
        without a column (document possession flags, asset booleans, …) are
        not derivable from the profile tables and are left untouched: they
        remain submission-sourced until a new submission or an admin
        verifies them.

        Returns a small summary dict for the API response.
        """
        citizen = await self._load_citizen_full(citizen_id)
        if citizen is None:
            return {"citizen_id": str(citizen_id), "facts_updated": [], "skipped_verified": []}

        summary: dict[str, Any] = {"facts_updated": [], "skipped_verified": []}
        source = "USER_INPUT"  # self-reported profile edit

        # Batch-load every open fact once.
        syncable = [
            (key, entry)
            for key, entry in _iter_syncable_entries()
        ]
        fact_codes = {entry.fact_code for _, entry in syncable if entry.fact_code}
        open_facts = await self.profiles.get_open_facts(citizen_id, list(fact_codes))

        for key, entry in syncable:
            fact_code = entry.fact_code
            if fact_code is None:
                continue

            value = self._read_value(citizen, key, entry)
            serialized = canonical_fact_value(entry.data_type, value)

            existing = open_facts.get(fact_code)
            if existing is None:
                if serialized is None:
                    continue  # nothing to create from an empty profile field
                await self.profiles.create_fact(
                    citizen_id=citizen_id,
                    fact_code=fact_code,
                    fact_value=serialized,
                    data_type=entry.data_type,
                    source=source,
                    verified=False,
                )
                summary["facts_updated"].append(fact_code)
                await self._add_provenance(citizen_id, fact_code)
                continue

            if existing.verified and source not in _VERIFIED_SOURCES:
                if fact_code not in summary["skipped_verified"]:
                    summary["skipped_verified"].append(fact_code)
                continue

            if existing.fact_value != serialized:
                if serialized is None:
                    # Profile field was cleared; keep the last known value
                    # rather than wiping a fact the engine may rely on.
                    continue
                existing.fact_value = serialized
                existing.data_type = entry.data_type
                existing.source = source
                if fact_code not in summary["facts_updated"]:
                    summary["facts_updated"].append(fact_code)
                await self._add_provenance(citizen_id, fact_code)

        await self._rerun_derivations(citizen_id, summary)
        await self.db.flush()
        summary["facts_updated"] = sorted(set(summary["facts_updated"]))
        summary["skipped_verified"] = sorted(set(summary["skipped_verified"]))
        return summary

    async def _rerun_derivations(self, citizen_id: uuid.UUID, summary: dict[str, Any]) -> None:
        """Re-apply DERIVATION_RULES so chained facts track their sources —
        e.g. DOB changed → AGE and SENIOR_CITIZEN must move with it."""
        # A fact row needs provenance only once; derivations reference the
        # deterministic rule, and re-runs are deduplicated on the reference.
        for rule in DERIVATION_RULES:
            facts: dict[str, str | None] = {}
            ok = True
            for code in rule.source_facts:
                fact = await self.profiles.get_open_fact(citizen_id, code)
                if fact is None or not fact.fact_value:
                    ok = False
                    break
                facts[code] = fact.fact_value
            if not ok:
                continue
            try:
                value = rule.compute(facts)
            except (ValueError, KeyError, TypeError):
                continue
            if value is None:
                continue
            serialized = canonical_fact_value(rule.data_type, value)
            existing = await self.profiles.get_open_fact(citizen_id, rule.derived_fact)
            if existing is None:
                await self.profiles.create_fact(
                    citizen_id=citizen_id,
                    fact_code=rule.derived_fact,
                    fact_value=serialized,
                    data_type=rule.data_type,
                    source="SYSTEM_DERIVED",
                    verified=False,
                )
                summary["facts_updated"].append(rule.derived_fact)
            elif existing.fact_value != serialized and not existing.verified:
                existing.fact_value = serialized
                existing.data_type = rule.data_type
                if rule.derived_fact not in summary["facts_updated"]:
                    summary["facts_updated"].append(rule.derived_fact)
            elif existing.verified:
                if rule.derived_fact not in summary["skipped_verified"]:
                    summary["skipped_verified"].append(rule.derived_fact)

    async def _add_provenance(self, citizen_id: uuid.UUID, fact_code: str) -> None:
        """Attach one provenance row per synced fact, deduplicated on the
        reference so repeated edits never stack duplicates."""
        fact = await self.profiles.get_open_fact(citizen_id, fact_code)
        if fact is None:
            return
        reference = f"PROFILE_EDIT:{fact_code}"
        existing = await self.profiles.get_provenance_by_reference(fact.fact_id, reference)
        if existing is not None:
            return
        await self.profiles.add_provenance(
            fact_id=fact.fact_id,
            source_type="USER_INPUT",
            source_reference=reference,
            source_text=f"{fact_code} updated from a direct citizen profile edit",
            form_answer_id=None,
            verification_status="PENDING",
        )

    async def _load_citizen(self, citizen_id: uuid.UUID) -> CitizenMaster | None:
        """Eager-load the citizen with all three profile singletons — lazy
        loading is illegal inside an AsyncSession (MissingGreenlet), and the
        sync path reads demographic/financial/location attributes directly."""
        return await self._load_citizen_full(citizen_id)

    # ------------------------------------------------------------------
    # Prefill (read path)
    # ------------------------------------------------------------------

    async def compute_prefill(
        self, citizen_id: uuid.UUID, questions: Sequence[Any]
    ) -> dict[str, Any]:
        """
        Map question_code -> value for every question whose profile_field
        resolves to a canonical profile location the citizen's tables hold.

        Values come from the profile singletons and citizen master only —
        the same authority the fact sync writes from. Read-only.
        """
        citizen = await self._load_citizen_full(citizen_id)
        if citizen is None:
            return {"values": {}, "unavailable": []}

        values: dict[str, Any] = {}
        unavailable: list[str] = []

        for question in questions:
            profile_field = getattr(question, "profile_field", None)
            if not profile_field:
                continue
            entry = resolve_profile_field(profile_field)
            if entry is None:
                continue

            # Identity fields live on the citizen master row.
            identity_value = self._identity_value(citizen, profile_field)
            if identity_value is not None:
                values[question.question_code] = identity_value
                continue

            if entry.column is None or entry.domain not in SINGLETON_DOMAINS:
                # No canonical column (fact-only or multi-row domain):
                # nothing in the profile tables to prefill from.
                unavailable.append(question.question_code)
                continue

            row = getattr(citizen, f"{entry.domain}_profile", None)
            if row is None:
                unavailable.append(question.question_code)
                continue

            raw = getattr(row, entry.column)
            if raw is None:
                unavailable.append(question.question_code)
                continue
            values[question.question_code] = self._serialize(raw)

        return {"values": values, "unavailable": unavailable}

    def _identity_value(self, citizen: CitizenMaster, profile_field: str) -> Any:
        # Bare names for identity (the form never asks these; prefill only
        # mirrors them when a legacy question still exists).
        for bare, getter in _PREFILL_IDENTITY_BARE.items():
            if profile_field == bare or profile_field in (
                f"citizen.{bare}",
                f"demographic.{bare}" if bare != "date_of_birth" else "demographic.date_of_birth",
            ):
                value = getter(citizen)
                if value is not None:
                    return self._serialize(value)
        return None

    async def _load_citizen_full(self, citizen_id: uuid.UUID) -> CitizenMaster | None:
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        result = await self.db.execute(
            select(CitizenMaster)
            .options(
                selectinload(CitizenMaster.demographic_profile),
                selectinload(CitizenMaster.financial_profile),
                selectinload(CitizenMaster.location_profile),
            )
            .where(CitizenMaster.citizen_id == citizen_id)
        )
        return result.scalar_one_or_none()

    def _serialize(self, raw: Any) -> Any:
        if isinstance(raw, (date, datetime)):
            return raw.isoformat()
        if hasattr(raw, "quantize"):  # Decimal
            return float(raw)
        return raw

    def _read_value(self, citizen: CitizenMaster, key: str, entry: ProfileField) -> Any:
        if key in _IDENTITY_KEYS:
            return _IDENTITY_KEYS[key](citizen)
        if entry.column is None or entry.domain not in SINGLETON_DOMAINS:
            return None
        row = getattr(citizen, f"{entry.domain}_profile", None)
        if row is None:
            return None
        return getattr(row, entry.column, None)


def _iter_syncable_entries():
    """All registry entries with both a fact_code and a canonical column."""
    from app.services.profile_mapping import REGISTRY

    syncable_domains = set(SINGLETON_DOMAINS) | {"citizen"}
    for key, entry in REGISTRY.items():
        if entry.fact_code and entry.column and entry.domain in syncable_domains:
            yield key, entry
