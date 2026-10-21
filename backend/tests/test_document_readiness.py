import uuid
from datetime import date, datetime, timezone
import pytest
from unittest.mock import AsyncMock, patch

from app.models.citizen import CitizenMaster
from app.models.document import CitizenDocument
from app.models.scheme import SchemeDocumentMaster, SchemeMaster
from app.schemas.assessment import RecommendationItem
from app.schemas.scheme import SchemeResponse
from app.services.document_service import (
    DocumentService,
    find_matching_citizen_document,
    is_document_compatible,
)
from app.services.recommendation_service import rank_recommendations


def _make_doc(
    requirement_type: str,
    original_filename: str = "doc.pdf",
    detected_type: str | None = None,
    validation_status: str = "VALID",
    validation_message: str | None = None,
) -> CitizenDocument:
    doc = CitizenDocument(
        document_id=uuid.uuid4(),
        citizen_id=uuid.uuid4(),
        requirement_type=requirement_type,
        original_filename=original_filename,
        content_type="application/pdf",
        file_size=1024,
        detected_type=detected_type or requirement_type,
        validation_status=validation_status,
        validation_message=validation_message,
        uploaded_at=datetime.now(timezone.utc),
    )
    return doc


def _make_scheme_req(doc_type: str, mandatory: bool = True) -> SchemeDocumentMaster:
    req = SchemeDocumentMaster(
        document_id=uuid.uuid4(),
        scheme_id=uuid.uuid4(),
        document_type=doc_type,
        mandatory_flag=mandatory,
    )
    return req


def _make_recommendation_item(
    scheme_id: uuid.UUID,
    scheme_name: str,
    eligibility_result: bool,
    rule_match_score: float = 80.0,
    document_status: str = "COMPLETE",
) -> RecommendationItem:
    return RecommendationItem(
        scheme=SchemeResponse(
            scheme_id=scheme_id,
            scheme_name=scheme_name,
            status="ACTIVE",
            group_combining_operator="AND",
        ),
        eligibility_result=eligibility_result,
        rule_match_score=rule_match_score,
        assessment_date=date(2026, 1, 1),
        document_status=document_status,
    )


# ---------------------------------------------------------------------------
# 1. Compatibility and Document Matching Tests
# ---------------------------------------------------------------------------

def test_aadhaar_matching_valid():
    """A valid Aadhaar document uploaded under IDENTITY_PROOF matches AADHAAR requirement."""
    doc = _make_doc(
        requirement_type="IDENTITY_PROOF",
        original_filename="aadhaar_card.pdf",
        detected_type="AADHAAR",
        validation_status="VALID",
    )
    assert is_document_compatible(doc, "AADHAAR") is True

    matched = find_matching_citizen_document("AADHAAR", [doc])
    assert matched is doc
    assert matched.validation_status == "VALID"


def test_incompatible_identity_document_does_not_satisfy_aadhaar():
    """A PAN card or generic ID proof does not satisfy specific AADHAAR requirement."""
    pan_doc = _make_doc(
        requirement_type="IDENTITY_PROOF",
        original_filename="pan_card.pdf",
        detected_type="PAN_CARD",
        validation_status="VALID",
    )
    assert is_document_compatible(pan_doc, "AADHAAR") is False
    assert find_matching_citizen_document("AADHAAR", [pan_doc]) is None

    # Neither does Aadhaar satisfy Voter ID or Photograph
    aadhaar_doc = _make_doc(
        requirement_type="IDENTITY_PROOF",
        original_filename="aadhaar.pdf",
        detected_type="AADHAAR",
        validation_status="VALID",
    )
    assert is_document_compatible(aadhaar_doc, "VOTER_ID") is False
    assert is_document_compatible(aadhaar_doc, "PHOTOGRAPH") is False


def test_bank_passbook_matching_valid():
    """A valid Bank Proof uploaded by citizen matches BANK_PASSBOOK requirement."""
    doc = _make_doc(
        requirement_type="BANK_PROOF",
        original_filename="bank_passbook.pdf",
        detected_type="BANK_PASSBOOK",
        validation_status="VALID",
    )
    assert is_document_compatible(doc, "BANK_PASSBOOK") is True

    matched = find_matching_citizen_document("BANK_PASSBOOK", [doc])
    assert matched is doc
    assert matched.validation_status == "VALID"


