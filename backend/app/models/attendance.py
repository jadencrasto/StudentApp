import uuid
from datetime import datetime, date
from sqlalchemy import String, Integer, Date, DateTime, Time, ForeignKey, Enum, Text, UniqueConstraint, Uuid, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
import enum


class Subject(Base):
    __tablename__ = "subjects"

    id:            Mapped[uuid.UUID]   = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:       Mapped[uuid.UUID]   = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name:          Mapped[str]         = mapped_column(String(255), nullable=False)
    code:          Mapped[str | None]  = mapped_column(String(50))
    total_classes: Mapped[int]         = mapped_column(Integer, default=0)
    created_at:    Mapped[datetime]    = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationships
    user             = relationship("User", back_populates="subjects")
    attendance_records = relationship("AttendanceRecord", back_populates="subject", cascade="all, delete-orphan")
    timetable_entries = relationship("TimetableEntry", back_populates="subject", cascade="all, delete-orphan")


class AttendanceStatus(str, enum.Enum):
    present = "present"
    absent  = "absent"
    late    = "late"
    excused = "excused"


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id:           Mapped[uuid.UUID]         = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:      Mapped[uuid.UUID]         = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subject_id:   Mapped[uuid.UUID]         = mapped_column(Uuid(as_uuid=True), ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False, index=True)
    class_date:   Mapped[date]              = mapped_column(Date, nullable=False, index=True)
    status:            Mapped[AttendanceStatus]  = mapped_column(Enum(AttendanceStatus, name="attendancestatus", native_enum=True), nullable=False)
    class_start_time:  Mapped[str | None]        = mapped_column(String(10))          # "HH:MM" slot identifier
    marked_at:         Mapped[datetime | None]   = mapped_column(DateTime(timezone=True))  # when student clicked
    notes:             Mapped[str | None]        = mapped_column(String(500))
    notification_sent: Mapped[bool]              = mapped_column(Boolean, default=False)
    notification_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at:        Mapped[datetime]          = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    __table_args__ = (
        # Include class_start_time so same subject appearing twice on the same day
        # creates two independent rows instead of colliding.
        UniqueConstraint("user_id", "subject_id", "class_date", "class_start_time", name="uq_attendance_per_slot"),
    )

    # Relationships
    user    = relationship("User")
    subject = relationship("Subject", back_populates="attendance_records")
