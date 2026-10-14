from uuid import UUID
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc
from app.models.user import User
from app.models.institution import Cohort
from app.models.class_attendance import ClassAttendanceRecord, ClassAttendanceChangeLog
from app.models.document_alert import Alert, AlertType, AlertSeverity
from app.schemas.class_attendance import (
    BulkMarkAttendanceRequest,
    CohortAttendanceResponse,
    StudentAttendanceSummaryItem,
    StudentClassAttendanceResponse,
    StudentSubjectSummary,
    StudentRecordItem,
)
from app.services.attendance_service import calculate_classes_needed_to_recover


def get_current_kolkata_date() -> date:
    """Return the current date in Asia/Kolkata timezone."""
    kolkata_tz = ZoneInfo("Asia/Kolkata")
    return datetime.now(kolkata_tz).date()


async def mark_class_attendance(
    admin_user: User,
    data: BulkMarkAttendanceRequest,
    db: AsyncSession,
) -> dict:
    """
    Save or update attendance for students in a class.
    Enforces:
    - Subject trimming & case-insensitive normalization.
    - Asia/Kolkata date limit (no future dates).
    - Max 300 students per batch.
    - All-or-nothing validation: any invalid student rejects entire request.
    - Audit change logging on status updates.
    """
    # 1. Subject name trimming and normalization
    cleaned_subject = data.subject_name.strip()
    if not cleaned_subject:
        raise HTTPException(status_code=400, detail="Subject name cannot be empty.")
    normalized_subject = cleaned_subject.lower()

    # 2. Date validation using Asia/Kolkata timezone
    kolkata_today = get_current_kolkata_date()
    if data.class_date > kolkata_today:
        raise HTTPException(
            status_code=400,
            detail=f"Attendance date cannot be in the future (latest allowed date is {kolkata_today} in Asia/Kolkata).",
        )

    # 3. Batch size checks
    if len(data.students) == 0:
        raise HTTPException(status_code=400, detail="Student list cannot be empty.")
    if len(data.students) > 300:
        raise HTTPException(
            status_code=400,
            detail="Cannot save attendance for more than 300 students in a single request.",
        )

    # 4. Cohort validation
    cohort = await db.get(Cohort, data.cohort_id)
    if not cohort or cohort.institution_id != admin_user.institution_id:
        raise HTTPException(status_code=404, detail="Class cohort not found in your institution.")

    # 5. Student validations — All-or-Nothing
    student_ids = [item.student_id for item in data.students]
    if len(student_ids) != len(set(student_ids)):
        raise HTTPException(status_code=400, detail="Duplicate student IDs found in attendance request.")

    # Fetch all students in batch
    users_result = await db.execute(select(User).where(User.id.in_(student_ids)))
    student_map: dict[UUID, User] = {u.id: u for u in users_result.scalars().all()}

    for item in data.students:
        student = student_map.get(item.student_id)
        if not student:
            raise HTTPException(status_code=400, detail=f"Student ID '{item.student_id}' does not exist.")
        if not student.is_active or student.archived_at is not None:
            name = student.full_name or student.username
            raise HTTPException(status_code=400, detail=f"Student '{name}' is deactivated or archived.")
        if student.institution_id != admin_user.institution_id:
            name = student.full_name or student.username
            raise HTTPException(status_code=400, detail=f"Student '{name}' does not belong to your institution.")
        if student.cohort_id != data.cohort_id:
            name = student.full_name or student.username
            raise HTTPException(status_code=400, detail=f"Student '{name}' is not currently enrolled in this class.")
        if item.status not in ("present", "absent"):
            raise HTTPException(status_code=400, detail=f"Invalid status '{item.status}'. Must be 'present' or 'absent'.")

    # 6. Fetch existing records for this (cohort, date, subject_normalized)
    rec_result = await db.execute(
        select(ClassAttendanceRecord).where(
            and_(
                ClassAttendanceRecord.cohort_id == data.cohort_id,
                ClassAttendanceRecord.class_date == data.class_date,
                ClassAttendanceRecord.subject_name_normalized == normalized_subject,
                ClassAttendanceRecord.student_id.in_(student_ids),
            )
        )
    )
    existing_records: dict[UUID, ClassAttendanceRecord] = {
        r.student_id: r for r in rec_result.scalars().all()
    }

    now_utc = datetime.now(timezone.utc)
    created_count = 0
    updated_count = 0

    for item in data.students:
        existing_rec = existing_records.get(item.student_id)
        if existing_rec:
            if existing_rec.status != item.status:
                # Log audit change
                log = ClassAttendanceChangeLog(
                    record_id=existing_rec.id,
                    changed_by=admin_user.id,
                    previous_status=existing_rec.status,
                    new_status=item.status,
                    changed_at=now_utc,
                    reason=item.reason or "Admin update",
                )
                db.add(log)
                existing_rec.status = item.status
                existing_rec.marked_by = admin_user.id
                existing_rec.updated_at = now_utc
                existing_rec.subject_name = cleaned_subject
                updated_count += 1
            else:
                # Same status, refresh subject casing if edited
                existing_rec.subject_name = cleaned_subject
        else:
            rec = ClassAttendanceRecord(
                institution_id=admin_user.institution_id,
                cohort_id=data.cohort_id,
                student_id=item.student_id,
                class_date=data.class_date,
                subject_name=cleaned_subject,
                subject_name_normalized=normalized_subject,
                status=item.status,
                marked_by=admin_user.id,
                created_at=now_utc,
                updated_at=now_utc,
            )
            db.add(rec)
            created_count += 1

    await db.flush()

    return {
        "success": True,
        "cohort_id": str(data.cohort_id),
        "class_date": str(data.class_date),
        "subject_name": cleaned_subject,
        "created": created_count,
        "updated": updated_count,
        "total": len(data.students),
    }


