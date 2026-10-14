import uuid
from datetime import datetime, date
from sqlalchemy import String, DateTime, ForeignKey, Date, Uuid, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ClassAttendanceRecord(Base):
    __tablename__ = "class_attendance_records"
    __table_args__ = (
        UniqueConstraint("cohort_id", "student_id", "class_date", "subject_name_normalized", name="uq_cohort_student_date_subject"),
        Index("ix_class_attendance_cohort_date", "cohort_id", "class_date"),
        Index("ix_class_attendance_student_cohort", "student_id", "cohort_id"),
    )

    id:                      Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id:          Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    cohort_id:               Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id:              Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    class_date:              Mapped[date]             = mapped_column(Date, nullable=False, index=True)
    subject_name:            Mapped[str]              = mapped_column(String(100), nullable=False)
    subject_name_normalized: Mapped[str]              = mapped_column(String(100), nullable=False)
    status:                  Mapped[str]              = mapped_column(String(20), nullable=False)  # "present" | "absent"
    marked_by:               Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at:              Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at:              Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    institution = relationship("Institution")
    cohort      = relationship("Cohort")
    student     = relationship("User", foreign_keys=[student_id])
    marker      = relationship("User", foreign_keys=[marked_by])
    change_logs = relationship("ClassAttendanceChangeLog", back_populates="record", cascade="all, delete-orphan", order_by="desc(ClassAttendanceChangeLog.changed_at)")


class ClassAttendanceChangeLog(Base):
    __tablename__ = "class_attendance_change_logs"

    id:              Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    record_id:       Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("class_attendance_records.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by:      Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    previous_status: Mapped[str]              = mapped_column(String(20), nullable=False)
    new_status:      Mapped[str]              = mapped_column(String(20), nullable=False)
    changed_at:      Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    reason:          Mapped[str | None]       = mapped_column(String(255), nullable=True)

    # Relationships
    record  = relationship("ClassAttendanceRecord", back_populates="change_logs")
    changer = relationship("User", foreign_keys=[changed_by])
