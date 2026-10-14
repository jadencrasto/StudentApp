import base64
import uuid
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_
from slowapi.util import get_remote_address

from app.core.rate_limiter import limiter
from app.database import get_db
from app.models.user import User
from app.models.institution import Cohort
from app.core.dependencies import require_admin, get_admin_institution_id
from app.core.security import hash_password
from app.schemas.schemas import (
    StudentCreateRequest,
    StudentOut,
    StudentListResponse,
    StudentMoveClassRequest,
    StudentBulkPreviewResponse,
    StudentBulkConfirmRequest,
    StudentBulkConfirmResponse,
    StudentCredentialsItem,
    StudentCredentialsOut,
)
from app.services.excel_student_service import (
    generate_temporary_password,
    generate_unique_username,
    generate_student_template_xlsx,
    parse_and_preview_students_xlsx,
    generate_bad_rows_xlsx,
    generate_credentials_xlsx,
    EMAIL_REGEX,
)

router = APIRouter(prefix="/admin/students", tags=["Admin Student Management"])


async def get_admin_student_or_404(
    student_id: UUID,
    admin_institution_id: UUID,
    db: AsyncSession,
) -> User:
    """
    CRITICAL REQUIREMENT 5:
    All /admin/students/{id} endpoints must only act on users with role=student
    in the admin's own institution. Return 404 otherwise.
    """
    user = await db.get(User, student_id)
    if (
        user is None
        or user.role != "student"
        or user.institution_id != admin_institution_id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student not found",
        )
    return user


async def build_student_out(student: User, db: AsyncSession) -> StudentOut:
    cohort_name = None
    if student.cohort_id:
        cohort = await db.get(Cohort, student.cohort_id)
        if cohort:
            cohort_name = cohort.name

    return StudentOut(
        id=student.id,
        email=student.email,
        username=student.username,
        full_name=student.full_name,
        role=student.role,
        institution_id=student.institution_id,
        cohort_id=student.cohort_id,
        cohort_name=cohort_name,
        is_active=student.is_active,
        must_change_password=student.must_change_password,
        created_by_admin=student.created_by_admin,
        created_at=student.created_at,
        archived_at=student.archived_at,
    )


