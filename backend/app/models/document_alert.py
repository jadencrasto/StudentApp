import uuid
from datetime import datetime, date
from sqlalchemy import String, Text, DateTime, ForeignKey, Date, Boolean, Enum, Uuid, JSON, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


# ─── Document ────────────────────────────────────────────────

class ExtractionStatus(str, enum.Enum):
    pending    = "pending"
    processing = "processing"
    done       = "done"
    failed     = "failed"


class Document(Base):
    __tablename__ = "documents"

    id:                 Mapped[uuid.UUID]         = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:            Mapped[uuid.UUID]         = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    original_filename:  Mapped[str | None]        = mapped_column(String(500))
    file_type:          Mapped[str | None]        = mapped_column(String(50))   # pdf, image, txt
    file_path:          Mapped[str | None]        = mapped_column(Text)
    storage_path:       Mapped[str | None]        = mapped_column(String(600), nullable=True)
    storage_bucket:     Mapped[str | None]        = mapped_column(String(100), nullable=True)
    raw_text:           Mapped[str | None]        = mapped_column(Text)         # full extracted text
    extracted_data:     Mapped[dict]              = mapped_column(JSON, default=dict)
    # e.g. {"subject": "Physics", "deadline": "2025-03-10",
    #        "task_type": "assignment", "title": "Wave Optics HW"}

    extraction_status:  Mapped[ExtractionStatus]  = mapped_column(Enum(ExtractionStatus), default=ExtractionStatus.pending)
    extraction_error:   Mapped[str | None]        = mapped_column(Text)

    created_at:         Mapped[datetime]          = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="documents")


# ─── Alert ───────────────────────────────────────────────────

class AlertType(str, enum.Enum):
    overload           = "overload"          # 3+ deadlines in 7 days
    attendance_low     = "attendance_low"    # attendance < 75%
    activity_conflict  = "activity_conflict" # activity clashes with deadline
    deadline_soon      = "deadline_soon"     # deadline within 24h
    custom             = "custom"


class AlertSeverity(str, enum.Enum):
    info     = "info"
    warning  = "warning"
    critical = "critical"


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (
        Index("ix_alerts_user_unread", "user_id", "is_read", "created_at"),
    )

    id:         Mapped[uuid.UUID]    = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:    Mapped[uuid.UUID]    = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    alert_type: Mapped[AlertType]    = mapped_column(Enum(AlertType), nullable=False, index=True)
    severity:   Mapped[AlertSeverity] = mapped_column(Enum(AlertSeverity), default=AlertSeverity.warning)
    title:      Mapped[str]          = mapped_column(String(500), nullable=False)
    message:    Mapped[str]          = mapped_column(Text, nullable=False)
    is_read:    Mapped[bool]         = mapped_column(Boolean, default=False, index=True)
    expires_at: Mapped[date | None]  = mapped_column(Date)

    # Optional FK links
    related_assignment_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("assignments.id", ondelete="SET NULL"), nullable=True)
    related_activity_id:   Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("activities.id",  ondelete="SET NULL"), nullable=True)
    related_subject_id:    Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("subjects.id",    ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    user       = relationship("User", back_populates="alerts")
    assignment = relationship("Assignment", back_populates="alerts", foreign_keys=[related_assignment_id])
    activity   = relationship("Activity",   back_populates="alerts", foreign_keys=[related_activity_id])
