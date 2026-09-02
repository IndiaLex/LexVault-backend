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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, UserResponse
from app.services.rbac import (
    get_current_user,
    verify_password,
    create_access_token,
)

router = APIRouter()


@router.post("/login", response_model=LoginResponse, summary="Login and receive a JWT token")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    """
    Authenticates a user with username and password against the database.
    Verifies bcrypt password hash and returns a signed JWT access token.

    Include the token in subsequent requests as:
        Authorization: Bearer <access_token>
    """
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "username": user.username,
            "role": user.role,
            "name": user.name,
        }
    )

    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        role=user.role,
        name=user.name,
        user_id=str(user.id),
    )


@router.get("/me", response_model=UserResponse, summary="Get the current authenticated user")
def me(current_user: User = Depends(get_current_user)):
    """
    Returns the authenticated user's profile from the database.
    Requires a valid JWT Bearer token in the Authorization header.
    """
    return UserResponse(
        id=str(current_user.id),
        username=current_user.username,
        name=current_user.name,
        role=current_user.role,
        created_at=current_user.created_at,
    )

