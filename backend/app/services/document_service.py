import base64
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.citizen import CitizenMaster
from app.models.document import CitizenDocument

DOMAIN_DOCUMENTS = {
    "STUDENT": [
        {"type": "IDENTITY_PROOF", "name": "Identity Proof", "required": True},
        {"type": "ADDRESS_PROOF", "name": "Address/Domicile Proof", "required": True},
        {"type": "10TH_MARKSHEET", "name": "10th Marksheet", "required": True},
        {"type": "12TH_MARKSHEET", "name": "12th Marksheet", "required": True},
        {"type": "COLLEGE_BONAFIDE", "name": "College Bonafide", "required": True},
        {"type": "PREVIOUS_MARKSHEET", "name": "Previous Semester/Year Marksheet", "required": True},
        {"type": "INCOME_CERTIFICATE", "name": "Income Certificate", "required": False},
        {"type": "CASTE_CERTIFICATE", "name": "Caste Certificate", "required": False},
        {"type": "CASTE_VALIDITY", "name": "Caste Validity", "required": False},
        {"type": "BANK_PROOF", "name": "Bank/Account Proof", "required": False},
    ],
    "FARMER": [
        {"type": "IDENTITY_PROOF", "name": "Identity Proof", "required": True},
        {"type": "ADDRESS_PROOF", "name": "Address/Domicile Proof", "required": False},
        {"type": "LAND_RECORD", "name": "Land Ownership/Land Record", "required": True},
        {"type": "FARMER_DOCUMENT", "name": "Relevant Farmer/Land Documents", "required": True},
        {"type": "BANK_PROOF", "name": "Bank/Account Proof", "required": True},
        {"type": "INCOME_CERTIFICATE", "name": "Income Document", "required": False},
    ],
    "PWD": [
        {"type": "IDENTITY_PROOF", "name": "Identity Proof", "required": True},
        {"type": "ADDRESS_PROOF", "name": "Address/Domicile Proof", "required": True},
        {"type": "DISABILITY_CERTIFICATE", "name": "Disability Certificate", "required": True},
        {"type": "INCOME_CERTIFICATE", "name": "Income/Category Document", "required": False},
    ],
    "SENIOR_CITIZEN": [
        {"type": "IDENTITY_PROOF", "name": "Identity Proof", "required": True},
        {"type": "AGE_PROOF", "name": "Age/Date-of-Birth Proof", "required": True},
        {"type": "ADDRESS_PROOF", "name": "Address/Domicile Proof", "required": True},
        {"type": "INCOME_CERTIFICATE", "name": "Income/BPL Document", "required": False},
        {"type": "BANK_PROOF", "name": "Bank/Account Proof", "required": False},
    ],
    "BUSINESS": [
        {"type": "IDENTITY_PROOF", "name": "Identity Proof", "required": True},
        {"type": "ADDRESS_PROOF", "name": "Address Proof", "required": True},
        {"type": "UDYAM_REGISTRATION", "name": "Business Registration/Udyam", "required": False},
        {"type": "BANK_PROOF", "name": "Bank/Account Proof", "required": True},
        {"type": "INCOME_CERTIFICATE", "name": "Income/Business-related Documents", "required": False},
    ],
    "DEFAULT": [
        {"type": "IDENTITY_PROOF", "name": "Identity Proof", "required": True},
        {"type": "ADDRESS_PROOF", "name": "Address Proof", "required": True},
        {"type": "INCOME_CERTIFICATE", "name": "Income Certificate", "required": False},
        {"type": "CASTE_CERTIFICATE", "name": "Category Document", "required": False},
    ]
}

