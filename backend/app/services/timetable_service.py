from datetime import datetime
from difflib import SequenceMatcher
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.attendance import AttendanceRecord, AttendanceStatus, Subject
from app.models.timetable import TimetableDocument, TimetableEntry
from app.services.ollama_timetable_extractor import OllamaTimetableExtractor


DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _parse_time_string(value):
    """Parse a time string (HH:MM or HH:MM:SS) or return a time object as-is."""
    from datetime import time as _time
    if isinstance(value, _time):
        return value
    value = str(value).strip()
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse time: {value!r}")


async def match_subject_to_database(extracted_name: str, user_id: UUID, db: AsyncSession) -> UUID | None:
    result = await db.execute(select(Subject).where(Subject.user_id == user_id))
    subjects = list(result.scalars().all())
    if not subjects:
        return None

    extracted_lower = extracted_name.lower()
    best_match = None
    best_score = 0.0

    for subject in subjects:
        compare_items = [subject.name.lower()]
        if subject.code:
            compare_items.append(subject.code.lower())

        for compare_text in compare_items:
            score = SequenceMatcher(None, extracted_lower, compare_text).ratio()
            if score > best_score:
                best_score = score
                best_match = subject

    if best_match and best_score >= 0.7:
        return best_match.id
    return None


async def process_timetable_upload(user_id: UUID, file_name: str, file_path: str, file_type: str, db: AsyncSession) -> dict:
    doc = TimetableDocument(
        user_id=user_id,
        file_name=file_name,
        file_path=file_path,
        file_type=file_type,
        extraction_status="processing",
        extracted_data={},
    )
    db.add(doc)
    await db.flush()

    # Use Ollama for timetable extraction (llava:7b for images, qwen2.5:7b for text)
    extractor = OllamaTimetableExtractor()
    result = await extractor.extract_from_file(file_path)

    if result["status"] == "failed":
        doc.extraction_status = "failed"
        doc.error_message = result.get("error", "Extraction failed")
        doc.extracted_data = {"error": doc.error_message}
        return {
            "status": "failed",
            "document_id": doc.id,
            "entries": [],
            "confidence": float(result.get("confidence", 0.0) or 0.0),
            "error": doc.error_message,
        }

    final_entries = []
    for entry in result.get("entries", []):
        subject_name = entry["subject"].strip()
        subject_id = await match_subject_to_database(subject_name, user_id, db)
        if not subject_id:
            code = "".join([c for c in subject_name.upper() if c.isalnum() or c == " "]).replace(" ", "")[:10]
            subject = Subject(user_id=user_id, name=subject_name, code=code or None)
            db.add(subject)
            await db.flush()
            subject_id = subject.id

        final_entries.append({
            "subject_id": str(subject_id),
            "subject": subject_name,
            "day_of_week": int(entry["day_of_week"]),
            "start_time": entry["start_time"],
            "end_time": entry["end_time"],
            "room": entry.get("room"),
            "notes": None,
        })

    doc.extraction_status = "success"
    doc.extracted_data = {
        "layout_type": result.get("layout_type", "horizontal"),
        "entries": final_entries,
        "confidence": float(result.get("confidence", 0.0) or 0.0),
        "notes": result.get("notes", ""),
    }

    return {
        "status": "success",
        "document_id": doc.id,
        "entries": final_entries,
        "confidence": float(result.get("confidence", 0.0) or 0.0),
        "notes": result.get("notes", ""),
    }


async def bulk_save_timetable(user_id: UUID, entries: list[dict], db: AsyncSession) -> dict:
    await db.execute(delete(TimetableEntry).where(TimetableEntry.user_id == user_id))

    for entry_data in entries:
        timetable_entry = TimetableEntry(
            user_id=user_id,
            subject_id=entry_data["subject_id"],
            day_of_week=entry_data["day_of_week"],
            start_time=_parse_time_string(entry_data["start_time"]),
            end_time=_parse_time_string(entry_data["end_time"]),
            room=entry_data.get("room"),
            notes=entry_data.get("notes"),
            is_active=True,
        )
        db.add(timetable_entry)

    await db.flush()
    return {"status": "success", "saved": len(entries)}


async def get_timetable_entries(user_id: UUID, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(TimetableEntry, Subject)
        .join(Subject, TimetableEntry.subject_id == Subject.id)
        .where(TimetableEntry.user_id == user_id)
        .order_by(TimetableEntry.day_of_week, TimetableEntry.start_time)
    )

    items = []
    for entry, subject in result.all():
        items.append({
            "id": entry.id,
            "subject_id": entry.subject_id,
            "subject_name": subject.name,
            "day_of_week": entry.day_of_week,
            "start_time": entry.start_time.strftime("%H:%M"),
            "end_time": entry.end_time.strftime("%H:%M"),
            "room": entry.room,
            "notes": entry.notes,
            "is_active": entry.is_active,
        })
    return items


