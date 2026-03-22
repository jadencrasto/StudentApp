from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.schemas import ActivityCreate, ActivityUpdate, ActivityOut
from app.services import activity_service

router = APIRouter(prefix="/activities", tags=["Activities"])


@router.post("", response_model=ActivityOut, status_code=201)
async def create_activity(
    data: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Add a new extracurricular activity.
    If recurrence_type is not 'none', instances are auto-generated for each
    occurrence date between recurrence_start_date and recurrence_end_date.
    """
    return await activity_service.create_activity(current_user.id, data, db)


@router.get("", response_model=list[ActivityOut])
async def list_activities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all activities (including recurring instances), ordered by date."""
    return await activity_service.get_activities(current_user.id, db)


@router.put("/{activity_id}", response_model=ActivityOut)
async def update_activity(
    activity_id: UUID,
    data: ActivityUpdate,
    update_series: bool = Query(default=False, description="If true and activity is a recurring instance, update the parent and regenerate all instances"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an activity. Pass update_series=true to update an entire recurring series."""
    return await activity_service.update_activity(current_user.id, activity_id, data, db, update_series)


@router.delete("/{activity_id}", status_code=204)
async def delete_activity(
    activity_id: UUID,
    delete_series: bool = Query(default=False, description="If true and activity is a recurring instance, delete the parent and all instances"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an activity. Pass delete_series=true to delete an entire recurring series."""
    await activity_service.delete_activity(current_user.id, activity_id, db, delete_series)


@router.post("/refresh-conflicts")
async def refresh_conflicts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-run conflict detection for all activities."""
    count = await activity_service.refresh_all_conflicts(current_user.id, db)
    return {"updated": count}
