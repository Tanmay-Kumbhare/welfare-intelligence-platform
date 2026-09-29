import uuid
from typing import Any, List, Dict
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_optional_user, require_same_citizen
from app.database import get_db
from app.repositories.citizen_repository import CitizenRepository
from app.services.document_service import DocumentService

router = APIRouter()

class DocumentUploadRequest(BaseModel):
    requirement_type: str
    filename: str
    content_type: str
    content_base64: str

@router.get("/requirements/{citizen_id}")
async def get_document_requirements(
    citizen_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_optional_user),
) -> Any:
    """Returns domain-level document requirements and current upload status."""
    await require_same_citizen(user, citizen_id, db)
    
    citizen_repo = CitizenRepository(db)
    citizen = await citizen_repo.get_full_profile(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")
        
    doc_service = DocumentService(db)
    return await doc_service.get_requirements_for_citizen(citizen)


@router.post("/upload/{citizen_id}")
async def upload_document(
    citizen_id: uuid.UUID,
    payload: DocumentUploadRequest,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_optional_user),
) -> Any:
    """Uploads a document (base64 encoded), classifies it, and returns status."""
    await require_same_citizen(user, citizen_id, db)
    
    citizen_repo = CitizenRepository(db)
    citizen = await citizen_repo.get_by_id(citizen_id)
    if not citizen:
        raise HTTPException(status_code=404, detail="Citizen not found")
        
    doc_service = DocumentService(db)
    try:
        doc = await doc_service.upload_document(
            citizen_id=citizen_id,
            requirement_type=payload.requirement_type,
            filename=payload.filename,
            content_type=payload.content_type,
            content_base64=payload.content_base64
        )
        return {
            "document_id": str(doc.document_id),
            "original_filename": doc.original_filename,
            "detected_type": doc.detected_type,
            "validation_status": doc.validation_status,
            "validation_message": doc.validation_message,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{citizen_id}/{document_id}")
async def delete_document(
    citizen_id: uuid.UUID,
    document_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: Any = Depends(get_optional_user),
) -> Any:
    """Deletes an uploaded document."""
    await require_same_citizen(user, citizen_id, db)
    
    doc_service = DocumentService(db)
    success = await doc_service.delete_document(citizen_id, document_id)
    if not success:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"status": "deleted"}
