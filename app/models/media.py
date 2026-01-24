import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, ForeignKey, Text, DateTime, Numeric
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class GeneratedAudio(Base):
    __tablename__ = "generated_audio"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Core Metadata
    storage_path = Column(String, nullable=False)
    public_url = Column(String, nullable=False)
    cost = Column(Numeric(18, 6), nullable=False, default=0.0)
    text_prompt = Column(Text, nullable=False)
    voice_name = Column(String, nullable=True)
    provider = Column(String, default="google")
    source_message_id = Column(UUID(as_uuid=True), ForeignKey("messages.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)

    # Relationships
    user = relationship("User", back_populates="audios")


class GeneratedImage(Base):
    __tablename__ = "generated_images"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    storage_path = Column(String, nullable=False) # Path in R2
    public_url = Column(String, nullable=False)   # Public R2 URL
    prompt = Column(Text, nullable=False)
    reference_image_url = Column(String, nullable=True)
    revised_prompt = Column(Text, nullable=True)
    
    # Model & Cost
    model = Column(String, default="gpt-image-1.5")
    size = Column(String, default="1024x1024")
    quality = Column(String, default="standard")
    cost = Column(Numeric(18, 6), nullable=False, default=0.0)
    
    created_at = Column(DateTime(timezone=True), default=utc_now)

    # Relationships
    user = relationship("User", back_populates="images")



class GeneratedVideo(Base):
    __tablename__ = "generated_videos"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    
    # Assets
    storage_path = Column(String, nullable=False)
    public_url = Column(String, nullable=False)
    thumbnail_url = Column(String, nullable=True)
    
    # Inputs
    script_text = Column(Text, nullable=False)
    source_audio_url = Column(String, nullable=False)
    avatar_image_url = Column(String, nullable=False)

    # Config
    provider = Column(String, default="d-id")
    model = Column(String, default="talks")
    external_job_id = Column(String, nullable=True)
    
    # Economics & Status
    cost = Column(Numeric(18, 6), nullable=False, default=0.0)
    status = Column(String, default="processing")
    error_message = Column(Text, nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=utc_now)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    user = relationship("User", back_populates="videos")