async def get_cohort_attendance_overview(
    admin_user: User,
    cohort_id: UUID,
    db: AsyncSession,
    class_date: date | None = None,
    subject_name: str | None = None,
) -> CohortAttendanceResponse:
    """
    Get summary and current marking state for a cohort.
    Only counts records from the student's CURRENT cohort.
    """
    cohort = await db.get(Cohort, cohort_id)
    if not cohort or cohort.institution_id != admin_user.institution_id:
        raise HTTPException(status_code=404, detail="Class cohort not found in your institution.")

    # 1. Fetch active students in this cohort
    students_res = await db.execute(
        select(User).where(
            and_(
                User.institution_id == admin_user.institution_id,
                User.cohort_id == cohort_id,
                User.role == "student",
                User.is_active == True,
                User.archived_at.is_(None),
            )
        ).order_by(User.full_name, User.username)
    )
    students = list(students_res.scalars().all())

    # 2. Fetch distinct subjects already used in this cohort
    subjects_res = await db.execute(
        select(ClassAttendanceRecord.subject_name, ClassAttendanceRecord.subject_name_normalized)
        .where(ClassAttendanceRecord.cohort_id == cohort_id)
        .distinct()
    )
    # Deduplicate normalized subjects while keeping last casing
    seen_normalized: dict[str, str] = {}
    for sub_name, norm in subjects_res.all():
        if norm not in seen_normalized:
            seen_normalized[norm] = sub_name
    distinct_subjects = sorted(list(seen_normalized.values()), key=lambda s: s.lower())

    # 3. If class_date and subject_name provided, load status on date
    norm_subject = subject_name.strip().lower() if subject_name and subject_name.strip() else None
    cleaned_subject = subject_name.strip() if subject_name and subject_name.strip() else None

    date_status_map: dict[UUID, str] = {}
    if class_date and norm_subject:
        records_res = await db.execute(
            select(ClassAttendanceRecord).where(
                and_(
                    ClassAttendanceRecord.cohort_id == cohort_id,
                    ClassAttendanceRecord.class_date == class_date,
                    ClassAttendanceRecord.subject_name_normalized == norm_subject,
                )
            )
        )
        for r in records_res.scalars().all():
            date_status_map[r.student_id] = r.status

    # 4. Compute overall statistics for each student in CURRENT cohort
    # Fetch all records for this cohort
    all_cohort_records_res = await db.execute(
        select(ClassAttendanceRecord).where(ClassAttendanceRecord.cohort_id == cohort_id)
    )
    all_records = list(all_cohort_records_res.scalars().all())

    student_stats: dict[UUID, dict] = {}
    for r in all_records:
        if r.student_id not in student_stats:
            student_stats[r.student_id] = {"present": 0, "absent": 0, "total": 0}
        stats = student_stats[r.student_id]
        stats["total"] += 1
        if r.status == "present":
            stats["present"] += 1
        elif r.status == "absent":
            stats["absent"] += 1

    summary_items: list[StudentAttendanceSummaryItem] = []
    for s in students:
        stats = student_stats.get(s.id, {"present": 0, "absent": 0, "total": 0})
        total = stats["total"]
        present = stats["present"]
        absent = stats["absent"]
        pct = round((present / total) * 100, 2) if total > 0 else 0.0

        # Requirement 5: Require at least 3 sessions before flagging as below threshold
        below_thresh = (pct < 75.0) if total >= 3 else False

        summary_items.append(
            StudentAttendanceSummaryItem(
                student_id=s.id,
                full_name=s.full_name or s.username,
                email=s.email,
                username=s.username,
                total_classes=total,
                present_count=present,
                absent_count=absent,
                attendance_percentage=pct,
                below_threshold=below_thresh,
                status_on_date=date_status_map.get(s.id),
            )
        )

    return CohortAttendanceResponse(
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        academic_year=cohort.academic_year,
        level_type=cohort.level_type,
        level_value=cohort.level_value,
        class_date=class_date,
        subject_name=cleaned_subject,
        subjects=distinct_subjects,
        students=summary_items,
    )


