import uuid
from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.citizen_repository import CitizenRepository
from app.repositories.scheme_repository import SchemeRepository
from app.schemas.assessment import AssessmentResponse
from app.services.eligibility_engine import EligibilityEngine

router = APIRouter()


@router.post("/evaluate/{citizen_id}", response_model=List[AssessmentResponse])
async def evaluate_citizen_eligibility(
    citizen_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Evaluates the citizen against ALL active schemes and stores the assessments.
    Returns the updated list of assessments.
    """
    citizen_repo = CitizenRepository(db)
    scheme_repo = SchemeRepository(db)
    assessment_repo = AssessmentRepository(db)
    engine = EligibilityEngine()

    citizen = await citizen_repo.get_full_profile(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")

    schemes = await scheme_repo.get_all_active()
    assessments = []

    for scheme in schemes:
        overall_result, evaluation_details, reason = engine.evaluate_scheme(citizen, scheme)
        
        # Save assessment to DB
        assessment = await assessment_repo.upsert_assessment(
            citizen_id=citizen.citizen_id,
            scheme_id=scheme.scheme_id,
            eligibility_result=overall_result,
            reason=reason,
            evaluation_details=evaluation_details,
        )
        assessments.append(assessment)

    return assessments
