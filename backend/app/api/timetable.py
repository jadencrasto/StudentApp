import os
import uuid
import aiofiles
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.dependencies import get_current_user
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
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    filename = file.filename or "timetable_upload"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=422, detail="Only PNG, JPG, JPEG, and PDF files are supported")

    timetable_upload_dir = os.path.join(settings.UPLOAD_DIR, "timetables")
    os.makedirs(timetable_upload_dir, exist_ok=True)

    stored_name = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join(timetable_upload_dir, stored_name)

    file_bytes = await file.read()
    async with aiofiles.open(file_path, "wb") as out:
        await out.write(file_bytes)

    try:
        result = await timetable_service.process_timetable_upload(
            user_id=current_user.id,
            file_name=filename,
            file_path=file_path,
            file_type=ext,
            db=db,
        )
    except Exception as e:
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
    payload = [entry.model_dump() for entry in entries]
    return await timetable_service.bulk_save_timetable(current_user.id, payload, db)


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
