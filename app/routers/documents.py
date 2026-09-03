"""
app/routers/documents.py
------------------------
Document upload and retrieval endpoints — Phase B3: real upload pipeline.

Endpoints:
  POST /cases/:case_id/documents        -> DocumentUploadResponse  (201)
  GET  /documents/:id                   -> DocumentResponse
  GET  /documents/:id/download          -> DocumentDownloadResponse (presigned URL)

Upload pipeline (fully real in B3):
  1. Read file bytes from multipart upload.
  2. Validate MIME type — 400 if not in allowed list.
  3. Validate file size — 413 if over 50 MB.
  4. Compute SHA-256 of raw bytes.
  5. Upload to MinIO: storage_key = "{case_id}/{sha256}_{filename}".
  6. Insert Document row.
  7. Insert DocumentVersion row (version 1).
  8. Record UPLOADED custody event (tamper-evident hash of the event).
  9. Commit all DB changes.
  10. Dispatch async AI processing in BackgroundTasks (non-blocking).
  11. Return DocumentUploadResponse immediately (status="processing").

Background AI task:
  Opens its own DB session (request session is closed by response time),
  calls process_document(), stores AIAnalysis, records OCR_COMPLETE,
  NER_COMPLETE, and REDACTED custody events.

Download pipeline:
  1. Load Document from DB — 404 if not found.
  2. Generate 15-min presigned MinIO URL.
  3. Record DOWNLOADED custody event.
  4. Return presigned URL.

Contract for Frontend team:
  - Content-Type: multipart/form-data
  - Field name: "file"
  - Max size: 50 MB
  - Allowed MIME types: application/pdf, image/jpeg, image/png, image/tiff
  - Upload response is immediate (<2s). Poll GET /cases/:id/graph for AI progress.
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.models.case import Case
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.ai_analysis import AIAnalysis
from app.models.user import User
from app.schemas.document import DocumentDownloadResponse, DocumentResponse, DocumentUploadResponse
from app.services.ai_client import process_document
from app.services.custody_service import record_event
from app.services.rbac import get_current_user
from app.services.rate_limiter import rate_limit_upload
from app.services.storage_service import get_storage_service
from app.config import settings
from contracts.enums import CustodyEventType, Role

router = APIRouter()


# ---------------------------------------------------------------------------
# Background task: AI dispatch + custody event recording
# ---------------------------------------------------------------------------

def _ai_dispatch_task(document_id: str, storage_key: str, case_id: str, actor_id: str):
    """
    Runs after the HTTP response is returned.

    Opens its own DB session (the request session is already closed).
    Calls the AI service, stores the AIAnalysis result, and records
    OCR_COMPLETE, NER_COMPLETE, and REDACTED custody events.
    Silently suppresses any errors — a failed AI dispatch is not fatal;
    it will show up as missing graph nodes which the admin can retry.
    """
    db = SessionLocal()
    try:
        # process_document is async; run it in the sync context via asyncio.run()
        result = asyncio.run(process_document(document_id, storage_key))

        if result is None:
            return  # AI service unavailable; retry later

        # Save AIAnalysis row
        analysis = AIAnalysis(
            document_id=document_id,
            ocr_text=result.ocr_text,
            entities=[e.model_dump() for e in result.entities],
            redaction_boxes=[b.model_dump() for b in result.redaction_boxes],
            doc_class=result.doc_class,
            confidence=result.confidence,
            needs_review=result.needs_review,
            review_count=result.review_count,
            processed_at=datetime.now(timezone.utc),
        )
        db.add(analysis)
        db.flush()

        # Record custody events for each AI stage
        for event_type in [
            CustodyEventType.OCR_COMPLETE.value,
            CustodyEventType.NER_COMPLETE.value,
            CustodyEventType.REDACTED.value,
        ]:
            record_event(
                db=db,
                case_id=case_id,
                event_type=event_type,
                actor_id=actor_id,
                document_id=document_id,
                metadata={"ai_service": "mock" if settings.MOCK_AI_SERVICE else "real"},
            )

        db.commit()

    except Exception as exc:
        # Never crash the background thread — errors appear as absent graph nodes
        print(f"[ai_dispatch] ERROR for doc {document_id}: {exc}")
        db.rollback()
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Upload endpoint
# ---------------------------------------------------------------------------

@router.post(
    "/cases/{case_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
    summary="Upload a document to a case",
    tags=["Documents"],
)
async def upload_document(
    case_id: str,
    background_tasks: BackgroundTasks,
    request: Request,
    file: UploadFile = File(..., description="PDF, JPEG, PNG, or TIFF only. Max 50 MB."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Uploads a document and starts asynchronous AI processing.

    Response is immediate (<2s). Poll GET /cases/:id/graph to see
    OCR_COMPLETE, NER_COMPLETE, and REDACTED nodes appear.
    """
    # 0. Rate limiting (10 uploads / min per user)
    rate_limit_upload(request, current_user)

    # 1. Verify the case exists
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    # 2. RBAC check: Only officer, forensic, supervisor, admin can upload (Auditor cannot)
    allowed_roles = [Role.OFFICER.value, Role.FORENSIC.value, Role.SUPERVISOR.value, Role.ADMIN.value]
    if current_user.role not in allowed_roles:
        record_event(
            db=db,
            case_id=case_id,
            event_type=CustodyEventType.ACCESS_DENIED.value,
            actor_id=current_user.id,
            metadata={
                "action": "upload_document",
                "role": current_user.role,
                "reason": "insufficient_role",
            },
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Access forbidden: role '{current_user.role}' is not authorized to upload documents. Allowed: {allowed_roles}",
        )

    # 3. Read file bytes
    data = await file.read()

    # 3. Validate MIME type
    content_type = file.content_type or ""
    if content_type not in settings.allowed_mime_types_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File type '{content_type}' is not allowed. "
                f"Allowed types: {settings.allowed_mime_types_list}"
            ),
        )

    # 4. Validate file size
    if len(data) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB} MB",
        )

    # 5. Compute SHA-256
    storage = get_storage_service()
    sha256 = storage.compute_sha256(data)

    # 6. Upload to MinIO
    filename = file.filename or "unnamed_file"
    storage_key = storage.upload_file(case_id, filename, data, sha256)

    # 7. Insert Document row
    document = Document(
        case_id=case_id,
        filename=filename,
        storage_key=storage_key,
        sha256=sha256,
        mime=content_type,
        size=len(data),
        uploaded_by=current_user.id,
        current_version=1,
    )
    db.add(document)
    db.flush()  # get document.id without committing

    # 8. Insert DocumentVersion row (first version)
    version = DocumentVersion(
        document_id=document.id,
        sha256=sha256,
        storage_key=storage_key,
        created_by=current_user.id,
    )
    db.add(version)
    db.flush()

    # 9. Record UPLOADED custody event
    record_event(
        db=db,
        case_id=case_id,
        event_type=CustodyEventType.UPLOADED.value,
        actor_id=current_user.id,
        document_id=document.id,
        metadata={
            "filename": filename,
            "sha256": sha256,
            "size": len(data),
            "mime": content_type,
        },
    )

    # 10. Commit all DB changes
    db.commit()

    # 11. Dispatch AI processing in the background (non-blocking)
    background_tasks.add_task(
        _ai_dispatch_task,
        str(document.id),
        storage_key,
        str(case_id),
        str(current_user.id),
    )

    # 12. Return immediately
    return DocumentUploadResponse(
        document_id=str(document.id),
        filename=filename,
        sha256=sha256,
        size=len(data),
        status="processing",
    )


