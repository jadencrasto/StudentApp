from uuid import UUID
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Request, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limiter import limiter
from app.database import get_db
from app.models.user import User
from app.core.dependencies import get_current_user, require_admin
from app.schemas.class_attendance import (
    BulkMarkAttendanceRequest,
    CohortAttendanceResponse,
    StudentClassAttendanceResponse,
)
from app.services.class_attendance_service import (
    mark_class_attendance,
    get_cohort_attendance_overview,
    get_cohort_distinct_subjects,
    get_student_class_attendance_summary,
)

router = APIRouter(tags=["Class Attendance"])


# ─── Admin Endpoints ─────────────────────────────────────────────

@router.get("/admin/attendance/cohorts/{cohort_id}", response_model=CohortAttendanceResponse)
async def get_cohort_attendance(
    cohort_id: UUID,
    class_date: date | None = Query(None, description="Optional class date to view status"),
    subject_name: str | None = Query(None, description="Optional subject to view status"),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get class roster, summary attendance percentages, and status for a given date/subject.
    """
    return await get_cohort_attendance_overview(
        admin_user=admin_user,
        cohort_id=cohort_id,
        db=db,
        class_date=class_date,
        subject_name=subject_name,
    )


@router.get("/admin/attendance/cohorts/{cohort_id}/subjects", response_model=list[str])
async def get_cohort_subjects(
    cohort_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Get list of distinct subject names already recorded in this cohort.
    """
    return await get_cohort_distinct_subjects(
        admin_user=admin_user,
        cohort_id=cohort_id,
        db=db,
    )


@router.post("/admin/attendance/mark")
@limiter.limit("30/minute")
async def mark_attendance_batch(
    request: Request,
    data: BulkMarkAttendanceRequest,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Mark / update attendance for students in a cohort on a given date and subject.
    Enforces all-or-nothing validation, max 300 students, Asia/Kolkata date limit,
    and logs changes to the audit table.
    """
    return await mark_class_attendance(
        admin_user=admin_user,
        data=data,
        db=db,
    )


# ─── Student Endpoints ───────────────────────────────────────────

@router.get("/student/class-attendance", response_model=StudentClassAttendanceResponse)
async def get_student_class_attendance(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get official class attendance records and statistics for the authenticated student.
    - Restricted to student role only (403 for non-students).
    - If student is not in a class, returns a clean empty result.
    - Counts only records from the student's current cohort.
    """
    return await get_student_class_attendance_summary(
        student=current_user,
        db=db,
    )
