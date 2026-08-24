import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.citizen_repository import CitizenRepository
from app.schemas.assessment import RecommendationsResponse, RecommendationItem

router = APIRouter()


@router.get("/{citizen_id}", response_model=RecommendationsResponse)
async def get_citizen_recommendations(
    citizen_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
) -> Any:
    """
    Returns the previously stored eligibility assessments formatted as recommendations.
    Call POST /eligibility/evaluate/{citizen_id} first to generate these.
    """
    citizen_repo = CitizenRepository(db)
    citizen = await citizen_repo.get_by_id(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")

    assessment_repo = AssessmentRepository(db)
    assessments = await assessment_repo.get_citizen_assessments(citizen_id)

    eligible = []
    ineligible = []

    for a in assessments:
        item = RecommendationItem(
            scheme=a.scheme,
            eligibility_result=a.eligibility_result,
            reason=a.reason,
            evaluation_details=a.evaluation_details,
            assessment_date=a.assessment_date,
            documents=a.scheme.documents,
        )
        if a.eligibility_result:
            eligible.append(item)
        else:
            ineligible.append(item)

    return RecommendationsResponse(
        citizen_id=citizen_id,
        total_schemes_evaluated=len(assessments),
        eligible_count=len(eligible),
        ineligible_count=len(ineligible),
        eligible_schemes=eligible,
        ineligible_schemes=ineligible,
    )
