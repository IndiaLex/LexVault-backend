from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql://securedocx:securedocx@localhost:5432/securedocx"

    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "securedocx"
    MINIO_SECURE: bool = False

    JWT_SECRET: str = "change-me-in-production"
    JWT_EXPIRE_MINUTES: int = 60

    AI_SERVICE_URL: str = "http://localhost:8001"
    BLOCKCHAIN_SERVICE_URL: str = "http://localhost:3000"

    MOCK_AI_SERVICE: bool = True
    MOCK_BLOCKCHAIN_SERVICE: bool = True

    MAX_UPLOAD_SIZE_MB: int = 50
    ALLOWED_MIME_TYPES: str = "application/pdf,image/jpeg,image/png,image/tiff"
    RATE_LIMIT_ENABLED: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024

    @property
    def allowed_mime_types_list(self) -> List[str]:
        return [t.strip() for t in self.ALLOWED_MIME_TYPES.split(",")]


settings = Settings()
