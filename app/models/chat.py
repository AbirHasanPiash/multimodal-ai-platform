import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, ForeignKey, DateTime, Integer, Numeric, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.core.database import Base

def utc_now():
    return datetime.now(timezone.utc)

class Chat(Base):
    __tablename__ = "chats"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    title = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")
    user = relationship("User", back_populates="chats")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    chat_id = Column(UUID(as_uuid=True), ForeignKey("chats.id"), nullable=False)
    
    role = Column(String, nullable=False)
    content = Column(Text, nullable=False)
    attachments = Column(JSON, default=list)
    model = Column(String, nullable=True)
    
    tokens = Column(Integer, default=0)
    cost = Column(Numeric(18, 6), default=0.000000)
    created_at = Column(DateTime(timezone=True), default=utc_now)
    
    chat = relationship("Chat", back_populates="messages")

    __table_args__ = (
        Index('ix_messages_chat_id_created_at', 'chat_id', 'created_at'),
    )