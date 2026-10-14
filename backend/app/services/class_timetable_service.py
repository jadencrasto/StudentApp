"""
Phase 6C — Admin Class Timetable Service.

Handles:
- Image validation, dimension capping (<=8000px), re-encoding via Pillow.
- Secure storage under backend/uploads/class_timetables/ (git-ignored, not served publicly).
- Single-attempt Gemini extraction without retry on 429 quota, fallback to Tesseract.
- Draft creation, updates, discard (with image deletion), and publication.
- Atomic publication (old published -> archived, draft -> published).
- Strict server-side re-validation: day Mon=0..Sun=6, end > start, non-empty subject, 100-row cap, text limits.
- Overlap detection with warnings and admin override.
- Copy published to draft.
- Suggested subjects aggregated from attendance and past timetables.
"""
import copy
import io
import logging
import os
import uuid
from datetime import datetime, time
from typing import Any, Dict, List, Optional, Tuple

import anyio
from fastapi import HTTPException
from PIL import Image
from sqlalchemy import select, update, delete, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limiter import quota_cooldown_tracker
from app.models.class_attendance import ClassAttendanceRecord
from app.models.class_timetable import ClassTimetable
from app.models.institution import Cohort, Institution
from app.models.user import User
from app.services.gemini_timetable_extractor import (
    GeminiTimetableExtractor,
    EXTRACTION_PROMPT,
)

logger = logging.getLogger(__name__)

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
MAX_ROWS = 100
MAX_DIMENSION = 8000
MAX_SUBJECT_LEN = 100
MAX_ROOM_LEN = 50
MAX_TEACHER_LEN = 100


def get_upload_dir() -> str:
    dir_path = os.path.join(settings.UPLOAD_DIR, "class_timetables")
    os.makedirs(dir_path, exist_ok=True)
    return dir_path


def cleanup_stored_image(image_path: Optional[str]) -> None:
    """Delete the stored timetable image from disk if it exists."""
    if not image_path:
        return
    try:
        if os.path.isfile(image_path):
            os.remove(image_path)
            logger.info("Deleted stored timetable image: %s", image_path)
    except Exception as exc:
        logger.warning("Could not delete stored timetable image %s: %s", image_path, exc)


def validate_and_reencode_image(file_bytes: bytes) -> Tuple[bytes, str]:
    """
    Validate image with Pillow verify(), enforce <=8000px dimension limit,
    and re-encode to a safe PNG in memory. Returns (reencoded_bytes, file_path_on_disk).
    """
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded.")

    # 1. Pillow verify()
    try:
        verify_img = Image.open(io.BytesIO(file_bytes))
        verify_img.verify()
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid or readable image.")

    # 2. Re-open and check dimensions
    try:
        img = Image.open(io.BytesIO(file_bytes))
        width, height = img.size
        if width > MAX_DIMENSION or height > MAX_DIMENSION:
            raise HTTPException(
                status_code=400,
                detail=f"Image dimensions ({width}x{height}) exceed maximum allowed size ({MAX_DIMENSION}x{MAX_DIMENSION} px).",
            )

        # 3. Re-encode to clean PNG
        buf = io.BytesIO()
        if img.mode in ("RGBA", "P"):
            converted = img.convert("RGBA")
        else:
            converted = img.convert("RGB")
        converted.save(buf, format="PNG")
        reencoded_bytes = buf.getvalue()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to process and re-encode image: {exc}")

    # 4. Save to secure uploads folder
    upload_dir = get_upload_dir()
    file_name = f"{uuid.uuid4()}.png"
    stored_path = os.path.join(upload_dir, file_name)
    with open(stored_path, "wb") as f:
        f.write(reencoded_bytes)

    return reencoded_bytes, stored_path


def _parse_time_str(val: Any) -> time:
    """Parse HH:MM string to time object."""
    if isinstance(val, time):
        return val
    s = str(val).strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            pass
    raise ValueError(f"Invalid time format: {val}. Expected HH:MM (24-hour).")


