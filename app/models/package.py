import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, Numeric, Text
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Package(Base):
    __tablename__ = "packages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    
    # Package Details
    name = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    
    # Economics
    price = Column(Numeric(10, 2), nullable=False)
    currency = Column(String, default="USD")
    credits = Column(Numeric(18, 6), nullable=False)

    # Metadata
    is_active = Column(Boolean, default=True)
    is_featured = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
    transactions = relationship("Transaction", back_populates="package")