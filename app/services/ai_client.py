"""
app/services/ai_client.py
--------------------------
Client for the Backend AI service.

When MOCK_AI_SERVICE=true (default), returns a hardcoded AIResult that
matches the contract exactly. This lets Backend Core be fully developed
and tested before the AI team has their service running.

When MOCK_AI_SERVICE=false, POSTs to AI_SERVICE_URL/ai/process and
expects the same AIResult shape back.

AI team contract reference: contracts/entities.py -> ProcessRequest, AIResult
"""

import httpx
from typing import Optional
from app.config import settings
from contracts.entities import AIResult, Entity, RedactionBox, ProcessRequest


# ---------------------------------------------------------------------------
# Mock response — matches the contract exactly, used in Phase 1-2
# ---------------------------------------------------------------------------

def _mock_ai_result(document_id: str) -> AIResult:
    """
    Hardcoded AIResult for mock mode.
    Redaction boxes use normalized coordinates (0.0-1.0) as agreed with
    the AI team and Frontend team in Phase 0.
    """
    return AIResult(
        document_id=document_id,
        ocr_text=(
            "FIRST INFORMATION REPORT\n"
            "FIR No: 2026/0417\n"
            "Name of Complainant: Rahul Kumar\n"
            "Aadhaar: 1234 5678 9012\n"
            "Mobile: 9876543210\n"
            "Address: 123 MG Road, Bangalore - 560001\n"
            "Incident Date: 2026-08-15\n"
            "Officer: Inspector Sharma, Badge No: KA-1042"
        ),
        entities=[
            Entity(
                entity_id="ent-01",
                text="Rahul Kumar",
                label="PERSON",
                start_char=57,
                end_char=68,
                page=1,
                confidence=0.95,
            ),
            Entity(
                entity_id="ent-02",
                text="1234 5678 9012",
                label="AADHAAR",
                start_char=78,
                end_char=92,
                page=1,
                confidence=0.99,
            ),
            Entity(
                entity_id="ent-03",
                text="9876543210",
                label="PHONE",
                start_char=101,
                end_char=111,
                page=1,
                confidence=0.97,
            ),
        ],
        redaction_boxes=[
            RedactionBox(
                page=1, x=0.10, y=0.18, width=0.22, height=0.03,
                reason="PERSON", confidence=0.95, entity_id="ent-01",
            ),
            RedactionBox(
                page=1, x=0.10, y=0.24, width=0.28, height=0.03,
                reason="AADHAAR", confidence=0.99, entity_id="ent-02",
            ),
            RedactionBox(
                page=1, x=0.10, y=0.30, width=0.20, height=0.03,
                reason="PHONE", confidence=0.97, entity_id="ent-03",
            ),
        ],
        doc_class="FIR",
        confidence=0.93,
        needs_review=False,
        review_count=0,
    )


# ---------------------------------------------------------------------------
# Real client — used when MOCK_AI_SERVICE=false
# ---------------------------------------------------------------------------

async def _real_process(document_id: str, storage_key: str) -> AIResult:
    payload = ProcessRequest(document_id=document_id, storage_key=storage_key)
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{settings.AI_SERVICE_URL}/ai/process",
            json=payload.model_dump(),
        )
        response.raise_for_status()
        return AIResult(**response.json())


# ---------------------------------------------------------------------------
# Public interface — the only function the rest of the app calls
# ---------------------------------------------------------------------------

async def process_document(document_id: str, storage_key: str) -> Optional[AIResult]:
    """
    Send a document to the AI service for OCR + NER + PII detection.

    Returns an AIResult on success, None on failure (caller records the error
    as a custody event and retries later).

    Args:
        document_id: UUID of the Document row.
        storage_key: MinIO object key, e.g. "{case_id}/{sha256}_{filename}".
    """
    if settings.MOCK_AI_SERVICE:
        return _mock_ai_result(document_id)

    try:
        return await _real_process(document_id, storage_key)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        print(f"[ai_client] ERROR calling AI service: {exc}")
        return None
