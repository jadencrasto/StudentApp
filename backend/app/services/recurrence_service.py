"""
RecurrenceService — generates and manages recurring activity instances.
"""
from __future__ import annotations

import uuid
from datetime import date, timedelta
from typing import List, Optional

from dateutil.relativedelta import relativedelta
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity


class RecurrenceService:

    @staticmethod
    def generate_occurrence_dates(
        recurrence_type: str,
        start_date: date,
        end_date: date,
        custom_interval: Optional[int] = None,
        custom_interval_unit: Optional[str] = None,
    ) -> List[date]:
        """
        Return every date from start_date to end_date (inclusive) on which
        the activity should occur, given the recurrence_type.
        """
        if recurrence_type == "none":
            return [start_date]

        # Guard against runaway loops (max ~5 years of daily occurrences)
        MAX_OCCURRENCES = 1827

        occurrences: List[date] = []
        current = start_date

        while current <= end_date and len(occurrences) < MAX_OCCURRENCES:
            occurrences.append(current)

            if recurrence_type == "daily":
                current += timedelta(days=1)
            elif recurrence_type == "every_2_days":
                current += timedelta(days=2)
            elif recurrence_type == "every_3_days":
                current += timedelta(days=3)
            elif recurrence_type == "weekly":
                current += timedelta(weeks=1)
            elif recurrence_type == "biweekly":
                current += timedelta(weeks=2)
            elif recurrence_type == "monthly":
                current += relativedelta(months=1)
            elif recurrence_type == "custom":
                unit = custom_interval_unit or "days"
                n = custom_interval or 1
                if unit == "days":
                    current += timedelta(days=n)
                elif unit == "weeks":
                    current += timedelta(weeks=n)
                elif unit == "months":
                    current += relativedelta(months=n)
                else:
                    break
            else:
                break  # Unknown type — return what we have so far

        return occurrences

    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def create_recurring_instances(
        parent: Activity,
        db: AsyncSession,
    ) -> List[Activity]:
        """
        Create one Activity row per occurrence date for *parent*.
        All instances reference parent via parent_activity_id.
        """
        if not parent.recurrence_start_date or not parent.recurrence_end_date:
            return []

        dates = RecurrenceService.generate_occurrence_dates(
            recurrence_type=parent.recurrence_type or "none",
            start_date=parent.recurrence_start_date,
            end_date=parent.recurrence_end_date,
            custom_interval=parent.custom_interval,
            custom_interval_unit=parent.custom_interval_unit,
        )

        instances: List[Activity] = []
        for occurrence_date in dates:
            instance = Activity(
                user_id=parent.user_id,
                title=parent.title,
                category=parent.category,
                activity_date=occurrence_date,
                start_time=parent.start_time,
                end_time=parent.end_time,
                location=parent.location,
                description=parent.description,
                # Recurrence metadata (carried for display)
                recurrence_type="none",          # instances don't recurse
                parent_activity_id=parent.id,
                is_recurring_instance=True,
            )
            db.add(instance)
            instances.append(instance)

        await db.flush()
        return instances

    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def delete_recurring_instances(
        parent_activity_id: uuid.UUID,
        db: AsyncSession,
    ) -> None:
        """Delete every instance that belongs to *parent_activity_id*."""
        await db.execute(
            delete(Activity).where(
                Activity.parent_activity_id == parent_activity_id,
                Activity.is_recurring_instance.is_(True),
            )
        )
        await db.flush()

    # ──────────────────────────────────────────────────────────────────────────

    @staticmethod
    async def update_recurring_instances(
        parent: Activity,
        db: AsyncSession,
    ) -> None:
        """Rebuild all instances for *parent* (delete old ones, then recreate)."""
        await RecurrenceService.delete_recurring_instances(parent.id, db)
        await RecurrenceService.create_recurring_instances(parent, db)
