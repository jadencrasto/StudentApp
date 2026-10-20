from __future__ import annotations

from uuid import UUID
from datetime import datetime, timezone
from decimal import Decimal
from typing import Sequence

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, desc

from app.models.user import User
from app.models.institution import Cohort
from app.models.class_marks import Exam, Mark, MarkChangeRecord
from app.schemas.class_marks import (
    CreateExamRequest,
    UpdateExamRequest,
    ExamResponse,
    PublishExamResponse,
    StudentMarkItem,
    StudentMarkEntryInput,
    SaveMarksRequest,
    ExamRosterMarksResponse,
    StudentExamMarkResponse,
    StudentMarksOverviewResponse,
)


def _normalize_string(val: str) -> str:
    """Trim and lowercase for unique constraint enforcement."""
    return val.strip().lower()


def _format_exam_response(exam: Exam, cohort_name: str | None = None, counts: dict | None = None) -> ExamResponse:
    """Build an ExamResponse from an Exam ORM object.

    ``cohort_name`` MUST be supplied by the caller — it must never be resolved
    via ``exam.cohort.name`` because that triggers a lazy load which raises
    ``MissingGreenlet`` in async SQLAlchemy after commit / outside the query
    context.
    """
    c = counts or {}
    return ExamResponse(
        id=exam.id,
        institution_id=exam.institution_id,
        cohort_id=exam.cohort_id,
        cohort_name=cohort_name,
        exam_type=exam.exam_type,
        title=exam.title,
        subject=exam.subject,
        max_marks=exam.max_marks,
        exam_date=exam.exam_date,
        status=exam.status,
        published_at=exam.published_at,
        created_at=exam.created_at,
        updated_at=exam.updated_at,
        total_students=c.get("total", 0),
        graded_count=c.get("graded", 0),
        absent_count=c.get("absent", 0),
        unentered_count=c.get("unentered", 0),
    )


async def create_exam(
    admin_user: User,
    data: CreateExamRequest,
    db: AsyncSession,
) -> ExamResponse:
    # 1. Tenancy check
    cohort = await db.get(Cohort, data.cohort_id)
    if not cohort or cohort.institution_id != admin_user.institution_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class cohort not found in your institution.",
        )

    norm_title = _normalize_string(data.title)
    norm_subject = _normalize_string(data.subject)
    norm_type = _normalize_string(data.exam_type)

    # 2. Duplicate exam check (same cohort + type + title + subject)
    dup_stmt = select(Exam).where(
        Exam.cohort_id == data.cohort_id,
        Exam.exam_type == norm_type,
        Exam.title_normalized == norm_title,
        Exam.subject_normalized == norm_subject,
    )
    existing = await db.scalar(dup_stmt)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"An exam with title '{data.title}' and subject '{data.subject}' ({data.exam_type}) already exists for this class.",
        )

    new_exam = Exam(
        institution_id=admin_user.institution_id,
        cohort_id=data.cohort_id,
        exam_type=norm_type,
        title=data.title.strip(),
        title_normalized=norm_title,
        subject=data.subject.strip(),
        subject_normalized=norm_subject,
        max_marks=data.max_marks,
        exam_date=data.exam_date,
        status="draft",
        created_by=admin_user.id,
    )
    db.add(new_exam)
    await db.commit()
    await db.refresh(new_exam)

    # Count active students in cohort
    count_stmt = select(func.count(User.id)).where(
        User.cohort_id == cohort.id,
        User.is_active == True,
        User.archived_at == None,
    )
    active_count = await db.scalar(count_stmt) or 0

    return _format_exam_response(new_exam, cohort_name=cohort.name, counts={
        "total": active_count,
        "graded": 0,
        "absent": 0,
        "unentered": active_count,
    })


