"""
SAIS Scheduler — Cron Jobs
Runs daily at 8AM to:
  1. Generate fresh AI alerts for all active users
  2. Mark assignments as overdue if deadline has passed
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from zoneinfo import ZoneInfo
import logging

logger = logging.getLogger("sais.scheduler")
KOLKATA_TZ = ZoneInfo("Asia/Kolkata")
scheduler = AsyncIOScheduler(timezone=KOLKATA_TZ)


async def _daily_alert_job():
    """Run alert generation for all active users."""
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from app.services.alert_service import generate_alerts

    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.is_active == True))
        users = result.scalars().all()
        total_alerts = 0
        for user in users:
            try:
                alerts = await generate_alerts(user.id, db)
                total_alerts += len(alerts)
            except Exception as e:
                logger.error(f"Alert generation failed for user {user.id}: {e}")
        await db.commit()
        logger.info(f"Daily alerts: generated {total_alerts} alerts for {len(users)} users")


async def _mark_overdue_job():
    """Mark assignments as overdue if their deadline has passed."""
    from datetime import date
    from sqlalchemy import select, and_, update
    from app.database import AsyncSessionLocal
    from app.models.assignment import Assignment, AssignmentStatus

    async with AsyncSessionLocal() as db:
        today = date.today()
        await db.execute(
            update(Assignment)
            .where(
                and_(
                    Assignment.deadline < today,
                    Assignment.status == AssignmentStatus.pending.value,
                )
            )
            .values(status=AssignmentStatus.overdue.value)
        )
        await db.commit()
        logger.info("Overdue job complete")


async def _college_events_sync_job():
    """Periodic sync for configured colleges (best-effort)."""
    from app.college_events.college_loader import CollegeLoader
    from app.college_events.main import fetch_events_for_college
    from app.database import AsyncSessionLocal

    loader = CollegeLoader()
    colleges = loader.list_colleges()
    if not colleges:
        return

    async with AsyncSessionLocal() as db:
        for college in colleges:
            try:
                await fetch_events_for_college(college.name, db)
            except Exception as exc:
                logger.warning("College sync failed for %s: %s", college.name, exc)
        await db.commit()


async def _storage_cleanup_job():
    """
    Daily maintenance job for storage leftovers:
    1. Class timetable drafts > 48h abandoned.
    2. Student timetable uploads never saved > 7d (failed or abandoned).
    3. Storage objects in bucket with no matching DB row.
    Runs in DRY-RUN / log-only mode by default until approved.
    """
    import os
    import shutil
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import select, or_
    from app.config import settings
    from app.database import AsyncSessionLocal
    from app.models.class_timetable import ClassTimetable
    from app.models.timetable import TimetableDocument
    from app.models.document_alert import Document
    from app.services.storage_service import get_storage_service

    now = datetime.now(timezone.utc)
    cutoff_drafts = now - timedelta(hours=48)
    cutoff_student_uploads = now - timedelta(days=7)

    logger.info("[storage-cleanup] Running storage audit (DRY_RUN=%s)...", settings.STORAGE_CLEANUP_DRY_RUN)

    async with AsyncSessionLocal() as db:
        # 1. Draft class timetables > 48 hours old
        drafts_res = await db.execute(
            select(ClassTimetable).where(
                ClassTimetable.status == "draft",
                ClassTimetable.created_at < cutoff_drafts,
            )
        )
        abandoned_drafts = drafts_res.scalars().all()

        # 2. Student timetables never saved > 7 days old (with residual storage or file path)
        student_res = await db.execute(
            select(TimetableDocument).where(
                TimetableDocument.uploaded_at < cutoff_student_uploads,
                or_(
                    TimetableDocument.storage_path.isnot(None),
                    TimetableDocument.file_path.isnot(None),
                ),
            )
        )
        abandoned_student_docs = student_res.scalars().all()

        # 3. Bucket files with no matching DB row
        orphaned_bucket_files = []
        try:
            storage = get_storage_service()
            bucket = settings.SUPABASE_STORAGE_BUCKET
            bucket_files = await storage.list_files(bucket)
            if bucket_files:
                doc_paths_res = await db.execute(select(Document.storage_path).where(Document.storage_path.isnot(None)))
                ct_paths_res = await db.execute(select(ClassTimetable.image_storage_path).where(ClassTimetable.image_storage_path.isnot(None)))
                tt_paths_res = await db.execute(select(TimetableDocument.storage_path).where(TimetableDocument.storage_path.isnot(None)))

                known_paths = set(doc_paths_res.scalars().all()) | set(ct_paths_res.scalars().all()) | set(tt_paths_res.scalars().all())
                orphaned_bucket_files = [f for f in bucket_files if f not in known_paths]
        except Exception as scan_err:
            logger.warning("[storage-cleanup] Cloud bucket file scan skipped/failed: %s", scan_err)

        logger.info(
            "[storage-cleanup] Candidates found: %d abandoned class drafts (>48h), %d unsaved student timetables (>7d), %d orphaned bucket files (no DB row)",
            len(abandoned_drafts),
            len(abandoned_student_docs),
            len(orphaned_bucket_files),
        )

        for d in abandoned_drafts:
            logger.info("  [abandoned-class-draft] id=%s, cohort=%s, storage=%s, local=%s", d.id, d.cohort_id, d.image_storage_path, d.image_path)
        for s in abandoned_student_docs:
            logger.info("  [unsaved-student-doc] id=%s, user=%s, status=%s, storage=%s, local=%s", s.id, s.user_id, s.extraction_status, s.storage_path, s.file_path)
        for orphan in orphaned_bucket_files:
            logger.info("  [orphaned-bucket-file] path=%s (no matching DB row)", orphan)

        if settings.STORAGE_CLEANUP_DRY_RUN:
            logger.info("[storage-cleanup] DRY-RUN active — log-only audit complete, no files deleted.")
            return

        # LIVE MODE: executed only when STORAGE_CLEANUP_DRY_RUN=False
        trash_dir = os.path.join("_trash", f"uploads_cleanup_{now.strftime('%Y%m%d_%H%M%S')}")
        os.makedirs(trash_dir, exist_ok=True)
        storage = get_storage_service()

        for d in abandoned_drafts:
            if d.image_storage_path:
                try:
                    await storage.delete_file(d.image_storage_bucket or settings.SUPABASE_STORAGE_BUCKET, d.image_storage_path)
                except Exception as exc:
                    logger.warning("[storage-cleanup] Storage delete failed for %s: %s", d.image_storage_path, exc)
                d.image_storage_path = None
            if d.image_path and os.path.isfile(d.image_path):
                try:
                    shutil.move(d.image_path, os.path.join(trash_dir, os.path.basename(d.image_path)))
                except Exception as exc:
                    logger.warning("[storage-cleanup] Trash move failed for %s: %s", d.image_path, exc)
                d.image_path = None

        for s in abandoned_student_docs:
            if s.storage_path:
                try:
                    await storage.delete_file(s.storage_bucket or settings.SUPABASE_STORAGE_BUCKET, s.storage_path)
                except Exception as exc:
                    logger.warning("[storage-cleanup] Storage delete failed for %s: %s", s.storage_path, exc)
                s.storage_path = None
            if s.file_path and os.path.isfile(s.file_path):
                try:
                    shutil.move(s.file_path, os.path.join(trash_dir, os.path.basename(s.file_path)))
                except Exception as exc:
                    logger.warning("[storage-cleanup] Trash move failed for %s: %s", s.file_path, exc)
                s.file_path = None

        for orphan in orphaned_bucket_files:
            try:
                await storage.delete_file(settings.SUPABASE_STORAGE_BUCKET, orphan)
            except Exception as exc:
                logger.warning("[storage-cleanup] Storage delete failed for orphan %s: %s", orphan, exc)

        await db.commit()
        logger.info("[storage-cleanup] Live cleanup complete. Local files moved to %s", trash_dir)


async def _prune_rate_limit_events_job():
    """Daily job to delete rate_limit_events rows older than 24 hours."""
    from datetime import datetime, timedelta, timezone
    from sqlalchemy import delete
    from app.database import AsyncSessionLocal
    from app.models.rate_limit import RateLimitEvent
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    try:
        async with AsyncSessionLocal() as session:
            stmt = delete(RateLimitEvent).where(RateLimitEvent.timestamp < cutoff)
            res = await session.execute(stmt)
            await session.commit()
            logger.info("[scheduler] Pruned %d expired rate limit events (>24h).", res.rowcount)
    except Exception as exc:
        logger.warning("[scheduler] Pruning rate limit events failed: %s", exc)


def start_scheduler():
    # Run alert generation every day at 8:00 AM (Asia/Kolkata)
    scheduler.add_job(
        _daily_alert_job,
        trigger=CronTrigger(hour=8, minute=0, timezone=KOLKATA_TZ),
        id="daily_alerts",
        replace_existing=True,
    )
    # Mark overdue assignments every day at midnight (Asia/Kolkata)
    scheduler.add_job(
        _mark_overdue_job,
        trigger=CronTrigger(hour=0, minute=0, timezone=KOLKATA_TZ),
        id="mark_overdue",
        replace_existing=True,
    )
    # Crawl configured college sites once a day at 2:00 AM (Asia/Kolkata)
    scheduler.add_job(
        _college_events_sync_job,
        trigger=CronTrigger(hour=2, minute=0, timezone=KOLKATA_TZ),
        id="college_events_sync",
        replace_existing=True,
    )
    # Storage audit & cleanup once a day at 3:00 AM (Asia/Kolkata)
    scheduler.add_job(
        _storage_cleanup_job,
        trigger=CronTrigger(hour=3, minute=0, timezone=KOLKATA_TZ),
        id="storage_cleanup",
        replace_existing=True,
    )
    # Prune expired rate limit events once a day at 4:00 AM (Asia/Kolkata)
    scheduler.add_job(
        _prune_rate_limit_events_job,
        trigger=CronTrigger(hour=4, minute=0, timezone=KOLKATA_TZ),
        id="prune_rate_limit_events",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        "Scheduler started (Asia/Kolkata): daily_alerts at 8AM, mark_overdue at midnight, "
        "college_events_sync at 2AM, storage_cleanup at 3AM, prune_rate_limits at 4AM"
    )


async def run_startup_catchup() -> dict[str, str]:
    """
    Idempotent catch-up on server boot or wake-up from sleep.
    Runs ONLY safe, idempotent tasks:
      1. _mark_overdue_job: sets status='overdue' where deadline < today and status='pending'
      2. _prune_rate_limit_events_job: purges rate limit audit records older than 24 hours
    Strictly DOES NOT scrape college portals or generate duplicate student alerts.
    """
    logger.info("[scheduler] Running idempotent startup catch-up...")
    results = {}
    try:
        await _mark_overdue_job()
        results["mark_overdue"] = "success"
    except Exception as exc:
        logger.warning("[scheduler] Startup catch-up mark_overdue failed: %s", exc)
        results["mark_overdue"] = f"error: {exc}"

    try:
        await _prune_rate_limit_events_job()
        results["prune_rate_limits"] = "success"
    except Exception as exc:
        logger.warning("[scheduler] Startup catch-up prune_rate_limits failed: %s", exc)
        results["prune_rate_limits"] = f"error: {exc}"

    logger.info("[scheduler] Startup catch-up complete: %s", results)
    return results


def stop_scheduler():
    scheduler.shutdown(wait=False)
