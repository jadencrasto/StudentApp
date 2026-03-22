"""
SAIS Scheduler — Cron Jobs
Runs daily at 8AM to:
  1. Generate fresh AI alerts for all active users
  2. Mark assignments as overdue if deadline has passed
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import logging

logger = logging.getLogger("sais.scheduler")
scheduler = AsyncIOScheduler()


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


def start_scheduler():
    # Run alert generation every day at 8:00 AM
    scheduler.add_job(
        _daily_alert_job,
        trigger=CronTrigger(hour=8, minute=0),
        id="daily_alerts",
        replace_existing=True,
    )
    # Mark overdue assignments every day at midnight
    scheduler.add_job(
        _mark_overdue_job,
        trigger=CronTrigger(hour=0, minute=0),
        id="mark_overdue",
        replace_existing=True,
    )
    # Crawl configured college sites every hour (cron-ready)
    scheduler.add_job(
        _college_events_sync_job,
        trigger=CronTrigger(minute=0),
        id="college_events_sync",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started: daily_alerts at 8AM, mark_overdue at midnight, college_events_sync hourly")


def stop_scheduler():
    scheduler.shutdown(wait=False)
