from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.schemas.schemas import AssignmentCreate, AssignmentUpdate, AssignmentOut, EstimateTimeRequest
from app.services import assignment_service
from app.services.time_estimator import estimate_assignment_time

router = APIRouter(prefix="/assignments", tags=["Assignments"])


@router.post("", response_model=AssignmentOut, status_code=201)
async def create(
    data: AssignmentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new assignment manually."""
    return await assignment_service.create_assignment(current_user.id, data, db)


@router.get("", response_model=list[AssignmentOut])
async def list_assignments(
    status:  str | None = Query(default=None),
    subject: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all assignments. Optional filters: status, subject."""
    return await assignment_service.get_assignments(current_user.id, db, status, subject)


@router.get("/upcoming", response_model=list[AssignmentOut])
async def upcoming(
    days: int = Query(default=7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get assignments due in the next N days (default 7)."""
    return await assignment_service.get_upcoming_assignments(current_user.id, db, days)


@router.get("/{assignment_id}", response_model=AssignmentOut)
async def get_one(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await assignment_service.get_assignment_by_id(current_user.id, assignment_id, db)


@router.patch("/{assignment_id}", response_model=AssignmentOut)
async def update(
    assignment_id: UUID,
    data: AssignmentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Partially update an assignment (status, deadline, etc.)."""
    return await assignment_service.update_assignment(current_user.id, assignment_id, data, db)


@router.delete("/{assignment_id}", status_code=204)
async def delete(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await assignment_service.delete_assignment(current_user.id, assignment_id, db)


@router.post("/estimate-time")
async def estimate_time(
    data: EstimateTimeRequest,
    current_user: User = Depends(get_current_user),
):
    if not data.text.strip():
        raise HTTPException(status_code=400, detail="Text is required")

    return await estimate_assignment_time(data.text, data.task_type)


@router.post("/estimate-all")
async def estimate_all_assignments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Backfill time estimates for all assignments missing them."""
    return await assignment_service.bulk_estimate_assignments(current_user.id, db)


@router.post("/{assignment_id}/estimate", response_model=AssignmentOut)
async def estimate_single(
    assignment_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-run time estimation for a single assignment and save the result."""
    assignment = await assignment_service.get_assignment_by_id(current_user.id, assignment_id, db)
    text = f"{assignment.title or ''} {assignment.description or ''}".strip()
    time_estimate = await estimate_assignment_time(text, assignment.task_type)
    assignment.ai_metadata = {**(assignment.ai_metadata or {}), "time_estimate": time_estimate}
    await db.flush()
    return assignment
