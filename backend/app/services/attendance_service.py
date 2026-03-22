from uuid import UUID
from datetime import date, timedelta
from typing import Dict, List
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func
from app.models.attendance import Subject, AttendanceRecord, AttendanceStatus
from app.schemas.schemas import SubjectCreate, SubjectUpdate, AttendanceMarkRequest, AttendanceSummaryOut


# ─── Subject CRUD ─────────────────────────────────────────────

async def create_subject(user_id: UUID, data: SubjectCreate, db: AsyncSession) -> Subject:
    subject = Subject(user_id=user_id, name=data.name, code=data.code)
    db.add(subject)
    await db.flush()
    return subject


async def get_subjects(user_id: UUID, db: AsyncSession) -> list[Subject]:
    result = await db.execute(
        select(Subject).where(Subject.user_id == user_id).order_by(Subject.name)
    )
    return list(result.scalars().all())


async def update_subject(user_id: UUID, subject_id: UUID, data: SubjectUpdate, db: AsyncSession) -> Subject:
    result = await db.execute(
        select(Subject).where(and_(Subject.id == subject_id, Subject.user_id == user_id))
    )
    subject = result.scalar_one_or_none()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    updates = data.model_dump(exclude_unset=True)
    if "name" in updates and updates["name"] is not None:
        subject.name = updates["name"].strip()
    if "code" in updates:
        subject.code = updates["code"].strip() if updates["code"] else None

    await db.flush()
    return subject


async def delete_subject(user_id: UUID, subject_id: UUID, db: AsyncSession) -> None:
    result = await db.execute(
        select(Subject).where(and_(Subject.id == subject_id, Subject.user_id == user_id))
    )
    subject = result.scalar_one_or_none()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    await db.delete(subject)
    await db.flush()


# ─── Attendance Marking ───────────────────────────────────────

async def mark_attendance(
    user_id: UUID, data: AttendanceMarkRequest, db: AsyncSession
) -> AttendanceRecord:
    # Verify subject belongs to user
    result = await db.execute(
        select(Subject).where(
            and_(Subject.id == data.subject_id, Subject.user_id == user_id)
        )
    )
    subject = result.scalar_one_or_none()
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")

    # Upsert — update if record for this date already exists
    existing = await db.execute(
        select(AttendanceRecord).where(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.subject_id == data.subject_id,
                AttendanceRecord.class_date == data.class_date,
            )
        )
    )
    record = existing.scalar_one_or_none()

    if record:
        record.status = AttendanceStatus(data.status)
        record.notes = data.notes
    else:
        record = AttendanceRecord(
            user_id=user_id,
            subject_id=data.subject_id,
            class_date=data.class_date,
            status=AttendanceStatus(data.status),
            notes=data.notes,
        )
        db.add(record)
        # Increment total_classes on the subject
        subject.total_classes += 1

    await db.flush()
    return record


# ─── Attendance Summary / Percentage ─────────────────────────

async def get_attendance_summary(
    user_id: UUID, db: AsyncSession
) -> list[AttendanceSummaryOut]:
    """
    Returns attendance stats per subject for the current user.
    Calculates present%, flags if below 75%.
    """
    subjects_result = await db.execute(
        select(Subject).where(Subject.user_id == user_id)
    )
    subjects = subjects_result.scalars().all()

    summaries = []
    for subject in subjects:
        records_result = await db.execute(
            select(AttendanceRecord).where(
                and_(
                    AttendanceRecord.user_id == user_id,
                    AttendanceRecord.subject_id == subject.id,
                )
            )
        )
        records = records_result.scalars().all()

        total = len(records)
        present_count = 0
        absent_count = 0
        late_count = 0

        for r in records:
            if r.status == AttendanceStatus.present.value:
                present_count += 1
            elif r.status == AttendanceStatus.late.value:
                present_count += 1  # present for logic
                late_count += 1
            elif r.status == AttendanceStatus.absent.value:
                absent_count += 1

        pct = round((present_count / total) * 100, 2) if total > 0 else 0.0

        summaries.append(AttendanceSummaryOut(
            subject_id=subject.id,
            subject_name=subject.name,
            subject_code=subject.code,
            total_classes=total,
            present_count=present_count,
            absent_count=absent_count,
            late_count=late_count,
            attendance_percentage=pct,
            below_threshold=pct < 75.0,
        ))

    return summaries


