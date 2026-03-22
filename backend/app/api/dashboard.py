from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.models.assignment import Assignment, AssignmentStatus
from app.models.activity import Activity
from app.services.attendance_service import get_attendance_summary
from app.services.alert_service import get_alerts
from app.schemas.schemas import DashboardOut
from datetime import date, timedelta

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("", response_model=DashboardOut)
async def get_dashboard_data(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Stats
    # Pending Assignments
    res = await db.execute(
        select(func.count(Assignment.id)).where(
            Assignment.user_id == current_user.id,
            Assignment.status != AssignmentStatus.completed.value
        )
    )
    pending_count = res.scalar() or 0

    # Attendance Average
    attendance_summaries = await get_attendance_summary(current_user.id, db)
    if attendance_summaries:
        total_pct = sum(s.attendance_percentage for s in attendance_summaries)
        avg_attendance = round(total_pct / len(attendance_summaries), 1)
    else:
        avg_attendance = 0

    # Activities count (upcoming/total)
    res = await db.execute(
        select(func.count(Activity.id)).where(Activity.user_id == current_user.id)
    )
    activities_count = res.scalar() or 0

    # Alerts (unread)
    alerts = await get_alerts(current_user.id, db, unread_only=True)
    unread_alerts_count = len(alerts)

    # 2. Deadlines (next 5)
    res = await db.execute(
        select(Assignment)
        .where(
            Assignment.user_id == current_user.id,
            Assignment.status != AssignmentStatus.completed.value,
            Assignment.deadline >= date.today()
        )
        .order_by(Assignment.deadline.asc())
        .limit(5)
    )
    deadlines = res.scalars().all()

    return {
        "stats": {
            "pending_assignments": pending_count,
            "attendance_avg": avg_attendance,
            "upcoming_activities": activities_count,
            "unread_alerts": unread_alerts_count,
        },
        "deadlines": [
            {
                "id": str(a.id),
                "title": a.title,
                "subject": a.subject,
                "deadline": a.deadline.isoformat(),
                "status": a.status
            }
            for a in deadlines
        ],
        "alerts": [
            {
                "id": str(a.id),
                "title": a.title,
                "message": a.message,
                "type": a.alert_type.value,
                "created_at": a.created_at.isoformat()
            }
            for a in alerts[:5]
        ]
    }
