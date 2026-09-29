import pytest
import uuid
import base64
from unittest.mock import AsyncMock, patch

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
