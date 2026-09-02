"""
app/services/rbac.py
--------------------
Role-Based Access Control — FastAPI dependency injectors.

Phase B1: stub only — get_current_user returns a mock user so all
          endpoints can be tested without a real JWT.
Phase B2: full implementation with real JWT decode and DB lookup.

Usage in routers:
    from app.services.rbac import get_current_user, require_role
    from contracts.enums import Role

    @router.get("/cases")
    def list_cases(current_user = Depends(get_current_user)):
        ...

    @router.post("/cases/:id/anchor")
    def anchor(current_user = Depends(require_role(Role.OFFICER, Role.ADMIN))):
        ...
"""

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from app.models.user import User

# OAuth2 scheme — token extracted from Authorization: Bearer <token>
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


# ---------------------------------------------------------------------------
# Phase B1 STUB: returns a mock user — replace fully in Phase B2
# ---------------------------------------------------------------------------

def get_current_user(token: str = Depends(oauth2_scheme)) -> User:
    """
    [STUB — Phase B1]
    Returns a mock User object so all endpoints work without a real JWT.
    Full JWT decode + DB lookup implemented in Phase B2.
    """
    mock_user = User(
        id="00000000-0000-0000-0000-000000000001",
        username="stub_user",
        password_hash="",
        name="Stub User",
        role="officer",
    )
    return mock_user


def require_role(*allowed_roles: str):
    """
    [STUB — Phase B1]
    Returns a dependency that checks the current user has one of the allowed roles.
    Full enforcement implemented in Phase B2.
    """
    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        # In B1 stub mode, all roles pass through.
        return current_user
    return _dependency
