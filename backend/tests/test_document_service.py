import pytest
import uuid
import base64
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.document_service import DocumentClassifier

def test_document_classification_10th():
    content = base64.b64encode(b"This is my 10th marksheet.").decode('utf-8')
    assert DocumentClassifier.classify_document("doc.pdf", content) == "10TH_MARKSHEET"
    
def test_document_classification_12th():
    content = base64.b64encode(b"Here is the 12th marksheet from the board.").decode('utf-8')
    assert DocumentClassifier.classify_document("doc.pdf", content) == "12TH_MARKSHEET"
    
def test_document_classification_filename_12th():
    assert DocumentClassifier.classify_document("12th_marksheet.pdf", "") == "12TH_MARKSHEET"

def test_document_classification_invalid_10th_for_12th():
    content = base64.b64encode(b"Secondary 10th score").decode('utf-8')
    detected = DocumentClassifier.classify_document("doc.pdf", content)
    status, msg = DocumentClassifier.validate_type(detected, "12TH_MARKSHEET")
    assert status == "INVALID"
    assert "Expected" not in msg
    assert "Incorrect document. Required: 12Th Marksheet. Detected: 10Th Marksheet." in msg

def test_document_classification_invalid_12th_for_10th():
    detected = DocumentClassifier.classify_document("12th_marksheet.pdf", "")
    status, msg = DocumentClassifier.validate_type(detected, "10TH_MARKSHEET")
    assert status == "INVALID"
    assert "Incorrect document. Required: 10Th Marksheet. Detected: 12Th Marksheet." in msg

def test_document_classification_unknown():
    detected = DocumentClassifier.classify_document("unknown.pdf", "")
    status, msg = DocumentClassifier.validate_type(detected, "10TH_MARKSHEET")
    assert status == "REVIEW_REQUIRED"
    assert "Document type could not be determined" in msg

def test_document_classification_valid():
    detected = DocumentClassifier.classify_document("10th_marksheet.pdf", "")
    status, msg = DocumentClassifier.validate_type(detected, "10TH_MARKSHEET")
    assert status == "VALID"
    assert "Document verified as the required 10Th Marksheet." in msg


# ---------------------------------------------------------------------------
# DocumentService CRUD & Lifecycle Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_document_replaces_all_existing_duplicates():
    """upload_document removes all existing records for the same citizen and requirement_type."""
    from app.services.document_service import DocumentService
    from app.models.document import CitizenDocument

    db_mock = AsyncMock()
    db_mock.add = MagicMock()
    citizen_id = uuid.uuid4()
    req_type = "IDENTITY_PROOF"

    # Simulate two existing documents in the database
    doc1 = CitizenDocument(
        document_id=uuid.uuid4(),
        citizen_id=citizen_id,
        requirement_type=req_type,
        original_filename="old_aadhaar_1.pdf",
    )
    doc2 = CitizenDocument(
        document_id=uuid.uuid4(),
        citizen_id=citizen_id,
        requirement_type=req_type,
        original_filename="old_aadhaar_2.pdf",
    )

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [doc1, doc2]
    mock_result.scalars.return_value = mock_scalars
    db_mock.execute.return_value = mock_result

    service = DocumentService(db_mock)
    new_doc = await service.upload_document(
        citizen_id=citizen_id,
        requirement_type=req_type,
        filename="new_aadhaar.pdf",
        content_type="application/pdf",
        content_base64=base64.b64encode(b"This is an aadhaar card content.").decode("utf-8"),
    )

    # Verify both old documents were deleted
    assert db_mock.delete.call_count == 2
    deleted_calls = [c[0][0] for c in db_mock.delete.call_args_list]
    assert doc1 in deleted_calls
    assert doc2 in deleted_calls

    # Verify new document was added and committed
    db_mock.add.assert_called_once()
    assert db_mock.commit.call_count == 1
    assert db_mock.refresh.call_count == 1
    assert new_doc.original_filename == "new_aadhaar.pdf"
    assert new_doc.detected_type == "AADHAAR"
    assert new_doc.validation_status == "VALID"


@pytest.mark.asyncio
async def test_delete_document_success():
    """delete_document deletes the found document and returns True."""
    from app.services.document_service import DocumentService
    from app.models.document import CitizenDocument

    db_mock = AsyncMock()
    citizen_id = uuid.uuid4()
    document_id = uuid.uuid4()

    doc = CitizenDocument(
        document_id=document_id,
        citizen_id=citizen_id,
        requirement_type="BANK_PROOF",
    )

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = doc
    mock_result.scalars.return_value = mock_scalars
    db_mock.execute.return_value = mock_result

    service = DocumentService(db_mock)
    success = await service.delete_document(citizen_id, document_id)

    assert success is True
    db_mock.delete.assert_called_once_with(doc)
    assert db_mock.commit.call_count == 1


@pytest.mark.asyncio
async def test_delete_document_not_found():
    """delete_document returns False when the document does not exist."""
    from app.services.document_service import DocumentService

    db_mock = AsyncMock()
    citizen_id = uuid.uuid4()
    document_id = uuid.uuid4()

    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.first.return_value = None
    mock_result.scalars.return_value = mock_scalars
    db_mock.execute.return_value = mock_result

    service = DocumentService(db_mock)
    success = await service.delete_document(citizen_id, document_id)

    assert success is False
    assert db_mock.delete.call_count == 0


@pytest.mark.asyncio
async def test_get_requirements_decorates_existing_documents():
    """get_requirements_for_citizen decorates domain requirements with uploaded document metadata."""
    from app.services.document_service import DocumentService
    from app.models.citizen import CitizenMaster
    from app.models.document import CitizenDocument

    db_mock = AsyncMock()
    citizen_id = uuid.uuid4()

    uploaded_doc = CitizenDocument(
        document_id=uuid.uuid4(),
        citizen_id=citizen_id,
        requirement_type="IDENTITY_PROOF",
        original_filename="my_aadhaar.pdf",
        detected_type="AADHAAR",
        validation_status="VALID",
        validation_message="Document verified as the required Identity Proof.",
    )

    service = DocumentService(db_mock)
    service.get_citizen_documents = AsyncMock(return_value=[uploaded_doc])

    citizen = CitizenMaster(
        citizen_id=citizen_id,
        full_name="Pooja Sharma",
        citizen_type="GENERAL",
        profile_types=[],
    )

    groups = await service.get_requirements_for_citizen(citizen)
    assert "GENERAL" in groups
    id_req = next((r for r in groups["GENERAL"] if r["type"] == "IDENTITY_PROOF"), None)
    assert id_req is not None
    assert id_req["document"] is not None
    assert id_req["document"]["document_id"] == str(uploaded_doc.document_id)
    assert id_req["document"]["original_filename"] == "my_aadhaar.pdf"
    assert id_req["document"]["validation_status"] == "VALID"
