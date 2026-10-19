"""
Phase 6D — Admin-managed class marks model.

Tables:
  - exams: Belongs to ONE class (cohort). Has type, title, subject, max_marks, status (draft|published).
  - marks: Exact decimal marks obtained or absence flag for a student in an exam.
  - mark_change_records: Audit log for any mark edited after the exam was published.
"""
from __future__ import annotations

import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, DateTime, Date, Uuid, ForeignKey, Numeric,
    UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Exam(Base):
    __tablename__ = "exams"
    __table_args__ = (
        UniqueConstraint(
            "cohort_id", "exam_type", "subject_normalized", "title_normalized",
            name="uq_cohort_exam_type_subject_title"
        ),
        Index("ix_exams_cohort_status", "cohort_id", "status"),
        Index("ix_exams_institution", "institution_id"),
    )

    id:                 Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id:     Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    cohort_id:          Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_type:          Mapped[str]              = mapped_column(String(50), nullable=False, index=True)  # internals, mid-term, end-term, etc.
    title:              Mapped[str]              = mapped_column(String(150), nullable=False)            # e.g. "Test 1"
    title_normalized:   Mapped[str]              = mapped_column(String(150), nullable=False)
    subject:            Mapped[str]              = mapped_column(String(100), nullable=False)
    subject_normalized: Mapped[str]              = mapped_column(String(100), nullable=False)
    max_marks:          Mapped[Decimal]          = mapped_column(Numeric(6, 2), nullable=False)           # exact decimal
    exam_date:          Mapped[date | None]      = mapped_column(Date, nullable=True)
    status:             Mapped[str]              = mapped_column(String(20), nullable=False, default="draft", index=True)  # draft | published
    created_by:         Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at:       Mapped[datetime | None]  = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:         Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at:         Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    institution    = relationship("Institution")
    cohort         = relationship("Cohort")
    creator        = relationship("User", foreign_keys=[created_by])
    marks          = relationship("Mark", back_populates="exam", cascade="all, delete-orphan")
    change_records = relationship("MarkChangeRecord", back_populates="exam", cascade="all, delete-orphan")


class Mark(Base):
    __tablename__ = "marks"
    __table_args__ = (
        UniqueConstraint("exam_id", "student_id", name="uq_exam_student_mark"),
        Index("ix_marks_student_exam", "student_id", "exam_id"),
    )

    id:             Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    exam_id:        Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id:     Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    marks_obtained: Mapped[Decimal | None]   = mapped_column(Numeric(6, 2), nullable=True)
    is_absent:      Mapped[bool]             = mapped_column(Boolean, default=False, nullable=False)
    entered_by:     Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at:     Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at:     Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    exam           = relationship("Exam", back_populates="marks")
    student        = relationship("User", foreign_keys=[student_id])
    recorder       = relationship("User", foreign_keys=[entered_by])
    change_records = relationship("MarkChangeRecord", back_populates="mark", cascade="all, delete-orphan", order_by="desc(MarkChangeRecord.changed_at)")


class MarkChangeRecord(Base):
    __tablename__ = "mark_change_records"
    __table_args__ = (
        Index("ix_mark_change_mark", "mark_id"),
        Index("ix_mark_change_exam", "exam_id"),
    )

    id:              Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    mark_id:         Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("marks.id", ondelete="CASCADE"), nullable=False, index=True)
    exam_id:         Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("exams.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id:      Mapped[uuid.UUID]        = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    changed_by:      Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    previous_marks:  Mapped[Decimal | None]   = mapped_column(Numeric(6, 2), nullable=True)
    new_marks:       Mapped[Decimal | None]   = mapped_column(Numeric(6, 2), nullable=True)
    previous_absent: Mapped[bool]             = mapped_column(Boolean, default=False, nullable=False)
    new_absent:      Mapped[bool]             = mapped_column(Boolean, default=False, nullable=False)
    reason:          Mapped[str]              = mapped_column(String(255), nullable=False)
    changed_at:      Mapped[datetime]         = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    mark    = relationship("Mark", back_populates="change_records")
    exam    = relationship("Exam", back_populates="change_records")
    student = relationship("User", foreign_keys=[student_id])
    changer = relationship("User", foreign_keys=[changed_by])
