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
    Submit a join code to request membership in an institution.
    Safety features:
      - Rate limited to 10 attempts per hour per user.
      - Uses identical error message for nonexistent and inactive institutions.
      - Never discloses institution or cohort details before approval.
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
            detail="You are already a member of an institution",
        )

    # 3. Check for existing pending request
    existing_pending = await db.scalar(
        select(JoinRequest).where(
            JoinRequest.user_id == current_user.id,
            JoinRequest.status == "pending",
        )
    )
    if existing_pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have a pending join request",
        )

    # 4. Validate join code
    normalized_code = (data.join_code or "").strip().upper()

    cohort = await db.scalar(
        select(Cohort).where(Cohort.join_code == normalized_code)
    )
    if cohort is not None:
        if not cohort.join_code_enabled or not cohort.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid join code",
            )
        institution = await db.get(Institution, cohort.institution_id)
        if institution is None or not institution.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid join code",
            )
        target_institution_id = institution.id
        requested_cohort_id = cohort.id
    else:
        institution = await db.scalar(
            select(Institution).where(Institution.join_code == normalized_code)
        )
        if institution is None or not institution.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid join code",
            )
        target_institution_id = institution.id
        requested_cohort_id = None
        if data.requested_cohort_id:
            coh = await db.scalar(
                select(Cohort).where(
                    Cohort.id == data.requested_cohort_id,
                    Cohort.institution_id == institution.id,
                    Cohort.is_active == True,
                )
            )
            if coh is None:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid join code",
                )
            requested_cohort_id = coh.id

    # 6. Create pending join request
    join_request = JoinRequest(
        user_id=current_user.id,
        institution_id=target_institution_id,
        requested_cohort_id=requested_cohort_id,
        status="pending",
    )
    db.add(join_request)
    await db.commit()

    # Never reveal institution name or details before approval
    return JoinResponseOut(
        status="pending",
        message="Join request submitted successfully. Awaiting administrator approval.",
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
