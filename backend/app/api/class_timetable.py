"""
Phase 6C — Admin and Student Class Timetable API.

Endpoints:
- POST   /api/v1/admin/cohorts/{cohort_id}/timetable/extract
- GET    /api/v1/admin/cohorts/{cohort_id}/timetable
- GET    /api/v1/admin/cohorts/{cohort_id}/timetable/draft
- PUT    /api/v1/admin/cohorts/{cohort_id}/timetable/draft
- DELETE /api/v1/admin/cohorts/{cohort_id}/timetable/draft
- POST   /api/v1/admin/cohorts/{cohort_id}/timetable/publish
- POST   /api/v1/admin/cohorts/{cohort_id}/timetable/edit-published
- GET    /api/v1/admin/cohorts/{cohort_id}/timetable/suggested-subjects
- GET    /api/v1/student/class-timetable
"""
import os
import uuid
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, require_admin
from app.core.rate_limiter import ai_extraction_tracker, limiter
from app.database import get_db
from app.models.class_timetable import ClassTimetable
from app.models.institution import Cohort
from app.models.user import User
from app.schemas.class_timetable import (
    ClassTimetableOut,
    DraftResponse,
    ExtractTimetableResponse,
    PublishRequest,
    SaveDraftRequest,
    StudentClassTimetableResponse,
    TimetableOverviewResponse,
)
from app.services.class_timetable_service import (
    cleanup_stored_image,
    discard_draft_timetable,
    edit_published_timetable,
    extract_timetable_from_image,
    get_cohort_and_verify_admin,
    get_draft_timetable,
    get_published_timetable,
    get_suggested_subjects,
    publish_draft_timetable,
    save_or_update_draft,
    validate_and_reencode_image,
)

router = APIRouter(tags=["Class Timetable"])

ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


# ─────────────────────────────────────────────────────────────────────────
# Admin Timetable Management Endpoints
# ─────────────────────────────────────────────────────────────────────────

