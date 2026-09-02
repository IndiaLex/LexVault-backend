"""
app/routers/auth.py
-------------------
Authentication endpoints.

Phase B1: stubs — endpoints return placeholder data.
Phase B2: real JWT issue, DB lookup, bcrypt verification.

Endpoints:
  POST /auth/login   -> LoginResponse
  GET  /auth/me      -> UserResponse
"""

from fastapi import APIRouter, Depends
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse
from app.services.rbac import get_current_user

router = APIRouter()


@router.post("/login", response_model=LoginResponse, summary="Login and receive a JWT token")
def login(body: LoginRequest):
    """
    Accepts username + password.
    Returns a JWT bearer token, the user role, and display name.

    Frontend: store access_token in memory (not localStorage — XSS risk).
    Include as: Authorization: Bearer <token> on every subsequent request.

    [STUB - Phase B1] Returns hardcoded demo token.
    """
    return LoginResponse(
        access_token="stub-jwt-token",
        token_type="bearer",
        role="officer",
        name="Stub User",
        user_id="00000000-0000-0000-0000-000000000001",
    )


@router.get("/me", response_model=UserResponse, summary="Get the current authenticated user")
def me(current_user=Depends(get_current_user)):
    """
    Returns the currently authenticated user profile.
    Requires a valid Bearer token in the Authorization header.

    [STUB - Phase B1] Returns mock user from the rbac stub.
    """
    from datetime import datetime, timezone
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        name=current_user.name,
        role=current_user.role,
        created_at=datetime.now(timezone.utc),
    )
