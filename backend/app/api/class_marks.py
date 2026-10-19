from __future__ import annotations

from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.rate_limiter import limiter
from app.database import get_db
from app.models.user import User
from app.models.institution import Cohort
from app.core.dependencies import get_current_user, require_admin
from app.core.upload_security import validate_and_read_upload
from app.schemas.class_marks import (
    CreateExamRequest,
    UpdateExamRequest,
    ExamResponse,
    PublishExamResponse,
    ExamRosterMarksResponse,
    SaveMarksRequest,
    BulkMarksPreviewResponse,
    BulkMarksConfirmRequest,
    StudentMarksOverviewResponse,
)
from app.services.class_marks_service import (
    create_exam,
    get_exams_for_cohort,
    get_exam_by_id,
    update_exam,
    delete_exam,
    publish_exam,
    unpublish_exam,
    get_exam_roster_marks,
    save_exam_marks,
    get_student_marks_overview,
    _format_exam_response,
)
from app.services.excel_marks_service import (
    generate_marks_template,
    parse_and_preview_marks_excel,
    generate_marks_error_report,
)

router = APIRouter(tags=["Class Marks"])


# ─────────────────────────────────────────────────────────────────────────────
# Admin Endpoints: Exams Management
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/admin/marks/cohorts/{cohort_id}/exams", response_model=list[ExamResponse])
async def list_cohort_exams(
    cohort_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """List all exams for a specific class cohort in the admin's institution."""
    return await get_exams_for_cohort(admin_user, cohort_id, db)


@router.post("/admin/marks/exams", response_model=ExamResponse)
@limiter.limit("30/minute")
async def create_cohort_exam(
    request: Request,
    data: CreateExamRequest,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new draft exam for a class cohort."""
    return await create_exam(admin_user, data, db)


@router.get("/admin/marks/exams/{exam_id}", response_model=ExamResponse)
async def get_exam_details(
    exam_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get exam metadata."""
    exam = await get_exam_by_id(admin_user, exam_id, db)
    return _format_exam_response(exam)


@router.patch("/admin/marks/exams/{exam_id}", response_model=ExamResponse)
async def update_cohort_exam(
    exam_id: UUID,
    data: UpdateExamRequest,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Update exam metadata.
    Enforces that max_marks cannot be reduced below any already recorded mark.
    """
    return await update_exam(admin_user, exam_id, data, db)


@router.delete("/admin/marks/exams/{exam_id}")
async def delete_cohort_exam(
    exam_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a draft exam.
    Published exams can NEVER be deleted (they must be unpublished instead).
    """
    return await delete_exam(admin_user, exam_id, db)


@router.post("/admin/marks/exams/{exam_id}/publish", response_model=PublishExamResponse)
async def publish_cohort_exam(
    exam_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Publish an exam to make marks visible to students.
    Returns warning messages if any active students currently have no mark entered.
    """
    return await publish_exam(admin_user, exam_id, db)


@router.post("/admin/marks/exams/{exam_id}/unpublish", response_model=ExamResponse)
async def unpublish_cohort_exam(
    exam_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Unpublish an exam, immediately hiding it from the student view."""
    return await unpublish_exam(admin_user, exam_id, db)


# ─────────────────────────────────────────────────────────────────────────────
# Admin Endpoints: Marks Entry & Excel Workflows
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/admin/marks/exams/{exam_id}/roster", response_model=ExamRosterMarksResponse)
async def get_roster_marks(
    exam_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Fetch class roster with existing marks and absent flags for an exam."""
    return await get_exam_roster_marks(admin_user, exam_id, db)


@router.post("/admin/marks/exams/{exam_id}/marks")
@limiter.limit("60/minute")
async def save_roster_marks(
    request: Request,
    exam_id: UUID,
    data: SaveMarksRequest,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Save or update marks for students in an exam.
    If the exam is published, a non-empty 'reason' is required and change logs are recorded.
    """
    return await save_exam_marks(admin_user, exam_id, data, db)


@router.get("/admin/marks/exams/{exam_id}/template")
async def download_marks_template(
    exam_id: UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Download an Excel (.xlsx) template prefilled with the active students of this cohort.
    Includes formula injection protection.
    """
    exam = await get_exam_by_id(admin_user, exam_id, db)
    cohort = await db.get(Cohort, exam.cohort_id)

    st_stmt = (
        select(User)
        .where(
            User.cohort_id == exam.cohort_id,
            User.is_active == True,
            User.archived_at == None,
        )
        .order_by(User.full_name, User.username)
    )
    res = await db.execute(st_stmt)
    students = res.scalars().all()

    file_bytes = generate_marks_template(cohort, exam, students)
    filename = f"marks_template_{cohort.name}_{exam.title}.xlsx".replace(" ", "_")

    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/admin/marks/exams/{exam_id}/preview", response_model=BulkMarksPreviewResponse)
@limiter.limit("20/minute")
async def preview_marks_upload(
    request: Request,
    exam_id: UUID,
    file: UploadFile = File(...),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload and parse an Excel sheet of marks without writing to the database.
    Validates each row against active students and returns valid/invalid rows.
    """
    exam = await get_exam_by_id(admin_user, exam_id, db)
    cohort = await db.get(Cohort, exam.cohort_id)

    # Validate upload (.xlsx only, max 2MB)
    file_bytes, ext = await validate_and_read_upload(
        file=file,
        request=request,
        allowed_extensions={"xlsx"},
        max_size_mb=2,
    )

    st_stmt = select(User).where(
        User.cohort_id == exam.cohort_id,
        User.is_active == True,
        User.archived_at == None,
    )
    res = await db.execute(st_stmt)
    active_students = res.scalars().all()

    try:
        valid_rows, invalid_rows = parse_and_preview_marks_excel(
            file_bytes=file_bytes,
            exam=exam,
            cohort=cohort,
            active_students=active_students,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return BulkMarksPreviewResponse(
        exam_id=exam.id,
        total_rows=len(valid_rows) + len(invalid_rows),
        valid_rows_count=len(valid_rows),
        invalid_rows_count=len(invalid_rows),
        valid_rows=valid_rows,
        invalid_rows=invalid_rows,
        error_report_available=len(invalid_rows) > 0,
    )


@router.post("/admin/marks/exams/{exam_id}/error-report")
async def download_marks_error_report(
    exam_id: UUID,
    invalid_rows: list[dict],
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Download an Excel spreadsheet listing rejected rows and error reasons."""
    await get_exam_by_id(admin_user, exam_id, db)
    file_bytes = generate_marks_error_report(invalid_rows)
    return Response(
        content=file_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="marks_upload_errors.xlsx"'},
    )


@router.post("/admin/marks/exams/{exam_id}/confirm")
@limiter.limit("20/minute")
async def confirm_bulk_marks(
    request: Request,
    exam_id: UUID,
    payload: BulkMarksConfirmRequest,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirm and save marks from a previewed Excel sheet.
    Re-validates every row independently against the database state (never trusts client preview).
    All-or-Nothing transaction.
    """
    save_req = SaveMarksRequest(marks=payload.rows, reason=payload.reason)
    return await save_exam_marks(admin_user, exam_id, save_req, db)


# ─────────────────────────────────────────────────────────────────────────────
# Student Endpoints: Read-Only Marks View
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/student/marks", response_model=StudentMarksOverviewResponse)
async def get_student_marks(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Read-only endpoint for students.
    Returns published exams for the student's current active class cohort only.
    Shows the student's own marks only — no ranks, averages, or other students' marks.
    Students not enrolled in a class receive a clean empty result.
    """
    if current_user.role != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only students can access this endpoint.",
        )
    return await get_student_marks_overview(current_user, db)