@router.post(
    "/admin/cohorts/{cohort_id}/timetable/extract",
    response_model=ExtractTimetableResponse,
)
async def extract_timetable(
    cohort_id: uuid.UUID,
    file: UploadFile = File(...),
    replace_draft: bool = Query(
        False,
        description="Whether to replace an existing draft timetable if one already exists",
    ),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a class timetable image (PNG/JPG), re-encode with Pillow, enforce dimension bounds,
    and run AI extraction (Gemini Vision with Tesseract OCR fallback).
    Enforces a server-side limit of 5 AI extractions per hour per admin.
    """
    # 1. Verify cohort and administrative ownership
    cohort = await get_cohort_and_verify_admin(cohort_id, admin_user, db)

    # 2. Check server-side rate limit (5 attempts per hour per admin)
    if ai_extraction_tracker.is_rate_limited(str(admin_user.id), limit=5, window_seconds=3600):
        raise HTTPException(
            status_code=429,
            detail="AI extraction rate limit reached (5 attempts per hour). Please try again later or enter classes manually.",
        )

    # 3. Extension & MIME validation
    orig_name = (file.filename or "").lower()
    ext = os.path.splitext(orig_name)[1]
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file format '{ext}'. Only JPG, JPEG, and PNG images are supported.",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File exceeds maximum allowed size of {MAX_FILE_SIZE // (1024 * 1024)}MB.",
        )

    # Server tracks attempt regardless of outcome (failed attempts also count)
    ai_extraction_tracker.record_attempt(str(admin_user.id), window_seconds=3600)
    remaining = ai_extraction_tracker.remaining_attempts(str(admin_user.id), limit=5, window_seconds=3600)

    # 4. Pillow verify, dimension checking, re-encoding, and secure disk storage
    reencoded_bytes, stored_path = validate_and_reencode_image(file_bytes)

    # 5. Check if a draft already exists for this cohort
    existing_draft = await get_draft_timetable(cohort.id, db)
    if existing_draft and not replace_draft:
        cleanup_stored_image(stored_path)
        raise HTTPException(
            status_code=409,
            detail="A draft timetable already exists for this class. Please confirm if you wish to overwrite it.",
        )

    # 6. Run AI extraction (Gemini 1 call without sleep retry on 429, fallback to OCR)
    extraction_result = await extract_timetable_from_image(reencoded_bytes)
    extracted_entries = extraction_result.get("entries") or []

    # 7. Persist as draft if entries found or save empty draft for manual completion
    draft_record, warnings = await save_or_update_draft(
        cohort=cohort,
        entries=extracted_entries,
        admin_user=admin_user,
        db=db,
        image_path=stored_path,
    )
    await db.commit()
    await db.refresh(draft_record)

    return ExtractTimetableResponse(
        status=extraction_result["status"],
        extraction_method=extraction_result["extraction_method"],
        message=extraction_result["message"],
        draft=ClassTimetableOut.model_validate(draft_record),
        warnings=warnings,
        remaining_attempts=remaining,
    )


@router.get(
    "/admin/cohorts/{cohort_id}/timetable",
    response_model=TimetableOverviewResponse,
)
async def get_timetable_overview(
    cohort_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Get the current draft and published timetable state for a cohort."""
    cohort = await get_cohort_and_verify_admin(cohort_id, admin_user, db)
    draft = await get_draft_timetable(cohort.id, db)
    published = await get_published_timetable(cohort.id, db)

    return TimetableOverviewResponse(
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        has_draft=draft is not None,
        draft=ClassTimetableOut.model_validate(draft) if draft else None,
        has_published=published is not None,
        published=ClassTimetableOut.model_validate(published) if published else None,
    )


@router.get(
    "/admin/cohorts/{cohort_id}/timetable/draft",
    response_model=DraftResponse,
)
async def get_draft(
    cohort_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve the current draft timetable for a cohort."""
    cohort = await get_cohort_and_verify_admin(cohort_id, admin_user, db)
    draft = await get_draft_timetable(cohort.id, db)
    return DraftResponse(
        has_draft=draft is not None,
        draft=ClassTimetableOut.model_validate(draft) if draft else None,
        warnings=[],
    )


@router.put(
    "/admin/cohorts/{cohort_id}/timetable/draft",
    response_model=DraftResponse,
)
@limiter.limit("60/minute")
async def save_draft(
    request: Request,
    cohort_id: uuid.UUID,
    payload: SaveDraftRequest,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Save or update the draft timetable rows for a cohort (start from scratch or edit AI result).
    Validates limits, day ranges, and returns overlap warnings.
    """
    cohort = await get_cohort_and_verify_admin(cohort_id, admin_user, db)
    raw_entries = [entry.model_dump() for entry in payload.entries]

    draft, warnings = await save_or_update_draft(
        cohort=cohort,
        entries=raw_entries,
        admin_user=admin_user,
        db=db,
    )
    await db.commit()
    await db.refresh(draft)

    return DraftResponse(
        has_draft=True,
        draft=ClassTimetableOut.model_validate(draft),
        warnings=warnings,
    )


@router.delete(
    "/admin/cohorts/{cohort_id}/timetable/draft",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def discard_draft(
    cohort_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """Discard the draft timetable and delete the stored image file from disk."""
    cohort = await get_cohort_and_verify_admin(cohort_id, admin_user, db)
    discarded = await discard_draft_timetable(cohort, db)
    if not discarded:
        raise HTTPException(status_code=404, detail="No draft timetable found to discard.")
    return None


@router.post(
    "/admin/cohorts/{cohort_id}/timetable/publish",
    response_model=DraftResponse,
)
@limiter.limit("30/minute")
async def publish_timetable(
    request: Request,
    cohort_id: uuid.UUID,
    payload: PublishRequest = PublishRequest(force=False),
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Publish the stored draft timetable atomically.
    Re-validates rows, rejects overlaps unless force=True, archives old published timetable,
    sets draft to published, and removes stored image.
    """
    cohort = await get_cohort_and_verify_admin(cohort_id, admin_user, db)
    published, warnings = await publish_draft_timetable(
        cohort=cohort,
        admin_user=admin_user,
        db=db,
        force=payload.force,
    )

    return DraftResponse(
        has_draft=False,
        draft=ClassTimetableOut.model_validate(published),
        warnings=warnings,
    )


@router.post(
    "/admin/cohorts/{cohort_id}/timetable/edit-published",
    response_model=ClassTimetableOut,
)
async def copy_published_to_draft(
    cohort_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Copies current published timetable into a fresh draft for modification.
    Fails if a draft already exists.
    """
    cohort = await get_cohort_and_verify_admin(cohort_id, admin_user, db)
    draft = await edit_published_timetable(cohort, admin_user, db)
    return ClassTimetableOut.model_validate(draft)


@router.get(
    "/admin/cohorts/{cohort_id}/timetable/suggested-subjects",
    response_model=List[str],
)
async def get_suggested_subjects_endpoint(
    cohort_id: uuid.UUID,
    admin_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns suggested subjects derived from class attendance records
    and prior timetable sessions for this class.
    """
    cohort = await get_cohort_and_verify_admin(cohort_id, admin_user, db)
    return await get_suggested_subjects(cohort.id, db)


# ─────────────────────────────────────────────────────────────────────────
# Student Read-Only Timetable Endpoint
# ─────────────────────────────────────────────────────────────────────────

@router.get(
    "/student/class-timetable",
    response_model=StudentClassTimetableResponse,
)
async def get_student_class_timetable(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve the published timetable for the authenticated student's current class.
    - Read-only.
    - If student is not in an approved class, returns enrolled=False with empty entries.
    - If no timetable is published, returns has_timetable=False.
    - Draft timetables are NEVER exposed to students.
    """
    if current_user.role != "student":
        raise HTTPException(
            status_code=403,
            detail="Only students can access student class timetables.",
        )

    if not current_user.cohort_id or not current_user.institution_id:
        return StudentClassTimetableResponse(
            enrolled=False,
            cohort_id=None,
            cohort_name=None,
            has_timetable=False,
            published_at=None,
            entries=[],
        )

    cohort = await db.get(Cohort, current_user.cohort_id)
    if not cohort or getattr(cohort, "is_archived", False):
        return StudentClassTimetableResponse(
            enrolled=False,
            cohort_id=None,
            cohort_name=None,
            has_timetable=False,
            published_at=None,
            entries=[],
        )

    published = await get_published_timetable(cohort.id, db)
    if not published:
        return StudentClassTimetableResponse(
            enrolled=True,
            cohort_id=cohort.id,
            cohort_name=cohort.name,
            has_timetable=False,
            published_at=None,
            entries=[],
        )

    return StudentClassTimetableResponse(
        enrolled=True,
        cohort_id=cohort.id,
        cohort_name=cohort.name,
        has_timetable=True,
        published_at=published.published_at,
        entries=published.entries or [],
    )
