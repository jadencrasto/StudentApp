import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Uuid, ForeignKey, JSON, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_institution_role", "institution_id", "role"),
    )

    id:                    Mapped[uuid.UUID]  = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email:                 Mapped[str]        = mapped_column(String(255), unique=True, nullable=False, index=True)
    username:              Mapped[str]        = mapped_column(String(100), unique=True, nullable=False)
    full_name:             Mapped[str | None] = mapped_column(String(255), index=True)
    hashed_password:       Mapped[str]        = mapped_column(nullable=False)
    is_active:             Mapped[bool]       = mapped_column(Boolean, default=True)
    created_at:            Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at:            Mapped[datetime]   = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Phase 5A: Roles, Institution, and Onboarding
    role:                  Mapped[str]        = mapped_column(String(30), default="student", nullable=False)  # student | admin | super_admin
    institution_id:        Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True, index=True)
    cohort_id:             Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("cohorts.id", ondelete="SET NULL"), nullable=True, index=True)
    must_change_password:  Mapped[bool]       = mapped_column(Boolean, default=False, nullable=False)
    onboarding_completed:  Mapped[bool]       = mapped_column(Boolean, default=False, nullable=False)
    education_level:       Mapped[str | None] = mapped_column(String(50), nullable=True)  # school | college
    grade_or_year:         Mapped[str | None] = mapped_column(String(50), nullable=True)
    location:              Mapped[str | None] = mapped_column(String(255), nullable=True)
    institution_name_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    extra_info:            Mapped[dict | None] = mapped_column(JSON, nullable=True, default=dict)

    # Phase 6A: Student Management & Archiving
    created_by_admin:      Mapped[bool]       = mapped_column(Boolean, default=False, nullable=False)
    archived_at:           Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_changed_at:   Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    token_version:         Mapped[int]        = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    institution       = relationship("Institution", back_populates="users", foreign_keys=[institution_id])
    cohort            = relationship("Cohort", back_populates="users", foreign_keys=[cohort_id])
    join_requests     = relationship("JoinRequest", back_populates="user", foreign_keys="JoinRequest.user_id", cascade="all, delete-orphan")
    assignments       = relationship("Assignment",       back_populates="user", cascade="all, delete-orphan")
    subjects          = relationship("Subject",          back_populates="user", cascade="all, delete-orphan")
    activities        = relationship("Activity",         back_populates="user", cascade="all, delete-orphan")
    documents         = relationship("Document",         back_populates="user", cascade="all, delete-orphan")
    alerts            = relationship("Alert",            back_populates="user", cascade="all, delete-orphan")
    timetable_entries = relationship("TimetableEntry", back_populates="user", cascade="all, delete-orphan")
    timetable_documents = relationship("TimetableDocument", back_populates="user", cascade="all, delete-orphan")
    google_token      = relationship("GoogleToken", back_populates="user", cascade="all, delete-orphan", uselist=False)

