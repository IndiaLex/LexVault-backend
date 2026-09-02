"""
app/routers/documents.py
------------------------
Document upload and retrieval endpoints.

Phase B1: stubs.
Phase B3: real upload flow (MinIO + SHA-256 + DB rows + custody event + async AI dispatch).

Endpoints:
  POST /cases/:case_id/documents        -> DocumentUploadResponse  (201)
  GET  /documents/:id                   -> DocumentResponse
  GET  /documents/:id/download          -> DocumentDownloadResponse (presigned URL)

Upload contract (for Frontend team):
  - Content-Type: multipart/form-data
  - Field name: "file"
  - Max size: 50 MB (enforced server-side)
  - Allowed MIME types: application/pdf, image/jpeg, image/png, image/tiff
  - Response is immediate (< 2s). AI processing runs in the background.
    Poll GET /cases/:id/graph to see OCR_COMPLETE / REDACTED nodes appear.
"""

from fastapi import APIRouter, Depends, UploadFile, File
from datetime import datetime, timezone

from app.schemas.document import DocumentUploadResponse, DocumentResponse, DocumentDownloadResponse
from app.services.rbac import get_current_user

router = APIRouter()


@router.post(
    "/cases/{case_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
    summary="Upload a document to a case",
    tags=["Documents"],
)
def upload_document(
    case_id: str,
    file: UploadFile = File(..., description="PDF, JPEG, PNG, or TIFF only. Max 50 MB."),
    current_user=Depends(get_current_user),
):
    """
    Uploads a document and starts asynchronous AI processing.

    Steps (Phase B3 implementation):
      1. Validate MIME type and file size.
      2. Compute SHA-256 of the raw bytes.
      3. Store in MinIO: {case_id}/{sha256}_{filename}.
      4. Create Document + DocumentVersion rows.
      5. Record UPLOAD custody event.
      6. Dispatch to AI service in the background (non-blocking).
      7. Return immediately with document_id and status="processing".

    [STUB - Phase B1] Returns placeholder response.
    """
    return DocumentUploadResponse(
        document_id="doc-stub-001",
        filename=file.filename or "unknown",
        sha256="a" * 64,
        size=0,
        status="processing",
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get document metadata",
)
def get_document(document_id: str, current_user=Depends(get_current_user)):
    """
    Returns document metadata (not the file content).
    Use GET /documents/:id/download for a presigned download URL.

    [STUB - Phase B1]
    """
    return DocumentResponse(
        id=document_id,
        case_id="case-stub-001",
        filename="stub_document.pdf",
        storage_key="case-stub-001/aaa_stub_document.pdf",
        sha256="a" * 64,
        mime="application/pdf",
        size=1024,
        uploaded_by="00000000-0000-0000-0000-000000000001",
        uploaded_at=datetime.now(timezone.utc),
        current_version=1,
    )


@router.get(
    "/documents/{document_id}/download",
    response_model=DocumentDownloadResponse,
    summary="Get a time-limited presigned download URL",
)
def download_document(document_id: str, current_user=Depends(get_current_user)):
    """
    Returns a 15-minute presigned MinIO URL for direct file download.
    The URL is time-limited and single-use for security.

    Records a DOWNLOADED custody event on every call.

    [STUB - Phase B1]
    """
    return DocumentDownloadResponse(
        presigned_url=f"http://localhost:9000/securedocx/stub/{document_id}?X-Amz-Expires=900",
        expires_in_minutes=15,
    )
