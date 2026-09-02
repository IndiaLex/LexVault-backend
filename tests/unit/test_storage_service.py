import hashlib
from app.services.storage_service import StorageService


def test_compute_sha256():
    data = b"hello world"
    expected = hashlib.sha256(data).hexdigest()
    assert StorageService.compute_sha256(data) == expected


def test_compute_sha256_empty():
    data = b""
    expected = hashlib.sha256(data).hexdigest()
    assert StorageService.compute_sha256(data) == expected


def test_compute_sha256_deterministic():
    data = b"some test data for sha256"
    h1 = StorageService.compute_sha256(data)
    h2 = StorageService.compute_sha256(data)
    assert h1 == h2
