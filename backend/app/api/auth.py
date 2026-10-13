from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi.util import get_remote_address

from app.config import settings
from app.core.rate_limiter import limiter
from app.core.security import verify_password, hash_password
from app.database import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from sqlalchemy import select
from app.models.institution import Institution, Cohort, JoinRequest
from app.schemas.schemas import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    ChangePasswordRequest,
    UserOut,
    InstitutionBriefOut,
    CohortBriefOut,
    UserProfileUpdateRequest,
)
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


async def build_user_out(user: User, db: AsyncSession) -> UserOut:
    """Build UserOut with multi-tenant institution, cohort, and join request status."""
    institution_out = None
    if user.institution_id:
        inst = await db.get(Institution, user.institution_id)
        if inst:
            institution_out = InstitutionBriefOut.model_validate(inst)

    cohort_out = None
    if user.cohort_id:
        coh = await db.get(Cohort, user.cohort_id)
        if coh:
            cohort_out = CohortBriefOut.model_validate(coh)

    join_req = await db.scalar(
        select(JoinRequest)
        .where(JoinRequest.user_id == user.id)
        .order_by(JoinRequest.created_at.desc())
        .limit(1)
    )
    join_request_status = join_req.status if join_req else None

    return UserOut(
        id=user.id,
        email=user.email,
        username=user.username,
        full_name=user.full_name,
        created_at=user.created_at,
        role=user.role,
        must_change_password=user.must_change_password,
        onboarding_completed=user.onboarding_completed,
        education_level=user.education_level,
        grade_or_year=user.grade_or_year,
        location=user.location,
        institution_name_text=user.institution_name_text,
        extra_info=user.extra_info,
        institution=institution_out,
        cohort=cohort_out,
        join_request_status=join_request_status,
    )


@router.post("/register", response_model=UserOut, status_code=201)
@limiter.limit(f"{settings.RATE_LIMIT_AUTH_PER_MINUTE}/minute", key_func=get_remote_address)
async def register(request: Request, data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user account."""
    user = await auth_service.register_user(data, db)
    return await build_user_out(user, db)


@router.post("/signup", response_model=UserOut, status_code=201)
@limiter.limit(f"{settings.RATE_LIMIT_AUTH_PER_MINUTE}/minute", key_func=get_remote_address)
async def signup(request: Request, data: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Alias for register to support /auth/signup path."""
    user = await auth_service.register_user(data, db)
    return await build_user_out(user, db)


@router.post("/login", response_model=TokenResponse)
@limiter.limit(f"{settings.RATE_LIMIT_AUTH_PER_MINUTE}/minute", key_func=get_remote_address)
async def login(request: Request, data: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login and receive a JWT access token."""
    token = await auth_service.login_user(data, db)
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Get the currently authenticated user's profile with institution, cohort, and join status."""
    return await build_user_out(current_user, db)


@router.patch("/me/profile", response_model=UserOut)
async def update_profile_auth(
    data: UserProfileUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Update onboarding profile fields.
    Automatically marks onboarding_completed=True.
    A user cannot alter their role, institution_id, or cohort_id.
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


@router.post("/change-password", response_model=UserOut)
@limiter.limit("5/minute", key_func=get_remote_address)
async def change_password(
    request: Request,
    data: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Change user password. Clears must_change_password.
    Rate limited to 5 attempts per minute.
    """
    if not verify_password(data.current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )

    current_user.hashed_password = hash_password(data.new_password)
    current_user.must_change_password = False
    await db.commit()
    await db.refresh(current_user)
    return await build_user_out(current_user, db)