async def get_today_classes(user_id: UUID, db: AsyncSession) -> list[dict]:
    today = datetime.now()
    weekday = today.weekday()
    today_date = today.date()
    
    result = await db.execute(
        select(TimetableEntry, Subject, AttendanceRecord)
        .join(Subject, TimetableEntry.subject_id == Subject.id)
        .outerjoin(
            AttendanceRecord,
            and_(
                AttendanceRecord.subject_id == Subject.id,
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.class_date == today_date
            )
        )
        .where(
            and_(
                TimetableEntry.user_id == user_id,
                TimetableEntry.day_of_week == weekday,
                TimetableEntry.is_active.is_(True),
            )
        )
        .order_by(TimetableEntry.start_time)
    )

    classes = []
    for entry, subject, attendance_record in result.all():
        classes.append({
            "id": str(entry.id),
            "subject_id": str(subject.id),
            "subject_name": subject.name,
            "day_of_week": entry.day_of_week,
            "start_time": entry.start_time.strftime("%H:%M"),
            "end_time": entry.end_time.strftime("%H:%M"),
            "room": entry.room,
            "notes": entry.notes,
            "is_active": entry.is_active,
            "attendance_status": attendance_record.status.value if attendance_record else None,
            "attendance_id": str(attendance_record.id) if attendance_record else None,
        })
    return classes


async def delete_timetable_entry(user_id: UUID, entry_id: UUID, db: AsyncSession) -> None:
    result = await db.execute(
        select(TimetableEntry).where(TimetableEntry.id == entry_id, TimetableEntry.user_id == user_id)
    )
    entry = result.scalar_one_or_none()
    if not entry:
        raise HTTPException(status_code=404, detail="Timetable entry not found")
    await db.delete(entry)


async def get_morning_checkin(user_id: UUID, db: AsyncSession) -> dict:
    today = datetime.now()
    day_of_week = today.weekday()
    today_date = today.date()

    result = await db.execute(
        select(TimetableEntry, Subject)
        .join(Subject, TimetableEntry.subject_id == Subject.id)
        .where(
            and_(
                TimetableEntry.user_id == user_id,
                TimetableEntry.day_of_week == day_of_week,
                TimetableEntry.is_active.is_(True),
            )
        )
        .order_by(TimetableEntry.start_time)
    )
    classes = result.all()

    marked_result = await db.execute(
        select(AttendanceRecord.subject_id).where(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.class_date == today_date,
            )
        )
    )
    marked_ids = {subject_id for (subject_id,) in marked_result.all()}

    payload_classes = []
    for entry, subject in classes:
        payload_classes.append({
            "subject_id": entry.subject_id,
            "subject_name": subject.name,
            "start_time": entry.start_time.strftime("%H:%M"),
            "end_time": entry.end_time.strftime("%H:%M"),
            "room": entry.room,
            "is_marked": entry.subject_id in marked_ids,
        })

    marked_count = len([c for c in payload_classes if c["is_marked"]])
    return {
        "type": "morning_checkin",
        "classes": payload_classes,
        "total": len(payload_classes),
        "marked": marked_count,
    }


async def get_unmarked_classes(user_id: UUID, db: AsyncSession) -> dict:
    now = datetime.now()
    day_of_week = now.weekday()
    today_date = now.date()
    current_time = now.time()

    result = await db.execute(
        select(TimetableEntry, Subject)
        .join(Subject, TimetableEntry.subject_id == Subject.id)
        .where(
            and_(
                TimetableEntry.user_id == user_id,
                TimetableEntry.day_of_week == day_of_week,
                TimetableEntry.end_time < current_time,
                TimetableEntry.is_active.is_(True),
            )
        )
    )
    ended_classes = result.all()

    marked_result = await db.execute(
        select(AttendanceRecord.subject_id).where(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.class_date == today_date,
            )
        )
    )
    marked_ids = {subject_id for (subject_id,) in marked_result.all()}

    unmarked = []
    for entry, subject in ended_classes:
        if entry.subject_id not in marked_ids:
            unmarked.append({
                "subject_id": entry.subject_id,
                "subject_name": subject.name,
                "time": f"{entry.start_time.strftime('%H:%M')}-{entry.end_time.strftime('%H:%M')}",
            })

    return {
        "type": "unmarked",
        "classes": unmarked,
        "count": len(unmarked),
    }


async def get_end_of_day_summary(user_id: UUID, db: AsyncSession) -> dict:
    today = datetime.now()
    day_of_week = today.weekday()
    today_date = today.date()

    classes_result = await db.execute(
        select(TimetableEntry).where(
            and_(
                TimetableEntry.user_id == user_id,
                TimetableEntry.day_of_week == day_of_week,
                TimetableEntry.is_active.is_(True),
            )
        )
    )
    classes = list(classes_result.scalars().all())

    records_result = await db.execute(
        select(AttendanceRecord).where(
            and_(
                AttendanceRecord.user_id == user_id,
                AttendanceRecord.class_date == today_date,
            )
        )
    )
    records = list(records_result.scalars().all())

    present_count = len([r for r in records if r.status == AttendanceStatus.present])
    absent_count = len([r for r in records if r.status == AttendanceStatus.absent])
    late_count = len([r for r in records if r.status == AttendanceStatus.late])

    return {
        "type": "end_of_day",
        "total_classes": len(classes),
        "marked_classes": len(records),
        "present_count": present_count,
        "absent_count": absent_count,
        "late_count": late_count,
        "unmarked_count": max(0, len(classes) - len(records)),
    }
