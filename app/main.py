"""
app/main.py
-----------
FastAPI application entry point for IndiaLex Backend Core.

Startup sequence:
  1. Create all DB tables (idempotent via create_all).
  2. Warm up MinIO connection and ensure the bucket exists.
  3. Register all routers with their URL prefixes.

Health endpoint (/health) reports live status of:
  - DB connectivity
  - MinIO / object storage
  - Mock flag states (so other teams can see what is wired vs. mocked)
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.config import settings
from app.database import create_all, get_engine
from app.routers import auth, cases, documents, custody, anchor


# ---------------------------------------------------------------------------
# Lifespan: runs once at startup and shutdown
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    # 1. Ensure all DB tables exist (safe to run on every boot).
    create_all()

    # 2. Warm up MinIO - creates the bucket if it does not exist.
    #    Failures are non-fatal so the service still boots when MinIO is
    #    briefly unavailable (e.g., during docker-compose ordering).
    try:
        from app.services.storage_service import get_storage_service
        get_storage_service()
    except Exception as exc:
        print(f"[startup] WARNING: MinIO not reachable - {exc}")

    yield  # app is running

    # Shutdown: nothing to clean up.


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------

app = FastAPI(
    title="IndiaLex - Backend Core",
    description=(
        "Document Management System for IndiaLex (SIH 2026).\n\n"
        "**Talks to:**\n"
        "- Frontend (serves REST)\n"
        "- Backend AI (calls /ai/process)\n"
        "- Blockchain Service (calls /anchor/submit, /anchor/verify, /custody/record)\n\n"
        "**Mock flags** (flip via .env as other services come online):\n"
        "- MOCK_AI_SERVICE=true/false\n"
        "- MOCK_BLOCKCHAIN_SERVICE=true/false"
    ),
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

# CORS: permissive for the hackathon; restrict origins in production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth.router,      prefix="/auth",      tags=["Auth"])
app.include_router(cases.router,     prefix="/cases",     tags=["Cases"])
app.include_router(documents.router,                      tags=["Documents"])
app.include_router(custody.router,                        tags=["Custody"])
app.include_router(anchor.router,                         tags=["Anchor"])


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------

@app.get("/health", tags=["Health"], summary="Service liveness check")
def health():
    """
    Returns the live status of all dependencies.

    Other service teams should call this endpoint to confirm Backend Core
    is ready before running integration tests.

    Response fields:
    - status: ok if all dependencies healthy, degraded otherwise.
    - db: ok or error string.
    - storage: ok or error string.
    - mock_ai: whether the AI service is mocked.
    - mock_blockchain: whether the Blockchain service is mocked.
    """
    # Database check
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception as exc:
        db_status = f"error: {exc}"

    # Storage check
    try:
        from app.services.storage_service import get_storage_service
        get_storage_service()
        storage_status = "ok"
    except Exception as exc:
        storage_status = f"error: {exc}"

    all_ok = db_status == "ok" and storage_status == "ok"

    return {
        "status": "ok" if all_ok else "degraded",
        "db": db_status,
        "storage": storage_status,
        "mock_ai": settings.MOCK_AI_SERVICE,
        "mock_blockchain": settings.MOCK_BLOCKCHAIN_SERVICE,
    }
