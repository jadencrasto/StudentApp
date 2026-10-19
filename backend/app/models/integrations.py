import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class GoogleToken(Base):
    __tablename__ = "google_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True, unique=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(Text)
    expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="google_token")


class CollegeEvent(Base):
    __tablename__ = "college_events"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    institution_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=True, index=True)
    college: Mapped[str] = mapped_column(String(255), index=True)
    event_name: Mapped[str] = mapped_column(String(500), index=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    event_date: Mapped[str | None] = mapped_column(String(120), index=True)
    semester: Mapped[str | None] = mapped_column(String(120))
    department: Mapped[str | None] = mapped_column(String(255))
    source_url: Mapped[str] = mapped_column(Text)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_manual: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    institution = relationship("Institution")