async def get_cohort_distinct_subjects(
    admin_user: User,
    cohort_id: UUID,
    db: AsyncSession,
) -> list[str]:
    """Return distinct subject names used in a cohort."""
    cohort = await db.get(Cohort, cohort_id)
    if not cohort or cohort.institution_id != admin_user.institution_id:
        raise HTTPException(status_code=404, detail="Class cohort not found in your institution.")

    subjects_res = await db.execute(
        select(ClassAttendanceRecord.subject_name, ClassAttendanceRecord.subject_name_normalized)
        .where(ClassAttendanceRecord.cohort_id == cohort_id)
        .distinct()
    )
    seen_normalized: dict[str, str] = {}
    for sub_name, norm in subjects_res.all():
        if norm not in seen_normalized:
            seen_normalized[norm] = sub_name
    return sorted(list(seen_normalized.values()), key=lambda s: s.lower())


async def get_student_class_attendance_summary(
    student: User,
    db: AsyncSession,
) -> StudentClassAttendanceResponse:
    """
    Get student's official class attendance summary and history.
    - If student is not in a class, returns clean empty structure.
    - Counts only records from the student's CURRENT class.
    - Flags below threshold only if at least 3 sessions have been held.
    """
    if student.role != "student":
        raise HTTPException(status_code=403, detail="Only students can access student attendance records.")

    if not student.cohort_id or not student.institution_id:
        return StudentClassAttendanceResponse(
            enrolled=False,
            cohort=None,
            overall_percentage=0.0,
            total_classes=0,
            present_count=0,
            absent_count=0,
            subjects=[],
            recent_records=[],
        )

    cohort = await db.get(Cohort, student.cohort_id)
    if not cohort:
        return StudentClassAttendanceResponse(
            enrolled=False,
            cohort=None,
            overall_percentage=0.0,
            total_classes=0,
            present_count=0,
            absent_count=0,
            subjects=[],
            recent_records=[],
        )

    # Fetch ONLY records for the student's CURRENT cohort
    records_res = await db.execute(
        select(ClassAttendanceRecord).where(
            and_(
                ClassAttendanceRecord.student_id == student.id,
                ClassAttendanceRecord.cohort_id == student.cohort_id,
            )
        ).order_by(desc(ClassAttendanceRecord.class_date), desc(ClassAttendanceRecord.created_at))
    )
    records = list(records_res.scalars().all())

    # Group by normalized subject name
    subject_map: dict[str, list[ClassAttendanceRecord]] = {}
    for r in records:
        subject_map.setdefault(r.subject_name_normalized, []).append(r)

    subject_summaries: list[StudentSubjectSummary] = []
    total_all = len(records)
    present_all = 0
    absent_all = 0

    for norm_name, recs in subject_map.items():
        disp_name = recs[0].subject_name
        tot = len(recs)
        pres = sum(1 for r in recs if r.status == "present")
        ab = sum(1 for r in recs if r.status == "absent")
        present_all += pres
        absent_all += ab
        pct = round((pres / tot) * 100, 2) if tot > 0 else 0.0

        # Requirement 5: at least 3 sessions before flagging
        below_thresh = (pct < 75.0) if tot >= 3 else False
        needed = calculate_classes_needed_to_recover(pres, tot, 75.0) if below_thresh else 0

        subject_summaries.append(
            StudentSubjectSummary(
                subject_name=disp_name,
                total_classes=tot,
                present_count=pres,
                absent_count=ab,
                attendance_percentage=pct,
                below_threshold=below_thresh,
                classes_needed_to_recover=needed,
            )
        )

    subject_summaries.sort(key=lambda s: s.subject_name.lower())

    overall_pct = round((present_all / total_all) * 100, 2) if total_all > 0 else 0.0

    recent_record_items = [
        StudentRecordItem(
            id=r.id,
            class_date=r.class_date,
            subject_name=r.subject_name,
            status=r.status,
            created_at=r.created_at,
        )
        for r in records[:50]
    ]

    return StudentClassAttendanceResponse(
        enrolled=True,
        cohort={
            "id": str(cohort.id),
            "name": cohort.name,
            "level_type": cohort.level_type,
            "level_value": cohort.level_value,
            "department": cohort.department,
            "academic_year": cohort.academic_year,
        },
        overall_percentage=overall_pct,
        total_classes=total_all,
        present_count=present_all,
        absent_count=absent_all,
        subjects=subject_summaries,
        recent_records=recent_record_items,
    )
