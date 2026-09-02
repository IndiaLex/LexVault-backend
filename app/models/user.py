import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime
from sqlalchemy.orm import relationship
from app.database import Base
from contracts.enums import Role


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(200), nullable=False)
    role = Column(String(20), nullable=False, default=Role.OFFICER.value)
    wallet_address = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    cases = relationship("Case", back_populates="creator")
    documents_uploaded = relationship("Document", back_populates="uploader")
    custody_events = relationship("CustodyEvent", back_populates="actor")