def test_incompatible_document_type_rejected():
    """An unrelated document (e.g. Land record) does not satisfy BANK_PASSBOOK or AADHAAR."""
    land_doc = _make_doc(
        requirement_type="LAND_RECORD",
        original_filename="land_712.pdf",
        detected_type="LAND_RECORD",
        validation_status="VALID",
    )
    assert is_document_compatible(land_doc, "AADHAAR") is False
    assert is_document_compatible(land_doc, "BANK_PASSBOOK") is False
    assert find_matching_citizen_document("AADHAAR", [land_doc]) is None
    assert find_matching_citizen_document("BANK_PASSBOOK", [land_doc]) is None


def test_marksheet_matches_academic_documents():
    """10th and 12th marksheets satisfy general MARKSHEET requirement."""
    doc_10th = _make_doc(
        requirement_type="10TH_MARKSHEET",
        original_filename="10th_marksheet.pdf",
        detected_type="10TH_MARKSHEET",
        validation_status="VALID",
    )
    assert is_document_compatible(doc_10th, "MARKSHEET") is True
    assert find_matching_citizen_document("MARKSHEET", [doc_10th]) is doc_10th


def test_valid_document_prioritized_over_invalid_or_pending():
    """When both valid and invalid uploads exist, find_matching_citizen_document prioritizes the VALID one."""
    invalid_doc = _make_doc(
        requirement_type="IDENTITY_PROOF",
        original_filename="aadhaar_old.pdf",
        detected_type="AADHAAR",
        validation_status="INVALID",
        validation_message="Document is blurry",
    )
    valid_doc = _make_doc(
        requirement_type="IDENTITY_PROOF",
        original_filename="aadhaar_new.pdf",
        detected_type="AADHAAR",
        validation_status="VALID",
    )

    matched = find_matching_citizen_document("AADHAAR", [invalid_doc, valid_doc])
    assert matched is valid_doc
    assert matched.validation_status == "VALID"


def test_invalid_document_returned_when_no_valid_document_exists():
    """When only an invalid or pending document exists, it is returned so diagnostics can surface."""
    invalid_doc = _make_doc(
        requirement_type="IDENTITY_PROOF",
        original_filename="aadhaar_blurry.pdf",
        detected_type="AADHAAR",
        validation_status="INVALID",
        validation_message="Document is illegible",
    )
    matched = find_matching_citizen_document("AADHAAR", [invalid_doc])
    assert matched is invalid_doc
    assert matched.validation_status == "INVALID"
    assert matched.validation_message == "Document is illegible"


# ---------------------------------------------------------------------------
# 2. Scheme Readiness and Evaluation Details Integration
# ---------------------------------------------------------------------------

def test_scheme_document_readiness_complete():
    """When all mandatory documents are satisfied with VALID status, readiness is COMPLETE."""
    docs = [
        _make_doc("IDENTITY_PROOF", "aadhaar.pdf", "AADHAAR", "VALID"),
        _make_doc("BANK_PROOF", "passbook.pdf", "BANK_PASSBOOK", "VALID"),
    ]
    reqs = [
        _make_scheme_req("AADHAAR", mandatory=True),
        _make_scheme_req("BANK_PASSBOOK", mandatory=True),
        _make_scheme_req("INCOME_CERTIFICATE", mandatory=False),  # Optional missing doc
    ]

    is_complete = True
    scheme_documents = []
    for req in reqs:
        c_doc = find_matching_citizen_document(req.document_type, docs)
        status = c_doc.validation_status if c_doc else "MISSING"
        if req.mandatory_flag and status != "VALID":
            is_complete = False
        scheme_documents.append({
            "document_type": req.document_type,
            "status": status,
            "required": req.mandatory_flag,
        })

    assert is_complete is True
    doc_status = "COMPLETE" if is_complete else "MISSING_DOCUMENTS"
    assert doc_status == "COMPLETE"
    assert len(scheme_documents) == 3
    assert scheme_documents[0]["status"] == "VALID"
    assert scheme_documents[1]["status"] == "VALID"
    assert scheme_documents[2]["status"] == "MISSING"


def test_scheme_document_readiness_missing_mandatory():
    """Missing a mandatory document prevents COMPLETE status."""
    docs = [
        _make_doc("IDENTITY_PROOF", "aadhaar.pdf", "AADHAAR", "VALID"),
        # BANK_PASSBOOK not uploaded
    ]
    reqs = [
        _make_scheme_req("AADHAAR", mandatory=True),
        _make_scheme_req("BANK_PASSBOOK", mandatory=True),
    ]

    is_complete = True
    for req in reqs:
        c_doc = find_matching_citizen_document(req.document_type, docs)
        status = c_doc.validation_status if c_doc else "MISSING"
        if req.mandatory_flag and status != "VALID":
            is_complete = False

    assert is_complete is False
    doc_status = "COMPLETE" if is_complete else "MISSING_DOCUMENTS"
    assert doc_status == "MISSING_DOCUMENTS"


