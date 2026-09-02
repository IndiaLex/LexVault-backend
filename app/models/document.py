import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class Document(Base):
    __tablename__ = "documents"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    storage_key = Column(String(500), nullable=False)
    sha256 = Column(String(64), nullable=False, index=True)
    mime = Column(String(100), nullable=False)
    size = Column(Integer, nullable=False)
    uploaded_by = Column(String(36), ForeignKey("users.id"), nullable=False)
    uploaded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    current_version = Column(Integer, nullable=False, default=1)

    case = relationship("Case", back_populates="documents")
    uploader = relationship("User", back_populates="documents_uploaded")
    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    ai_analysis = relationship("AIAnalysis", back_populates="document", uselist=False, cascade="all, delete-orphan")
    custody_events = relationship("CustodyEvent", back_populates="document")
