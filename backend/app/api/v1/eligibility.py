import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_optional_user, require_same_citizen
from app.database import get_db
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.citizen_repository import CitizenRepository
from app.repositories.scheme_repository import SchemeRepository
from app.schemas.assessment import AssessmentResponse
from app.schemas.simulation import SimulationInput, SimulationResponse
from app.services.eligibility_engine import EligibilityEngine

router = APIRouter()


@router.post("/evaluate/{citizen_id}", response_model=List[AssessmentResponse])
async def evaluate_citizen_eligibility(
    citizen_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_optional_user),
) -> Any:
    """
    Evaluates the citizen against ALL active schemes and stores the assessments.
    Returns the updated list of assessments.
    """
    # Authenticated callers may only evaluate their own profile.
    await require_same_citizen(user, citizen_id, db)
    citizen_repo = CitizenRepository(db)
    scheme_repo = SchemeRepository(db)
    assessment_repo = AssessmentRepository(db)
    engine = EligibilityEngine()

    citizen = await citizen_repo.get_full_profile(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")

    schemes = await scheme_repo.get_all_active_for_evaluation()
    assessment_rows = []

    for scheme in schemes:
        overall_result, evaluation_details, reason = engine.evaluate_scheme(citizen, scheme)
        assessment_rows.append(
            {
                "citizen_id": citizen.citizen_id,
                "scheme_id": scheme.scheme_id,
                "eligibility_result": overall_result,
                "reason": reason,
                "evaluation_details": evaluation_details,
            }
        )

    return await assessment_repo.upsert_assessments(assessment_rows)


@router.post("/simulate/{citizen_id}", response_model=SimulationResponse)
async def simulate_citizen_eligibility(
    citizen_id: uuid.UUID,
    payload: SimulationInput,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_optional_user),
) -> Any:
    """
    Simulates what-if profile changes for a citizen against all active schemes.
    Does NOT save changes to the citizen profile, facts, or assessment database.
    """
    await require_same_citizen(user, citizen_id, db)
    citizen_repo = CitizenRepository(db)
    scheme_repo = SchemeRepository(db)

    citizen = await citizen_repo.get_full_profile(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")

    schemes = await scheme_repo.get_all_active_for_evaluation()

    from app.services.simulation_service import SimulationService
    return SimulationService.simulate_citizen_eligibility(
        citizen=citizen,
        schemes=schemes,
        simulation_input=payload,
    )
