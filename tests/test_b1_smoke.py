"""
tests/test_b1_smoke.py
----------------------
Phase B1 smoke tests — verifies every endpoint is registered, responds
with the correct HTTP status code, and returns the correct schema shape.

These tests run against the LIVE stack (Docker or local uvicorn).
They do NOT need a DB connection — they just hit the HTTP layer.

Run:
    pytest tests/test_b1_smoke.py -v

Expected: all 14 tests PASS before moving to Phase B2.
"""

import pytest
import httpx

BASE = "http://localhost:8000"


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=10) as c:
        yield c


@pytest.fixture(scope="module")
def auth_client():
    with httpx.Client(base_url=BASE, timeout=10) as c:
        r = c.post("/auth/login", json={"username": "demo_officer", "password": "password123"})
        assert r.status_code == 200
        token = r.json()["access_token"]
        c.headers["Authorization"] = f"Bearer {token}"
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert "status" in body
    assert "db" in body
    assert "storage" in body
    assert "mock_ai" in body
    assert "mock_blockchain" in body


def test_docs_accessible(client):
    r = client.get("/docs")
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

def test_login_returns_token(client):
    r = client.post("/auth/login", json={"username": "demo_officer", "password": "password123"})
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body
    assert "role" in body
    assert "name" in body
    assert "user_id" in body


def test_me_returns_user(auth_client):
    r = auth_client.get("/auth/me")
    assert r.status_code == 200
    body = r.json()
    assert "id" in body
    assert body["role"] == "officer"
    assert body["username"] == "demo_officer"


# ---------------------------------------------------------------------------
# Cases
# ---------------------------------------------------------------------------

def test_create_case(auth_client):
    r = auth_client.post("/cases", json={"title": "Test Case B1"})
    assert r.status_code == 201
    body = r.json()
    assert "id" in body
    assert "title" in body
    assert "status" in body


def test_list_cases(auth_client):
    r = auth_client.get("/cases")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_get_case(auth_client):
    r = auth_client.get("/cases/case-stub-001")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "case-stub-001"


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def test_upload_document(auth_client):
    r = auth_client.post(
        "/cases/case-stub-001/documents",
        files={"file": ("test.pdf", b"%PDF-1.4 test content", "application/pdf")},
    )
    assert r.status_code == 201
    body = r.json()
    assert "document_id" in body
    assert "status" in body
    assert body["status"] == "processing"


def test_get_document(auth_client):
    r = auth_client.get("/documents/doc-stub-001")
    assert r.status_code == 200
    body = r.json()
    assert "id" in body
    assert "filename" in body
    assert "sha256" in body


def test_download_document(auth_client):
    r = auth_client.get("/documents/doc-stub-001/download")
    assert r.status_code == 200
    body = r.json()
    assert "presigned_url" in body
    assert "expires_in_minutes" in body


# ---------------------------------------------------------------------------
# Custody / Graph
# ---------------------------------------------------------------------------

def test_get_graph(auth_client):
    r = auth_client.get("/cases/case-stub-001/graph")
    assert r.status_code == 200
    body = r.json()
    assert "nodes" in body
    assert "edges" in body
    assert len(body["nodes"]) > 0
    # Every node must have required fields
    for node in body["nodes"]:
        assert "id" in node
        assert "lane" in node
        assert "type" in node
        assert "hash" in node
        assert "anchored" in node


def test_get_custody_log(auth_client):
    r = auth_client.get("/cases/case-stub-001/custody-log")
    assert r.status_code == 200
    body = r.json()
    assert "events" in body
    assert "total" in body


# ---------------------------------------------------------------------------
# Anchor
# ---------------------------------------------------------------------------

def test_trigger_anchor(auth_client):
    r = auth_client.post("/cases/case-stub-001/anchor")
    assert r.status_code == 202
    body = r.json()
    assert "batch_id" in body
    assert "status" in body
    assert body["status"] == "pending"


def test_get_anchor_batch(auth_client):
    r = auth_client.get("/anchors/mock-batch-stub-001")
    assert r.status_code == 200
    body = r.json()
    assert "batch_id" in body
    assert "status" in body


def test_verify_anchor(auth_client):
    r = auth_client.get("/anchors/mock-batch-stub-001/verify", params={"hash": "a" * 64})
    assert r.status_code == 200
    body = r.json()
    assert "valid" in body
    assert "local_hash_match" in body
    assert "explorer_url" in body