async def project_attendance(
    user_id: UUID, subject_id: UUID, db: AsyncSession,
    total_remaining: int = 10  # assume 10 more classes in semester
) -> dict:
    """
    Project whether attendance will drop below 75% by semester end.
    Assumes student attends all remaining classes.
    """
    summaries = await get_attendance_summary(user_id, db)
    for s in summaries:
        if s.subject_id == subject_id:
            projected_total   = s.total_classes + total_remaining
            projected_present = s.present_count + total_remaining
            projected_pct = round((projected_present / projected_total) * 100, 2)
            return {
                "current_percentage":   s.attendance_percentage,
                "projected_percentage": projected_pct,
                "safe": projected_pct >= 75.0,
            }
    raise HTTPException(status_code=404, detail="Subject not found")

async def get_attendance_history(user_id: UUID, subject_id: UUID, db: AsyncSession) -> list[AttendanceRecord]:
    result = await db.execute(
        select(AttendanceRecord).where(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.subject_id == subject_id
            )
        ).order_by(AttendanceRecord.class_date.desc())
    )
    return list(result.scalars().all())


# ── Alert Generation Functions ─────────────────────────────────

async def generate_attendance_alerts(user_id: UUID, db: AsyncSession) -> List[Dict]:
    """
    Generate smart alerts for all subjects with attendance issues.
    Returns list of alert objects sorted by severity.
    """
    summaries = await get_attendance_summary(user_id, db)
    alerts = []

    for summary in summaries:
        # Alert 1: Below Threshold (<75%)
        if summary.attendance_percentage < 75:
            classes_needed = calculate_classes_needed_to_recover(
                summary.present_count,
                summary.total_classes,
                target_percentage=75
            )
            severity = 'critical' if summary.attendance_percentage < 70 else 'warning'
            alerts.append({
                'id': f"threshold_{summary.subject_id}",
                'subject_id': str(summary.subject_id),
                'subject_name': summary.subject_name,
                'type': 'threshold_breach',
                'severity': severity,
                'title': f"⚠️ {summary.subject_name}: Below 75%",
                'message': f"Current: {summary.attendance_percentage}%. Need {classes_needed} consecutive present marks to recover.",
                'action': 'Attend all upcoming classes',
                'data': {
                    'current_percentage': summary.attendance_percentage,
                    'classes_needed': classes_needed,
                    'target': 75
                }
            })

        # Alert 2: Danger Zone (70-74%) — only if not already covered by threshold alert
        elif 70 <= summary.attendance_percentage < 75:
            alerts.append({
                'id': f"danger_{summary.subject_id}",
                'subject_id': str(summary.subject_id),
                'subject_name': summary.subject_name,
                'type': 'danger_zone',
                'severity': 'warning',
                'title': f"🔶 {summary.subject_name}: Danger Zone",
                'message': f"At {summary.attendance_percentage}% — one more absence drops you below 70%",
                'action': 'Critical — attend next class',
                'data': {'current_percentage': summary.attendance_percentage}
            })

        # Alert 3: Projection Warning
        projection = calculate_projection(
            summary.present_count,
            summary.total_classes,
            remaining_classes=10
        )
        if projection['projected_percentage'] < 75:
            alerts.append({
                'id': f"projection_{summary.subject_id}",
                'subject_id': str(summary.subject_id),
                'subject_name': summary.subject_name,
                'type': 'projection_warning',
                'severity': 'warning',
                'title': f"📊 {summary.subject_name}: Future Risk",
                'message': f"Projected to end at {projection['projected_percentage']:.1f}% even with perfect attendance",
                'action': 'Cannot afford any more absences',
                'data': projection
            })

        # Alert 4: Safe but Tight (75–79%)
        elif 75 <= summary.attendance_percentage < 80:
            can_miss = calculate_safe_absences(
                summary.present_count,
                summary.total_classes,
                remaining_classes=10
            )
            alerts.append({
                'id': f"tight_{summary.subject_id}",
                'subject_id': str(summary.subject_id),
                'subject_name': summary.subject_name,
                'type': 'safe_but_tight',
                'severity': 'info',
                'title': f"⚠️ {summary.subject_name}: Safe but Tight",
                'message': f"At {summary.attendance_percentage}% — can only miss {can_miss} more class{'es' if can_miss != 1 else ''}",
                'action': 'Stay vigilant',
                'data': {'can_miss': can_miss}
            })

        # Alert 5: Consecutive Absences Pattern
        records_result = await db.execute(
            select(AttendanceRecord)
            .where(
                and_(
                    AttendanceRecord.user_id == user_id,
                    AttendanceRecord.subject_id == summary.subject_id
                )
            )
            .order_by(AttendanceRecord.class_date.desc())
            .limit(5)
        )
        recent_records = list(records_result.scalars().all())

        consecutive_absences = 0
        for record in recent_records:
            if record.status == AttendanceStatus.absent.value:
                consecutive_absences += 1
            else:
                break

        if consecutive_absences >= 2:
            alerts.append({
                'id': f"streak_{summary.subject_id}",
                'subject_id': str(summary.subject_id),
                'subject_name': summary.subject_name,
                'type': 'negative_streak',
                'severity': 'critical',
                'title': f"🔥 {summary.subject_name}: Absence Streak",
                'message': f"{consecutive_absences} consecutive absences — attend next class!",
                'action': 'Break the streak',
                'data': {'streak': consecutive_absences}
            })

    # Sort by severity: critical > warning > info
    severity_order = {'critical': 0, 'warning': 1, 'info': 2}
    alerts.sort(key=lambda x: severity_order[x['severity']])
    return alerts


