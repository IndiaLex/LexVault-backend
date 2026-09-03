"""
tests/test_b3_cases_docs.py
---------------------------
Phase B3 integration tests: Cases CRUD + Document upload/metadata/download.

Requirements verified by this suite:
  - POST /cases       → 201, real UUID in DB, correct title/status/creator
  - GET  /cases       → 200, list contains the newly created case
  - GET  /cases/:id   → 200, correct fields from DB
  - GET  /cases/fake  → 404
  - POST /cases/:id/documents  → 201, real sha256, status="processing"
  - POST /cases/:id/documents  → 400 for bad MIME type
  - GET  /documents/:id        → 200, real DB fields
  - GET  /documents/fake       → 404
  - GET  /documents/:id/download → 200, presigned URL + expires_in_minutes=15
  - POST /cases/fake/documents → 404 (case not found)

All tests run against the live local service (http://localhost:8000).
Docker must be up: docker-compose up -d
"""

import io
import uuid
import pytest
import httpx

BASE_URL = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Shared auth fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def officer_token():
    """Authenticate as demo_officer and return a Bearer token."""
    resp = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"username": "demo_officer", "password": "password123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(officer_token):
    return {"Authorization": f"Bearer {officer_token}"}


# ---------------------------------------------------------------------------
# State shared across module-scoped tests (created case + document IDs)
# ---------------------------------------------------------------------------

created_case_id: str = ""
created_document_id: str = ""

# ---------------------------------------------------------------------------
# Cases tests
# ---------------------------------------------------------------------------

class TestCases:

    def test_create_case(self, auth_headers):
        """POST /cases — should create a real case in the DB and return 201."""
        global created_case_id
        resp = httpx.post(
            f"{BASE_URL}/cases",
            json={"title": "B3-TEST FIR-2026-9999 Integration Test Case"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        body = resp.json()

        # Must be a real UUID (not stub)
        parsed = uuid.UUID(body["id"])
        assert str(parsed) == body["id"], "id is not a valid UUID"

        assert body["title"] == "B3-TEST FIR-2026-9999 Integration Test Case"
        assert body["status"] == "open"
        assert "created_by" in body
        assert body["creator_name"] == "Inspector Sharma"
        assert "created_at" in body

        created_case_id = body["id"]

    def test_list_cases(self, auth_headers):
        """GET /cases — should return list containing the created case."""
        resp = httpx.get(f"{BASE_URL}/cases", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()

        assert isinstance(body, list)
        assert len(body) >= 1

        ids = [c["id"] for c in body]
        assert created_case_id in ids, f"Created case {created_case_id} not in list: {ids}"

    def test_get_case(self, auth_headers):
        """GET /cases/:id — should return real DB fields."""
        resp = httpx.get(f"{BASE_URL}/cases/{created_case_id}", headers=auth_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()

        assert body["id"] == created_case_id
        assert body["title"] == "B3-TEST FIR-2026-9999 Integration Test Case"
        assert body["status"] == "open"

    def test_get_case_not_found(self, auth_headers):
        """GET /cases/fake-id — should return 404."""
        fake_id = str(uuid.uuid4())
        resp = httpx.get(f"{BASE_URL}/cases/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        assert "not found" in resp.json()["detail"].lower()

    def test_unauthenticated_case_create(self):
        """POST /cases without token — should return 401."""
        resp = httpx.post(
            f"{BASE_URL}/cases",
            json={"title": "Should be rejected"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Document upload tests
# ---------------------------------------------------------------------------

class TestDocuments:

    def test_upload_document_success(self, auth_headers):
        """POST /cases/:id/documents — real PDF bytes, should return 201."""
        global created_document_id

        # Minimal valid PDF header (recognised as application/pdf)
        fake_pdf_bytes = b"%PDF-1.4\n%test content for securedocx B3 integration test\n"

        resp = httpx.post(
            f"{BASE_URL}/cases/{created_case_id}/documents",
            headers=auth_headers,
            files={"file": ("test_b3.pdf", io.BytesIO(fake_pdf_bytes), "application/pdf")},
        )
        assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
        body = resp.json()

        # document_id must be a real UUID
        parsed = uuid.UUID(body["document_id"])
        assert str(parsed) == body["document_id"], "document_id is not a valid UUID"

        assert body["filename"] == "test_b3.pdf"

        # sha256 must be 64 hex chars
        assert len(body["sha256"]) == 64
        assert all(c in "0123456789abcdef" for c in body["sha256"])

        assert body["size"] == len(fake_pdf_bytes)
        assert body["status"] == "processing"

        created_document_id = body["document_id"]

    def test_upload_document_bad_mime(self, auth_headers):
        """POST /cases/:id/documents with disallowed MIME — should return 400."""
        resp = httpx.post(
            f"{BASE_URL}/cases/{created_case_id}/documents",
            headers=auth_headers,
            files={"file": ("malware.exe", io.BytesIO(b"MZ bad file"), "application/octet-stream")},
        )
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        assert "not allowed" in resp.json()["detail"].lower()

    def test_upload_document_case_not_found(self, auth_headers):
        """POST /cases/fake/documents — should return 404."""
        fake_id = str(uuid.uuid4())
        resp = httpx.post(
            f"{BASE_URL}/cases/{fake_id}/documents",
            headers=auth_headers,
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        )
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"

    def test_get_document(self, auth_headers):
        """GET /documents/:id — should return real DB fields."""
        resp = httpx.get(
            f"{BASE_URL}/documents/{created_document_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()

        assert body["id"] == created_document_id
        assert body["case_id"] == created_case_id
        assert body["filename"] == "test_b3.pdf"
        assert len(body["sha256"]) == 64
        assert body["mime"] == "application/pdf"
        assert body["current_version"] == 1

    def test_get_document_not_found(self, auth_headers):
        """GET /documents/fake-id — should return 404."""
        fake_id = str(uuid.uuid4())
        resp = httpx.get(f"{BASE_URL}/documents/{fake_id}", headers=auth_headers)
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        assert "not found" in resp.json()["detail"].lower()

    def test_download_document(self, auth_headers):
        """GET /documents/:id/download — should return presigned URL."""
        resp = httpx.get(
            f"{BASE_URL}/documents/{created_document_id}/download",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()

        assert "presigned_url" in body
        assert body["presigned_url"].startswith("http")
        assert body["expires_in_minutes"] == 15

    def test_unauthenticated_document_upload(self):
        """POST /cases/:id/documents without token — should return 401."""
        resp = httpx.post(
            f"{BASE_URL}/cases/{created_case_id}/documents",
            files={"file": ("x.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        )
        assert resp.status_code == 401