class DocumentClassifier:
    @staticmethod
    def classify_document(filename: str, content_base64: str) -> str:
        snippet = ""
        try:
            decoded = base64.b64decode(content_base64)
            snippet = decoded[:1000].decode("utf-8", errors="ignore").lower()
        except Exception:
            pass
            
        text_to_search = (filename + " " + snippet).lower()
        
        import re
        if "10th" in text_to_search or "secondary" in text_to_search or "ssc" in text_to_search:
            return "10TH_MARKSHEET"
        if "12th" in text_to_search or "hsc" in text_to_search or "higher secondary" in text_to_search:
            return "12TH_MARKSHEET"
        if "bonafide" in text_to_search or "college" in text_to_search:
            return "COLLEGE_BONAFIDE"
        if "income" in text_to_search:
            return "INCOME_CERTIFICATE"
        if "caste" in text_to_search:
            if "validity" in text_to_search:
                return "CASTE_VALIDITY"
            return "CASTE_CERTIFICATE"
        if "domicile" in text_to_search or "address" in text_to_search:
            return "ADDRESS_PROOF"
        if "aadhaar" in text_to_search or "identity" in text_to_search or re.search(r'\bpan\b', text_to_search):
            return "IDENTITY_PROOF"
        if "disability" in text_to_search or "handicap" in text_to_search:
            return "DISABILITY_CERTIFICATE"
        if "land" in text_to_search or "7/12" in text_to_search:
            return "LAND_RECORD"
        if "bank" in text_to_search or "passbook" in text_to_search:
            return "BANK_PROOF"
        if "udyam" in text_to_search or "business" in text_to_search:
            return "UDYAM_REGISTRATION"
        if re.search(r'\bage\b', text_to_search) or "birth" in text_to_search or re.search(r'\bdob\b', text_to_search):
            return "AGE_PROOF"
        if "farmer" in text_to_search:
            return "FARMER_DOCUMENT"
        if "previous" in text_to_search or "semester" in text_to_search:
            return "PREVIOUS_MARKSHEET"
        
        return "UNKNOWN"

    @staticmethod
    def validate_type(detected_type: str, requirement_type: str) -> tuple[str, str | None]:
        if detected_type == requirement_type:
            return "VALID", f"Document verified as the required {requirement_type.replace('_', ' ').title()}."
        
        if detected_type == "UNKNOWN":
            return "REVIEW_REQUIRED", "Document type could not be determined. Please upload a clearer or supported document."
        
        return "INVALID", f"Incorrect document. Required: {requirement_type.replace('_', ' ').title()}. Detected: {detected_type.replace('_', ' ').title()}. Please upload the correct document."

    @staticmethod
    def check_profile_consistency(citizen: CitizenMaster, document: CitizenDocument) -> str:
        # We do not have structured document metadata for name extraction without OCR,
        # so we safely return NOT_AVAILABLE.
        return "NOT_AVAILABLE"

class DocumentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_requirements_for_citizen(self, citizen: CitizenMaster) -> Dict[str, List[Dict[str, Any]]]:
        profile_types = citizen.profile_types or []
        groups = {}
        
        if not profile_types:
            groups["GENERAL"] = DOMAIN_DOCUMENTS["DEFAULT"]
        else:
            for pt in profile_types:
                if pt in DOMAIN_DOCUMENTS:
                    groups[pt] = DOMAIN_DOCUMENTS[pt]
                elif "EMPLOYEE" in pt or "HOMEMAKER" in pt or "OTHER" in pt:
                    if "GENERAL" not in groups:
                        groups["GENERAL"] = DOMAIN_DOCUMENTS["DEFAULT"]
                        
        # Decorate with existing uploads
        existing_docs = await self.get_citizen_documents(citizen.citizen_id)
        docs_by_req = {doc.requirement_type: doc for doc in existing_docs}
        
        decorated_groups = {}
        for group_name, reqs in groups.items():
            decorated_reqs = []
            for req in reqs:
                doc = docs_by_req.get(req["type"])
                req_copy = req.copy()
                req_copy["document"] = None
                if doc:
                    req_copy["document"] = {
                        "document_id": str(doc.document_id),
                        "original_filename": doc.original_filename,
                        "validation_status": doc.validation_status,
                        "validation_message": doc.validation_message,
                        "detected_type": doc.detected_type,
                        "profile_consistency": DocumentClassifier.check_profile_consistency(citizen, doc),
                    }
                decorated_reqs.append(req_copy)
            decorated_groups[group_name] = decorated_reqs
            
        return decorated_groups

    async def get_citizen_documents(self, citizen_id: uuid.UUID) -> List[CitizenDocument]:
        result = await self.db.execute(
            select(CitizenDocument).where(CitizenDocument.citizen_id == citizen_id)
        )
        return list(result.scalars().all())

    async def upload_document(
        self, citizen_id: uuid.UUID, requirement_type: str, filename: str, content_type: str, content_base64: str
    ) -> CitizenDocument:
        # Calculate size approximation
        size = len(content_base64) * 3 // 4
        if size == 0:
            raise ValueError("File is empty.")
            
        detected = DocumentClassifier.classify_document(filename, content_base64)
        status, message = DocumentClassifier.validate_type(detected, requirement_type)
        
        # Delete existing if replacing
        existing = await self.db.execute(
            select(CitizenDocument)
            .where(CitizenDocument.citizen_id == citizen_id, CitizenDocument.requirement_type == requirement_type)
        )
        existing_doc = existing.scalars().first()
        if existing_doc:
            await self.db.delete(existing_doc)

        new_doc = CitizenDocument(
            citizen_id=citizen_id,
            requirement_type=requirement_type,
            original_filename=filename,
            content_type=content_type,
            file_size=size,
            detected_type=detected,
            validation_status=status,
            validation_message=message,
        )
        self.db.add(new_doc)
        await self.db.commit()
        await self.db.refresh(new_doc)
        return new_doc

    async def delete_document(self, citizen_id: uuid.UUID, document_id: uuid.UUID) -> bool:
        result = await self.db.execute(
            select(CitizenDocument).where(CitizenDocument.citizen_id == citizen_id, CitizenDocument.document_id == document_id)
        )
        doc = result.scalars().first()
        if doc:
            await self.db.delete(doc)
            await self.db.commit()
            return True
        return False
