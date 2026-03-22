"""
Alert / Prediction Service

Rules:
  1. OVERLOAD      — if 3+ assignment deadlines in the next 7 days
  2. ATTENDANCE    — if any subject attendance < 75%
  3. CONFLICT      — if an activity date matches an assignment deadline
  4. DEADLINE_SOON — if an assignment is due within 24 hours

This is called:
  - On-demand via GET /alerts/refresh
  - By the cron job (scheduler.py) every morning
"""
from uuid import UUID
from datetime import date, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.models.document_alert import Alert, AlertType, AlertSeverity
from app.models.assignment import Assignment, AssignmentStatus
from app.models.activity import Activity
from app.services.attendance_service import get_attendance_summary


async def generate_alerts(user_id: UUID, db: AsyncSession) -> list[Alert]:
    """Run all prediction rules and save new alerts to DB."""
    new_alerts: list[Alert] = []

    new_alerts += await _check_overload(user_id, db)
    new_alerts += await _check_attendance(user_id, db)
    new_alerts += await _check_deadline_soon(user_id, db)
    new_alerts += await _check_activity_conflicts(user_id, db)

    # Persist only alerts not already saved (avoid duplicates)
    for alert in new_alerts:
        db.add(alert)
    await db.flush()
    return new_alerts


async def get_alerts(
    user_id: UUID, db: AsyncSession, unread_only: bool = False
) -> list[Alert]:
    query = select(Alert).where(Alert.user_id == user_id)
    if unread_only:
        query = query.where(Alert.is_read.is_(False))
    query = query.order_by(Alert.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def mark_alert_read(user_id: UUID, alert_id: UUID, db: AsyncSession) -> None:
    result = await db.execute(
        select(Alert).where(and_(Alert.id == alert_id, Alert.user_id == user_id))
    )
    alert = result.scalar_one_or_none()
    if not alert:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.is_read = True
    await db.flush()


# ─── Rule 1: Overload ─────────────────────────────────────────

async def _check_overload(user_id: UUID, db: AsyncSession) -> list[Alert]:
    today  = date.today()
    cutoff = today + timedelta(days=7)

    result = await db.execute(
        select(Assignment).where(
            and_(
                Assignment.user_id == user_id,
                Assignment.deadline >= today,
                Assignment.deadline <= cutoff,
                Assignment.status != AssignmentStatus.completed.value,
            )
        ).order_by(Assignment.deadline)
    )
    upcoming = result.scalars().all()

    if len(upcoming) < 3:
        return []

    # Avoid duplicate alert for same window
    existing = await _alert_exists(user_id, AlertType.overload, db)
    if existing:
        return []

    subjects = list({a.subject or "Unknown" for a in upcoming})
    return [Alert(
        user_id=user_id,
        alert_type=AlertType.overload,
        severity=AlertSeverity.critical,
        title="Academic Overload Warning",
        message=(
            f"You have {len(upcoming)} deadlines in the next 7 days: "
            + ", ".join(a.title for a in upcoming[:5])
            + (f" (+{len(upcoming)-5} more)" if len(upcoming) > 5 else "")
            + ". Consider prioritizing your tasks."
        ),
        expires_at=cutoff,
    )]


# ─── Rule 2: Low Attendance ───────────────────────────────────

async def _check_attendance(user_id: UUID, db: AsyncSession) -> list[Alert]:
    summaries = await get_attendance_summary(user_id, db)
    alerts = []

    for s in summaries:
        if not s.below_threshold:
            continue

        existing = await _alert_exists(
            user_id, AlertType.attendance_low, db, subject_id=s.subject_id
        )
        if existing:
            continue

        # How many more classes to attend to reach 75%?
        safe_threshold = 0.75
        # solve: (present + x) / (total + x) >= 0.75
        if s.total_classes > 0:
            x = max(0, int((safe_threshold * s.total_classes - s.present_count) / (1 - safe_threshold)))
            classes_needed_msg = f" You need to attend {x} consecutive classes to recover."
        else:
            classes_needed_msg = ""

        alerts.append(Alert(
            user_id=user_id,
            alert_type=AlertType.attendance_low,
            severity=AlertSeverity.critical,
            title=f"Low Attendance: {s.subject_name}",
            message=(
                f"Your attendance in {s.subject_name} is {s.attendance_percentage}%, "
                f"which is below the required 75%.{classes_needed_msg}"
            ),
            related_subject_id=s.subject_id,
        ))

    return alerts


# ─── Rule 3: Deadline in 24 hours ─────────────────────────────

async def _check_deadline_soon(user_id: UUID, db: AsyncSession) -> list[Alert]:
    today    = date.today()
    tomorrow = today + timedelta(days=1)

    result = await db.execute(
        select(Assignment).where(
            and_(
                Assignment.user_id == user_id,
                Assignment.deadline == tomorrow,
                Assignment.status != AssignmentStatus.completed.value,
            )
        )
    )
    due_tomorrow = result.scalars().all()
    alerts = []

    for assignment in due_tomorrow:
        existing = await _alert_exists(
            user_id, AlertType.deadline_soon, db, assignment_id=assignment.id
        )
        if existing:
            continue

        alerts.append(Alert(
            user_id=user_id,
            alert_type=AlertType.deadline_soon,
            severity=AlertSeverity.warning,
            title=f"Due Tomorrow: {assignment.title}",
            message=(
                f"'{assignment.title}' ({assignment.subject or 'No subject'}) "
                f"is due tomorrow. Mark it complete once done."
            ),
            related_assignment_id=assignment.id,
            expires_at=tomorrow,
        ))

    return alerts


# ─── Rule 4: Activity-Assignment Conflict ─────────────────────

async def _check_activity_conflicts(user_id: UUID, db: AsyncSession) -> list[Alert]:
    """Flag activities whose date matches an assignment deadline."""
    today = date.today()

    # Get activities in the future
    activities_result = await db.execute(
        select(Activity).where(
            and_(
                Activity.user_id == user_id,
                Activity.activity_date >= today,
            )
        )
    )
    activities = activities_result.scalars().all()
    if not activities:
        return []

    # Get non-completed assignments with deadlines
    assignments_result = await db.execute(
        select(Assignment).where(
            and_(
                Assignment.user_id == user_id,
                Assignment.deadline >= today,
                Assignment.status != AssignmentStatus.completed.value,
            )
        )
    )
    assignments = assignments_result.scalars().all()
    if not assignments:
        return []

    # Build a set of deadline dates for quick lookup
    deadline_map: dict[date, list[Assignment]] = {}
    for a in assignments:
        if a.deadline:
            deadline_map.setdefault(a.deadline, []).append(a)

    alerts = []
    for activity in activities:
        conflicting = deadline_map.get(activity.activity_date, [])
        if not conflicting:
            continue

        # Check if we already logged this conflict alert
        existing = await _alert_exists(
            user_id, AlertType.activity_conflict, db, assignment_id=conflicting[0].id
        )
        if existing:
            continue

        conflict_titles = ", ".join(a.title for a in conflicting[:3])
        alerts.append(Alert(
            user_id=user_id,
            alert_type=AlertType.activity_conflict,
            severity=AlertSeverity.warning,
            title=f"Schedule Conflict: {activity.title}",
            message=(
                f"Your activity '{activity.title}' on {activity.activity_date.isoformat()} "
                f"conflicts with deadline(s): {conflict_titles}. "
                "Consider rescheduling or completing the assignment(s) early."
            ),
            related_assignment_id=conflicting[0].id,
            related_activity_id=activity.id,
            expires_at=activity.activity_date,
        ))

    return alerts


# ─── Helper: avoid duplicate alerts ───────────────────────────

async def _alert_exists(
    user_id: UUID,
    alert_type: AlertType,
    db: AsyncSession,
    subject_id: UUID | None = None,
    assignment_id: UUID | None = None,
) -> bool:
    from datetime import datetime
    query = select(Alert).where(
        and_(
            Alert.user_id == user_id,
            Alert.alert_type == alert_type,
            Alert.is_read.is_(False),
        )
    )
    if subject_id:
        query = query.where(Alert.related_subject_id == subject_id)
    if assignment_id:
        query = query.where(Alert.related_assignment_id == assignment_id)

    result = await db.execute(query)
    return result.scalar_one_or_none() is not None
