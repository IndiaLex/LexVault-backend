import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class CustodyEvent(Base):
    __tablename__ = "custody_events"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    case_id = Column(String(36), ForeignKey("cases.id"), nullable=False, index=True)
    document_id = Column(String(36), ForeignKey("documents.id"), nullable=True, index=True)
    type = Column(String(30), nullable=False)
    actor_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    event_metadata = Column("metadata", JSON, nullable=True)
    event_hash = Column(String(64), nullable=False)
    anchor_batch_id = Column(String(36), ForeignKey("anchor_batches.id"), nullable=True)

    case = relationship("Case", back_populates="custody_events")
    document = relationship("Document", back_populates="custody_events")
    actor = relationship("User", back_populates="custody_events")
    anchor_batch = relationship("AnchorBatch", back_populates="custody_events")
