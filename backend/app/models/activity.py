import uuid
from datetime import datetime, date, time
from typing import Optional
from sqlalchemy import String, Text, Date, Time, DateTime, ForeignKey, Boolean, Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Activity(Base):
    __tablename__ = "activities"

    id:             Mapped[uuid.UUID]   = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id:        Mapped[uuid.UUID]   = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    title:          Mapped[str]         = mapped_column(String(500), nullable=False)
    category:       Mapped[str | None]  = mapped_column(String(100))   # Sports, Cultural, Tech
    activity_date:  Mapped[date | None]  = mapped_column(Date, nullable=True, index=True)
    start_time:     Mapped[time | None] = mapped_column(Time)
    end_time:       Mapped[time | None] = mapped_column(Time)
    location:       Mapped[str | None]  = mapped_column(String(255))
    description:    Mapped[str | None]  = mapped_column(Text)

    # Set by AI conflict checker
    has_conflict:     Mapped[bool]        = mapped_column(Boolean, default=False)
    conflict_detail:  Mapped[str | None]  = mapped_column(Text)

    # ── Recurrence ───────────────────────────────────────────────
    # Values: 'none' | 'daily' | 'every_2_days' | 'every_3_days' |
    #         'weekly' | 'biweekly' | 'monthly' | 'custom'
    recurrence_type:       Mapped[str | None]       = mapped_column(String(50),  default="none")
    recurrence_start_date: Mapped[Optional[date]]   = mapped_column(Date, nullable=True)
    recurrence_end_date:   Mapped[Optional[date]]   = mapped_column(Date, nullable=True)
    custom_interval:       Mapped[Optional[int]]    = mapped_column(Integer, nullable=True)
    # Values: 'days' | 'weeks' | 'months'
    custom_interval_unit:  Mapped[str | None]       = mapped_column(String(20), nullable=True)

    # Links generated instances back to their parent
    parent_activity_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("activities.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    is_recurring_instance: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at:  Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user   = relationship("User", back_populates="activities")
    alerts = relationship("Alert", back_populates="activity", foreign_keys="Alert.related_activity_id")

    # Self-referential: parent → children (cascade delete)
    recurring_instances = relationship(
        "Activity",
        cascade="all, delete-orphan",
        back_populates="parent_activity",
        foreign_keys="[Activity.parent_activity_id]",
        uselist=True,
    )

    # Many-to-one: child instance → parent
    parent_activity = relationship(
        "Activity",
        back_populates="recurring_instances",
        foreign_keys="[Activity.parent_activity_id]",
        remote_side="[Activity.id]",
        uselist=False,
    )
