"""
app/routers/cases.py
--------------------
Case CRUD endpoints.

Phase B1: stubs.
Phase B3: real DB operations + RBAC + custody event recording.

Endpoints:
  POST /cases          -> CaseResponse
  GET  /cases          -> List[CaseResponse]
  GET  /cases/:id      -> CaseResponse
"""

from fastapi import APIRouter, Depends
from typing import List
from datetime import datetime, timezone

from app.schemas.case import CaseCreate, CaseResponse
from app.services.rbac import get_current_user

router = APIRouter()


@router.post("", response_model=CaseResponse, status_code=201, summary="Create a new case")
def create_case(body: CaseCreate, current_user=Depends(get_current_user)):
    """
    Creates a new case and returns its record.
    The requesting officer becomes the case creator.

    [STUB - Phase B1]
    """
    return CaseResponse(
        id="case-stub-001",
        title=body.title,
        status="open",
        created_by=current_user.id,
        creator_name=current_user.name,
        created_at=datetime.now(timezone.utc),
    )


@router.get("", response_model=List[CaseResponse], summary="List all accessible cases")
def list_cases(current_user=Depends(get_current_user)):
    """
    Returns cases visible to the current user based on role:
    - officer: own cases only
    - supervisor: department cases
    - auditor / admin: all cases

    [STUB - Phase B1]
    """
    return [
        CaseResponse(
            id="case-stub-001",
            title="FIR-2026-0417 - Stub Case",
            status="open",
            created_by=current_user.id,
            creator_name=current_user.name,
            created_at=datetime.now(timezone.utc),
        )
    ]


@router.get("/{case_id}", response_model=CaseResponse, summary="Get a single case by ID")
def get_case(case_id: str, current_user=Depends(get_current_user)):
    """
    Returns full case detail including status and creator.

    [STUB - Phase B1]
    """
    return CaseResponse(
        id=case_id,
        title="FIR-2026-0417 - Stub Case",
        status="open",
        created_by=current_user.id,
        creator_name=current_user.name,
        created_at=datetime.now(timezone.utc),
    )