def validate_timetable_entries(entries: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    Server-side validation for class timetable entries:
    - 100-row cap
    - valid day (Mon=0..Sun=6)
    - non-empty subject
    - text length limits
    - valid start_time and end_time (HH:MM), end_time > start_time
    - detects overlapping slots on the same day and returns warning messages
    """
    if len(entries) > MAX_ROWS:
        raise HTTPException(
            status_code=400,
            detail=f"Timetable cannot exceed {MAX_ROWS} rows (received {len(entries)}).",
        )

    sanitized: List[Dict[str, Any]] = []

    for idx, raw in enumerate(entries, start=1):
        # Day of week
        try:
            day = int(raw.get("day_of_week", -1))
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail=f"Row {idx}: Invalid day_of_week.")
        if day < 0 or day > 6:
            raise HTTPException(status_code=400, detail=f"Row {idx}: day_of_week must be between 0 (Monday) and 6 (Sunday).")

        # Subject
        subject = str(raw.get("subject") or "").strip()
        if not subject:
            raise HTTPException(status_code=400, detail=f"Row {idx}: Subject name cannot be empty.")
        if len(subject) > MAX_SUBJECT_LEN:
            raise HTTPException(status_code=400, detail=f"Row {idx}: Subject exceeds max length of {MAX_SUBJECT_LEN} characters.")

        # Times
        try:
            st = _parse_time_str(raw.get("start_time"))
            et = _parse_time_str(raw.get("end_time"))
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=f"Row {idx}: {str(ve)}")

        if et <= st:
            raise HTTPException(
                status_code=400,
                detail=f"Row {idx} ('{subject}'): End time ({et.strftime('%H:%M')}) must be strictly after start time ({st.strftime('%H:%M')}).",
            )

        # Room & Teacher
        room = str(raw.get("room") or "").strip() or None
        if room and len(room) > MAX_ROOM_LEN:
            raise HTTPException(status_code=400, detail=f"Row {idx}: Room exceeds max length of {MAX_ROOM_LEN} characters.")

        teacher = str(raw.get("teacher") or "").strip() or None
        if teacher and len(teacher) > MAX_TEACHER_LEN:
            raise HTTPException(status_code=400, detail=f"Row {idx}: Teacher exceeds max length of {MAX_TEACHER_LEN} characters.")

        sanitized.append({
            "day_of_week": day,
            "start_time": st.strftime("%H:%M"),
            "end_time": et.strftime("%H:%M"),
            "subject": subject,
            "room": room,
            "teacher": teacher,
        })

    # Overlap detection on same day
    warnings: List[str] = []
    by_day: Dict[int, List[Dict[str, Any]]] = {}
    for item in sanitized:
        by_day.setdefault(item["day_of_week"], []).append(item)

    for day, day_slots in by_day.items():
        sorted_slots = sorted(day_slots, key=lambda x: x["start_time"])
        for i in range(len(sorted_slots) - 1):
            curr = sorted_slots[i]
            nxt = sorted_slots[i + 1]
            if nxt["start_time"] < curr["end_time"]:
                day_name = DAY_NAMES[day]
                warnings.append(
                    f"{day_name}: '{curr['subject']}' ({curr['start_time']}–{curr['end_time']}) "
                    f"overlaps with '{nxt['subject']}' ({nxt['start_time']}–{nxt['end_time']})."
                )

    return sanitized, warnings


def _is_gemini_503(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 503:
        return True
    msg = str(exc).lower()
    return ("503" in msg or "unavailable" in msg) and "429" not in msg and "quota" not in msg and "resource_exhausted" not in msg


def _is_gemini_429(exc: Exception) -> bool:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429:
        return True
    msg = str(exc).lower()
    return "429" in msg or "quota" in msg or "resource_exhausted" in msg


async def extract_timetable_from_image(file_bytes: bytes) -> Dict[str, Any]:
    """
    Attempt extraction using Gemini Vision:
    - If Gemini returns 503 UNAVAILABLE (busy): wait ~3 seconds and retry ONCE.
    - If still 503: return friendly message 'Google's AI is busy right now. Try again in a few minutes, or start from scratch.'
      and mark is_503=True so it does NOT count against the 5-per-hour limit.
    - Never retry on 429 daily quota.
    - If daily quota (429): set cooldown tracker and try Tesseract fallback or return friendly message.
    """
    extractor = GeminiTimetableExtractor()

    gemini_entries = None
    last_exc: Optional[Exception] = None
    is_quota = False

    for attempt in (1, 2):
        try:
            payload = await anyio.to_thread.run_sync(
                lambda: extractor._extract_bytes_sync(file_bytes)
            )
            if "error" not in payload:
                processed = extractor._post_process_entries(payload.get("entries") or [])
                if processed:
                    gemini_entries = processed
                    break
            else:
                err_str = str(payload.get("error"))
                last_exc = Exception(err_str)
                if _is_gemini_503(last_exc) and attempt == 1:
                    logger.info("Gemini 503 UNAVAILABLE (attempt 1). Waiting ~3 seconds before retry...")
                    await anyio.sleep(3.0)
                    continue
                break
        except Exception as exc:
            last_exc = exc
            logger.warning("Gemini timetable extraction attempt %d failed: %s", attempt, exc)
            if _is_gemini_503(exc) and attempt == 1:
                logger.info("Gemini 503 UNAVAILABLE (attempt 1). Waiting ~3 seconds before retry...")
                await anyio.sleep(3.0)
                continue
            # Never retry on 429 daily quota or other non-503 errors
            break

    if gemini_entries:
        return {
            "status": "success",
            "entries": gemini_entries,
            "extraction_method": "gemini",
            "message": "Timetable extracted successfully with Gemini Vision.",
        }

    # If still 503 after retry: friendly message and mark is_503=True so it won't count against 5-per-hour limit
    if last_exc and _is_gemini_503(last_exc):
        return {
            "status": "failed",
            "entries": [],
            "extraction_method": "none",
            "is_503": True,
            "message": "Google's AI is busy right now. Try again in a few minutes, or start from scratch.",
        }

    # If daily quota reached (429): activate cooldown tracker
    if last_exc and _is_gemini_429(last_exc):
        quota_cooldown_tracker.set_cooldown(300.0)
        is_quota = True

    # 2. Fallback to Tesseract OCR
    logger.info("Attempting Tesseract OCR fallback for class timetable...")
    ocr_entries = []
    try:
        import pytesseract
        image = Image.open(io.BytesIO(file_bytes))
        text = pytesseract.image_to_string(image, config="--psm 6")
        lines_entries = extractor._parse_day_time_lines(text)
        if not lines_entries:
            lines_entries = extractor._parse_grid_rows(text)
        processed_ocr = extractor._post_process_entries(lines_entries)
        if processed_ocr:
            ocr_entries = processed_ocr
    except Exception as fallback_exc:
        logger.warning("Tesseract OCR fallback failed: %s", fallback_exc)

    if ocr_entries:
        return {
            "status": "fallback_ocr",
            "entries": ocr_entries,
            "extraction_method": "ocr",
            "is_quota": is_quota,
            "message": "Gemini extraction was unavailable; timetable extracted via OCR fallback. Please review and verify slots.",
        }

    # 3. Both failed
    if is_quota:
        return {
            "status": "failed",
            "entries": [],
            "extraction_method": "none",
            "is_quota": True,
            "message": "AI daily quota reached. Please try again tomorrow, or enter your timetable manually.",
        }

    return {
        "status": "failed",
        "entries": [],
        "extraction_method": "none",
        "message": (
            "AI extraction could not read the schedule from this image. "
            "You can start from scratch and enter the timetable rows manually."
        ),
    }


# =========================================================================
# Class Timetable Database Operations
# =========================================================================

async def get_cohort_and_verify_admin(
    cohort_id: uuid.UUID,
    admin_user: User,
    db: AsyncSession,
) -> Cohort:
    """Verify that cohort exists, belongs to admin's institution, and is not archived."""
    res = await db.execute(select(Cohort).where(Cohort.id == cohort_id))
    cohort = res.scalar_one_or_none()
    if not cohort:
        raise HTTPException(status_code=404, detail="Class (cohort) not found.")

    if admin_user.role != "superadmin":
        if not admin_user.institution_id or cohort.institution_id != admin_user.institution_id:
            raise HTTPException(
                status_code=403,
                detail="You do not have administrative access to this class's institution.",
            )

    if getattr(cohort, "is_archived", False):
        raise HTTPException(status_code=400, detail="Cannot modify timetable for an archived class.")

    return cohort


async def get_draft_timetable(cohort_id: uuid.UUID, db: AsyncSession) -> Optional[ClassTimetable]:
    res = await db.execute(
        select(ClassTimetable).where(
            ClassTimetable.cohort_id == cohort_id,
            ClassTimetable.status == "draft",
        )
    )
    return res.scalar_one_or_none()


async def get_published_timetable(cohort_id: uuid.UUID, db: AsyncSession) -> Optional[ClassTimetable]:
    res = await db.execute(
        select(ClassTimetable).where(
            ClassTimetable.cohort_id == cohort_id,
            ClassTimetable.status == "published",
        )
    )
    return res.scalar_one_or_none()


async def save_or_update_draft(
    cohort: Cohort,
    entries: List[Dict[str, Any]],
    admin_user: User,
    db: AsyncSession,
    image_path: Optional[str] = None,
) -> Tuple[ClassTimetable, List[str]]:
    """Save or update the single draft timetable for this cohort."""
    sanitized, warnings = validate_timetable_entries(entries)

    draft = await get_draft_timetable(cohort.id, db)
    if draft:
        draft.entries = sanitized
        if image_path:
            cleanup_stored_image(draft.image_path)
            draft.image_path = image_path
        draft.updated_at = datetime.utcnow()
    else:
        draft = ClassTimetable(
            institution_id=cohort.institution_id,
            cohort_id=cohort.id,
            status="draft",
            entries=sanitized,
            image_path=image_path,
            created_by=admin_user.id,
        )
        db.add(draft)

    await db.flush()
    return draft, warnings


async def discard_draft_timetable(cohort: Cohort, db: AsyncSession) -> bool:
    """Discard existing draft and delete any associated stored image."""
    draft = await get_draft_timetable(cohort.id, db)
    if not draft:
        return False

    if draft.image_path:
        cleanup_stored_image(draft.image_path)

    await db.delete(draft)
    await db.commit()
    return True


async def publish_draft_timetable(
    cohort: Cohort,
    admin_user: User,
    db: AsyncSession,
    force: bool = False,
) -> Tuple[ClassTimetable, List[str]]:
    """
    Publish the stored draft timetable atomically:
    1. Re-validate entries strictly.
    2. Overlap check: if overlapping and not force, raise error with warnings.
    3. Old published timetable -> archived.
    4. Draft timetable -> published.
    5. Clean up stored image.
    """
    draft = await get_draft_timetable(cohort.id, db)
    if not draft:
        raise HTTPException(
            status_code=400,
            detail="No draft timetable found to publish. Please create or extract a timetable first.",
        )

    if not draft.entries:
        raise HTTPException(
            status_code=400,
            detail="Cannot publish an empty timetable. Please add at least one class session.",
        )

    sanitized, warnings = validate_timetable_entries(draft.entries)
    if warnings and not force:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Overlapping class slots detected. Confirm to publish anyway.",
                "warnings": warnings,
                "can_override": True,
            },
        )

    # 1. Archive current published timetable
    existing_published = await get_published_timetable(cohort.id, db)
    if existing_published:
        existing_published.status = "archived"
        existing_published.updated_at = datetime.utcnow()
        await db.flush()  # Ensure existing row is archived in DB before promoting draft

    # 2. Update draft to published
    draft.entries = sanitized
    draft.status = "published"
    draft.published_at = datetime.utcnow()
    draft.updated_at = datetime.utcnow()

    # 3. Clean up stored image file upon publishing
    if draft.image_path:
        cleanup_stored_image(draft.image_path)
        draft.image_path = None

    await db.commit()
    await db.refresh(draft)
    return draft, warnings