async def get_exams_for_cohort(
    admin_user: User,
    cohort_id: UUID,
    db: AsyncSession,
) -> list[ExamResponse]:
    cohort = await db.get(Cohort, cohort_id)
    if not cohort or cohort.institution_id != admin_user.institution_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Class cohort not found in your institution.",
        )

    # Fetch active students in this cohort
    active_students_stmt = select(User.id).where(
        User.cohort_id == cohort_id,
        User.is_active == True,
        User.archived_at == None,
    )
    active_res = await db.execute(active_students_stmt)
    active_student_ids = set(active_res.scalars().all())
    total_active = len(active_student_ids)

    # Fetch all exams for this cohort
    exams_stmt = (
        select(Exam)
        .where(Exam.cohort_id == cohort_id)
        .order_by(desc(Exam.exam_date), desc(Exam.created_at))
    )
    res = await db.execute(exams_stmt)
    exams = res.scalars().all()

    # Pre-fetch mark counts per exam for active students
    responses: list[ExamResponse] = []
    for exam in exams:
        marks_stmt = select(Mark).where(
            Mark.exam_id == exam.id,
            Mark.student_id.in_(active_student_ids) if active_student_ids else False,
        )
        marks_res = await db.execute(marks_stmt)
        marks_list = marks_res.scalars().all()

        graded = sum(1 for m in marks_list if not m.is_absent and m.marks_obtained is not None)
        absent = sum(1 for m in marks_list if m.is_absent)
        unentered = max(0, total_active - (graded + absent))

        responses.append(_format_exam_response(
            exam,
            cohort_name=cohort.name,
            counts={
                "total": total_active,
                "graded": graded,
                "absent": absent,
                "unentered": unentered,
            },
        ))

    return responses


async def get_exam_by_id(
    admin_user: User,
    exam_id: UUID,
    db: AsyncSession,
) -> Exam:
    exam = await db.get(Exam, exam_id)
    if not exam or exam.institution_id != admin_user.institution_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Exam not found in your institution.",
        )
    return exam


async def update_exam(
    admin_user: User,
    exam_id: UUID,
    data: UpdateExamRequest,
    db: AsyncSession,
) -> ExamResponse:
    exam = await get_exam_by_id(admin_user, exam_id, db)

    # Load cohort name BEFORE commit so we never lazy-load after commit
    cohort = await db.get(Cohort, exam.cohort_id)
    cohort_name = cohort.name if cohort else None

    # 1. Check max_marks constraint: max marks can never be lowered below any existing mark
    if data.max_marks is not None and data.max_marks != exam.max_marks:
        highest_mark_stmt = select(func.max(Mark.marks_obtained)).where(
            Mark.exam_id == exam_id,
            Mark.marks_obtained != None,
        )
        highest_mark = await db.scalar(highest_mark_stmt)
        if highest_mark is not None and data.max_marks < highest_mark:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reduce max marks to {data.max_marks} because an existing student mark is {highest_mark}.",
            )
        exam.max_marks = data.max_marks

    # 2. Check duplicate constraint if title, subject, or type are being updated
    new_title = data.title.strip() if data.title else exam.title
    new_subject = data.subject.strip() if data.subject else exam.subject
    new_type = _normalize_string(data.exam_type) if data.exam_type else exam.exam_type

    norm_title = _normalize_string(new_title)
    norm_subject = _normalize_string(new_subject)

    if (
        norm_title != exam.title_normalized
        or norm_subject != exam.subject_normalized
        or new_type != exam.exam_type
    ):
        dup_stmt = select(Exam).where(
            Exam.cohort_id == exam.cohort_id,
            Exam.exam_type == new_type,
            Exam.title_normalized == norm_title,
            Exam.subject_normalized == norm_subject,
            Exam.id != exam.id,
        )
        existing = await db.scalar(dup_stmt)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"An exam with title '{new_title}' and subject '{new_subject}' ({new_type}) already exists for this class.",
            )

        exam.title = new_title
        exam.title_normalized = norm_title
        exam.subject = new_subject
        exam.subject_normalized = norm_subject
        exam.exam_type = new_type

    if data.exam_date is not None:
        exam.exam_date = data.exam_date

    exam.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(exam)

    return _format_exam_response(exam, cohort_name=cohort_name)


async def delete_exam(
    admin_user: User,
    exam_id: UUID,
    db: AsyncSession,
) -> dict:
    exam = await get_exam_by_id(admin_user, exam_id, db)

    # RULE: Published exams can be unpublished but NEVER hard-deleted.
    if exam.status == "published" or exam.published_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Published exams cannot be deleted. You can unpublish the exam instead.",
        )

    await db.delete(exam)
    await db.commit()
    return {"message": "Draft exam deleted successfully."}


