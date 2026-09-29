# Part 6: Domain-wise Document Requirements & Validation Final Report

## 1. Existing Document Architecture Discovered
There was no existing citizen document table (only `tbl_scheme_document_master` and `tbl_scheme_source_document` which belonged to scheme administration). No OCR pipeline existed. Therefore, I built a modular `DocumentService` with a `CitizenDocument` model and a fallback mock text-classifier since OCR dependencies (like PyMuPDF/tesseract) were not installed.

## 2. Files Changed / Added
* **Added `backend/app/models/document.py`**: Created the `CitizenDocument` ORM model.
* **Modified `backend/app/models/__init__.py`**: Exported the new model.
* **Added `backend/alembic/versions/0006_domain_documents.py`**: An Alembic migration script for the new table.
* **Added `backend/app/services/document_service.py`**: Added `DocumentClassifier` and `DocumentService` to handle domain logic and fake-OCR classification.
* **Added `backend/app/api/v1/documents.py`**: Created REST endpoints for requirement retrieval, upload, and deletion.
* **Modified `backend/app/api/v1/router.py`**: Wired up the new `documents` router.
* **Added `backend/tests/test_document_service.py`**: Included unit tests for the classification logic.
* **Added `frontend/src/pages/DocumentsPage.jsx`**: Created a citizen-facing Document Upload UI.
* **Modified `frontend/src/App.jsx`**: Added the `/documents` route.
* **Modified `frontend/src/components/layout/Header.jsx`**: Added "Documents" to the primary navigation bar.

## 3. Domain-wise Document Mapping Implemented
Implemented in `document_service.py` (`DOMAIN_DOCUMENTS`). It maps multiple profile types (e.g. `STUDENT`, `FARMER`, `PWD`, `SENIOR_CITIZEN`, `BUSINESS`) to domain-level requirements (Identity Proof, Address Proof, 10th Marksheet, Land Record, etc.). The service handles multiple roles dynamically (e.g., Student + Farmer gets requirements for both domains simultaneously).

## 4. Required/Optional Logic
The `DOMAIN_DOCUMENTS` dictionary defines a `required: bool` for each document requirement. The UI renders an `excl` badge for REQUIRED and a `neutral` badge for OPTIONAL.

## 5. Upload Flow
The `DocumentsPage.jsx` component displays grouped requirements. Users can select a file and click "Upload". Instead of multipart forms (which lacked `python-multipart` backend support), the frontend converts the file to Base64 and sends it as standard JSON payload. 

## 6. Document Classification Approach
A mock text classifier (`DocumentClassifier`) safely decodes Base64 payloads (if they happen to be text-based) and checks for keywords like "10th", "bonafide", "land", "caste". It falls back to searching keywords in the filename. The classifier is strictly limited to returning "What type of document does this appear to be?" rather than making false claims of authenticity.

## 7. 10th vs 12th Mismatch Validation
The classifier distinguishes "10TH_MARKSHEET" from "12TH_MARKSHEET". If a citizen uploads a 10th marksheet for a 12th marksheet requirement, the `validate_type()` function explicitly returns `"INVALID"` with the message: `"Expected 12TH_MARKSHEET but detected 10TH_MARKSHEET. Please upload the correct document."` The UI displays this exact message without falsely denying eligibility.

## 8. OCR Integration Status
No external OCR was integrated because `PyMuPDF` / `pytesseract` did not exist in the stack. Used a secure string extraction heuristic on base64 content to fulfill validation logic cleanly without inflating dependencies.

## 9. APIs Added
* `GET /api/v1/documents/requirements/{citizen_id}`
* `POST /api/v1/documents/upload/{citizen_id}`
* `DELETE /api/v1/documents/{citizen_id}/{document_id}`

## 10. Security/Authorization Implemented
Every endpoint strictly validates citizen ownership using `await require_same_citizen(user, citizen_id, db)`. A citizen cannot query, fetch, upload, or delete another citizen's documents.

## 11. Tests Run and Results
Ran `pytest tests/test_document_service.py`. All 7 classification tests passed successfully, verifying 10th vs 12th document validation matrices.

## 12. DB / Migration Issues
The `0006_domain_documents.py` Alembic migration is correct and ready. However, running it locally failed with `asyncpg.exceptions.InvalidPasswordError: password authentication failed for user "postgres"`, preventing live e2e DB tests.

## 13. Limitations
The classifier relies heavily on filename heuristics and simple text extraction since no OCR package is available in the venv.

## 14. Explicit Confirmation
The existing eligibility engine (`eligibility_engine.py`), scheme rules, and `evaluate_scheme` methods were **NOT** touched or modified. The architecture cleanly complements the existing setup.