async def edit_published_timetable(
    cohort: Cohort,
    admin_user: User,
    db: AsyncSession,
) -> ClassTimetable:
    """Copies current published timetable into a fresh draft."""
    existing_draft = await get_draft_timetable(cohort.id, db)
    if existing_draft:
        raise HTTPException(
            status_code=400,
            detail="A draft timetable already exists for this class. Please discard or publish it before creating a new draft.",
        )

    published = await get_published_timetable(cohort.id, db)
    if not published:
        raise HTTPException(
            status_code=404,
            detail="No published timetable found for this class to edit.",
        )

    new_draft = ClassTimetable(
        institution_id=cohort.institution_id,
        cohort_id=cohort.id,
        status="draft",
        entries=copy.deepcopy(published.entries),
        image_path=None,
        created_by=admin_user.id,
    )
    db.add(new_draft)
    await db.commit()
    await db.refresh(new_draft)
    return new_draft


async def get_suggested_subjects(cohort_id: uuid.UUID, db: AsyncSession) -> List[str]:
    """
    Return sorted unique list of suggested subject names for this class
    from attendance records and past timetables.
    """
    subjects_set = set()

    # 1. From ClassAttendanceRecord
    try:
        att_res = await db.execute(
            select(distinct(ClassAttendanceRecord.subject_name)).where(
                ClassAttendanceRecord.cohort_id == cohort_id
            )
        )
        for s in att_res.scalars().all():
            if s and s.strip():
                subjects_set.add(s.strip())
    except Exception as exc:
        logger.warning("Could not fetch subjects from ClassAttendanceRecord: %s", exc)

    # 2. From all timetables for this cohort
    try:
        tt_res = await db.execute(
            select(ClassTimetable.entries).where(ClassTimetable.cohort_id == cohort_id)
        )
        for row in tt_res.scalars().all():
            if isinstance(row, list):
                for entry in row:
                    subj = str(entry.get("subject") or "").strip()
                    if subj:
                        subjects_set.add(subj)
    except Exception as exc:
        logger.warning("Could not fetch subjects from ClassTimetable: %s", exc)

    return sorted(list(subjects_set), key=lambda x: x.lower())
