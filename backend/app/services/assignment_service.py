# =============================================================================
# ASSIGNMENT SERVICE
# =============================================================================
# This service handles all assignment-related operations in the SAIS system.
# It provides functions to create, read, update, delete assignments and
# also handles syncing assignments from Google Classroom.
# =============================================================================
from uuid import UUID
from datetime import date
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, func, case
from app.models.assignment import Assignment, AssignmentStatus
from app.models.document_alert import Document
import logging
from app.models.assignment import TaskType, Priority
from app.schemas.schemas import AssignmentCreate, AssignmentUpdate, AssignmentOut
from app.services.time_estimator import estimate_assignment_time

logger = logging.getLogger(__name__)

async def create_assignment(user_id: UUID, data: AssignmentCreate, db: AsyncSession) -> Assignment:
    """Create a new manual assignment in the database."""
    assignment = Assignment(
        user_id=user_id,
        title=data.title,
        subject=data.subject,
        task_type=data.task_type,
        deadline=data.deadline,
        priority=data.priority,
        status=AssignmentStatus.pending,
        description=data.description,
        ai_metadata={},
    )
    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)
    return assignment


async def estimate_assignment_time_background(
    assignment_id: UUID,
    user_id: UUID,
    title: str,
    description: str,
    task_type: str | None = None,
) -> None:
    """Estimate time in a background task and save to ai_metadata without blocking creation."""
    try:
        from app.database import AsyncSessionLocal
        from app.services.time_estimator import estimate_assignment_time

        text = f"{title} {description}".strip()
        time_estimate = await estimate_assignment_time(text, task_type)

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Assignment).where(
                    Assignment.id == assignment_id,
                    Assignment.user_id == user_id,
                )
            )
            assignment = result.scalar_one_or_none()
            if assignment:
                metadata = dict(assignment.ai_metadata or {})
                metadata["time_estimate"] = time_estimate
                assignment.ai_metadata = metadata
                await session.commit()
    except Exception as exc:
        logger.warning("Background assignment time estimation failed (%s)", type(exc).__name__)

# =============================================================================
# GET ASSIGNMENTS
# =============================================================================
# Step 5 — Send to frontend
# Retrieves assignments with optional filtering by status and subject
# =============================================================================
async def get_assignments(
    user_id: UUID,
    db: AsyncSession,
    status: str | None = None,
    subject: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[Assignment], int]:
    """Get assignments for a user with optional status/subject/date filtering and pagination.
    Returns (assignments, total_count).
    """
    base_where = [Assignment.user_id == user_id]

    if status:
        try:
            status_enum = AssignmentStatus(status)
            base_where.append(Assignment.status == status_enum)
        except ValueError:
            pass  # ignore invalid status values

    if subject:
        base_where.append(Assignment.subject.ilike(f"%{subject}%"))

    if start_date:
        base_where.append(Assignment.deadline >= start_date)

    if end_date:
        base_where.append(Assignment.deadline <= end_date)

    # 1. Total count matching criteria
    count_query = select(func.count(Assignment.id)).where(and_(*base_where))
    total_res = await db.execute(count_query)
    total_count = total_res.scalar() or 0

    # 2. Fetch rows with deterministic stable tie-breaker: deadline ASC NULLS LAST, id ASC
    query = (
        select(Assignment)
        .where(and_(*base_where))
        .order_by(Assignment.deadline.asc().nulls_last(), Assignment.id.asc())
    )

    if offset > 0:
        query = query.offset(offset)
    if limit is not None:
        query = query.limit(limit)

    result = await db.execute(query)
    return list(result.scalars().all()), total_count


