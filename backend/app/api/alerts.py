from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.schemas import AlertOut
from app.services import alert_service

router = APIRouter(prefix="/alerts", tags=["Alerts"])


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    unread_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List alerts. Pass ?unread_only=true to get only unread."""
    return await alert_service.get_alerts(current_user.id, db, unread_only)


@router.post("/refresh")
async def refresh_alerts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Manually trigger AI prediction engine.
    Runs all rules and saves new alerts to DB.
    Also called by the cron job every morning.
    """
    new_alerts = await alert_service.generate_alerts(current_user.id, db)
    return {"generated": len(new_alerts)}


@router.patch("/{alert_id}/read", status_code=204)
async def mark_read(
    alert_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark a single alert as read."""
    await alert_service.mark_alert_read(current_user.id, alert_id, db)
