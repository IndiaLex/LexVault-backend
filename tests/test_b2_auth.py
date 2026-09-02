"""
tests/test_b2_auth.py
---------------------
Comprehensive test suite for Phase B2 (Authentication & RBAC).

Tests:
  1. Login success for all 5 seeded roles (officer, supervisor, forensic, auditor, admin).
  2. Login failure on wrong password -> 401.
  3. Login failure on non-existent username -> 401.
  4. /auth/me returns the correct user profile for each authenticated role.
  5. /auth/me rejects missing Authorization header -> 401.
  6. /auth/me rejects malformed / invalid JWT -> 401.
  7. /auth/me rejects tampered JWT signature -> 401.
  8. /auth/me rejects expired JWT -> 401.
  9. require_role passes for matching role.
  10. require_role raises 403 Forbidden for non-matching role.
"""

from datetime import timedelta
import pytest
import httpx
from fastapi import HTTPException
from app.services.rbac import create_access_token, require_role
from app.models.user import User
from contracts.enums import Role

BASE = "http://localhost:8000"

DEMO_ACCOUNTS = [
    ("demo_officer", "password123", Role.OFFICER.value, "Inspector Sharma"),
    ("demo_supervisor", "password123", Role.SUPERVISOR.value, "SP Gupta"),
    ("demo_forensic", "password123", Role.FORENSIC.value, "Dr. Mehta"),
    ("demo_auditor", "password123", Role.AUDITOR.value, "Auditor Patel"),
    ("demo_admin", "password123", Role.ADMIN.value, "Admin"),
]


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE, timeout=10) as c:
        yield c


# ---------------------------------------------------------------------------
# 1. Login Tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("username,password,expected_role,expected_name", DEMO_ACCOUNTS)
def test_login_success_all_roles(client, username, password, expected_role, expected_name):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, f"Login failed for {username}: {r.text}"
    body = r.json()
    assert "access_token" in body
    assert len(body["access_token"]) > 20
    assert body["token_type"] == "bearer"
    assert body["role"] == expected_role
    assert body["name"] == expected_name
    assert "user_id" in body
    assert len(body["user_id"]) == 36  # UUID length


def test_login_wrong_password(client):
    r = client.post("/auth/login", json={"username": "demo_officer", "password": "wrongpassword!"})
    assert r.status_code == 401
    assert "Incorrect username or password" in r.json().get("detail", "")


def test_login_nonexistent_user(client):
    r = client.post("/auth/login", json={"username": "ghost_officer_999", "password": "password123"})
    assert r.status_code == 401
    assert "Incorrect username or password" in r.json().get("detail", "")


# ---------------------------------------------------------------------------
# 2. /auth/me Profile Verification
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("username,password,expected_role,expected_name", DEMO_ACCOUNTS)
def test_me_returns_profile_all_roles(client, username, password, expected_role, expected_name):
    login_resp = client.post("/auth/login", json={"username": username, "password": password})
    token = login_resp.json()["access_token"]

    r = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == username
    assert body["role"] == expected_role
    assert body["name"] == expected_name
    assert "created_at" in body
    assert "id" in body


def test_me_unauthorized_missing_token(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_me_unauthorized_invalid_token(client):
    r = client.get("/auth/me", headers={"Authorization": "Bearer not-a-valid-jwt-token"})
    assert r.status_code == 401


def test_me_unauthorized_tampered_token(client):
    # Obtain a genuine token
    login_resp = client.post("/auth/login", json={"username": "demo_officer", "password": "password123"})
    token = login_resp.json()["access_token"]
    # Tamper with the payload section of the JWT
    parts = token.split(".")
    tampered = parts[0] + "." + parts[1][:-2] + "xx." + parts[2]
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {tampered}"})
    assert r.status_code == 401


def test_me_unauthorized_expired_token(client):
    # Fetch demo officer ID
    login_resp = client.post("/auth/login", json={"username": "demo_officer", "password": "password123"})
    user_id = login_resp.json()["user_id"]

    # Generate an expired token
    expired_token = create_access_token(
        data={"sub": user_id, "username": "demo_officer", "role": "officer", "name": "Inspector Sharma"},
        expires_delta=timedelta(seconds=-60),
    )
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# 3. RBAC Dependency Unit Tests
# ---------------------------------------------------------------------------

def test_require_role_allows_authorized():
    user = User(id="uid-1", username="officer1", role=Role.OFFICER.value, name="Officer One")
    checker = require_role(Role.OFFICER.value, Role.SUPERVISOR.value)
    result = checker(current_user=user)
    assert result == user


def test_require_role_forbids_unauthorized():
    user = User(id="uid-2", username="auditor1", role=Role.AUDITOR.value, name="Auditor One")
    checker = require_role(Role.ADMIN.value, Role.SUPERVISOR.value)
    with pytest.raises(HTTPException) as exc_info:
        checker(current_user=user)
    assert exc_info.value.status_code == 403
    assert "Access forbidden" in exc_info.value.detail
