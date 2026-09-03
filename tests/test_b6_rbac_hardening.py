"""
tests/test_b6_rbac_hardening.py
-------------------------------
Phase B6 integration tests: Full RBAC enforcement, ACCESS_DENIED custody events,
rate limiting (429), and input validation / hardening.

Requirements verified:
  1. RBAC on Case Creation (POST /cases):
     - officer, supervisor, admin -> 201
     - forensic, auditor -> 403
  2. RBAC on Document Upload (POST /cases/:id/documents):
     - officer, forensic, supervisor, admin -> 201
     - auditor -> 403 + ACCESS_DENIED event recorded in case custody trail
  3. RBAC on Case Anchoring (POST /cases/:id/anchor):
     - officer, supervisor, admin -> 202
     - forensic, auditor -> 403 + ACCESS_DENIED event recorded in case custody trail
  4. Input Validation & Hardening:
     - Short title (< 3 chars) -> 422
     - Invalid hash length on verify -> 422
     - Disallowed MIME type -> 400
  5. Rate Limiting:
     - Exceeding 10 uploads/min triggers 429 Too Many Requests with Retry-After header
     - Exceeding 30 verifies/min triggers 429 Too Many Requests with Retry-After header

All tests run against the live local service (http://localhost:8000).
"""

import io
import uuid
import pytest
import httpx
from app.services.rate_limiter import upload_rate_limiter, verify_rate_limiter

BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Auth fixtures for all 5 roles
# ---------------------------------------------------------------------------

def get_token(username: str) -> str:
    resp = httpx.post(f"{BASE_URL}/auth/login", json={"username": username, "password": "password123"})
    assert resp.status_code == 200, f"Login failed for {username}: {resp.text}"
    return resp.json()["access_token"]


@pytest.fixture(scope="module")
def officer_headers():
    return {"Authorization": f"Bearer {get_token('demo_officer')}"}


@pytest.fixture(scope="module")
def supervisor_headers():
    return {"Authorization": f"Bearer {get_token('demo_supervisor')}"}


@pytest.fixture(scope="module")
def forensic_headers():
    return {"Authorization": f"Bearer {get_token('demo_forensic')}"}


@pytest.fixture(scope="module")
def auditor_headers():
    return {"Authorization": f"Bearer {get_token('demo_auditor')}"}


@pytest.fixture(scope="module")
def admin_headers():
    return {"Authorization": f"Bearer {get_token('demo_admin')}"}


@pytest.fixture(autouse=True)
def reset_rate_limiters():
    """Reset rate limit state before each test to prevent cross-test interference."""
    upload_rate_limiter.reset()
    verify_rate_limiter.reset()


# ---------------------------------------------------------------------------
# 1. RBAC: Case Creation
# ---------------------------------------------------------------------------

class TestRBACCaseCreation:

    def test_officer_can_create_case(self, officer_headers):
        r = httpx.post(f"{BASE_URL}/cases", json={"title": "Officer Case B6"}, headers=officer_headers)
        assert r.status_code == 201

    def test_supervisor_can_create_case(self, supervisor_headers):
        r = httpx.post(f"{BASE_URL}/cases", json={"title": "Supervisor Case B6"}, headers=supervisor_headers)
        assert r.status_code == 201

    def test_admin_can_create_case(self, admin_headers):
        r = httpx.post(f"{BASE_URL}/cases", json={"title": "Admin Case B6"}, headers=admin_headers)
        assert r.status_code == 201

    def test_auditor_cannot_create_case(self, auditor_headers):
        r = httpx.post(f"{BASE_URL}/cases", json={"title": "Auditor Case B6"}, headers=auditor_headers)
        assert r.status_code == 403
        assert "forbidden" in r.json()["detail"].lower()

    def test_forensic_cannot_create_case(self, forensic_headers):
        r = httpx.post(f"{BASE_URL}/cases", json={"title": "Forensic Case B6"}, headers=forensic_headers)
        assert r.status_code == 403
        assert "forbidden" in r.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 2. RBAC: Document Upload & ACCESS_DENIED Logging
# ---------------------------------------------------------------------------

class TestRBACDocumentUpload:

    def test_allowed_roles_can_upload(self, officer_headers, forensic_headers, supervisor_headers, admin_headers):
        # Create case with officer
        r_case = httpx.post(f"{BASE_URL}/cases", json={"title": "Upload Permissions Case"}, headers=officer_headers)
        assert r_case.status_code == 201
        case_id = r_case.json()["id"]

        for headers, role_name in [
            (officer_headers, "officer"),
            (forensic_headers, "forensic"),
            (supervisor_headers, "supervisor"),
            (admin_headers, "admin"),
        ]:
            r_up = httpx.post(
                f"{BASE_URL}/cases/{case_id}/documents",
                headers=headers,
                files={"file": (f"{role_name}.pdf", io.BytesIO(f"%PDF-1.4 {role_name} {uuid.uuid4()}".encode()), "application/pdf")},
            )
            assert r_up.status_code == 201, f"{role_name} failed to upload: {r_up.text}"

    def test_auditor_cannot_upload_and_logs_access_denied(self, officer_headers, auditor_headers):
        # Create case with officer
        r_case = httpx.post(f"{BASE_URL}/cases", json={"title": "Auditor Denied Upload Case"}, headers=officer_headers)
        assert r_case.status_code == 201
        case_id = r_case.json()["id"]

        # Auditor attempts upload -> 403
        r_up = httpx.post(
            f"{BASE_URL}/cases/{case_id}/documents",
            headers=auditor_headers,
            files={"file": ("auditor_leak.pdf", io.BytesIO(b"%PDF-1.4 unauthorized"), "application/pdf")},
        )
        assert r_up.status_code == 403

        # Verify ACCESS_DENIED custody event was recorded
        r_log = httpx.get(
            f"{BASE_URL}/cases/{case_id}/custody-log",
            params={"type": "ACCESS_DENIED"},
            headers=officer_headers,
        )
        assert r_log.status_code == 200
        events = r_log.json()["events"]
        assert len(events) >= 1
        assert events[0]["type"] == "ACCESS_DENIED"
        assert events[0]["actor"] == "Auditor Patel"


