"""
app/schemas/anchor.py
---------------------
Pydantic schemas for the anchor and verify endpoints.

IMPORTANT for Blockchain team:
  These schemas exactly mirror what the Blockchain Service must return.
  See contracts/entities.py for AnchorSubmitRequest / AnchorBatchResponse.

IMPORTANT for Frontend team:
  POST /cases/:id/anchor returns 202 + AnchorTriggerResponse.
  Poll GET /anchors/:batchId until status == "confirmed".
  Then use GET /anchors/:batchId/verify?hash=<sha256> for tamper check.
  AnchorVerifyResponse.explorer_url is the Polygon Amoy block explorer link
  - clicking it during the demo is what makes blockchain feel real.
"""

from pydantic import BaseModel
from typing import Optional, List


class AnchorTriggerResponse(BaseModel):
    """Returned immediately from POST /cases/:id/anchor (202 Accepted)."""
    batch_id: str
    status: str = "pending"
    hashes_submitted: int


class AnchorBatchStatusResponse(BaseModel):
    """Returned from GET /anchors/:batchId."""
    batch_id: str
    status: str                         # pending | confirmed | failed
    merkle_root: Optional[str] = None
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    chain_id: Optional[str] = None
    confirmed_at: Optional[str] = None


class AnchorVerifyResponse(BaseModel):
    """
    Returned from GET /anchors/:batchId/verify?hash=<sha256>.

    Two-stage check:
      1. local_hash_match: re-hashes the stored file and compares to DB record.
         False means the file was tampered with locally (no chain call needed).
      2. chain_valid: Merkle proof verified against on-chain root.
         False means the recorded hash was altered in the DB.
      Both must be True for overall valid=True.
    """
    valid: bool
    local_hash_match: bool
    chain_valid: Optional[bool] = None   # None if local check already failed
    merkle_root: Optional[str] = None
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None
    chain_id: Optional[str] = None
    proof: List[str] = []
    explorer_url: Optional[str] = None
    reason: Optional[str] = None         # "hash_mismatch" | "proof_invalid" | None
