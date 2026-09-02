from app.services.storage_service import get_storage_service, StorageService
from app.services.custody_service import compute_event_hash, record_event, build_graph
from app.services.ai_client import process_document
from app.services.blockchain_client import (
    submit_hashes,
    get_batch_status,
    verify_hash,
    record_custody_event,
)
from app.services.rbac import (
    get_current_user,
    require_role,
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
)

__all__ = [
    # Storage
    "get_storage_service",
    "StorageService",
    # Custody
    "compute_event_hash",
    "record_event",
    "build_graph",
    # AI client
    "process_document",
    # Blockchain client
    "submit_hashes",
    "get_batch_status",
    "verify_hash",
    "record_custody_event",
    # RBAC & Auth
    "get_current_user",
    "require_role",
    "verify_password",
    "get_password_hash",
    "create_access_token",
    "decode_access_token",
]
