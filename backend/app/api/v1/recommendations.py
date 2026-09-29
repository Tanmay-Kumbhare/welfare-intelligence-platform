import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_optional_user, require_same_citizen
from app.database import get_db
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.citizen_repository import CitizenRepository
from app.schemas.assessment import RecommendationsResponse, RecommendationItem

router = APIRouter()


@router.get("/{citizen_id}", response_model=RecommendationsResponse)
async def get_citizen_recommendations(
    citizen_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_optional_user),
) -> Any:
    """
    Returns the previously stored eligibility assessments formatted as recommendations.
    Call POST /eligibility/evaluate/{citizen_id} first to generate these.
    """
    # Authenticated callers may only read their own recommendations.
    await require_same_citizen(user, citizen_id, db)
    citizen_repo = CitizenRepository(db)
    citizen = await citizen_repo.get_by_id(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")

    assessment_repo = AssessmentRepository(db)
    assessments = await assessment_repo.get_citizen_assessments(citizen_id)

    from app.services.document_service import DocumentService
    doc_service = DocumentService(db)
    citizen_docs = await doc_service.get_citizen_documents(citizen_id)
    citizen_doc_map = {d.requirement_type: d for d in citizen_docs}

    eligible = []
    ineligible = []

    for a in assessments:
        scheme_documents = []
        is_complete = True
        
        for req in a.scheme.documents:
            c_doc = citizen_doc_map.get(req.document_type)
            
            if not c_doc:
                status = "MISSING"
                msg = None
            else:
                status = c_doc.validation_status
                msg = c_doc.validation_message
                
            if req.mandatory_flag and status != "VALID":
                is_complete = False
                
            scheme_documents.append(
                {
                    "document_type": req.document_type,
                    "name": req.document_type.replace("_", " ").title(),
                    "required": req.mandatory_flag,
                    "status": status,
                    "validation_message": msg
                }
            )
            
        doc_status = "NOT_APPLICABLE"
        if len(a.scheme.documents) > 0:
            doc_status = "COMPLETE" if is_complete else "MISSING_DOCUMENTS"

        item = RecommendationItem(
            scheme=a.scheme,
            eligibility_result=a.eligibility_result,
            reason=a.reason,
            evaluation_details=a.evaluation_details,
            assessment_date=a.assessment_date,
            documents=a.scheme.documents,
            document_status=doc_status,
            scheme_documents=scheme_documents,
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
