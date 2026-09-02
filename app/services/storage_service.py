import hashlib
from io import BytesIO
from datetime import timedelta
from minio import Minio
from minio.error import S3Error
from app.config import settings


class StorageService:
    def __init__(self):
        self.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(settings.MINIO_BUCKET):
            self.client.make_bucket(settings.MINIO_BUCKET)

    @staticmethod
    def compute_sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def upload_file(self, case_id: str, filename: str, data: bytes, sha256: str) -> str:
        storage_key = f"{case_id}/{sha256}_{filename}"
        data_stream = BytesIO(data)
        self.client.put_object(
            settings.MINIO_BUCKET,
            storage_key,
            data_stream,
            length=len(data),
            content_type="application/octet-stream",
        )
        return storage_key

    def download_file(self, storage_key: str) -> bytes:
        response = self.client.get_object(settings.MINIO_BUCKET, storage_key)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

    def get_presigned_url(self, storage_key: str, expiry_minutes: int = 15) -> str:
        return self.client.presigned_get_object(
            settings.MINIO_BUCKET,
            storage_key,
            expires=timedelta(minutes=expiry_minutes),
        )

    def file_exists(self, storage_key: str) -> bool:
        try:
            self.client.stat_object(settings.MINIO_BUCKET, storage_key)
            return True
        except S3Error:
            return False

    def delete_file(self, storage_key: str):
        try:
            self.client.remove_object(settings.MINIO_BUCKET, storage_key)
        except S3Error:
            pass

    def detect_tampering(self, storage_key: str, expected_sha256: str) -> dict:
        data = self.download_file(storage_key)
        current_hash = self.compute_sha256(data)
        is_tampered = current_hash != expected_sha256
        return {
            "is_tampered": is_tampered,
            "expected_hash": expected_sha256,
            "current_hash": current_hash,
        }


_storage_service = None


def get_storage_service() -> StorageService:
    global _storage_service
    if _storage_service is None:
        _storage_service = StorageService()
    return _storage_service
