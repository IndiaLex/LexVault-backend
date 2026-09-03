"""
app/routers/anchor.py
---------------------
Anchoring and on-chain verification endpoints — Phase B5: real orchestration.

Endpoints:
  POST /cases/:case_id/anchor               -> AnchorTriggerResponse  (202)
  GET  /anchors/:batch_id                   -> AnchorBatchStatusResponse
  GET  /anchors/:batch_id/verify?hash=      -> AnchorVerifyResponse

Anchoring flow (for all teams):
  1. POST /cases/:id/anchor
       - Collects SHA-256 values of all documents in the case that have
         NOT yet been included in a confirmed anchor batch.
       - Submits hashes to the Blockchain Service via submit_hashes().
       - Creates an AnchorBatch DB row with status=pending.
       - Records ANCHORED custody events for every document anchored.
       - Returns 202 + batch_id immediately.
  2. Frontend polls GET /anchors/:batchId until status == "confirmed".
  3. On confirmation, ANCHORED events appear in the graph.

Verification flow (two-stage, for all teams):
  Stage 1 (local tamper check):
    - Find Document by sha256 query param.
    - Re-download from MinIO via StorageService.detect_tampering().
    - If current hash != DB sha256: tamper detected, return valid=false
      (no chain call needed, file is locally modified).
  Stage 2 (on-chain Merkle proof):
    - Call verify_hash(hash_value, batch_id) on blockchain_client.
    - If proof fails: chain_valid=false, valid=false.
    - Both stages must pass for valid=true.
  In all cases, record a VERIFIED custody event with result="pass" or "fail".

IMPORTANT for Blockchain team:
  This router calls your service at:
    POST {BLOCKCHAIN_SERVICE_URL}/anchor/submit
    GET  {BLOCKCHAIN_SERVICE_URL}/anchor/:batchId
    GET  {BLOCKCHAIN_SERVICE_URL}/anchor/verify?hash=&batchId=
  See app/services/blockchain_client.py for exact request/response shapes.
"""

import asyncio
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.anchor_batch import AnchorBatch
from app.models.case import Case
from app.models.custody_event import CustodyEvent
from app.models.document import Document
from app.models.user import User
from app.schemas.anchor import (
    AnchorTriggerResponse,
    AnchorBatchStatusResponse,
    AnchorVerifyResponse,
)
from app.services.blockchain_client import submit_hashes, get_batch_status, verify_hash
from app.services.custody_service import record_event
from app.services.rbac import get_current_user
from app.services.storage_service import get_storage_service
from contracts.enums import AnchorBatchStatus, CustodyEventType

router = APIRouter()

# Polygon Amoy block explorer
AMOY_EXPLORER = "https://www.oklink.com/amoy/tx"


# ---------------------------------------------------------------------------
# Helper: find documents not yet anchored in a confirmed batch
# ---------------------------------------------------------------------------

def _unanchored_documents(db: Session, case_id: str):
    """
    Returns all Document rows for the case that do NOT already have an
    ANCHORED custody event linked to a confirmed AnchorBatch.

    We do a simple approach: any document that has never had an ANCHORED
    custody event with a non-null anchor_batch_id is considered unanchored.
    """
    from app.models.custody_event import CustodyEvent

    anchored_doc_ids = (
        db.query(CustodyEvent.document_id)
        .filter(
            CustodyEvent.case_id == case_id,
            CustodyEvent.type == CustodyEventType.ANCHORED.value,
            CustodyEvent.anchor_batch_id.isnot(None),
        )
        .distinct()
        .all()
    )
    anchored_ids = {row[0] for row in anchored_doc_ids}

    docs = db.query(Document).filter(Document.case_id == case_id).all()
    return [d for d in docs if str(d.id) not in anchored_ids]


# ---------------------------------------------------------------------------
# Trigger anchor
# ---------------------------------------------------------------------------