# ---------------------------------------------------------------------------
# Document metadata endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/documents/{document_id}",
    response_model=DocumentResponse,
    summary="Get document metadata",
)
def get_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns document metadata (not the file content).
    Use GET /documents/:id/download for a presigned download URL.

    Raises 404 if the document does not exist.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    return DocumentResponse(
        id=str(document.id),
        case_id=str(document.case_id),
        filename=document.filename,
        storage_key=document.storage_key,
        sha256=document.sha256,
        mime=document.mime,
        size=document.size,
        uploaded_by=str(document.uploaded_by),
        uploaded_at=document.uploaded_at,
        current_version=document.current_version,
    )


# ---------------------------------------------------------------------------
# Document download endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/documents/{document_id}/download",
    response_model=DocumentDownloadResponse,
    summary="Get a time-limited presigned download URL",
)
def download_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns a 15-minute presigned MinIO URL for direct file download.

    Records a DOWNLOADED custody event on every call.
    Raises 404 if the document does not exist.
    """
    document = db.query(Document).filter(Document.id == document_id).first()
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document '{document_id}' not found",
        )

    # Generate presigned URL
    storage = get_storage_service()
    presigned_url = storage.get_presigned_url(document.storage_key, expiry_minutes=15)

    # Record DOWNLOADED custody event
    record_event(
        db=db,
        case_id=str(document.case_id),
        event_type=CustodyEventType.DOWNLOADED.value,
        actor_id=current_user.id,
        document_id=document_id,
        metadata={"storage_key": document.storage_key},
    )
    db.commit()

    return DocumentDownloadResponse(
        presigned_url=presigned_url,
        expires_in_minutes=15,
    )
