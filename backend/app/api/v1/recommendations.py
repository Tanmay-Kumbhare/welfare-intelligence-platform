import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_authenticated_user, require_same_citizen
from app.database import get_db
from app.models.auth import UserAccount
from app.repositories.assessment_repository import AssessmentRepository
from app.repositories.citizen_repository import CitizenRepository
from app.schemas.assessment import RecommendationsResponse, RecommendationItem

router = APIRouter()


@router.get("/{citizen_id}", response_model=RecommendationsResponse)
async def get_citizen_recommendations(
    citizen_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: UserAccount = Depends(get_authenticated_user),
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
    assessments = await assessment_repo.get_citizen_assessments(citizen_id, active_only=True)

    from app.services.document_service import DocumentService, find_matching_citizen_document
    doc_service = DocumentService(db)
    citizen_docs = await doc_service.get_citizen_documents(citizen_id)

    eligible = []
    ineligible = []

    ref_date = datetime.now(timezone.utc).date()

    for a in assessments:
        scheme = a.scheme
        if not scheme:
            continue

        # Redundant safety guard: verify status and validity dates
        if scheme.status != "ACTIVE":
            continue
        if scheme.start_date and scheme.start_date > ref_date:
            continue
        if scheme.end_date and scheme.end_date < ref_date:
            continue

        eval_time = getattr(a, "updated_at", None) or getattr(a, "created_at", None)
        is_stale = False
        if scheme.last_updated_at and eval_time:
            s_time = (
                scheme.last_updated_at
                if scheme.last_updated_at.tzinfo
                else scheme.last_updated_at.replace(tzinfo=timezone.utc)
            )
            e_time = (
                eval_time
                if eval_time.tzinfo
                else eval_time.replace(tzinfo=timezone.utc)
            )
            if s_time > e_time:
                is_stale = True

        reason = a.reason
        if is_stale:
            reason = "Scheme rules changed since your last evaluation. Re-evaluation recommended."
        scheme_documents = []
        is_complete = True
        
        for req in a.scheme.documents:
            c_doc = find_matching_citizen_document(req.document_type, citizen_docs)
            
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

        eval_details = a.evaluation_details or {}
        rule_match_score = eval_details.get("rule_match_score")
        match_score = eval_details.get("match_score")
        if match_score is None:
            # Fallback derivation directly from rules structure
            total_r = 0
            passed_r = 0
            m_rules = []
            f_rules = []
            for g in eval_details.get("groups", []):
                for r in g.get("rules", []):
                    total_r += 1
                    desc = r.get("description") or r.get("parameter", "")
                    if r.get("passed"):
                        passed_r += 1
                        m_rules.append(desc)
                    else:
                        f_rules.append(desc)
            match_score = (
                round((passed_r / total_r) * 100.0, 1)
                if total_r > 0
                else (100.0 if a.eligibility_result else 0.0)
            )
            matched_rules = m_rules
            failed_rules = f_rules
        else:
            matched_rules = eval_details.get("matched_rules", [])
            failed_rules = eval_details.get("failed_rules", [])

        unknown_rules = eval_details.get("unknown_rules", [])
        failed_mandatory_rules = eval_details.get("failed_mandatory_rules", [])

        from app.services.gap_analysis_service import GapAnalysisService
        gap_analysis = GapAnalysisService.analyze_gaps(
            evaluation_details=a.evaluation_details,
            scheme_documents=scheme_documents,
            eligibility_result=a.eligibility_result,
        )

        item = RecommendationItem(
            scheme=a.scheme,
            eligibility_result=a.eligibility_result,
            is_stale=is_stale,
            rule_match_score=rule_match_score,
            match_score=float(match_score) if match_score is not None else None,
            matched_rules=matched_rules,
            failed_rules=failed_rules,
            unknown_rules=unknown_rules,
            failed_mandatory_rules=failed_mandatory_rules,
            reason=reason,
            evaluation_details=a.evaluation_details,
            assessment_date=a.assessment_date,
            documents=a.scheme.documents,
            document_status=doc_status,
            scheme_documents=scheme_documents,
            gap_analysis=gap_analysis,
        )
        if a.eligibility_result:
            eligible.append(item)
        else:
            ineligible.append(item)

    from app.services.recommendation_service import rank_recommendations
    from app.services.alternative_scheme_service import AlternativeSchemeService

    eligible_ranked = rank_recommendations(eligible, citizen=citizen)
    ineligible_ranked = rank_recommendations(ineligible, citizen=citizen)

    # Attach alternative scheme suggestions to ineligible schemes
    AlternativeSchemeService.attach_alternatives_to_recommendations(
        eligible_items=eligible_ranked,
        ineligible_items=ineligible_ranked,
    )

    return RecommendationsResponse(
        citizen_id=citizen_id,
        total_schemes_evaluated=len(assessments),
        eligible_count=len(eligible_ranked),
        ineligible_count=len(ineligible_ranked),
        eligible_schemes=eligible_ranked,
        ineligible_schemes=ineligible_ranked,
    )

