"""
app/schemas/case.py
-------------------
Pydantic schemas for Case endpoints.

Used by:
  - Frontend team: case list, case creation, case detail.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class CaseCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=500, description="Human-readable case title, e.g. FIR-2026-0417")


class CaseResponse(BaseModel):
    id: str
    title: str
    status: str
    created_by: str
    created_at: datetime
    creator_name: Optional[str] = None   # joined from User table

    class Config:
        from_attributes = True