# ---------------------------------------------------------------------------
# 3. RBAC: Anchoring & ACCESS_DENIED Logging
# ---------------------------------------------------------------------------

class TestRBACAnchor:

    def test_allowed_roles_can_anchor(self, officer_headers, supervisor_headers, admin_headers):
        for headers in [officer_headers, supervisor_headers, admin_headers]:
            r_case = httpx.post(f"{BASE_URL}/cases", json={"title": f"Anchor Case {uuid.uuid4()}"}, headers=headers)
            assert r_case.status_code == 201
            case_id = r_case.json()["id"]

            r_up = httpx.post(
                f"{BASE_URL}/cases/{case_id}/documents",
                headers=headers,
                files={"file": ("doc.pdf", io.BytesIO(f"%PDF-1.4 {uuid.uuid4()}".encode()), "application/pdf")},
            )
            assert r_up.status_code == 201

            r_anc = httpx.post(f"{BASE_URL}/cases/{case_id}/anchor", headers=headers)
            assert r_anc.status_code == 202

    def test_forensic_and_auditor_cannot_anchor_and_logs_access_denied(self, officer_headers, forensic_headers, auditor_headers):
        r_case = httpx.post(f"{BASE_URL}/cases", json={"title": "Denied Anchor Case"}, headers=officer_headers)
        assert r_case.status_code == 201
        case_id = r_case.json()["id"]

        for headers in [forensic_headers, auditor_headers]:
            r_anc = httpx.post(f"{BASE_URL}/cases/{case_id}/anchor", headers=headers)
            assert r_anc.status_code == 403

        # Verify 2 ACCESS_DENIED events in custody log
        r_log = httpx.get(
            f"{BASE_URL}/cases/{case_id}/custody-log",
            params={"type": "ACCESS_DENIED"},
            headers=officer_headers,
        )
        assert r_log.status_code == 200
        assert r_log.json()["total"] == 2


# ---------------------------------------------------------------------------
# 4. Input Validation & Hardening
# ---------------------------------------------------------------------------

class TestInputValidation:

    def test_short_case_title_fails(self, officer_headers):
        r = httpx.post(f"{BASE_URL}/cases", json={"title": "AB"}, headers=officer_headers)
        assert r.status_code == 422  # pydantic min_length validation

    def test_invalid_verify_hash_length(self, officer_headers):
        fake_batch = str(uuid.uuid4())
        r = httpx.get(
            f"{BASE_URL}/anchors/{fake_batch}/verify",
            params={"hash": "too_short_hash"},
            headers=officer_headers,
        )
        assert r.status_code == 422  # min_length=64 validation

    def test_disallowed_mime_fails(self, officer_headers):
        r_case = httpx.post(f"{BASE_URL}/cases", json={"title": "MIME test case"}, headers=officer_headers)
        case_id = r_case.json()["id"]

        r_up = httpx.post(
            f"{BASE_URL}/cases/{case_id}/documents",
            headers=officer_headers,
            files={"file": ("script.sh", io.BytesIO(b"#!/bin/bash echo bad"), "application/x-sh")},
        )
        assert r_up.status_code == 400
        assert "not allowed" in r_up.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 5. Rate Limiting (429 Too Many Requests)
# ---------------------------------------------------------------------------

class TestRateLimiting:

    def test_upload_rate_limit_exceeded(self, supervisor_headers):
        r_case = httpx.post(f"{BASE_URL}/cases", json={"title": "Rate Limit Case"}, headers=supervisor_headers)
        assert r_case.status_code == 201
        case_id = r_case.json()["id"]

        # Limit is 10 uploads/min. Send requests until 429 is triggered:
        got_429 = False
        for i in range(12):
            r = httpx.post(
                f"{BASE_URL}/cases/{case_id}/documents",
                headers=supervisor_headers,
                files={"file": (f"f_{i}.pdf", io.BytesIO(f"%PDF-1.4 {i} {uuid.uuid4()}".encode()), "application/pdf")},
            )
            if r.status_code == 429:
                got_429 = True
                assert "rate limit exceeded" in r.json()["detail"].lower()
                assert "retry-after" in r.headers
                break
            assert r.status_code == 201

        assert got_429, "Expected 429 rate limit to be triggered within 12 requests"

    def test_verify_rate_limit_exceeded(self, supervisor_headers):
        fake_batch = str(uuid.uuid4())
        fake_hash = "a" * 64

        # Limit is 30 verifies/min. Send requests until 429 is triggered:
        got_429 = False
        for _ in range(35):
            r = httpx.get(
                f"{BASE_URL}/anchors/{fake_batch}/verify",
                params={"hash": fake_hash},
                headers=supervisor_headers,
            )
            if r.status_code == 429:
                got_429 = True
                assert "rate limit exceeded" in r.json()["detail"].lower()
                assert "retry-after" in r.headers
                break

        assert got_429, "Expected 429 rate limit to be triggered within 35 requests"
