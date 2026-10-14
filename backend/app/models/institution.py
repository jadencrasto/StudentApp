import uuid
import secrets
import string
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Uuid, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


def generate_join_code(length: int = 8) -> str:
    """Generate an unambiguous, hard-to-guess uppercase alphanumeric join code."""
    # Exclude characters easily confused: 0, O, 1, I
    charset = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(secrets.choice(charset) for _ in range(length))


class Institution(Base):
    __tablename__ = "institutions"

    id:         Mapped[uuid.UUID]  = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name:       Mapped[str]        = mapped_column(String(255), nullable=False)
    type:       Mapped[str]        = mapped_column(String(50), nullable=False)  # 'school' or 'college'
    location:   Mapped[str | None] = mapped_column(String(255), nullable=True)
    join_code:  Mapped[str]        = mapped_column(String(32), unique=True, nullable=False, index=True)
    is_active:  Mapped[bool]       = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    cohorts       = relationship("Cohort", back_populates="institution", cascade="all, delete-orphan")
    users         = relationship("User", back_populates="institution", foreign_keys="User.institution_id")
    join_requests = relationship("JoinRequest", back_populates="institution", cascade="all, delete-orphan")


class Cohort(Base):
    __tablename__ = "cohorts"
    __table_args__ = (
        UniqueConstraint("institution_id", "name", "academic_year", name="uq_institution_cohort_academic_year"),
    )

    id:             Mapped[uuid.UUID]  = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID]  = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    name:           Mapped[str]        = mapped_column(String(100), nullable=False)  # e.g. "Grade 9-A" or "SE Computer"
    level_type:     Mapped[str]        = mapped_column(String(50), nullable=False)   # 'grade' or 'college_year'
    level_value:    Mapped[str]        = mapped_column(String(50), nullable=False)   # e.g. "9", "SE"
    department:        Mapped[str | None] = mapped_column(String(100), nullable=True)
    academic_year:     Mapped[str]        = mapped_column(String(50), nullable=False)   # e.g. "2026-27"
    is_active:         Mapped[bool]       = mapped_column(Boolean, default=True, nullable=False)
    join_code:         Mapped[str | None] = mapped_column(String(32), unique=True, nullable=True, index=True)
    join_code_enabled: Mapped[bool]       = mapped_column(Boolean, default=True, nullable=False)
    created_at:        Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    institution   = relationship("Institution", back_populates="cohorts")
    users         = relationship("User", back_populates="cohort", foreign_keys="User.cohort_id")
    join_requests = relationship("JoinRequest", back_populates="requested_cohort", foreign_keys="JoinRequest.requested_cohort_id")


class JoinRequest(Base):
    __tablename__ = "join_requests"

    id:                  Mapped[uuid.UUID]  = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:             Mapped[uuid.UUID]  = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    institution_id:      Mapped[uuid.UUID]  = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False, index=True)
    requested_cohort_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True)
    status:              Mapped[str]        = mapped_column(String(20), default="pending", nullable=False)  # pending | approved | rejected
    request_type:        Mapped[str]        = mapped_column(String(30), default="institution", nullable=False)  # institution | class
    decided_by:          Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at:          Mapped[datetime | None]  = mapped_column(DateTime(timezone=True), nullable=True)
    created_at:          Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)

    # Relationships
    user             = relationship("User", back_populates="join_requests", foreign_keys=[user_id])
    institution      = relationship("Institution", back_populates="join_requests")
    requested_cohort = relationship("Cohort", back_populates="join_requests", foreign_keys=[requested_cohort_id])
    decider          = relationship("User", foreign_keys=[decided_by])
