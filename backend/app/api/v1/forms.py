"""
Dynamic form API routes (Phase 2A).

Read endpoints serve the database-driven form hierarchy; submission
endpoints implement the draft → in-progress → completed lifecycle.
Errors from the service layer (FormServiceError subclasses) are mapped to
clean HTTP responses — raw database errors never surface here.
"""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.form_repository import FormRepository
from app.schemas.form import (
    FormDetail,
    FormSummary,
    FormVersionsResponse,
    SubmissionComplete,
    SubmissionCreate,
    SubmissionLifecycleError,
    SubmissionResponse,
    SubmissionUpdate,
)
from app.schemas.normalization import NormalizeRequest, NormalizationSummary
from app.services.form_logic import FormServiceError, SubmissionNotFoundError, SubmissionOwnershipError
from app.services.form_service import FormService
from app.services.normalization_service import (
    NormalizationService,
    SubmissionNotCompletedError,
)
from app.services.submission_service import SubmissionService

router = APIRouter()


@router.get("/", response_model=List[FormSummary], summary="List active forms")
async def list_forms(
    target_citizen_type: Optional[str] = Query(
        None,
        description="Filter forms by target citizen type (e.g. GENERAL, STUDENT, FARMER).",
    ),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Available ACTIVE forms, latest version per form_code."""
    service = FormService(FormRepository(db))
    return await service.list_active_forms(target_citizen_type)


@router.get(
    "/submissions/{submission_id}",
    response_model=SubmissionResponse,
    summary="Get a submission with its answers",
)
async def get_submission(
    submission_id: uuid.UUID,
    citizen_id: uuid.UUID = Query(..., description="Owner of the submission"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = SubmissionService(db)
    try:
        return await service.get_submission(submission_id, citizen_id)
    except FormServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail())


@router.get(
    "/{form_code}/versions",
    response_model=FormVersionsResponse,
    summary="List versions of a form",
)
async def list_form_versions(
    form_code: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = FormService(FormRepository(db))
    try:
        return await service.list_versions(form_code)
    except FormServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail())


@router.get(
    "/{form_code}/versions/{version}",
    response_model=FormDetail,
    summary="Get a specific form version",
)
async def get_form_version(
    form_code: str,
    version: int,
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = FormService(FormRepository(db))
    try:
        return await service.get_form_version(form_code, version)
    except FormServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail())


@router.get(
    "/{form_code}",
    response_model=FormDetail,
    summary="Get the active version of a form",
)
async def get_form(
    form_code: str,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Full hierarchy: sections → questions → options/conditions."""
    service = FormService(FormRepository(db))
    try:
        return await service.get_active_form(form_code)
    except FormServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail())


@router.post(
    "/{form_code}/submissions",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start (or resume) a submission",
    responses={
        403: {"description": "Submission belongs to another citizen"},
        404: {"description": "Form or citizen not found"},
        422: {"description": "Invalid answer payload"},
    },
)
async def create_submission(
    form_code: str,
    data: SubmissionCreate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Creates a DRAFT submission; re-calling resumes the existing draft."""
    service = SubmissionService(db)
    try:
        return await service.create_submission(form_code, data)
    except FormServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail())


@router.put(
    "/submissions/{submission_id}",
    response_model=SubmissionResponse,
    summary="Save progress on a draft submission",
    responses={
        403: {"description": "Submission belongs to another citizen"},
        404: {"description": "Submission not found"},
        409: {"description": "Submission no longer editable"},
        422: {"description": "Invalid answer payload"},
    },
)
async def update_submission(
    submission_id: uuid.UUID,
    data: SubmissionUpdate,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Saves partial answers; required validation is deferred to completion."""
    service = SubmissionService(db)
    try:
        return await service.update_submission(submission_id, data)
    except FormServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail())


@router.post(
    "/submissions/{submission_id}/normalize",
    response_model=NormalizationSummary,
    summary="Normalize a completed submission into canonical profiles and facts",
    responses={
        403: {"description": "Submission belongs to another citizen"},
        404: {"description": "Submission not found"},
        409: {"description": "Submission is not COMPLETED"},
    },
)
async def normalize_submission(
    submission_id: uuid.UUID,
    data: NormalizeRequest,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Runs deterministic normalization of a COMPLETED submission: writes
    canonical domain-profile columns, upserts open profile facts, records
    provenance, and reports unmapped answers. Idempotent — safe to re-run.
    """
    service = NormalizationService(db)
    try:
        return await service.normalize_submission(submission_id, data.citizen_id)
    except FormServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail())
    except SubmissionNotCompletedError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"message": exc.message})


@router.post(
    "/submissions/{submission_id}/complete",
    response_model=SubmissionResponse,
    summary="Complete a submission",
    responses={
        403: {"description": "Submission belongs to another citizen"},
        404: {"description": "Submission not found"},
        409: {"description": "Submission no longer editable"},
        422: {
            "model": SubmissionLifecycleError,
            "description": "Incomplete submission — body lists missing required question codes",
        },
    },
)
async def complete_submission(
    submission_id: uuid.UUID,
    data: SubmissionComplete,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Attempts completion. Returns 422 with the missing required question
    codes when applicable required questions are unanswered.
    """
    service = SubmissionService(db)
    try:
        return await service.complete_submission(submission_id, data.citizen_id)
    except FormServiceError as exc:
        if exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY:
            raise HTTPException(
                status_code=exc.status_code,
                detail=SubmissionLifecycleError(
                    message=exc.message,
                    missing_required=exc.extra.get("missing_required", []),
                ).model_dump(),
            )
        raise HTTPException(status_code=exc.status_code, detail=exc.to_detail())
