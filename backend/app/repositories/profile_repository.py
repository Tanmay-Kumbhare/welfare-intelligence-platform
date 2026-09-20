"""
Profile repository — async SQLAlchemy data access for canonical domain
profiles, profile facts, and fact provenance (Phase 2B).

Idempotency strategy (Part 3):
  - Singleton domain profiles (demographic/financial/location/education/
    employment/agriculture/disability) are get-or-create on the unique
    citizen_id column — re-normalization updates the same row.
  - Open facts are get-or-create on the partial unique index
    (citizen_id, fact_code) WHERE effective_until IS NULL — re-running
    never duplicates facts.
  - Provenance is deduplicated on (fact_id, form_answer_id) — the same
    answer never produces a second provenance row for the same fact.
  - Family members dedupe on the natural key (relationship, name,
    date_of_birth); no destructive deletes.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Sequence, Type

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.citizen import (
    CitizenMaster,
    DemographicProfile,
    FinancialProfile,
    LocationProfile,
)
from app.models.domain_profile import (
    AgricultureProfile,
    DisabilityProfile,
    EducationProfile,
    EmploymentProfile,
    FamilyMember,
)
from app.models.profile_fact import ProfileFact, ProfileFactProvenance

_SINGLETON_DOMAINS: dict[str, type] = {
    "demographic": DemographicProfile,
    "financial": FinancialProfile,
    "location": LocationProfile,
    "education": EducationProfile,
    "employment": EmploymentProfile,
    "agriculture": AgricultureProfile,
    "disability": DisabilityProfile,
}

# Public alias: normalization consults this before writing scalar columns
# so multi-row domains (assets) degrade to a warning instead of a KeyError.
SINGLETON_DOMAINS = _SINGLETON_DOMAINS


class ProfileRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        # Per-run cache of singleton domain rows keyed (domain, citizen_id).
        # A single normalization touches the same domain rows repeatedly
        # (answers + derived facts); one SELECT per (domain, citizen) instead
        # of one per attribute matters on remote databases. Rows added to the
        # session are cached pre-flush, so repeated get-or-create within a run
        # is a plain dict hit.
        self._singleton_cache: dict[tuple[str, uuid.UUID], object] = {}

    # ------------------------------------------------------------------
    # Canonical domain profiles
    # ------------------------------------------------------------------

    async def get_or_create_singleton(self, domain: str, citizen_id: uuid.UUID):
        """Get-or-create the citizen's single row for a singleton domain."""
        cache_key = (domain, citizen_id)
        if cache_key in self._singleton_cache:
            return self._singleton_cache[cache_key]
        model = _SINGLETON_DOMAINS[domain]
        result = await self.db.execute(
            select(model).where(model.citizen_id == citizen_id).limit(1)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = model(citizen_id=citizen_id)
            self.db.add(row)
            await self.db.flush()
        self._singleton_cache[cache_key] = row
        return row

    async def get_identity_profile(self, citizen_id: uuid.UUID) -> CitizenMaster | None:
        """Fetch just the citizen-master identity row (name/DOB/gender).
        Used to seed identity facts from the authoritative registration
        record; a dedicated narrow SELECT avoids dragging the sub-profiles."""
        return await self.get_citizen(citizen_id)

    async def get_citizen(self, citizen_id: uuid.UUID) -> CitizenMaster | None:
        result = await self.db.execute(
            select(CitizenMaster).where(CitizenMaster.citizen_id == citizen_id)
        )
        return result.scalar_one_or_none()

    # ------------------------------------------------------------------
    # Profile facts
    # ------------------------------------------------------------------

    async def get_open_facts(
        self, citizen_id: uuid.UUID, fact_codes: Sequence[str]
    ) -> dict[str, ProfileFact]:
        """Batched open-fact lookup: one SELECT IN instead of one query per
        code. Derivation rules and the engine resolve several codes per run."""
        if not fact_codes:
            return {}
        result = await self.db.execute(
            select(ProfileFact).where(
                ProfileFact.citizen_id == citizen_id,
                ProfileFact.fact_code.in_(fact_codes),
                ProfileFact.effective_until.is_(None),
            )
        )
        return {fact.fact_code: fact for fact in result.scalars().all()}

    async def get_open_fact(
        self, citizen_id: uuid.UUID, fact_code: str
    ) -> ProfileFact | None:
        """Current (open) fact for (citizen, code), if any."""
        result = await self.db.execute(
            select(ProfileFact)
            .where(
                ProfileFact.citizen_id == citizen_id,
                ProfileFact.fact_code == fact_code,
                ProfileFact.effective_until.is_(None),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def create_fact(
        self,
        citizen_id: uuid.UUID,
        fact_code: str,
        fact_value: str | None,
        data_type: str,
        source: str,
        verified: bool = False,
    ) -> ProfileFact:
        fact = ProfileFact(
            citizen_id=citizen_id,
            fact_code=fact_code,
            fact_value=fact_value,
            data_type=data_type,
            source=source,
            verified=verified,
        )
        self.db.add(fact)
        await self.db.flush()
        return fact

    async def retire_fact(self, fact: ProfileFact, until: date | None = None) -> None:
        """Close a fact's current row when its value is superseded by a
        verified source; history is preserved, never deleted."""
        fact.effective_until = until or date.today()
        await self.db.flush()

    async def get_provenance_by_answer(
        self, fact_id: uuid.UUID, form_answer_id: uuid.UUID
    ) -> ProfileFactProvenance | None:
        result = await self.db.execute(
            select(ProfileFactProvenance)
            .where(
                ProfileFactProvenance.fact_id == fact_id,
                ProfileFactProvenance.form_answer_id == form_answer_id,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_provenance_by_reference(
        self, fact_id: uuid.UUID, source_reference: str
    ) -> ProfileFactProvenance | None:
        """Dedup for derived provenance (which has no form answer)."""
        result = await self.db.execute(
            select(ProfileFactProvenance)
            .where(
                ProfileFactProvenance.fact_id == fact_id,
                ProfileFactProvenance.source_reference == source_reference,
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def add_provenance(
        self,
        fact_id: uuid.UUID,
        source_type: str,
        source_reference: str | None,
        source_text: str | None,
        form_answer_id: uuid.UUID | None,
        verification_status: str = "PENDING",
    ) -> ProfileFactProvenance:
        provenance = ProfileFactProvenance(
            fact_id=fact_id,
            source_type=source_type,
            source_reference=source_reference,
            source_text=source_text,
            form_answer_id=form_answer_id,
            verification_status=verification_status,
        )
        self.db.add(provenance)
        await self.db.flush()
        return provenance

    # ------------------------------------------------------------------
    # Family members (multi-row domain)
    # ------------------------------------------------------------------

    async def list_family_members(
        self, citizen_id: uuid.UUID
    ) -> Sequence[FamilyMember]:
        result = await self.db.execute(
            select(FamilyMember).where(FamilyMember.citizen_id == citizen_id)
        )
        return result.scalars().all()

    async def upsert_family_member(
        self,
        citizen_id: uuid.UUID,
        relationship: str,
        name: str | None,
        date_of_birth: date | None,
        **fields,
    ) -> tuple[FamilyMember, bool, bool]:
        """
        Upsert on the natural key (citizen, relationship, name, dob).
        Returns (member, created, changed) where changed is True only when
        an existing row actually got a new field value — re-normalization
        of identical data is a no-op. Never deletes rows from other sources.
        """
        result = await self.db.execute(
            select(FamilyMember)
            .where(
                FamilyMember.citizen_id == citizen_id,
                FamilyMember.relationship == relationship,
                FamilyMember.name == name,
                FamilyMember.date_of_birth == date_of_birth,
            )
            .limit(1)
        )
        member = result.scalar_one_or_none()
        created = member is None
        changed = False
        if member is None:
            member = FamilyMember(
                citizen_id=citizen_id,
                relationship=relationship,
                name=name,
                date_of_birth=date_of_birth,
            )
            self.db.add(member)
        for key, value in fields.items():
            if value is not None and getattr(member, key) != value:
                setattr(member, key, value)
                changed = True
        await self.db.flush()
        return member, created, changed
