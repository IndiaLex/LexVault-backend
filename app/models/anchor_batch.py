import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from contracts.enums import AnchorBatchStatus


class AnchorBatch(Base):
    __tablename__ = "anchor_batches"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    merkle_root = Column(String(64), nullable=True)
    tx_hash = Column(String(66), nullable=True)
    chain_id = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default=AnchorBatchStatus.PENDING.value)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    custody_events = relationship("CustodyEvent", back_populates="anchor_batch")
