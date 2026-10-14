from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.core.dependencies import get_current_user
from app.core.rate_limiter import join_attempt_tracker
from app.models.user import User
from app.models.institution import Institution, Cohort, JoinRequest
from app.schemas.schemas import (
    JoinCodeSubmitRequest,
    ClassCodeSubmitRequest,
    JoinResponseOut,
    UserProfileUpdateRequest,
    UserOut,
)
from app.api.auth import build_user_out

router = APIRouter(tags=["Student Join & Profile"])


@router.post("/join", response_model=JoinResponseOut)
async def submit_join_request(
    data: JoinCodeSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Step 1: Submit an institution join code to request membership in an institution.
    Safety features:
      - Rate limited to 10 attempts per hour per user.
      - Class code cannot be entered at this step.
      - Uses identical error message for nonexistent and inactive institutions.
      - Never discloses institution details before approval.
      - Enforces that a user can have only one pending join request.
    """
    # 1. Rate limiting per user
    if join_attempt_tracker.is_rate_limited(str(current_user.id), limit=10, window_seconds=3600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: too many join attempts. Please try again later.",
        )
    join_attempt_tracker.record_attempt(str(current_user.id), window_seconds=3600)

    # 2. Check if user is already in an institution
    if current_user.institution_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already a member of an institution. Use a class join code to join a class.",
        )

    # 3. Check for existing pending request (only ONE pending request at a time)
    existing_pending = await db.scalar(
        select(JoinRequest).where(
            JoinRequest.user_id == current_user.id,
            JoinRequest.status == "pending",
        )
    )
    if existing_pending:
        req_type_label = "class" if existing_pending.request_type == "class" else "institution"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You already have a pending {req_type_label} join request awaiting approval.",
        )

    # 4. Validate institution join code strictly (reject class codes at Step 1)
    normalized_code = (data.join_code or "").strip().upper()

    institution = await db.scalar(
        select(Institution).where(Institution.join_code == normalized_code)
    )
    if institution is None or not institution.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid join code",
        )

    # 5. Create pending institution join request (requested_cohort_id is ALWAYS None)
    join_request = JoinRequest(
        user_id=current_user.id,
        institution_id=institution.id,
        requested_cohort_id=None,
        request_type="institution",
        status="pending",
    )
    db.add(join_request)
    await db.commit()

    return JoinResponseOut(
        status="pending",
        message="Join request submitted successfully. Awaiting administrator approval.",
    )


@router.post("/join/class", response_model=JoinResponseOut)
async def submit_class_join_request(
    data: ClassCodeSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Step 2: Submit a class join code to request membership in a specific class.
    Safety features:
      - Rate limited to 10 attempts per hour per user.
      - User MUST already be approved into an institution.
      - User must NOT already be enrolled in a class.
      - Enforces that a user can have only one pending join request.
      - Class code must belong to user's own institution. Codes from other institutions
        or non-existent codes return generic 'Invalid class code' (no information disclosure).
    """
    # 1. Rate limiting per user
    if join_attempt_tracker.is_rate_limited(str(current_user.id), limit=10, window_seconds=3600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded: too many join attempts. Please try again later.",
        )
    join_attempt_tracker.record_attempt(str(current_user.id), window_seconds=3600)

    # 2. Check institution membership and active status
    if current_user.institution_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must be approved into an institution before entering a class code.",
        )
    institution = await db.get(Institution, current_user.institution_id)
    if institution is None or not institution.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid class code",
        )

    # 3. Check if already in a class
    if current_user.cohort_id is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are already enrolled in a class.",
        )

    # 4. Check for existing pending request (only ONE pending request at a time)
    existing_pending = await db.scalar(
        select(JoinRequest).where(
            JoinRequest.user_id == current_user.id,
            JoinRequest.status == "pending",
        )
    )
    if existing_pending:
        req_type_label = "class" if existing_pending.request_type == "class" else "institution"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"You already have a pending {req_type_label} join request awaiting approval.",
        )

    # 5. Validate class join code
    normalized_code = (data.join_code or "").strip().upper()
    cohort = await db.scalar(
        select(Cohort).where(Cohort.join_code == normalized_code)
    )
    # Reject if cohort doesn't exist, inactive, join code disabled, or belongs to another institution
    if (
        cohort is None
        or not cohort.is_active
        or not cohort.join_code_enabled
        or cohort.institution_id != current_user.institution_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid class code",
        )

    # 6. Create class join request
    join_request = JoinRequest(
        user_id=current_user.id,
        institution_id=current_user.institution_id,
        requested_cohort_id=cohort.id,
        request_type="class",
        status="pending",
    )
    db.add(join_request)
    await db.commit()

    return JoinResponseOut(
        status="pending",
        message="Class join request submitted successfully. Awaiting administrator approval.",
    )


@router.patch("/me/profile", response_model=UserOut)
async def update_profile(
    data: UserProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update onboarding profile fields.
    Automatically marks onboarding_completed=True.
    A student can never change their own role, institution_id, or cohort_id.
    """
    if data.education_level is not None:
        current_user.education_level = data.education_level
    if data.grade_or_year is not None:
        current_user.grade_or_year = data.grade_or_year
    if data.location is not None:
        current_user.location = data.location
    if data.institution_name_text is not None:
        current_user.institution_name_text = data.institution_name_text
    if data.extra_info is not None:
        current_user.extra_info = data.extra_info

    current_user.onboarding_completed = True
    await db.commit()
    await db.refresh(current_user)
    return await build_user_out(current_user, db)
