import uuid
from datetime import datetime, date
from sqlalchemy import String, Text, Date, DateTime, ForeignKey, Enum, Uuid, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class TaskType(str, enum.Enum):
    assignment   = "assignment"
    exam         = "exam"
    quiz         = "quiz"
    project      = "project"
    announcement = "announcement"
    other        = "other"


class Priority(str, enum.Enum):
    low    = "low"
    medium = "medium"
    high   = "high"


class AssignmentStatus(str, enum.Enum):
    pending     = "pending"
    in_progress = "in_progress"
    completed   = "completed"
    overdue     = "overdue"
class Assignment(Base):
    __tablename__ = "assignments"

    id:                  Mapped[uuid.UUID]      = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:             Mapped[uuid.UUID]      = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title:               Mapped[str]            = mapped_column(String(500), nullable=False)
    subject:             Mapped[str | None]     = mapped_column(String(255))
    task_type:           Mapped[str]            = mapped_column(String(50), default=TaskType.assignment.value)
    description:         Mapped[str | None]     = mapped_column(Text)
    deadline:            Mapped[date | None]    = mapped_column(Date, index=True)
    priority:            Mapped[str]            = mapped_column(String(50), default=Priority.medium.value)
    status:              Mapped[str]            = mapped_column(String(50), default=AssignmentStatus.pending.value, index=True)
    ai_metadata:         Mapped[dict | None]    = mapped_column(JSON)

    source_document_id:  Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    classroom_id:        Mapped[str | None]     = mapped_column(String(255), nullable=True, index=True)

    created_at:          Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at:          Mapped[datetime]       = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user     = relationship("User", back_populates="assignments")
    document = relationship("Document", foreign_keys=[source_document_id])
    alerts   = relationship("Alert", back_populates="assignment", foreign_keys="Alert.related_assignment_id")
