import enum


class CustodyEventType(str, enum.Enum):
    UPLOADED = "UPLOADED"
    OCR_COMPLETE = "OCR_COMPLETE"
    NER_COMPLETE = "NER_COMPLETE"
    REDACTED = "REDACTED"
    ANCHORED = "ANCHORED"
    VERIFIED = "VERIFIED"
    TRANSFERRED = "TRANSFERRED"
    ACCESSED = "ACCESSED"
    ACCESS_DENIED = "ACCESS_DENIED"
    DOWNLOADED = "DOWNLOADED"
    VERSION_CREATED = "VERSION_CREATED"


class Role(str, enum.Enum):
    OFFICER = "officer"
    SUPERVISOR = "supervisor"
    FORENSIC = "forensic"
    AUDITOR = "auditor"
    ADMIN = "admin"


class CaseStatus(str, enum.Enum):
    OPEN = "open"
    UNDER_INVESTIGATION = "under_investigation"
    PENDING_REVIEW = "pending_review"
    CLOSED = "closed"


class AnchorBatchStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"


class DocumentStatus(str, enum.Enum):
    ACTIVE = "active"
    TAMPERED = "tampered"
    ARCHIVED = "archived"
