import os
import uuid
import aiofiles
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_user
from app.core.upload_security import validate_and_read_upload
from app.database import get_db
from app.models.user import User
from app.schemas.schemas import (
    EndOfDayOut,
    MorningCheckinOut,
    TimetableEntryCreate,
    TimetableEntryOut,
    TimetableUploadOut,
    UnmarkedReminderOut,
)
from app.services import timetable_service

import logging

router = APIRouter(prefix="/timetable", tags=["Timetable"])
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf"}


@router.post("/upload", response_model=TimetableUploadOut)
async def upload_timetable(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_bytes, ext = await validate_and_read_upload(
        file,
        request=request,
        allowed_extensions=ALLOWED_EXTENSIONS,
    )
    filename = file.filename or "timetable_upload"

    from app.services.storage_service import get_storage_service
    storage = get_storage_service()
    bucket = settings.SUPABASE_STORAGE_BUCKET
    stored_name = f"{uuid.uuid4()}.{ext}"
    storage_path = f"users/{current_user.id}/timetables/{stored_name}"
    content_type = file.content_type or f"image/{ext}"

    # 1. Upload to storage first
    try:
        await storage.upload_file(bucket, storage_path, file_bytes, content_type)
    except Exception as exc:
        logger.exception("Storage upload failed for timetable: %s", exc)
        raise HTTPException(status_code=503, detail="Storage service unavailable. Please try again later.") from exc

    # Optional local mirror for dev compatibility if directory configured
    timetable_upload_dir = os.path.join(settings.UPLOAD_DIR, "timetables")
    os.makedirs(timetable_upload_dir, exist_ok=True)
    file_path = os.path.join(timetable_upload_dir, stored_name)
    try:
        async with aiofiles.open(file_path, "wb") as out:
            await out.write(file_bytes)
    except Exception as disk_err:
        logger.warning("Local mirror write skipped/failed: %s", disk_err)

    try:
        result = await timetable_service.process_timetable_upload(
            user_id=current_user.id,
            file_name=filename,
            file_path=file_path,
            storage_path=storage_path,
            storage_bucket=bucket,
            file_bytes=file_bytes,
            file_type=ext,
            db=db,
        )
        await db.commit()
    except Exception as e:
        await db.rollback()
        # Compensating delete from storage
        try:
            await storage.delete_file(bucket, storage_path)
        except Exception as del_err:
            logger.warning("Compensating storage delete failed for %s: %s", storage_path, del_err)
        if os.path.isfile(file_path):
            try:
                os.remove(file_path)
            except Exception as rem_err:
                logger.warning("Failed removing local timetable file %s: %s", file_path, rem_err)
        logger.exception("Timetable extraction failed for %s", filename)
        raise HTTPException(
            status_code=500,
            detail=f"Timetable extraction failed: {str(e)}"
        )
    return result


@router.post("/entries/bulk")
async def save_timetable_entries_bulk(
    entries: list[TimetableEntryCreate],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        payload = [entry.model_dump() for entry in entries]
        return await timetable_service.bulk_save_timetable(current_user.id, payload, db)
    except Exception as e:
        logger.exception("Bulk save timetable entries failed: %s", e)
        raise


@router.get("/entries", response_model=list[TimetableEntryOut])
async def get_timetable_entries(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await timetable_service.get_timetable_entries(current_user.id, db)


@router.get("/today", response_model=list[TimetableEntryOut])
async def get_today_classes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await timetable_service.get_today_classes(current_user.id, db)


@router.delete("/entries/{entry_id}", status_code=204)
async def delete_timetable_entry(
    entry_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await timetable_service.delete_timetable_entry(current_user.id, entry_id, db)


@router.get("/reminders/morning-checkin", response_model=MorningCheckinOut)
async def morning_checkin(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await timetable_service.get_morning_checkin(current_user.id, db)


@router.get("/reminders/unmarked", response_model=UnmarkedReminderOut)
async def unmarked_reminders(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await timetable_service.get_unmarked_classes(current_user.id, db)


@router.get("/reminders/end-of-day", response_model=EndOfDayOut)
async def end_of_day_reminder(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await timetable_service.get_end_of_day_summary(current_user.id, db)
