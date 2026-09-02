"""
app/routers/anchor.py
---------------------
Anchoring and on-chain verification endpoints.

Phase B1: stubs.
Phase B5: real anchor orchestration + two-stage verify (local hash + chain proof).

Endpoints:
  POST /cases/:case_id/anchor               -> AnchorTriggerResponse  (202)
  GET  /anchors/:batch_id                   -> AnchorBatchStatusResponse
  GET  /anchors/:batch_id/verify?hash=      -> AnchorVerifyResponse

Anchoring flow (for all teams):
  1. POST /cases/:id/anchor   -> returns 202 + batch_id immediately.
  2. Frontend polls GET /anchors/:batch_id until status == "confirmed".
  3. On confirmation, ANCHORED custody events appear in the graph.

Verification flow (two-stage):
  Stage 1 (local): re-hash the stored file, compare to DB sha256.
    - Mismatch = tamper detected locally. Returns valid=false immediately.
    - No chain call needed for local tampering.
  Stage 2 (chain): Merkle proof against on-chain root via Blockchain Service.
    - Proves the *record* was not altered (not just the file).
  Both stages must pass for valid=true.

IMPORTANT for Blockchain team:
  This router calls your service at:
    POST {BLOCKCHAIN_SERVICE_URL}/anchor/submit
    GET  {BLOCKCHAIN_SERVICE_URL}/anchor/:batchId
    GET  {BLOCKCHAIN_SERVICE_URL}/anchor/verify?hash=&batchId=
  See app/services/blockchain_client.py for the exact request/response shapes.
"""

from fastapi import APIRouter, Depends
from app.schemas.anchor import AnchorTriggerResponse, AnchorBatchStatusResponse, AnchorVerifyResponse
from app.services.rbac import get_current_user

router = APIRouter()


@router.post(
    "/cases/{case_id}/anchor",
    response_model=AnchorTriggerResponse,
    status_code=202,
    summary="Trigger Merkle batch anchoring for a case",
    tags=["Cases", "Anchor"],
)
def trigger_anchor(case_id: str, current_user=Depends(get_current_user)):
    """
    Collects all unanchored document SHA-256 hashes for the case,
    submits them to the Blockchain Service for Merkle batching,
    and returns immediately with a batch_id (202 Accepted).

    The batch is processed asynchronously. Poll GET /anchors/:batch_id
    for confirmation. On confirmation, ANCHORED events appear in the graph.

    [STUB - Phase B1]
    """
    return AnchorTriggerResponse(
        batch_id="mock-batch-stub-001",
        status="pending",
        hashes_submitted=4,
    )


@router.get(
    "/anchors/{batch_id}",
    response_model=AnchorBatchStatusResponse,
    summary="Get the status of an anchor batch",
)
def get_anchor_batch(batch_id: str, current_user=Depends(get_current_user)):
    """
    Polls the status of a previously triggered anchor batch.
    Status values: pending | confirmed | failed

    On confirmed: merkle_root, tx_hash, block_number are populated.

    [STUB - Phase B1]
    """
    return AnchorBatchStatusResponse(
        batch_id=batch_id,
        status="confirmed",
        merkle_root="0x" + "a" * 64,
        tx_hash="0x" + "b" * 64,
        block_number=12345678,
        chain_id="80002",
        confirmed_at="2026-09-02T15:00:00Z",
    )


@router.get(
    "/anchors/{batch_id}/verify",
    response_model=AnchorVerifyResponse,
    summary="Verify a document hash against the on-chain anchor",
)
def verify_anchor(
    batch_id: str,
    hash: str,
    current_user=Depends(get_current_user),
):
    """
    Two-stage tamper verification for a document.

    Query params:
      - hash: SHA-256 of the document to verify (the document.sha256 value).

    Stage 1 (local): re-hashes the stored file, compares to DB sha256.
    Stage 2 (chain): verifies Merkle proof against the on-chain root.

    A VERIFIED custody event is recorded with result=pass or result=fail.
    This event appears in the graph as a green (pass) or red (fail) node.

    [STUB - Phase B1] Always returns valid=true.
    """
    return AnchorVerifyResponse(
        valid=True,
        local_hash_match=True,
        chain_valid=True,
        merkle_root="0x" + "a" * 64,
        tx_hash="0x" + "b" * 64,
        block_number=12345678,
        chain_id="80002",
        proof=["0x" + "c" * 64, "0x" + "d" * 64],
        explorer_url=f"https://www.oklink.com/amoy/tx/0x{'b' * 64}",
        reason=None,
    )
