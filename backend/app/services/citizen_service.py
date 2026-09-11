"""
Citizen service — orchestrates citizen domain operations.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.citizen import CitizenMaster
from app.repositories.citizen_repository import CitizenRepository
from app.schemas.citizen import (
    CitizenCreate,
    CitizenResponse,
    DemographicProfileResponse,
    FinancialProfileResponse,
    LocationProfileResponse,
)


def _to_response(citizen: CitizenMaster) -> CitizenResponse:
    """Map ORM relationship names to the public citizen response fields."""
    return CitizenResponse(
        citizen_id=citizen.citizen_id,
        full_name=citizen.full_name,
        date_of_birth=citizen.date_of_birth,
        gender=citizen.gender,
        mobile_number=citizen.mobile_number,
        email_id=citizen.email_id,
        citizen_type=citizen.citizen_type,
        registration_date=citizen.registration_date,
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
    )


class CitizenService:
    def __init__(self, db: AsyncSession) -> None:
        self.repo = CitizenRepository(db)

    async def register_citizen(self, data: CitizenCreate) -> CitizenResponse:
        # Additional business logic/validation could go here
        created = await self.repo.create(data)
        loaded = await self.repo.get_by_id(created.citizen_id)
        return _to_response(loaded or created)

    async def get_citizen(self, citizen_id: uuid.UUID) -> Optional[CitizenResponse]:
        citizen = await self.repo.get_by_id(citizen_id)
        return _to_response(citizen) if citizen else None
