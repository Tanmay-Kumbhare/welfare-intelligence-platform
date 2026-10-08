"""
Citizen repository — async SQLAlchemy queries for citizen domain tables.
No business logic here; only data access.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.models.citizen import CitizenMaster, DemographicProfile, FinancialProfile, LocationProfile
from app.schemas.citizen import CitizenCreate, CitizenUpdate


class CitizenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: CitizenCreate) -> CitizenMaster:
        """Create a citizen master record with all sub-profiles."""
        citizen = CitizenMaster(
            full_name=data.full_name,
            date_of_birth=data.date_of_birth,
            gender=data.gender,
            mobile_number=data.mobile_number,
            email_id=data.email_id,
            citizen_type=data.citizen_type,
            profile_types=data.profile_types,
        )
        self.db.add(citizen)
        await self.db.flush()  # Get citizen_id without committing

        demographic = DemographicProfile(
            citizen_id=citizen.citizen_id,
            **data.demographic.model_dump(),
        )
        financial = FinancialProfile(
            citizen_id=citizen.citizen_id,
            **data.financial.model_dump(),
        )
        location = LocationProfile(
            citizen_id=citizen.citizen_id,
            **data.location.model_dump(),
        )
        self.db.add_all([demographic, financial, location])
        await self.db.flush()
        await self.db.refresh(citizen)
        return citizen

    async def create_for_user(
        self, user_id: uuid.UUID, data: dict
    ) -> CitizenMaster:
        """Create an owned citizen profile for an authenticated user."""
        from app.schemas.citizen import CitizenCreate

        payload = CitizenCreate.model_validate(data)
        citizen = CitizenMaster(
            full_name=payload.full_name,
            date_of_birth=payload.date_of_birth,
            gender=payload.gender,
            mobile_number=payload.mobile_number,
            email_id=payload.email_id,
            citizen_type=payload.citizen_type,
            profile_types=payload.profile_types,
            owning_user_id=user_id,
        )
        self.db.add(citizen)
        await self.db.flush()

        demographic = DemographicProfile(
            citizen_id=citizen.citizen_id,
            **payload.demographic.model_dump(),
        )
        financial = FinancialProfile(
            citizen_id=citizen.citizen_id,
            **payload.financial.model_dump(),
        )
        location = LocationProfile(
            citizen_id=citizen.citizen_id,
            **payload.location.model_dump(),
        )
        self.db.add_all([demographic, financial, location])
        await self.db.flush()
        await self.db.refresh(citizen)
        return citizen

    async def get_by_owning_user(self, user_id: uuid.UUID) -> CitizenMaster | None:
        """Fetch the citizen profile owned by an authenticated user in a single joined query."""
        result = await self.db.execute(
            select(CitizenMaster)
            .where(CitizenMaster.owning_user_id == user_id)
            .options(
                joinedload(CitizenMaster.demographic_profile),
                joinedload(CitizenMaster.financial_profile),
                joinedload(CitizenMaster.location_profile),
                selectinload(CitizenMaster.education_records),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, citizen_id: uuid.UUID) -> Optional[CitizenMaster]:
        """Fetch a citizen with all sub-profiles eagerly loaded via single joined query."""
        result = await self.db.execute(
            select(CitizenMaster)
            .where(CitizenMaster.citizen_id == citizen_id)
            .options(
                joinedload(CitizenMaster.demographic_profile),
                joinedload(CitizenMaster.financial_profile),
                joinedload(CitizenMaster.location_profile),
                selectinload(CitizenMaster.education_records),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def exists(self, citizen_id: uuid.UUID) -> bool:
        """Lean existence check — identity columns only, no relationship
        loading. Used by flows that only need to verify the citizen row."""
        result = await self.db.execute(
            select(CitizenMaster.citizen_id).where(
                CitizenMaster.citizen_id == citizen_id
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def update(self, citizen_id: uuid.UUID, data: CitizenUpdate) -> Optional[CitizenMaster]:
        """Update the existing authoritative citizen and one-to-one profiles."""
        citizen = await self.get_by_id(citizen_id)
        if citizen is None:
            return None
        for field in (
            "full_name", "date_of_birth", "gender", "mobile_number",
            "email_id", "citizen_type", "profile_types",
        ):
            setattr(citizen, field, getattr(data, field))
        flag_modified(citizen, "profile_types")
        citizen.profile_version = (getattr(citizen, "profile_version", 1) or 1) + 1

        # Guarantee sub-profiles exist
        if citizen.demographic_profile is None:
            citizen.demographic_profile = DemographicProfile(citizen_id=citizen.citizen_id)
            self.db.add(citizen.demographic_profile)
        if citizen.financial_profile is None:
            citizen.financial_profile = FinancialProfile(citizen_id=citizen.citizen_id)
            self.db.add(citizen.financial_profile)
        if citizen.location_profile is None:
            citizen.location_profile = LocationProfile(citizen_id=citizen.citizen_id)
            self.db.add(citizen.location_profile)

        for profile, values in (
            (citizen.demographic_profile, data.demographic.model_dump()),
            (citizen.financial_profile, data.financial.model_dump()),
            (citizen.location_profile, data.location.model_dump()),
        ):
            for field, value in values.items():
                setattr(profile, field, value)

        if citizen.demographic_profile and citizen.demographic_profile.type_specific_metadata is not None:
            flag_modified(citizen.demographic_profile, "type_specific_metadata")
        if citizen.location_profile and citizen.location_profile.current_address is not None:
            flag_modified(citizen.location_profile, "current_address")

        await self.db.flush()
        return citizen

    async def update_for_user(
        self, user_id: uuid.UUID, data: dict
    ) -> Optional[CitizenMaster]:
        """Update the citizen profile owned by an authenticated user."""
        from app.schemas.citizen import CitizenUpdate

        citizen = await self.get_by_owning_user(user_id)
        if citizen is None:
            return None
        payload = CitizenUpdate.model_validate(data)
        for field in (
            "full_name", "date_of_birth", "gender", "mobile_number",
            "email_id", "citizen_type", "profile_types",
        ):
            setattr(citizen, field, getattr(payload, field))
        flag_modified(citizen, "profile_types")
        citizen.profile_version = (getattr(citizen, "profile_version", 1) or 1) + 1

        if citizen.demographic_profile is None:
            citizen.demographic_profile = DemographicProfile(citizen_id=citizen.citizen_id)
            self.db.add(citizen.demographic_profile)
        if citizen.financial_profile is None:
            citizen.financial_profile = FinancialProfile(citizen_id=citizen.citizen_id)
            self.db.add(citizen.financial_profile)
        if citizen.location_profile is None:
            citizen.location_profile = LocationProfile(citizen_id=citizen.citizen_id)
            self.db.add(citizen.location_profile)

        for profile, values in (
            (citizen.demographic_profile, payload.demographic.model_dump()),
            (citizen.financial_profile, payload.financial.model_dump()),
            (citizen.location_profile, payload.location.model_dump()),
        ):
            for field, value in values.items():
                setattr(profile, field, value)

        if citizen.demographic_profile and citizen.demographic_profile.type_specific_metadata is not None:
            flag_modified(citizen.demographic_profile, "type_specific_metadata")
        if citizen.location_profile and citizen.location_profile.current_address is not None:
            flag_modified(citizen.location_profile, "current_address")

        await self.db.flush()
        return citizen

    async def get_full_profile(self, citizen_id: uuid.UUID) -> Optional[CitizenMaster]:
        """
        Fetch a citizen with all sub-profiles, education records, and facts.
        Used by the eligibility engine which needs every profile field.
        """
        result = await self.db.execute(
            select(CitizenMaster)
            .where(CitizenMaster.citizen_id == citizen_id)
            .options(
                joinedload(CitizenMaster.demographic_profile),
                joinedload(CitizenMaster.financial_profile),
                joinedload(CitizenMaster.location_profile),
                selectinload(CitizenMaster.education_records),
                selectinload(CitizenMaster.profile_facts),
            )
        )
        return result.scalar_one_or_none()