@router.post(
    "/cases/{case_id}/anchor",
    response_model=AnchorTriggerResponse,
    status_code=202,
    summary="Trigger Merkle batch anchoring for a case",
    tags=["Cases", "Anchor"],
)
async def trigger_anchor(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Collects all unanchored document SHA-256 hashes for the case,
    submits them to the Blockchain Service for Merkle batching,
    and returns immediately with a batch_id (202 Accepted).

    If all documents are already anchored, returns 202 with hashes_submitted=0
    and a note. The batch is processed asynchronously on the blockchain side.

    Poll GET /anchors/:batch_id for confirmation.
    On confirmation, ANCHORED events appear in the graph.

    Raises 404 if the case does not exist.
    """
    # Verify case exists
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    # Collect unanchored documents
    unanchored = _unanchored_documents(db, case_id)
    hashes = [d.sha256 for d in unanchored]

    if not hashes:
        # All documents already anchored — create a no-op batch for the response
        batch = AnchorBatch(
            status=AnchorBatchStatus.CONFIRMED.value,
            confirmed_at=datetime.now(timezone.utc),
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)
        return AnchorTriggerResponse(
            batch_id=str(batch.id),
            status="confirmed",
            hashes_submitted=0,
        )

    # Submit hashes to blockchain service
    result = await submit_hashes(hashes)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Blockchain service is unavailable. Try again later.",
        )

    # Create AnchorBatch row with pending status
    batch = AnchorBatch(
        status=AnchorBatchStatus.PENDING.value,
    )
    db.add(batch)
    db.flush()

    # Record ANCHORED custody event for each document submitted
    for doc in unanchored:
        record_event(
            db=db,
            case_id=case_id,
            event_type=CustodyEventType.ANCHORED.value,
            actor_id=current_user.id,
            document_id=str(doc.id),
            metadata={
                "batch_id": str(batch.id),
                "sha256": doc.sha256,
                "blockchain_batch_id": result.get("batch_id"),
            },
            anchor_batch_id=str(batch.id),
        )

    db.commit()

    return AnchorTriggerResponse(
        batch_id=str(batch.id),
        status=result.get("status", "pending"),
        hashes_submitted=len(hashes),
    )


# ---------------------------------------------------------------------------
# Get anchor batch status
# ---------------------------------------------------------------------------

@router.get(
    "/anchors/{batch_id}",
    response_model=AnchorBatchStatusResponse,
    summary="Get the status of an anchor batch",
)
async def get_anchor_batch(
    batch_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Polls the live status of a previously triggered anchor batch.
    Status values: pending | confirmed | failed

    On confirmed: merkle_root, tx_hash, block_number are populated.
    This endpoint first checks the DB, then polls the Blockchain Service
    to pick up any status updates (confirmed, failed) since last checked.

    Raises 404 if the batch_id does not exist in the DB.
    """
    batch = db.query(AnchorBatch).filter(AnchorBatch.id == batch_id).first()
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anchor batch '{batch_id}' not found",
        )

    # If already confirmed or failed in DB, return cached status
    if batch.status in (AnchorBatchStatus.CONFIRMED.value, AnchorBatchStatus.FAILED.value):
        return AnchorBatchStatusResponse(
            batch_id=str(batch.id),
            status=batch.status,
            merkle_root=batch.merkle_root,
            tx_hash=batch.tx_hash,
            chain_id=batch.chain_id,
            confirmed_at=batch.confirmed_at.isoformat() if batch.confirmed_at else None,
        )

    # Still pending — poll blockchain service for update
    chain_result = await get_batch_status(batch_id)
    if chain_result and chain_result.get("status") == "confirmed":
        # Update DB with confirmed data
        batch.status = AnchorBatchStatus.CONFIRMED.value
        batch.merkle_root = chain_result.get("merkle_root")
        batch.tx_hash = chain_result.get("tx_hash")
        batch.chain_id = chain_result.get("chain_id", "80002")
        batch.confirmed_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(batch)

    return AnchorBatchStatusResponse(
        batch_id=str(batch.id),
        status=batch.status,
        merkle_root=batch.merkle_root,
        tx_hash=batch.tx_hash,
        chain_id=batch.chain_id,
        block_number=chain_result.get("block_number") if chain_result else None,
        confirmed_at=batch.confirmed_at.isoformat() if batch.confirmed_at else None,
    )


# ---------------------------------------------------------------------------
# Verify anchor
# ---------------------------------------------------------------------------