def to_trimmed_assignment_out(a: Assignment) -> AssignmentOut:
    """Trim heavy ai_metadata fields in list view to reduce payload size."""
    meta = a.ai_metadata
    if meta and isinstance(meta, dict):
        trimmed_meta = {}
        if "time_estimate" in meta and isinstance(meta["time_estimate"], dict):
            te = meta["time_estimate"]
            trimmed_meta["time_estimate"] = {
                "estimated_hours": te.get("estimated_hours"),
                "complexity": te.get("complexity"),
            }
        if "classroom" in meta and isinstance(meta["classroom"], dict):
            cr = meta["classroom"]
            trimmed_meta["classroom"] = {
                "classroom_label": cr.get("classroom_label"),
                "submission_status": cr.get("submission_status"),
                "workflow_status": cr.get("workflow_status"),
                "link": cr.get("link"),
            }
        meta = trimmed_meta or None

    return AssignmentOut(
        id=a.id,
        user_id=a.user_id,
        title=a.title,
        subject=a.subject,
        task_type=a.task_type.value if hasattr(a.task_type, "value") else str(a.task_type),
        description=a.description,
        deadline=a.deadline,
        priority=a.priority.value if hasattr(a.priority, "value") else str(a.priority),
        status=a.status.value if hasattr(a.status, "value") else str(a.status),
        ai_metadata=meta,
        source_document_id=a.source_document_id,
        classroom_id=a.classroom_id,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


async def get_assignment_status_counts(user_id: UUID, db: AsyncSession) -> dict[str, int]:
    """Get total, open (pending+in_progress+overdue), pending, and overdue counts in a single query."""
    stmt = select(
        func.count(Assignment.id).label("total"),
        func.count(
            case(
                (Assignment.status.in_([AssignmentStatus.pending, AssignmentStatus.in_progress, AssignmentStatus.overdue]), 1)
            )
        ).label("open_count"),
        func.count(case((Assignment.status == AssignmentStatus.pending, 1))).label("pending_count"),
        func.count(case((Assignment.status == AssignmentStatus.overdue, 1))).label("overdue_count"),
    ).where(Assignment.user_id == user_id)
    row = (await db.execute(stmt)).one()
    return {
        "total": row.total or 0,
        "open": row.open_count or 0,
        "pending": row.pending_count or 0,
        "overdue": row.overdue_count or 0,
    }

# =============================================================================
# GET ASSIGNMENT BY ID
# =============================================================================
async def get_assignment_by_id(user_id: UUID, assignment_id: UUID, db: AsyncSession) -> Assignment:
    """Get a single assignment by ID for a user."""
    result = await db.execute(
        select(Assignment).where(
            and_(Assignment.id == assignment_id, Assignment.user_id == user_id)
        )
    )
    assignment = result.scalar_one_or_none()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")
    return assignment


async def update_assignment(
    user_id: UUID, assignment_id: UUID, data: AssignmentUpdate, db: AsyncSession
) -> Assignment:
    """Update an existing assignment with new data."""
    assignment = await get_assignment_by_id(user_id, assignment_id, db)
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(assignment, field, value)
    await db.flush()
    return assignment


# =============================================================================
# DELETE ASSIGNMENT
# =============================================================================
# Step 4 — Save to database (delete from database)
# Deletes an assignment from the database
# =============================================================================
async def delete_assignment(user_id: UUID, assignment_id: UUID, db: AsyncSession) -> None:
    """Delete an assignment from the database."""
    assignment = await get_assignment_by_id(user_id, assignment_id, db)
    await db.delete(assignment)
    await db.flush()


async def bulk_estimate_assignments(user_id: UUID, db: AsyncSession) -> dict:
    """Disabled — too slow for large assignment counts. Use per-assignment estimate instead."""
    return {"updated": 0, "total": 0, "message": "Bulk estimation disabled. Use per-assignment estimate button."}


async def get_upcoming_assignments(user_id: UUID, db: AsyncSession, days: int = 7) -> list[Assignment]:
    """Get assignments with deadlines in the next N days."""
    from datetime import timedelta
    from sqlalchemy import cast, String
    today = date.today()
    cutoff = today + timedelta(days=days)

    result = await db.execute(
        select(Assignment).where(
            and_(
                Assignment.user_id == user_id,
                Assignment.deadline >= today,
                Assignment.deadline <= cutoff,
                cast(Assignment.status, String) != AssignmentStatus.completed.value,
            )
        ).order_by(Assignment.deadline.asc())
    )
    return list(result.scalars().all())


# =============================================================================
# CREATE ASSIGNMENT FROM DOCUMENT
# =============================================================================
# Step 4 & 5 — Save to database and send to frontend
# Creates an assignment from an extracted document
# =============================================================================
async def create_assignment_from_document(user_id: UUID, document_id: UUID, db: AsyncSession) -> Assignment:
    """Create an assignment from an extracted document (Step 4 - Save to database)."""
    result = await db.execute(
        select(Document).where(
            and_(Document.id == document_id, Document.user_id == user_id)
        )
    )
    document = result.scalar_one_or_none()

    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    extracted = document.extracted_data or {}
    if not extracted:
        raise HTTPException(status_code=400, detail="Document not extracted yet")

    raw_text = document.raw_text or ""
    time_estimate = await estimate_assignment_time(
        text=raw_text,
        task_type=extracted.get("task_type") or "assignment",
    )

    title = extracted.get("title") or document.original_filename or "Extracted Assignment"
    subject = extracted.get("subject")

    task_type_val = extracted.get("task_type") or "assignment"
    try:
        task_type_val = TaskType(task_type_val).value
    except ValueError:
        task_type_val = TaskType.assignment.value

    priority_val = extracted.get("priority") or Priority.medium.value
    try:
        priority_val = Priority(priority_val).value
    except ValueError:
        priority_val = Priority.medium.value

    deadline_val = extracted.get("deadline")
    if isinstance(deadline_val, str):
        try:
            from dateutil import parser as dateutil_parser
            deadline_val = dateutil_parser.parse(deadline_val).date()
        except Exception:
            deadline_val = None

    assignment = Assignment(
        user_id=user_id,
        title=title,
        subject=subject,
        task_type=task_type_val,
        description=extracted.get("description"),
        deadline=deadline_val,
        priority=priority_val,
        source_document_id=document_id,
        ai_metadata={"time_estimate": time_estimate},
    )

    db.add(assignment)
    await db.flush()
    await db.refresh(assignment)
    return assignment


# =============================================================================
# SYNC CLASSROOM ASSIGNMENTS
# =============================================================================
# Step 3 & 4 — Process data and save to database
# This is the core function that syncs Google Classroom assignments to SAIS
# =============================================================================
async def sync_classroom_assignments(
    user_id: UUID, events: list[dict], db: AsyncSession
) -> dict:

    from datetime import date as date_type
    import logging

    log = logging.getLogger(__name__)
    created = 0
    updated = 0

    for event in events:
        # Only sync actual assignments, not announcements
        if event.get("type") != "Assignment":
            continue

        classroom_id = event.get("classroom_id")
        if not classroom_id:
            continue

        # Check if already synced
        result = await db.execute(
            select(Assignment).where(
                and_(
                    Assignment.user_id == user_id,
                    Assignment.classroom_id == str(classroom_id),
                )
            )
        )
        existing = result.scalar_one_or_none()

        # Map classroom workflow status → assignment status (Step 3 - Process data)
        workflow = event.get("workflow_status", "")
        sub_status = event.get("submission_status", "assigned")
        if workflow == "graded" or sub_status == "submitted":
            status_val = AssignmentStatus.completed.value
        else:
            status_val = AssignmentStatus.pending.value

        # Parse deadline
        deadline = None
        if event.get("due_date"):
            try:
                deadline = date_type.fromisoformat(event["due_date"])
            except (ValueError, TypeError):
                pass

        # Build a human-readable classroom status label (Step 3 - Process data)
        if workflow == "graded":
            classroom_label = "graded"
        elif sub_status == "submitted":
            classroom_label = "submitted"
        elif sub_status == "missing":
            classroom_label = "missing"
        elif deadline:
            classroom_label = "assigned"
        else:
            classroom_label = "no due date"

        classroom_meta = {
            "source": "google_classroom",
            "course": event.get("course"),
            "submission_status": sub_status,
            "workflow_status": workflow,
            "classroom_label": classroom_label,
            "link": event.get("link"),
            "is_graded": event.get("is_graded", False),
            "assigned_grade": event.get("assigned_grade"),
            "has_due_date": deadline is not None,
        }

        if existing:
            # Update existing synced assignment
            existing.title = event.get("title") or existing.title
            existing.deadline = deadline or existing.deadline
            existing.subject = event.get("course") or existing.subject
            existing.status = status_val
            meta = existing.ai_metadata or {}
            meta["classroom"] = classroom_meta
            existing.ai_metadata = meta
            updated += 1
        else:
            # Create new assignment from classroom event
            new_assignment = Assignment(
                user_id=user_id,
                title=event.get("title") or "Untitled",
                subject=event.get("course"),
                task_type=TaskType.assignment.value,
                description=event.get("description"),
                deadline=deadline,
                priority=Priority.medium.value,
                status=status_val,
                classroom_id=str(classroom_id),
                ai_metadata={"classroom": classroom_meta},
            )
            db.add(new_assignment)
            created += 1

    if created or updated:
        await db.flush()

    log.info(
        "Classroom sync for user %s: %d created, %d updated",
        user_id, created, updated,
    )
    return {"created": created, "updated": updated}
