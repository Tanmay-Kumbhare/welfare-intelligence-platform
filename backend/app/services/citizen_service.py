"""
Citizen service — orchestrates citizen domain operations and education records.
"""

from __future__ import annotations

import uuid
from typing import Optional, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cache, citizen_key, invalidate_citizen
from app.models.citizen import CitizenMaster
from app.models.education_record import EducationRecord
from app.repositories.citizen_repository import CitizenRepository
from app.repositories.education_repository import EducationRepository
from app.schemas.citizen import (
    CitizenCreate,
    CitizenUpdate,
    CitizenResponse,
    DemographicProfileResponse,
    FinancialProfileResponse,
    LocationProfileResponse,
)
from app.schemas.education import (
    EducationRecordCreate,
    EducationRecordResponse,
    EducationRecordUpdate,
)


def compute_profile_completeness(citizen: CitizenMaster) -> tuple[str, int, list[str]]:
    """
    Authoritatively calculate profile completeness for welfare/scholarship eligibility.
    Returns: (profile_status, profile_completion, missing_fields)
    """
    missing: list[str] = []
    score = 0

    # 1. Identity: Full Name & DOB (20 pts)
    if citizen.full_name and citizen.date_of_birth:
        score += 20
    else:
        missing.append("Date of Birth")

    # 2. Gender (10 pts)
    if citizen.gender:
        score += 10
    else:
        missing.append("Gender")

    # 3. Profile / Citizen Type (10 pts)
    if citizen.citizen_type or (citizen.profile_types and len(citizen.profile_types) > 0):
        score += 10
    else:
        missing.append("Profile Type")

    # 4. Social Category (15 pts)
    demo = citizen.demographic_profile
    if demo and demo.social_category:
        score += 15
    else:
        missing.append("Social Category")

    # 5. Education Level / Records (15 pts)
    has_edu_level = bool(demo and demo.education_level)
    has_edu_records = bool(citizen.education_records and len(citizen.education_records) > 0)
    if has_edu_level or has_edu_records:
        score += 15
    else:
        missing.append("Education Details")

    # 6. Annual Income (15 pts)
    fin = citizen.financial_profile
    if fin and fin.annual_income is not None:
        score += 15
    else:
        missing.append("Annual Income")

    # 7. State / Location (15 pts)
    loc = citizen.location_profile
    if loc and loc.state:
        score += 15
    else:
        missing.append("State / Location")

    # Status is COMPLETE only when all core eligibility dimensions are provided
    core_missing = [f for f in missing if f in ("Date of Birth", "Gender", "Social Category", "Education Details", "Annual Income", "State / Location")]
    status = "COMPLETE" if len(core_missing) == 0 else "INCOMPLETE"

    return status, score, missing


def _to_response(citizen: CitizenMaster) -> CitizenResponse:
    """Map ORM relationship names to the public citizen response fields."""
    status, completion, missing = compute_profile_completeness(citizen)
    return CitizenResponse(
        citizen_id=citizen.citizen_id,
        full_name=citizen.full_name,
        date_of_birth=citizen.date_of_birth,
        gender=citizen.gender,
        mobile_number=citizen.mobile_number,
        email_id=citizen.email_id,
        citizen_type=citizen.citizen_type,
        profile_types=citizen.profile_types or [],
        registration_date=citizen.registration_date,
        created_at=citizen.created_at,
        updated_at=citizen.updated_at,
        profile_version=getattr(citizen, "profile_version", 1) or 1,
        verification_status=citizen.verification_status,
        demographic=(
            DemographicProfileResponse.model_validate(citizen.demographic_profile)
            if citizen.demographic_profile else None
        ),
        financial=(
            FinancialProfileResponse.model_validate(citizen.financial_profile)
            if citizen.financial_profile else None
        ),
        location=(
            LocationProfileResponse.model_validate(citizen.location_profile)
            if citizen.location_profile else None
        ),
        education_records=[
            EducationRecordResponse.model_validate(rec)
            for rec in (citizen.education_records or [])
        ],
        profile_status=status,
        profile_completion=completion,
        missing_fields=missing,
    )


class CitizenService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = CitizenRepository(db)
        self.education_repo = EducationRepository(db)

    async def register_citizen(
        self, data: CitizenCreate, user_id: Optional[uuid.UUID] = None
    ) -> CitizenResponse:
        if user_id:
            existing = await self.repo.get_by_owning_user(user_id)
            if existing:
                updated = await self.repo.update_for_user(user_id, data.model_dump())
                return _to_response(updated or existing)
            created = await self.repo.create_for_user(user_id, data.model_dump())
        else:
            created = await self.repo.create(data)
        loaded = await self.repo.get_by_id(created.citizen_id)
        return _to_response(loaded or created)

    async def get_citizen(self, citizen_id: uuid.UUID) -> Optional[CitizenResponse]:
        cache_key = citizen_key(citizen_id)
        cached = await cache.get(cache_key)
        if cached is not None:
            return CitizenResponse.model_validate(cached)

        citizen = await self.repo.get_by_id(citizen_id)
        if not citizen:
            return None
        response = _to_response(citizen)
        await cache.set(cache_key, response.model_dump(mode="json"), ttl=60)
        return response

    async def update_citizen(
        self, citizen_id: uuid.UUID, data: CitizenUpdate
    ) -> Optional[CitizenResponse]:
        citizen = await self.repo.update(citizen_id, data)
        if not citizen:
            return None
        await self._sync_and_invalidate(citizen_id)
        fresh = await self.repo.get_by_id(citizen_id)
        return _to_response(fresh or citizen)

    # ------------------------------------------------------------------
    # Education Records Operations
    # ------------------------------------------------------------------

    async def list_education_records(
        self, citizen_id: uuid.UUID
    ) -> Sequence[EducationRecordResponse]:
        records = await self.education_repo.list_for_citizen(citizen_id)
        return [EducationRecordResponse.model_validate(r) for r in records]

    async def get_education_record(
        self, record_id: uuid.UUID, citizen_id: uuid.UUID
    ) -> Optional[EducationRecordResponse]:
        record = await self.education_repo.get_by_id(record_id, citizen_id)
        if not record:
            return None
        return EducationRecordResponse.model_validate(record)

    async def add_education_record(
        self, citizen_id: uuid.UUID, data: EducationRecordCreate
    ) -> EducationRecordResponse:
        record = await self.education_repo.create(citizen_id, data)
        await self._sync_and_invalidate(citizen_id)
        return EducationRecordResponse.model_validate(record)

    async def update_education_record(
        self,
        record_id: uuid.UUID,
        citizen_id: uuid.UUID,
        data: EducationRecordUpdate,
    ) -> Optional[EducationRecordResponse]:
        record = await self.education_repo.update(record_id, citizen_id, data)
        if not record:
            return None
        await self._sync_and_invalidate(citizen_id)
        return EducationRecordResponse.model_validate(record)

    async def delete_education_record(
        self, record_id: uuid.UUID, citizen_id: uuid.UUID
    ) -> bool:
        success = await self.education_repo.delete(record_id, citizen_id)
        if success:
            await self._sync_and_invalidate(citizen_id)
        return success

    async def _sync_and_invalidate(self, citizen_id: uuid.UUID) -> dict[str, Any]:
        """Trigger fact synchronization and Redis cache invalidation atomically."""
        from app.services.profile_sync_service import ProfileSyncService
        sync_service = ProfileSyncService(self.db)
        summary = await sync_service.sync_facts_from_profile(citizen_id)
        await invalidate_citizen(citizen_id)
        return summary
