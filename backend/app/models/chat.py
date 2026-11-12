"""
Chat conversation model — stores chat messages between student and AI.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, Uuid, Integer, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ChatConversation(Base):
    """A conversation thread (e.g. general Q&A or viva on a specific document)."""
    __tablename__ = "chat_conversations"

    id:          Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:     Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title:       Mapped[str]       = mapped_column(String(500), default="New Chat")
    mode:        Mapped[str]       = mapped_column(String(50), default="general")  # "general" | "viva"
    document_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    is_active:   Mapped[bool]      = mapped_column(Boolean, default=True)
    created_at:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at:  Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user     = relationship("User", backref="chat_conversations")
    document = relationship("Document", backref="chat_conversations")
    messages = relationship("ChatMessage", back_populates="conversation", order_by="ChatMessage.created_at", cascade="all, delete-orphan")


class ChatMessage(Base):
    """Individual message in a conversation."""
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_conv_created", "conversation_id", "created_at"),
    )

    id:              Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("chat_conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    role:            Mapped[str]       = mapped_column(String(20), nullable=False)  # "user" | "assistant"
    content:         Mapped[str]       = mapped_column(Text, nullable=False)
    created_at:      Mapped[datetime]  = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    conversation = relationship("ChatConversation", back_populates="messages")
