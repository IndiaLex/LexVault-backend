"""
app/routers/cases.py
--------------------
Case CRUD endpoints — Phase B3: real DB operations.

Endpoints:
  POST /cases          -> CaseResponse (201)
  GET  /cases          -> List[CaseResponse]
  GET  /cases/:id      -> CaseResponse (404 if not found)

RBAC:
  All authenticated users can create and view cases.
  Granular role-based filtering (officer sees own cases only) is Phase B6.

Custody events:
  No CASE_OPENED enum exists in contracts/enums.py (shared contract — cannot
  be modified unilaterally). Custody trail starts with the first UPLOADED
  document event. Case creation is a plain DB insert.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from app.database import get_db
from app.models.case import Case
from app.models.user import User
from app.schemas.case import CaseCreate, CaseResponse
from app.services.rbac import get_current_user, require_role
from contracts.enums import CaseStatus, Role

router = APIRouter()


@router.post(
    "",
    response_model=CaseResponse,
    status_code=201,
    summary="Create a new case",
)
def create_case(
    body: CaseCreate,
    current_user: User = Depends(require_role(Role.OFFICER.value, Role.SUPERVISOR.value, Role.ADMIN.value)),
    db: Session = Depends(get_db),
):
    """
    Creates a new case. The requesting user becomes the case creator.

    Any authenticated role can create a case.
    Returns the persisted Case record with a real UUID.
    """
    case = Case(
        title=body.title,
        status=CaseStatus.OPEN.value,
        created_by=current_user.id,
    )
    db.add(case)
    db.commit()
    db.refresh(case)

    return CaseResponse(
        id=str(case.id),
        title=case.title,
        status=case.status,
        created_by=str(case.created_by),
        creator_name=current_user.name,
        created_at=case.created_at,
    )


@router.get(
    "",
    response_model=List[CaseResponse],
    summary="List all accessible cases",
)
def list_cases(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns all cases visible to the current user.

    Phase B3: all authenticated users see all cases.
    Phase B6: officer sees own cases, supervisor sees department cases,
              auditor/admin see all.
    """
    cases = db.query(Case).order_by(Case.created_at.desc()).all()

    result = []
    for c in cases:
        creator_name = c.creator.name if c.creator else None
        result.append(
            CaseResponse(
                id=str(c.id),
                title=c.title,
                status=c.status,
                created_by=str(c.created_by),
                creator_name=creator_name,
                created_at=c.created_at,
            )
        )
    return result


@router.get(
    "/{case_id}",
    response_model=CaseResponse,
    summary="Get a single case by ID",
)
def get_case(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns full case detail.

    Raises 404 if the case does not exist.
    """
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    creator_name = case.creator.name if case.creator else None

    return CaseResponse(
        id=str(case.id),
        title=case.title,
        status=case.status,
        created_by=str(case.created_by),
        creator_name=creator_name,
        created_at=case.created_at,
    )
