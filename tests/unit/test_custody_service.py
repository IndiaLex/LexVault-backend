import hashlib
from app.services.custody_service import compute_event_hash


def test_compute_event_hash():
    hash1 = compute_event_hash(
        case_id="case-1",
        document_id="doc-1",
        event_type="UPLOADED",
        actor_id="user-1",
        metadata={"filename": "test.pdf"},
    )
    assert len(hash1) == 64

    hash2 = compute_event_hash(
        case_id="case-1",
        document_id="doc-1",
        event_type="UPLOADED",
        actor_id="user-1",
        metadata={"filename": "test.pdf"},
    )
    assert hash1 == hash2

    hash3 = compute_event_hash(
        case_id="case-1",
        document_id="doc-1",
        event_type="DOWNLOADED",
        actor_id="user-1",
        metadata={"filename": "test.pdf"},
    )
    assert hash1 != hash3


def test_compute_event_hash_deterministic():
    args = {
        "case_id": "case-123",
        "document_id": "doc-456",
        "event_type": "ANCHORED",
        "actor_id": "user-789",
        "metadata": {"batch_id": "batch-001"},
    }
    h1 = compute_event_hash(**args)
    h2 = compute_event_hash(**args)
    assert h1 == h2