@router.get("", response_model=StudentListResponse)
async def list_students(
    search: str | None = None,
    cohort_id: UUID | None = None,
    is_active: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    current_admin: User = Depends(require_admin),
    institution_id: UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """
    List students belonging to the admin's institution with search, filter, and pagination.
    """
    base_query = select(User).where(
        User.institution_id == institution_id,
        User.role == "student",
    )

    if cohort_id:
        base_query = base_query.where(User.cohort_id == cohort_id)

    if is_active is not None:
        base_query = base_query.where(User.is_active == is_active)

    if search:
        s = f"%{search.strip().lower()}%"
        base_query = base_query.where(
            or_(
                func.lower(User.full_name).ilike(s),
                func.lower(User.email).ilike(s),
                func.lower(User.username).ilike(s),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(base_query.subquery())
    total = (await db.scalar(count_stmt)) or 0

    # Paginate
    offset = (page - 1) * page_size
    stmt = base_query.order_by(User.created_at.desc()).offset(offset).limit(page_size)
    students = (await db.execute(stmt)).scalars().all()

    # Pre-fetch cohorts for efficient naming
    cohort_ids = {s.cohort_id for s in students if s.cohort_id}
    cohort_map = {}
    if cohort_ids:
        c_res = await db.execute(select(Cohort).where(Cohort.id.in_(cohort_ids)))
        cohort_map = {c.id: c.name for c in c_res.scalars().all()}

    items = [
        StudentOut(
            id=s.id,
            email=s.email,
            username=s.username,
            full_name=s.full_name,
            role=s.role,
            institution_id=s.institution_id,
            cohort_id=s.cohort_id,
            cohort_name=cohort_map.get(s.cohort_id),
            is_active=s.is_active,
            must_change_password=s.must_change_password,
            created_by_admin=s.created_by_admin,
            created_at=s.created_at,
            archived_at=s.archived_at,
        )
        for s in students
    ]

    total_pages = (total + page_size - 1) // page_size if total > 0 else 1

    return StudentListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.post("", response_model=StudentCredentialsOut, status_code=status.HTTP_201_CREATED)
async def create_single_student(
    data: StudentCreateRequest,
    current_admin: User = Depends(require_admin),
    institution_id: UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a single student:
    - Enforces unique email system-wide.
    - Enforces cohort belongs to admin's institution and is active.
    - Generates unique username.
    - Generates strong temporary password starting with an ASCII letter.
    - Marks onboarding_completed=True, created_by_admin=True, must_change_password=True.
    - Returns credentials once.
    """
    cohort = await db.get(Cohort, data.cohort_id)
    if not cohort or cohort.institution_id != institution_id or not cohort.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid class or class does not belong to your institution",
        )

    norm_email = data.email.strip().lower()
    existing_user = await db.scalar(select(User.id).where(User.email == norm_email))
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered in the system",
        )

    username = await generate_unique_username(data.full_name, db)
    temp_password = generate_temporary_password(12)

    student_id = uuid.uuid4()
    student = User(
        id=student_id,
        email=norm_email,
        username=username,
        full_name=data.full_name.strip(),
        hashed_password=hash_password(temp_password),
        role="student",
        institution_id=institution_id,
        cohort_id=cohort.id,
        is_active=True,
        must_change_password=True,
        onboarding_completed=True,  # Requirement 6: fully approved
        created_by_admin=True,
        password_changed_at=datetime.utcnow(),
        token_version=1,
    )

    db.add(student)
    await db.commit()
    await db.refresh(student)

    return StudentCredentialsOut(
        id=student.id,
        full_name=student.full_name,
        email=student.email,
        username=student.username,
        temporary_password=temp_password,
        class_name=cohort.name,
    )


@router.get("/template")
async def download_template(
    current_admin: User = Depends(require_admin),
):
    """
    Download a sample Excel (.xlsx) template for student batch upload.
    Requirement 3: Cache-Control: no-store
    """
    xlsx_bytes = generate_student_template_xlsx()
    return Response(
        content=xlsx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="students_template.xlsx"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/upload-preview", response_model=StudentBulkPreviewResponse)
@limiter.limit("10/minute", key_func=get_remote_address)
async def upload_preview(
    request: Request,
    file: UploadFile = File(...),
    current_admin: User = Depends(require_admin),
    institution_id: UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload and preview .xlsx without saving to DB.
    Rate limited to 10 per minute. Max 2MB, max 500 rows.
    """
    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .xlsx Excel files are supported",
        )

    file_bytes = await file.read()
    if len(file_bytes) > 2 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds maximum 2 MB limit",
        )

    try:
        preview = await parse_and_preview_students_xlsx(file_bytes, institution_id, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    return preview


@router.post("/upload-confirm", response_model=StudentBulkConfirmResponse)
@limiter.limit("10/minute", key_func=get_remote_address)
async def upload_confirm(
    request: Request,
    payload: StudentBulkConfirmRequest,
    current_admin: User = Depends(require_admin),
    institution_id: UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Commit validated students to database:
    CRITICAL REQUIREMENT 1: Must RE-VALIDATE every single row on the server
    (email unique, class belongs to this admin's institution). Never trust client preview.
    Rate limited to 10 per minute.
    Requirement 3: In-memory credentials workbook returned once with Cache-Control: no-store.
    """
    if not payload.rows:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No student rows provided for confirmation",
        )

    if len(payload.rows) > 500:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Batch exceeds maximum limit of 500 students",
        )

    # 1. Fetch all active cohorts for this institution to re-validate
    cohort_stmt = select(Cohort).where(
        Cohort.institution_id == institution_id,
        Cohort.is_active == True,
    )
    c_res = await db.execute(cohort_stmt)
    cohort_map = {c.id: c for c in c_res.scalars().all()}

    # 2. Check existing emails in DB in bulk
    batch_emails = [r.email.strip().lower() for r in payload.rows if r.email]
    db_emails_stmt = select(User.email).where(User.email.in_(batch_emails))
    db_res = await db.execute(db_emails_stmt)
    existing_emails_in_db = {row[0].lower() for row in db_res.all()}

    seen_batch_emails = set()
    reserved_usernames = set()
    created_credentials = []

    for row in payload.rows:
        name_str = row.full_name.strip()
        email_str = row.email.strip().lower()
        cohort_id = row.cohort_id

        # Server-side re-validation
        if not name_str or not email_str:
            continue
        if not EMAIL_REGEX.match(email_str):
            continue
        if email_str in seen_batch_emails or email_str in existing_emails_in_db:
            continue

        cohort = cohort_map.get(cohort_id)
        if not cohort:
            continue

        seen_batch_emails.add(email_str)

        # Generate unique username and letter-starting temporary password
        username = await generate_unique_username(name_str, db, reserved_usernames)
        temp_pwd = generate_temporary_password(12)

        student_id = uuid.uuid4()
        student = User(
            id=student_id,
            email=email_str,
            username=username,
            full_name=name_str,
            hashed_password=hash_password(temp_pwd),
            role="student",
            institution_id=institution_id,
            cohort_id=cohort.id,
            is_active=True,
            must_change_password=True,
            onboarding_completed=True,  # Requirement 6: fully approved
            created_by_admin=True,
            password_changed_at=datetime.utcnow(),
            token_version=1,
        )
        db.add(student)

        created_credentials.append({
            "id": student_id,
            "full_name": name_str,
            "email": email_str,
            "username": username,
            "temporary_password": temp_pwd,
            "class_name": cohort.name,
        })

    if not created_credentials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="None of the submitted rows passed server validation (e.g. duplicate emails or invalid classes)",
        )

    await db.commit()

    # Generate one-time in-memory credentials workbook
    excel_bytes = generate_credentials_xlsx(created_credentials)
    b64_workbook = base64.b64encode(excel_bytes).decode("ascii")

    return StudentBulkConfirmResponse(
        created_count=len(created_credentials),
        credentials=[
            StudentCredentialsItem(
                id=c["id"],
                full_name=c["full_name"],
                email=c["email"],
                username=c["username"],
                temporary_password=c["temporary_password"],
                class_name=c["class_name"],
            )
            for c in created_credentials
        ],
        credentials_file_b64=b64_workbook,
    )


@router.post("/error-report")
async def download_error_report(
    bad_rows: list[dict],
    current_admin: User = Depends(require_admin),
):
    """
    Download error report of invalid rows.
    Requirement 3: Cache-Control: no-store
    """
    excel_bytes = generate_bad_rows_xlsx(bad_rows)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="upload_errors.xlsx"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/{student_id}/reset-password")
@limiter.limit("10/minute", key_func=get_remote_address)
async def reset_student_password(
    request: Request,
    student_id: UUID,
    current_admin: User = Depends(require_admin),
    institution_id: UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Reset student's password:
    - REQUIREMENT 5: Must only act on users with role=student in admin's own institution (404 otherwise).
    - REQUIREMENT 2: Temporary password must start with an ASCII letter.
    - REQUIREMENT 4: Must invalidate existing logins (bumps token_version and updates password_changed_at).
    - Rate limited to 10 per minute.
    """
    student = await get_admin_student_or_404(student_id, institution_id, db)

    temp_password = generate_temporary_password(12)
    student.hashed_password = hash_password(temp_password)
    student.must_change_password = True
    student.password_changed_at = datetime.utcnow()
    student.token_version = (student.token_version or 1) + 1  # Invalidates current JWT sessions

    await db.commit()

    return {
        "temporary_password": temp_password,
        "message": "Temporary password has been set. The student must change it on their next login.",
    }


@router.patch("/{student_id}/deactivate", response_model=StudentOut)
async def deactivate_student(
    student_id: UUID,
    current_admin: User = Depends(require_admin),
    institution_id: UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Deactivate student:
    - REQUIREMENT 5: Only act on role=student in admin's institution (404 otherwise).
    - REQUIREMENT 4: Must invalidate existing logins (sets is_active=False and bumps token_version).
    - Archives rather than hard deleting.
    """
    student = await get_admin_student_or_404(student_id, institution_id, db)

    student.is_active = False
    student.archived_at = datetime.utcnow()
    student.token_version = (student.token_version or 1) + 1  # Invalidate current session

    await db.commit()
    await db.refresh(student)

    return await build_student_out(student, db)


@router.patch("/{student_id}/reactivate", response_model=StudentOut)
async def reactivate_student(
    student_id: UUID,
    current_admin: User = Depends(require_admin),
    institution_id: UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Reactivate student:
    - REQUIREMENT 5: Only act on role=student in admin's institution (404 otherwise).
    - Sets is_active=True and unarchives.
    """
    student = await get_admin_student_or_404(student_id, institution_id, db)

    student.is_active = True
    student.archived_at = None

    await db.commit()
    await db.refresh(student)

    return await build_student_out(student, db)


@router.patch("/{student_id}/move-cohort", response_model=StudentOut)
async def move_student_cohort(
    student_id: UUID,
    payload: StudentMoveClassRequest,
    current_admin: User = Depends(require_admin),
    institution_id: UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Move student to another class within the admin's institution:
    - REQUIREMENT 5: Only act on role=student in admin's institution (404 otherwise).
    - Ensures target cohort belongs to the same institution.
    """
    student = await get_admin_student_or_404(student_id, institution_id, db)

    target_cohort = await db.get(Cohort, payload.cohort_id)
    if not target_cohort or target_cohort.institution_id != institution_id or not target_cohort.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Target class does not belong to your institution or is inactive",
        )

    student.cohort_id = target_cohort.id
    await db.commit()
    await db.refresh(student)

    return await build_student_out(student, db)
