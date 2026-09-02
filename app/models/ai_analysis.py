import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Integer, Boolean, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(String(36), ForeignKey("documents.id"), unique=True, nullable=False)
    ocr_text = Column(String(100000), nullable=True)
    entities = Column(JSON, nullable=True)
    redaction_boxes = Column(JSON, nullable=True)
    doc_class = Column(String(50), nullable=True)
    confidence = Column(String(10), nullable=True)
    needs_review = Column(Boolean, default=False)
    review_count = Column(Integer, default=0)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    document = relationship("Document", back_populates="ai_analysis")
