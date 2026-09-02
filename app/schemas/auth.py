"""
app/schemas/auth.py
-------------------
Pydantic schemas for authentication endpoints.

Used by:
  - Frontend team: POST /auth/login request/response shapes.
  - Backend Core: JWT payload structure.
"""

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str
    user_id: str


class UserResponse(BaseModel):
    id: str
    username: str
    name: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True


class TokenData(BaseModel):
    """Internal: decoded JWT payload."""
    user_id: str
    username: str
    role: str