def test_scheme_document_readiness_invalid_or_pending_mandatory():
    """An INVALID or PENDING mandatory document prevents COMPLETE status."""
    docs = [
        _make_doc("IDENTITY_PROOF", "aadhaar.pdf", "AADHAAR", "VALID"),
        _make_doc("BANK_PROOF", "passbook.pdf", "BANK_PASSBOOK", "PENDING"),
    ]
    reqs = [
        _make_scheme_req("AADHAAR", mandatory=True),
        _make_scheme_req("BANK_PASSBOOK", mandatory=True),
    ]

    is_complete = True
    for req in reqs:
        c_doc = find_matching_citizen_document(req.document_type, docs)
        status = c_doc.validation_status if c_doc else "MISSING"
        if req.mandatory_flag and status != "VALID":
            is_complete = False

    assert is_complete is False
    doc_status = "COMPLETE" if is_complete else "MISSING_DOCUMENTS"
    assert doc_status == "MISSING_DOCUMENTS"


# ---------------------------------------------------------------------------
# 3. Recommendation Ranking with Document Readiness Boost
# ---------------------------------------------------------------------------

def test_recommendation_ranking_prioritizes_document_ready_scheme():
    """Eligible scheme with document_status=COMPLETE ranks ahead of equal-scoring MISSING_DOCUMENTS scheme."""
    id1 = uuid.uuid4()
    id2 = uuid.uuid4()

    scheme_missing_docs = _make_recommendation_item(
        scheme_id=id1,
        scheme_name="Beta Scheme Missing Docs",
        eligibility_result=True,
        rule_match_score=85.0,
        document_status="MISSING_DOCUMENTS",
    )
    scheme_complete_docs = _make_recommendation_item(
        scheme_id=id2,
        scheme_name="Alpha Scheme Complete Docs",
        eligibility_result=True,
        rule_match_score=85.0,
        document_status="COMPLETE",
    )

    ranked = rank_recommendations([scheme_missing_docs, scheme_complete_docs])

    # Scheme with COMPLETE document readiness should be ranked first
    assert ranked[0].scheme.scheme_id == id2
    assert ranked[0].document_status == "COMPLETE"
    assert "All required documents uploaded" in ranked[0].recommendation_explanation

    assert ranked[1].scheme.scheme_id == id1
    assert ranked[1].document_status == "MISSING_DOCUMENTS"


# ---------------------------------------------------------------------------
# 4. Persona / Citizen Type Fallback in DocumentService
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_citizen_type_and_profile_types_fallback_in_document_service():
    """DocumentService.get_requirements_for_citizen falls back to citizen_type when profile_types is empty."""
    db_mock = AsyncMock()
    # Mock get_citizen_documents to return empty
    doc_service = DocumentService(db_mock)
    doc_service.get_citizen_documents = AsyncMock(return_value=[])

    # 1. Farmer fallback
    farmer = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Ramesh Farmer",
        citizen_type="FARMER",
        profile_types=[],
    )
    farmer_reqs = await doc_service.get_requirements_for_citizen(farmer)
    assert "FARMER" in farmer_reqs
    assert any(r["type"] == "LAND_RECORD" for r in farmer_reqs["FARMER"])

    # 2. Student fallback
    student = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Ananya Student",
        citizen_type="STUDENT",
        profile_types=None,
    )
    student_reqs = await doc_service.get_requirements_for_citizen(student)
    assert "STUDENT" in student_reqs
    assert any(r["type"] == "10TH_MARKSHEET" for r in student_reqs["STUDENT"])

    # 3. Senior fallback
    senior = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Kishore Senior",
        citizen_type="SENIOR",
        profile_types=[],
    )
    senior_reqs = await doc_service.get_requirements_for_citizen(senior)
    assert "SENIOR_CITIZEN" in senior_reqs
    assert any(r["type"] == "AGE_PROOF" for r in senior_reqs["SENIOR_CITIZEN"])

    # 4. Profile types SENIOR mapped to SENIOR_CITIZEN
    senior_pt = CitizenMaster(
        citizen_id=uuid.uuid4(),
        full_name="Kishore Senior 2",
        citizen_type="GENERAL",
        profile_types=["SENIOR"],
    )
    senior_pt_reqs = await doc_service.get_requirements_for_citizen(senior_pt)
    assert "SENIOR_CITIZEN" in senior_pt_reqs