async def publish_exam(
    admin_user: User,
    exam_id: UUID,
    db: AsyncSession,
) -> PublishExamResponse:
    exam = await get_exam_by_id(admin_user, exam_id, db)

    # Load cohort name BEFORE commit so we never lazy-load after commit
    cohort = await db.get(Cohort, exam.cohort_id)
    cohort_name = cohort.name if cohort else None

    # Fetch active students in cohort
    active_stmt = select(User).where(
        User.cohort_id == exam.cohort_id,
        User.is_active == True,
        User.archived_at == None,
    )
    res = await db.execute(active_stmt)
    active_students = res.scalars().all()
    total_active = len(active_students)
    active_ids = {s.id for s in active_students}

    # Fetch existing marks for active students
    marks_stmt = select(Mark).where(
        Mark.exam_id == exam.id,
        Mark.student_id.in_(active_ids) if active_ids else False,
    )
    m_res = await db.execute(marks_stmt)
    existing_marks = m_res.scalars().all()

    entered_ids = {
        m.student_id for m in existing_marks
        if m.is_absent or m.marks_obtained is not None
    }
    missing_count = total_active - len(entered_ids)

    warnings: list[str] = []
    if missing_count > 0:
        warnings.append(
            f"{missing_count} student{'' if missing_count == 1 else 's'} currently have no marks entered. They will see 'Not entered yet'."
        )

    exam.status = "published"
    exam.published_at = datetime.now(timezone.utc)
    exam.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(exam)

    counts = {
        "total": total_active,
        "graded": sum(1 for m in existing_marks if not m.is_absent and m.marks_obtained is not None),
        "absent": sum(1 for m in existing_marks if m.is_absent),
        "unentered": max(0, missing_count),
    }

    return PublishExamResponse(
        exam=_format_exam_response(exam, cohort_name=cohort_name, counts=counts),
        warnings=warnings,
    )


async def unpublish_exam(
    admin_user: User,
    exam_id: UUID,
    db: AsyncSession,
) -> ExamResponse:
    exam = await get_exam_by_id(admin_user, exam_id, db)

    # Load cohort name BEFORE commit so we never lazy-load after commit
    cohort = await db.get(Cohort, exam.cohort_id)
    cohort_name = cohort.name if cohort else None

    exam.status = "draft"
    exam.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(exam)

    return _format_exam_response(exam, cohort_name=cohort_name)


async def get_exam_roster_marks(
    admin_user: User,
    exam_id: UUID,
    db: AsyncSession,
) -> ExamRosterMarksResponse:
    exam = await get_exam_by_id(admin_user, exam_id, db)
    cohort = await db.get(Cohort, exam.cohort_id)

    # Fetch active students of cohort
    active_stmt = (
        select(User)
        .where(
            User.cohort_id == exam.cohort_id,
            User.is_active == True,
            User.archived_at == None,
        )
        .order_by(User.full_name, User.username)
    )
    s_res = await db.execute(active_stmt)
    active_students = s_res.scalars().all()

    # Fetch existing marks
    marks_stmt = select(Mark).where(Mark.exam_id == exam.id)
    m_res = await db.execute(marks_stmt)
    mark_by_student_id = {m.student_id: m for m in m_res.scalars().all()}

    student_items: list[StudentMarkItem] = []
    graded_count = 0
    absent_count = 0
    unentered_count = 0

    for st in active_students:
        mark = mark_by_student_id.get(st.id)
        if mark and mark.is_absent:
            absent_count += 1
            student_items.append(StudentMarkItem(
                student_id=st.id,
                student_name=st.full_name,
                student_email=st.email,
                student_username=st.username,
                marks_obtained=None,
                is_absent=True,
                percentage=None,
                status="absent",
            ))
        elif mark and mark.marks_obtained is not None:
            graded_count += 1
            pct = round((mark.marks_obtained / exam.max_marks) * 100, 2)
            student_items.append(StudentMarkItem(
                student_id=st.id,
                student_name=st.full_name,
                student_email=st.email,
                student_username=st.username,
                marks_obtained=mark.marks_obtained,
                is_absent=False,
                percentage=pct,
                status="graded",
            ))
        else:
            unentered_count += 1
            student_items.append(StudentMarkItem(
                student_id=st.id,
                student_name=st.full_name,
                student_email=st.email,
                student_username=st.username,
                marks_obtained=None,
                is_absent=False,
                percentage=None,
                status="not_entered",
            ))

    counts = {
        "total": len(active_students),
        "graded": graded_count,
        "absent": absent_count,
        "unentered": unentered_count,
    }

    return ExamRosterMarksResponse(
        exam=_format_exam_response(exam, cohort_name=cohort.name if cohort else None, counts=counts),
        students=student_items,
    )


