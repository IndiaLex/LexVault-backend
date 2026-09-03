"""
tests/test_b5_anchor.py
-----------------------
Phase B5 integration tests: Anchor trigger, batch status, and verify.

Requirements verified:
  POST /cases/:id/anchor
    - 202 with batch_id, status="pending", hashes_submitted >= 1
    - 404 for unknown case
    - Unauthenticated returns 401
    - ANCHORED events appear in custody log after triggering

  GET /anchors/:batch_id
    - 200 with batch_id, status, and fields populated
    - 404 for unknown batch_id
    - Unauthenticated returns 401

  GET /anchors/:batch_id/verify?hash=
    - 200 with valid, local_hash_match, chain_valid, explorer_url
    - local_hash_match=True for un-tampered file
    - valid=True when both stages pass
    - VERIFIED custody event appears in custody log
    - 404 for unknown batch_id
    - 404 when hash does not match any document
    - Unauthenticated returns 401

All tests run against the live local service (http://localhost:8000).
Server must be running: python -m uvicorn app.main:app --port 8000
MOCK_BLOCKCHAIN_SERVICE=True (default) — blockchain is mocked locally.
"""

import io
import uuid
import pytest
import httpx

BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Auth fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def auth_headers():
    resp = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"username": "demo_officer", "password": "password123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Bypass-Rate-Limit": "true"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_case(auth_headers, title="B5 Test Case") -> str:
    resp = httpx.post(f"{BASE_URL}/cases", json={"title": title}, headers=auth_headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def upload_doc(auth_headers, case_id: str, content: bytes = None, filename="b5_test.pdf") -> dict:
    data = content or f"%PDF-1.4 B5 anchor test content {uuid.uuid4()}".encode()
    resp = httpx.post(
        f"{BASE_URL}/cases/{case_id}/documents",
        headers=auth_headers,
        files={"file": (filename, io.BytesIO(data), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def trigger_anchor(auth_headers, case_id: str) -> dict:
    resp = httpx.post(f"{BASE_URL}/cases/{case_id}/anchor", headers=auth_headers)
    assert resp.status_code == 202, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# Trigger anchor tests
# ---------------------------------------------------------------------------

class TestTriggerAnchor:

    def test_trigger_anchor_success(self, auth_headers):
        """POST /cases/:id/anchor returns 202, batch_id, hashes_submitted >= 1."""
        case_id = create_case(auth_headers, "B5 Trigger Anchor")
        upload_doc(auth_headers, case_id)

        resp = httpx.post(f"{BASE_URL}/cases/{case_id}/anchor", headers=auth_headers)
        assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"
        body = resp.json()

        assert "batch_id" in body
        assert "status" in body
        assert "hashes_submitted" in body
        assert body["hashes_submitted"] >= 1
        assert body["status"] in ("pending", "confirmed")

        # batch_id must be a valid UUID
        uuid.UUID(body["batch_id"])

    def test_trigger_anchor_records_anchored_events(self, auth_headers):
        """After anchoring, custody log must contain ANCHORED events."""
        case_id = create_case(auth_headers, "B5 Anchor Events Check")
        upload_doc(auth_headers, case_id)
        trigger_anchor(auth_headers, case_id)

        resp = httpx.get(
            f"{BASE_URL}/cases/{case_id}/custody-log",
            params={"type": "ANCHORED"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1, "No ANCHORED custody events found after anchoring"
        for event in body["events"]:
            assert event["type"] == "ANCHORED"

    def test_trigger_anchor_already_anchored_docs(self, auth_headers):
        """Anchoring a case twice returns hashes_submitted=0 on second call."""
        case_id = create_case(auth_headers, "B5 Already Anchored")
        upload_doc(auth_headers, case_id)
        trigger_anchor(auth_headers, case_id)

        # Second anchor call
        resp = httpx.post(f"{BASE_URL}/cases/{case_id}/anchor", headers=auth_headers)
        assert resp.status_code == 202
        body = resp.json()
        assert body["hashes_submitted"] == 0, (
            f"Expected 0 hashes_submitted on re-anchor, got {body['hashes_submitted']}"
        )

    def test_trigger_anchor_404_unknown_case(self, auth_headers):
        """POST /cases/fake/anchor -> 404."""
        fake_id = str(uuid.uuid4())
        resp = httpx.post(f"{BASE_URL}/cases/{fake_id}/anchor", headers=auth_headers)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_trigger_anchor_unauthenticated(self):
        """POST /cases/:id/anchor without token -> 401."""
        resp = httpx.post(f"{BASE_URL}/cases/{str(uuid.uuid4())}/anchor")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Get anchor batch status tests
# ---------------------------------------------------------------------------

class TestGetAnchorBatch:

    def test_get_batch_status_success(self, auth_headers):
        """GET /anchors/:batch_id returns 200 with status and batch_id."""
        case_id = create_case(auth_headers, "B5 Get Batch")
        upload_doc(auth_headers, case_id)
        anchor_resp = trigger_anchor(auth_headers, case_id)
        batch_id = anchor_resp["batch_id"]

        resp = httpx.get(f"{BASE_URL}/anchors/{batch_id}", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()

        assert body["batch_id"] == batch_id
        assert body["status"] in ("pending", "confirmed", "failed")
        assert "merkle_root" in body
        assert "tx_hash" in body

    def test_get_batch_schema(self, auth_headers):
        """Batch status response must have all expected schema fields."""
        case_id = create_case(auth_headers, "B5 Batch Schema")
        upload_doc(auth_headers, case_id)
        anchor_resp = trigger_anchor(auth_headers, case_id)
        batch_id = anchor_resp["batch_id"]

        resp = httpx.get(f"{BASE_URL}/anchors/{batch_id}", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()

        # Required schema fields
        assert "batch_id" in body
        assert "status" in body
        # Optional fields present with correct types when not None
        if body["merkle_root"] is not None:
            assert body["merkle_root"].startswith("0x")
        if body["tx_hash"] is not None:
            assert body["tx_hash"].startswith("0x")

    def test_get_batch_404_unknown(self, auth_headers):
        """GET /anchors/fake-id -> 404."""
        fake_id = str(uuid.uuid4())
        resp = httpx.get(f"{BASE_URL}/anchors/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_get_batch_unauthenticated(self):
        """GET /anchors/:id without token -> 401."""
        resp = httpx.get(f"{BASE_URL}/anchors/{str(uuid.uuid4())}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Verify anchor tests
# ---------------------------------------------------------------------------

class TestVerifyAnchor:

    def test_verify_anchor_valid(self, auth_headers):
        """GET /anchors/:id/verify?hash= passes for un-tampered file."""
        case_id = create_case(auth_headers, "B5 Verify Valid")
        doc_resp = upload_doc(auth_headers, case_id)
        doc_sha256 = doc_resp["sha256"]

        anchor_resp = trigger_anchor(auth_headers, case_id)
        batch_id = anchor_resp["batch_id"]

        resp = httpx.get(
            f"{BASE_URL}/anchors/{batch_id}/verify",
            params={"hash": doc_sha256},
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()

        assert "valid" in body
        assert "local_hash_match" in body
        assert body["local_hash_match"] is True
        assert body["valid"] is True

    def test_verify_anchor_schema(self, auth_headers):
        """Verify response has all required schema fields."""
        case_id = create_case(auth_headers, "B5 Verify Schema")
        doc_resp = upload_doc(auth_headers, case_id)
        anchor_resp = trigger_anchor(auth_headers, case_id)
        batch_id = anchor_resp["batch_id"]

        resp = httpx.get(
            f"{BASE_URL}/anchors/{batch_id}/verify",
            params={"hash": doc_resp["sha256"]},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()

        assert "valid" in body
        assert "local_hash_match" in body
        assert "chain_valid" in body
        assert "proof" in body
        assert isinstance(body["proof"], list)
        assert "explorer_url" in body
        # Explorer URL must be a real URL when valid
        if body["valid"] and body["explorer_url"]:
            assert body["explorer_url"].startswith("http")

    def test_verify_anchor_records_verified_event(self, auth_headers):
        """VERIFIED custody event must appear in custody log after verify call."""
        case_id = create_case(auth_headers, "B5 Verify Event")
        doc_resp = upload_doc(auth_headers, case_id)
        anchor_resp = trigger_anchor(auth_headers, case_id)
        batch_id = anchor_resp["batch_id"]

        httpx.get(
            f"{BASE_URL}/anchors/{batch_id}/verify",
            params={"hash": doc_resp["sha256"]},
            headers=auth_headers,
        )

        log_resp = httpx.get(
            f"{BASE_URL}/cases/{case_id}/custody-log",
            params={"type": "VERIFIED"},
            headers=auth_headers,
        )
        assert log_resp.status_code == 200
        log_body = log_resp.json()
        assert log_body["total"] >= 1, "No VERIFIED custody event found after verify call"
        for event in log_body["events"]:
            assert event["type"] == "VERIFIED"

    def test_verify_anchor_404_unknown_batch(self, auth_headers):
        """GET /anchors/fake/verify?hash= -> 404 (batch not found)."""
        fake_batch_id = str(uuid.uuid4())
        resp = httpx.get(
            f"{BASE_URL}/anchors/{fake_batch_id}/verify",
            params={"hash": "a" * 64},
            headers=auth_headers,
        )
        assert resp.status_code == 404

    def test_verify_anchor_404_unknown_hash(self, auth_headers):
        """GET /anchors/:id/verify?hash=unknown -> 404 (document not found)."""
        case_id = create_case(auth_headers, "B5 Verify Unknown Hash")
        upload_doc(auth_headers, case_id)
        anchor_resp = trigger_anchor(auth_headers, case_id)
        batch_id = anchor_resp["batch_id"]

        resp = httpx.get(
            f"{BASE_URL}/anchors/{batch_id}/verify",
            params={"hash": "f" * 64},  # random hash not in DB
            headers=auth_headers,
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_verify_anchor_unauthenticated(self):
        """GET /anchors/:id/verify without token -> 401."""
        resp = httpx.get(
            f"{BASE_URL}/anchors/{str(uuid.uuid4())}/verify",
            params={"hash": "a" * 64},
        )
        assert resp.status_code == 401