def calculate_classes_needed_to_recover(
    present_count: int,
    total_classes: int,
    target_percentage: float = 75.0
) -> int:
    """
    Calculate how many consecutive present marks are needed to reach target_percentage.
    Solves: (present + x) / (total + x) >= target / 100
    """
    if total_classes == 0:
        return 0
    current_pct = (present_count / total_classes) * 100
    if current_pct >= target_percentage:
        return 0
    target_decimal = target_percentage / 100
    numerator = (target_decimal * total_classes) - present_count
    denominator = 1 - target_decimal
    if denominator == 0:
        return 999
    return max(0, int(numerator / denominator) + 1)


def calculate_projection(
    present_count: int,
    total_classes: int,
    remaining_classes: int = 10
) -> Dict:
    """
    Project final attendance percentage assuming perfect attendance from now.
    """
    if total_classes == 0:
        return {
            'projected_percentage': 100.0,
            'projected_total': remaining_classes,
            'projected_present': remaining_classes,
            'will_be_safe': True,
            'remaining_classes': remaining_classes
        }
    projected_total = total_classes + remaining_classes
    projected_present = present_count + remaining_classes
    projected_percentage = round((projected_present / projected_total) * 100, 2)
    return {
        'projected_percentage': projected_percentage,
        'projected_total': projected_total,
        'projected_present': projected_present,
        'will_be_safe': projected_percentage >= 75.0,
        'remaining_classes': remaining_classes
    }


def calculate_safe_absences(
    present_count: int,
    total_classes: int,
    remaining_classes: int = 10,
    threshold: float = 75.0
) -> int:
    """
    Calculate how many future classes can be missed while staying at or above threshold.
    """
    if total_classes == 0:
        return 0
    target_decimal = threshold / 100
    projected_total = total_classes + remaining_classes
    min_present_needed = int(projected_total * target_decimal)
    if (min_present_needed / projected_total) < target_decimal:
        min_present_needed += 1
    max_present_possible = present_count + remaining_classes
    return max(0, max_present_possible - min_present_needed)


async def get_recovery_plan(
    user_id: UUID,
    subject_id: UUID,
    db: AsyncSession
) -> Dict:
    """
    Generate a detailed recovery plan for a specific subject with scenarios.
    """
    summaries = await get_attendance_summary(user_id, db)
    summary = next((s for s in summaries if str(s.subject_id) == str(subject_id)), None)
    if not summary:
        raise HTTPException(status_code=404, detail="Subject not found")

    scenarios = []
    for target, label in [(75, 'Minimum Safe'), (80, 'Safe Zone'), (85, 'Comfort Zone')]:
        n = calculate_classes_needed_to_recover(summary.present_count, summary.total_classes, target)
        scenarios.append({
            'name': label,
            'target': target,
            'classes_needed': n,
            'message': f"Attend next {n} classes → {target}% ({'threshold' if target == 75 else 'safe' if target == 80 else 'excellent'})"
        })

    return {
        'subject_name': summary.subject_name,
        'current_percentage': summary.attendance_percentage,
        'scenarios': scenarios
    }
