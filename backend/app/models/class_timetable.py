"""
Phase 6C — Admin-managed class timetable model.

A timetable belongs to ONE class (cohort) and has three lifecycle states:
  draft → published → archived

Constraints:
  - Only one 'published' timetable per cohort (enforced by partial unique index).
  - Only one 'draft' timetable per cohort (enforced by partial unique index).
  - Multiple 'archived' timetables are permitted as historical records.
  - Entries are stored as a JSON array inside the timetable row itself.
"""
import uuid
from datetime import datetime
import sqlalchemy as sa
from sqlalchemy import (
    String, DateTime, Uuid, ForeignKey, JSON, Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ClassTimetable(Base):
    __tablename__ = "class_timetables"

    id:             Mapped[uuid.UUID]       = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID]       = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    cohort_id:      Mapped[uuid.UUID]       = mapped_column(Uuid(as_uuid=True), ForeignKey("cohorts.id", ondelete="CASCADE"), nullable=False, index=True)
    status:         Mapped[str]             = mapped_column(String(20), nullable=False, default="draft", index=True)  # draft | published | archived
    entries:        Mapped[list]            = mapped_column(JSON, nullable=False, default=list)
    image_path:     Mapped[str | None]      = mapped_column(String(500), nullable=True)
    created_by:     Mapped[uuid.UUID | None]= mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    published_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:     Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at:     Mapped[datetime]        = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    institution = relationship("Institution")
    cohort      = relationship("Cohort")
    creator     = relationship("User")

    __table_args__ = (
        Index(
            "uq_one_published_per_cohort",
            "cohort_id",
            unique=True,
            sqlite_where=sa.text("status = 'published'"),
            postgresql_where=sa.text("status = 'published'"),
        ),
        Index(
            "uq_one_draft_per_cohort",
            "cohort_id",
            unique=True,
            sqlite_where=sa.text("status = 'draft'"),
            postgresql_where=sa.text("status = 'draft'"),
        ),
        Index("ix_class_timetable_cohort_status", "cohort_id", "status"),
    )