async def save_exam_marks(
    admin_user: User,
    exam_id: UUID,
    data: SaveMarksRequest,
    db: AsyncSession,
) -> dict:
    """
    Save or update marks for students in an exam.
    Enforces:
    - All-or-Nothing transaction.
    - Tenant isolation.
    - Student active & cohort enrollment checks.
    - Marks must be <= exam.max_marks.
    - If exam is published, any mark change requires a reason and writes MarkChangeRecord.
    """
    exam = await get_exam_by_id(admin_user, exam_id, db)

    # 1. Check duplicate student IDs in input
    student_ids = [m.student_id for m in data.marks]
    if len(student_ids) != len(set(student_ids)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Duplicate student records found in input.",
        )

    # 2. Fetch students in batch to validate
    st_stmt = select(User).where(User.id.in_(student_ids)) if student_ids else None
    if st_stmt is not None:
        st_res = await db.execute(st_stmt)
        student_map = {s.id: s for s in st_res.scalars().all()}
    else:
        student_map = {}

    for item in data.marks:
        student = student_map.get(item.student_id)
        if not student:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Student ID '{item.student_id}' does not exist.",
            )
        if not student.is_active or student.archived_at is not None:
            name = student.full_name or student.username or str(student.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Student '{name}' is deactivated or archived.",
            )
        if student.institution_id != admin_user.institution_id:
            name = student.full_name or student.username or str(student.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Student '{name}' does not belong to your institution.",
            )
        if student.cohort_id != exam.cohort_id:
            name = student.full_name or student.username or str(student.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Student '{name}' is not currently enrolled in this class cohort.",
            )

        # Marks validation
        if not item.is_absent and item.marks_obtained is not None:
            if item.marks_obtained < 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Marks obtained cannot be negative for student '{student.full_name or student.username}'.",
                )
            if item.marks_obtained > exam.max_marks:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Marks ({item.marks_obtained}) exceed maximum allowed ({exam.max_marks}) for student '{student.full_name or student.username}'.",
                )

    # 3. Fetch existing marks to detect modifications
    existing_marks_stmt = select(Mark).where(
        Mark.exam_id == exam.id,
        Mark.student_id.in_(student_ids) if student_ids else False,
    )
    em_res = await db.execute(existing_marks_stmt)
    existing_marks_map = {m.student_id: m for m in em_res.scalars().all()}

    is_published = (exam.status == "published")
    reason_clean = (data.reason or "").strip()

    # Pre-check if any value actually changes for a published exam and verify reason
    changed_items: list[tuple[StudentMarkEntryInput, Mark | None]] = []
    for item in data.marks:
        existing = existing_marks_map.get(item.student_id)
        target_marks = None if item.is_absent else item.marks_obtained
        target_absent = item.is_absent

        if existing is None:
            if target_marks is not None or target_absent:
                changed_items.append((item, None))
        else:
            if existing.marks_obtained != target_marks or existing.is_absent != target_absent:
                changed_items.append((item, existing))

    if is_published and changed_items:
        if not reason_clean:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Editing marks for a published exam requires a reason for the audit log.",
            )

    now_utc = datetime.now(timezone.utc)
    created_count = 0
    updated_count = 0

    for item, existing in changed_items:
        target_marks = None if item.is_absent else item.marks_obtained
        target_absent = item.is_absent

        if existing is None:
            new_mark = Mark(
                exam_id=exam.id,
                student_id=item.student_id,
                marks_obtained=target_marks,
                is_absent=target_absent,
                entered_by=admin_user.id,
                created_at=now_utc,
                updated_at=now_utc,
            )
            db.add(new_mark)
            await db.flush()
            created_count += 1

            if is_published and reason_clean:
                change_rec = MarkChangeRecord(
                    mark_id=new_mark.id,
                    exam_id=exam.id,
                    student_id=item.student_id,
                    changed_by=admin_user.id,
                    previous_marks=None,
                    new_marks=target_marks,
                    previous_absent=False,
                    new_absent=target_absent,
                    reason=reason_clean,
                    changed_at=now_utc,
                )
                db.add(change_rec)
        else:
            prev_marks = existing.marks_obtained
            prev_absent = existing.is_absent

            existing.marks_obtained = target_marks
            existing.is_absent = target_absent
            existing.entered_by = admin_user.id
            existing.updated_at = now_utc
            updated_count += 1

            if is_published and reason_clean:
                change_rec = MarkChangeRecord(
                    mark_id=existing.id,
                    exam_id=exam.id,
                    student_id=item.student_id,
                    changed_by=admin_user.id,
                    previous_marks=prev_marks,
                    new_marks=target_marks,
                    previous_absent=prev_absent,
                    new_absent=target_absent,
                    reason=reason_clean,
                    changed_at=now_utc,
                )
                db.add(change_rec)

    exam.updated_at = now_utc
    await db.commit()

    return {
        "message": "Marks saved successfully.",
        "created": created_count,
        "updated": updated_count,
    }


