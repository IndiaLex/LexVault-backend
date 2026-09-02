"""
app/schemas/document.py
-----------------------
Pydantic schemas for Document endpoints.

Used by:
  - Frontend team: upload response, document detail, download URL.
  - AI team: document_id and storage_key are passed to /ai/process.
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List


class DocumentUploadResponse(BaseModel):
    """
    Returned immediately after a multipart upload.
    AI processing runs in the background; poll the graph for status updates.
    """
    document_id: str
    filename: str
    sha256: str
    size: int
    status: str = "processing"   # always "processing" at upload time


class DocumentResponse(BaseModel):
    id: str
    case_id: str
    filename: str
    storage_key: str
    sha256: str
    mime: str
    size: int
    uploaded_by: str
    uploaded_at: datetime
    current_version: int

    class Config:
        from_attributes = True


class DocumentDownloadResponse(BaseModel):
    presigned_url: str
    expires_in_minutes: int = 15
