from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.schemas import SubjectCreate, SubjectUpdate, SubjectOut, AttendanceMarkRequest, AttendanceSummaryOut, AttendanceRecordOut
from app.services import attendance_service

router = APIRouter(prefix="/attendance", tags=["Attendance"])


# ─── Subjects ────────────────────────────────────────────────

@router.post("/subjects", response_model=SubjectOut, status_code=201)
async def add_subject(
    data: SubjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a subject to track attendance for."""
    return await attendance_service.create_subject(current_user.id, data, db)


@router.get("/subjects", response_model=list[SubjectOut])
async def list_subjects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all subjects for the current user."""
    return await attendance_service.get_subjects(current_user.id, db)


@router.patch("/subjects/{subject_id}", response_model=SubjectOut)
async def edit_subject(
    subject_id: UUID,
    data: SubjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Edit subject name/code."""
    return await attendance_service.update_subject(current_user.id, subject_id, data, db)


@router.delete("/subjects/{subject_id}", status_code=204)
async def remove_subject(
    subject_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a subject and related attendance records."""
    await attendance_service.delete_subject(current_user.id, subject_id, db)


# ─── Marking ─────────────────────────────────────────────────

@router.post("/mark", status_code=201)
async def mark_attendance(
    data: AttendanceMarkRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark attendance for a subject on a specific date.
    If a record already exists for that date, it is updated (upsert).
    """
    record = await attendance_service.mark_attendance(current_user.id, data, db)
    return {
        "id":         str(record.id),
        "status":     record.status,
        "class_date": str(record.class_date),
        "marked_at":  record.marked_at.isoformat() if record.marked_at else None,
    }


# ─── Summary ─────────────────────────────────────────────────

@router.get("/summary", response_model=list[AttendanceSummaryOut])
async def attendance_summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get attendance percentage for each subject.
    Flags subjects below 75% with below_threshold=True.
    """
    return await attendance_service.get_attendance_summary(current_user.id, db)


@router.get("/project/{subject_id}")
async def project_attendance(
    subject_id: UUID,
    remaining_classes: int = 10,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Project future attendance assuming all remaining classes are attended.
    Returns current%, projected%, and whether it will be safe.
    """
    return await attendance_service.project_attendance(
        current_user.id, subject_id, db, remaining_classes
    )

@router.get("/history/{subject_id}", response_model=list[AttendanceRecordOut])
async def get_attendance_history(
    subject_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the full history of marked attendance records for a subject."""
    return await attendance_service.get_attendance_history(current_user.id, subject_id, db)


# ─── Smart Alerts ─────────────────────────────────────────────

@router.get("/alerts")
async def get_attendance_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get smart attendance alerts for the current user.
    Detects threshold breaches, danger zones, projection warnings,
    consecutive absence streaks, and safe-but-tight situations.
    """
    from app.services.attendance_service import generate_attendance_alerts
    return await generate_attendance_alerts(current_user.id, db)


@router.get("/recovery-plan/{subject_id}")
async def get_subject_recovery_plan(
    subject_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get a detailed recovery plan for a specific subject showing three scenarios:
    Minimum Safe (75%), Safe Zone (80%), and Comfort Zone (85%).
    """
    from app.services.attendance_service import get_recovery_plan
    return await get_recovery_plan(current_user.id, subject_id, db)
