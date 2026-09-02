"""
app/services/blockchain_client.py
----------------------------------
Client for the Blockchain Service.

When MOCK_BLOCKCHAIN_SERVICE=true (default), returns hardcoded responses
that match the contract exactly. This lets Backend Core be fully developed
before the Blockchain team has their service running.

When MOCK_BLOCKCHAIN_SERVICE=false, calls the real Blockchain Service.

Blockchain team contract reference: contracts/entities.py:
  - AnchorSubmitRequest, AnchorBatchResponse, AnchorStatusResponse, AnchorVerifyResponse

Endpoints consumed:
  POST /anchor/submit      { hashes[] }      -> { batchId, status, chain_id }
  GET  /anchor/:batchId                      -> { batchId, status, merkle_root, tx_hash, block_number }
  GET  /anchor/verify      ?hash=&batchId=   -> { valid, merkle_root, tx_hash, proof[], explorer_url }
  POST /custody/record     { docHash, eventHash } -> { tx_hash, status }
"""

import uuid
import hashlib
import httpx
from typing import List, Optional

from app.config import settings
from contracts.entities import (
    AnchorSubmitRequest,
    AnchorBatchResponse,
    AnchorStatusResponse,
    AnchorVerifyResponse,
)

# Polygon Amoy block explorer base URL
AMOY_EXPLORER = "https://www.oklink.com/amoy/tx"


# ---------------------------------------------------------------------------
# Mock responses — match the contract exactly
# ---------------------------------------------------------------------------

def _mock_batch_id() -> str:
    return f"mock-batch-{str(uuid.uuid4())[:8]}"


def _mock_submit(hashes: List[str]) -> dict:
    batch_id = _mock_batch_id()
    return {
        "batch_id": batch_id,
        "status": "pending",
        "chain_id": "80002",
    }


def _mock_batch_status(batch_id: str) -> dict:
    mock_tx = "0x" + hashlib.sha256(batch_id.encode()).hexdigest()
    return {
        "batch_id": batch_id,
        "status": "confirmed",
        "merkle_root": "0x" + hashlib.sha256(b"mock-root").hexdigest(),
        "tx_hash": mock_tx,
        "block_number": 12345678,
        "chain_id": "80002",
    }


def _mock_verify(hash_value: str, batch_id: str) -> dict:
    mock_tx = "0x" + hashlib.sha256(batch_id.encode()).hexdigest()
    return {
        "valid": True,
        "merkle_root": "0x" + hashlib.sha256(b"mock-root").hexdigest(),
        "tx_hash": mock_tx,
        "proof": [
            "0x" + hashlib.sha256(b"proof-0").hexdigest(),
            "0x" + hashlib.sha256(b"proof-1").hexdigest(),
        ],
        "explorer_url": f"{AMOY_EXPLORER}/{mock_tx}",
    }


def _mock_custody_record(doc_hash: str, event_hash: str) -> dict:
    mock_tx = "0x" + hashlib.sha256(f"{doc_hash}{event_hash}".encode()).hexdigest()
    return {"tx_hash": mock_tx, "status": "confirmed"}


# ---------------------------------------------------------------------------
# Real client calls
# ---------------------------------------------------------------------------

async def _real_submit(hashes: List[str]) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.BLOCKCHAIN_SERVICE_URL}/anchor/submit",
            json={"hashes": hashes},
        )
        resp.raise_for_status()
        return resp.json()


async def _real_batch_status(batch_id: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{settings.BLOCKCHAIN_SERVICE_URL}/anchor/{batch_id}")
        resp.raise_for_status()
        return resp.json()


async def _real_verify(hash_value: str, batch_id: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{settings.BLOCKCHAIN_SERVICE_URL}/anchor/verify",
            params={"hash": hash_value, "batchId": batch_id},
        )
        resp.raise_for_status()
        return resp.json()


async def _real_custody_record(doc_hash: str, event_hash: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{settings.BLOCKCHAIN_SERVICE_URL}/custody/record",
            json={"docHash": doc_hash, "eventHash": event_hash},
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# Public interface — the only functions the rest of the app calls
# ---------------------------------------------------------------------------

async def submit_hashes(hashes: List[str]) -> Optional[dict]:
    """
    Submit a list of SHA-256 hashes to the Blockchain Service for batching.

    Returns immediately with a batch_id. The batch is processed asynchronously.
    Poll get_batch_status() until status == "confirmed".

    Args:
        hashes: List of hex SHA-256 strings (document sha256 values).
    """
    if settings.MOCK_BLOCKCHAIN_SERVICE:
        return _mock_submit(hashes)
    try:
        return await _real_submit(hashes)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        print(f"[blockchain_client] ERROR submitting hashes: {exc}")
        return None


async def get_batch_status(batch_id: str) -> Optional[dict]:
    """
    Poll the status of a previously submitted batch.

    Returns dict with: batch_id, status, merkle_root, tx_hash, block_number.
    """
    if settings.MOCK_BLOCKCHAIN_SERVICE:
        return _mock_batch_status(batch_id)
    try:
        return await _real_batch_status(batch_id)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        print(f"[blockchain_client] ERROR getting batch status: {exc}")
        return None


async def verify_hash(hash_value: str, batch_id: str) -> Optional[dict]:
    """
    Verify that a hash is included in an anchored batch via Merkle proof.

    Returns dict with: valid, merkle_root, tx_hash, proof[], explorer_url.
    Note: this only proves the *record* was not altered. The local hash
    comparison (file re-hash vs DB sha256) must be done separately in
    the verify router.
    """
    if settings.MOCK_BLOCKCHAIN_SERVICE:
        return _mock_verify(hash_value, batch_id)
    try:
        return await _real_verify(hash_value, batch_id)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        print(f"[blockchain_client] ERROR verifying hash: {exc}")
        return None


async def record_custody_event(doc_hash: str, event_hash: str) -> Optional[dict]:
    """
    Record an individual custody event on the CustodyLedger contract.

    Used for high-value events (transfers, forensic access) that warrant
    their own on-chain record rather than just batch inclusion.

    Args:
        doc_hash: SHA-256 of the document (identifies the document on-chain).
        event_hash: SHA-256 of the canonical event (from compute_event_hash).
    """
    if settings.MOCK_BLOCKCHAIN_SERVICE:
        return _mock_custody_record(doc_hash, event_hash)
    try:
        return await _real_custody_record(doc_hash, event_hash)
    except (httpx.HTTPError, httpx.TimeoutException) as exc:
        print(f"[blockchain_client] ERROR recording custody event: {exc}")
        return None