async def get_student_marks_overview(
    student_user: User,
    db: AsyncSession,
) -> StudentMarksOverviewResponse:
    """
    Read-only view for enrolled students.
    Shows published exams of their current enrolled cohort ONLY.
    Shows student's own marks only — no ranks, averages, or other students' marks.
    If student is not in a cohort: returns clean empty result.
    If mark is not entered yet: returns 'not_entered' and 'Not entered yet', never 0.
    """
    if not student_user.cohort_id:
        return StudentMarksOverviewResponse(
            enrolled=False,
            cohort=None,
            exams=[],
            summary={
                "total_exams": 0,
                "completed_exams": 0,
                "overall_percentage": None,
            },
        )

    cohort = await db.get(Cohort, student_user.cohort_id)
    if not cohort:
        return StudentMarksOverviewResponse(
            enrolled=False,
            cohort=None,
            exams=[],
            summary={
                "total_exams": 0,
                "completed_exams": 0,
                "overall_percentage": None,
            },
        )

    # Query published exams for student's current cohort
    exams_stmt = (
        select(Exam)
        .where(
            Exam.cohort_id == student_user.cohort_id,
            Exam.status == "published",
        )
        .order_by(desc(Exam.exam_date), desc(Exam.published_at))
    )
    e_res = await db.execute(exams_stmt)
    published_exams = e_res.scalars().all()

    if not published_exams:
        return StudentMarksOverviewResponse(
            enrolled=True,
            cohort={"id": cohort.id, "name": cohort.name, "academic_year": cohort.academic_year},
            exams=[],
            summary={
                "total_exams": 0,
                "completed_exams": 0,
                "overall_percentage": None,
            },
        )

    exam_ids = [e.id for e in published_exams]
    marks_stmt = select(Mark).where(
        Mark.exam_id.in_(exam_ids),
        Mark.student_id == student_user.id,
    )
    m_res = await db.execute(marks_stmt)
    mark_by_exam_id = {m.exam_id: m for m in m_res.scalars().all()}

    student_exams: list[StudentExamMarkResponse] = []
    completed_percentages: list[Decimal] = []

    for ex in published_exams:
        mark = mark_by_exam_id.get(ex.id)

        if mark and mark.is_absent:
            status_val = "absent"
            marks_val = None
            pct_val = None
            disp = "Absent"
        elif mark and mark.marks_obtained is not None:
            status_val = "graded"
            marks_val = mark.marks_obtained
            pct_val = round((mark.marks_obtained / ex.max_marks) * 100, 2)
            disp = f"{marks_val} / {ex.max_marks}"
            completed_percentages.append(pct_val)
        else:
            status_val = "not_entered"
            marks_val = None
            pct_val = None
            disp = "Not entered yet"

        student_exams.append(StudentExamMarkResponse(
            exam_id=ex.id,
            exam_title=ex.title,
            exam_type=ex.exam_type,
            subject=ex.subject,
            max_marks=ex.max_marks,
            exam_date=ex.exam_date,
            marks_obtained=marks_val,
            is_absent=mark.is_absent if mark else False,
            percentage=pct_val,
            status=status_val,
            display_text=disp,
        ))

    overall_avg = None
    if completed_percentages:
        overall_avg = round(sum(completed_percentages) / len(completed_percentages), 2)

    return StudentMarksOverviewResponse(
        enrolled=True,
        cohort={"id": cohort.id, "name": cohort.name, "academic_year": cohort.academic_year},
        exams=student_exams,
        summary={
            "total_exams": len(published_exams),
            "completed_exams": len(completed_percentages),
            "overall_percentage": overall_avg,
        },
    )