@router.get(
    "/anchors/{batch_id}/verify",
    response_model=AnchorVerifyResponse,
    summary="Verify a document hash against the on-chain anchor",
)
async def verify_anchor(
    batch_id: str,
    hash: str = Query(
        ...,
        description="SHA-256 hex string of the document to verify (64 chars, no 0x prefix)",
        min_length=64,
        max_length=64,
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Two-stage tamper verification for a document.

    Query params:
      - hash: 64-char SHA-256 hex of the document (Document.sha256 value)

    Stage 1 (local): Re-downloads the file from MinIO and recomputes SHA-256.
      If current_hash != db_sha256: file was tampered. Returns valid=false.
    Stage 2 (chain): Calls Blockchain Service for Merkle proof.
      If proof fails: chain_valid=false, valid=false.

    A VERIFIED custody event is recorded with result="pass" or "fail".
    This event appears in the graph as a green or red node.

    Raises 404 if the batch or document is not found.
    """
    # Verify batch exists
    batch = db.query(AnchorBatch).filter(AnchorBatch.id == batch_id).first()
    if batch is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anchor batch '{batch_id}' not found",
        )

    # Find the document by sha256, preferring document tied to this batch
    anchored_event = (
        db.query(CustodyEvent)
        .filter(CustodyEvent.anchor_batch_id == batch_id)
        .join(Document, CustodyEvent.document_id == Document.id)
        .filter(Document.sha256 == hash)
        .first()
    )
    if anchored_event and anchored_event.document:
        document = anchored_event.document
    else:
        document = db.query(Document).filter(Document.sha256 == hash).first()

    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with sha256 '{hash}' not found",
        )

    # ---- Stage 1: Local tamper detection ----
    storage = get_storage_service()
    tamper_result = storage.detect_tampering(document.storage_key, hash)
    local_hash_match = not tamper_result["is_tampered"]

    if not local_hash_match:
        # File was locally modified — no need to check the chain
        record_event(
            db=db,
            case_id=str(document.case_id),
            event_type=CustodyEventType.VERIFIED.value,
            actor_id=current_user.id,
            document_id=str(document.id),
            metadata={
                "result": "fail",
                "reason": "hash_mismatch",
                "expected": hash,
                "found": tamper_result["current_hash"],
                "batch_id": batch_id,
            },
            anchor_batch_id=batch_id,
        )
        db.commit()

        return AnchorVerifyResponse(
            valid=False,
            local_hash_match=False,
            chain_valid=None,
            reason="hash_mismatch",
        )

    # ---- Stage 2: On-chain Merkle proof ----
    chain_result = await verify_hash(hash, batch_id)
    chain_valid = bool(chain_result and chain_result.get("valid", False))

    overall_valid = local_hash_match and chain_valid
    reason = None if overall_valid else "proof_invalid"

    # Record VERIFIED custody event
    record_event(
        db=db,
        case_id=str(document.case_id),
        event_type=CustodyEventType.VERIFIED.value,
        actor_id=current_user.id,
        document_id=str(document.id),
        metadata={
            "result": "pass" if overall_valid else "fail",
            "reason": reason,
            "batch_id": batch_id,
            "chain_valid": chain_valid,
        },
        anchor_batch_id=batch_id,
    )
    db.commit()

    # Build response
    explorer_url = None
    tx_hash = None
    merkle_root = None
    proof = []
    block_number = None
    chain_id = None

    if chain_result:
        tx_hash = chain_result.get("tx_hash")
        merkle_root = chain_result.get("merkle_root")
        proof = chain_result.get("proof", [])
        explorer_url = chain_result.get("explorer_url") or (
            f"{AMOY_EXPLORER}/{tx_hash}" if tx_hash else None
        )
        block_number = chain_result.get("block_number")
        chain_id = chain_result.get("chain_id", batch.chain_id)

    return AnchorVerifyResponse(
        valid=overall_valid,
        local_hash_match=local_hash_match,
        chain_valid=chain_valid,
        merkle_root=merkle_root,
        tx_hash=tx_hash,
        block_number=block_number,
        chain_id=chain_id,
        proof=proof,
        explorer_url=explorer_url,
        reason=reason,
    )
