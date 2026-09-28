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
        """Fetch the citizen profile owned by an authenticated user."""
        result = await self.db.execute(
            select(CitizenMaster)
            .where(CitizenMaster.owning_user_id == user_id)
            .options(
                selectinload(CitizenMaster.demographic_profile),
                selectinload(CitizenMaster.financial_profile),
                selectinload(CitizenMaster.location_profile),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, citizen_id: uuid.UUID) -> Optional[CitizenMaster]:
        """Fetch a citizen with all sub-profiles eagerly loaded."""
        result = await self.db.execute(
            select(CitizenMaster)
            .where(CitizenMaster.citizen_id == citizen_id)
            .options(
                selectinload(CitizenMaster.demographic_profile),
                selectinload(CitizenMaster.financial_profile),
                selectinload(CitizenMaster.location_profile),
            )
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
            "email_id", "citizen_type",
        ):
            setattr(citizen, field, getattr(data, field))
        for profile, values in (
            (citizen.demographic_profile, data.demographic.model_dump()),
            (citizen.financial_profile, data.financial.model_dump()),
            (citizen.location_profile, data.location.model_dump()),
        ):
            # Registration always creates all three rows. Keeping this guard
            # makes edits resilient to a legacy incomplete record without
            # creating a second citizen identity.
            if profile is not None:
                for field, value in values.items():
                    setattr(profile, field, value)
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
            "email_id", "citizen_type",
        ):
            setattr(citizen, field, getattr(payload, field))
        for profile, values in (
            (citizen.demographic_profile, payload.demographic.model_dump()),
            (citizen.financial_profile, payload.financial.model_dump()),
            (citizen.location_profile, payload.location.model_dump()),
        ):
            if profile is not None:
                for field, value in values.items():
                    setattr(profile, field, value)
        await self.db.flush()
        return citizen

    async def get_full_profile(self, citizen_id: uuid.UUID) -> Optional[CitizenMaster]:
        """
        Fetch a citizen with all sub-profiles and assessments.
        Used by the eligibility engine which needs every profile field.
        """
        result = await self.db.execute(
            select(CitizenMaster)
            .where(CitizenMaster.citizen_id == citizen_id)
            .options(
                # These are one-to-one relationships. Joining them keeps the
                # eligibility read to one query without multiplying rows.
                joinedload(CitizenMaster.demographic_profile),
                joinedload(CitizenMaster.financial_profile),
                joinedload(CitizenMaster.location_profile),
                # Open profile facts (AGE etc.) consumed by the engine.
                selectinload(CitizenMaster.profile_facts),
            )
        )
        return result.scalar_one_or_none()
