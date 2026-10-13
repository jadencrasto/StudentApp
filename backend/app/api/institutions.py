import uuid
import secrets
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database import get_db
from app.core.dependencies import (
    require_super_admin,
    require_admin,
    get_admin_institution_id,
    scope_to_institution,
    get_institution_scoped_entity,
)
from app.core.security import hash_password
from app.models.user import User
from app.models.institution import Institution, Cohort, JoinRequest, generate_join_code
from app.schemas.schemas import (
    InstitutionCreate,
    InstitutionOut,
    InstitutionWithCountsOut,
    AdminUserCreate,
    AdminUserOut,
    AdminUserFullOut,
    ResetPasswordOut,
    CohortCreate,
    CohortUpdate,
    CohortOut,
    JoinRequestDecisionRequest,
    JoinRequestOut,
)

router = APIRouter(tags=["Institutions & Administration"])


async def _generate_unique_join_code(db: AsyncSession, length: int = 8) -> str:
    """Generate a join code that is unique across BOTH institutions and cohorts."""
    for _ in range(20):
        code = generate_join_code(length)
        inst_exists = await db.scalar(select(Institution).where(Institution.join_code == code))
        coh_exists = await db.scalar(select(Cohort).where(Cohort.join_code == code))
        if not inst_exists and not coh_exists:
            return code
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Failed to generate unique join code",
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# SUPER ADMIN ENDPOINTS
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/super-admin/institutions", response_model=InstitutionOut, status_code=201)
async def create_institution(
    data: InstitutionCreate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super Admin: create an institution and generate its unique join code."""
    code = await _generate_unique_join_code(db)

    institution = Institution(
        name=data.name.strip(),
        type=data.type,
        location=data.location.strip() if data.location else None,
        join_code=code,
        is_active=True,
    )
    db.add(institution)
    await db.commit()
    await db.refresh(institution)
    return institution


@router.get("/super-admin/institutions", response_model=list[InstitutionOut])
async def list_institutions(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super Admin: list all institutions."""
    stmt = select(Institution).order_by(Institution.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.get("/super-admin/institutions-with-counts", response_model=list[InstitutionWithCountsOut])
async def list_institutions_with_counts(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super Admin: list all institutions with admin, class and student counts."""
    stmt = select(Institution).order_by(Institution.created_at.desc())
    result = await db.execute(stmt)
    institutions = result.scalars().all()

    out = []
    for inst in institutions:
        admin_count = await db.scalar(
            select(func.count()).select_from(User).where(
                User.institution_id == inst.id, User.role == "admin"
            )
        )
        class_count = await db.scalar(
            select(func.count()).select_from(Cohort).where(
                Cohort.institution_id == inst.id
            )
        )
        student_count = await db.scalar(
            select(func.count()).select_from(User).where(
                User.institution_id == inst.id, User.role == "student"
            )
        )
        out.append(InstitutionWithCountsOut(
            id=inst.id,
            name=inst.name,
            type=inst.type,
            location=inst.location,
            join_code=inst.join_code,
            is_active=inst.is_active,
            created_at=inst.created_at,
            admin_count=admin_count or 0,
            class_count=class_count or 0,
            student_count=student_count or 0,
        ))
    return out


@router.patch("/super-admin/institutions/{institution_id}/deactivate", response_model=InstitutionOut)
async def deactivate_institution(
    institution_id: uuid.UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super Admin: deactivate an institution."""
    institution = await db.get(Institution, institution_id)
    if not institution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")

    institution.is_active = False
    await db.commit()
    await db.refresh(institution)
    return institution


@router.post("/super-admin/institutions/{institution_id}/admins", response_model=AdminUserOut, status_code=201)
async def create_institution_admin(
    institution_id: uuid.UUID,
    data: AdminUserCreate,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super Admin: create an admin user for a specific institution."""
    institution = await db.get(Institution, institution_id)
    if not institution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")

    # Check unique email and username
    existing_email = await db.scalar(select(User).where(User.email == data.email.lower()))
    if existing_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

    existing_username = await db.scalar(select(User).where(User.username == data.username.lower()))
    if existing_username:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Username already taken")

    admin = User(
        email=data.email.lower(),
        username=data.username.lower(),
        full_name=data.full_name,
        hashed_password=hash_password(data.password),
        role="admin",
        institution_id=institution.id,
        must_change_password=True,
        onboarding_completed=True,
    )
    db.add(admin)
    await db.commit()
    await db.refresh(admin)
    return admin


@router.get("/super-admin/admins", response_model=list[AdminUserFullOut])
async def list_all_admins(
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super Admin: list all admin users across all institutions."""
    stmt = (
        select(User, Institution.name)
        .outerjoin(Institution, User.institution_id == Institution.id)
        .where(User.role == "admin")
        .order_by(User.created_at.desc())
    )
    result = await db.execute(stmt)
    rows = result.all()

    out = []
    for user, inst_name in rows:
        out.append(AdminUserFullOut(
            id=user.id,
            email=user.email,
            username=user.username,
            full_name=user.full_name,
            role=user.role,
            institution_id=user.institution_id,
            institution_name=inst_name,
            is_active=user.is_active,
            must_change_password=user.must_change_password,
            created_at=user.created_at,
        ))
    return out


@router.patch("/super-admin/admins/{admin_id}/deactivate", response_model=AdminUserFullOut)
async def deactivate_admin(
    admin_id: uuid.UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super Admin: deactivate an admin account."""
    admin = await db.get(User, admin_id)
    if not admin or admin.role != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

    admin.is_active = False
    await db.commit()
    await db.refresh(admin)

    inst_name = None
    if admin.institution_id:
        inst = await db.get(Institution, admin.institution_id)
        inst_name = inst.name if inst else None

    return AdminUserFullOut(
        id=admin.id, email=admin.email, username=admin.username,
        full_name=admin.full_name, role=admin.role,
        institution_id=admin.institution_id, institution_name=inst_name,
        is_active=admin.is_active, must_change_password=admin.must_change_password,
        created_at=admin.created_at,
    )


@router.patch("/super-admin/admins/{admin_id}/reactivate", response_model=AdminUserFullOut)
async def reactivate_admin(
    admin_id: uuid.UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super Admin: reactivate an admin account."""
    admin = await db.get(User, admin_id)
    if not admin or admin.role != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

    admin.is_active = True
    await db.commit()
    await db.refresh(admin)

    inst_name = None
    if admin.institution_id:
        inst = await db.get(Institution, admin.institution_id)
        inst_name = inst.name if inst else None

    return AdminUserFullOut(
        id=admin.id, email=admin.email, username=admin.username,
        full_name=admin.full_name, role=admin.role,
        institution_id=admin.institution_id, institution_name=inst_name,
        is_active=admin.is_active, must_change_password=admin.must_change_password,
        created_at=admin.created_at,
    )


@router.post("/super-admin/admins/{admin_id}/reset-password", response_model=ResetPasswordOut)
async def reset_admin_password(
    admin_id: uuid.UUID,
    current_user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Super Admin: reset admin password to a random temporary password and set must_change_password."""
    admin = await db.get(User, admin_id)
    if not admin or admin.role != "admin":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found")

    charset = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789!@#$"
    temp_password = "".join(secrets.choice(charset) for _ in range(12))

    admin.hashed_password = hash_password(temp_password)
    admin.must_change_password = True
    await db.commit()

    return ResetPasswordOut(
        temporary_password=temp_password,
        message="Temporary password has been set. The administrator must change it on next login.",
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# ADMIN ENDPOINTS (SCOPED STRICTLY TO ADMIN'S INSTITUTION)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

@router.post("/admin/cohorts", response_model=CohortOut, status_code=201)
async def create_cohort(
    data: CohortCreate,
    institution_id: uuid.UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """Admin: create a cohort within their own institution."""
    # Check uniqueness: (institution_id, name, academic_year)
    stmt = select(Cohort).where(
        Cohort.institution_id == institution_id,
        Cohort.name == data.name.strip(),
        Cohort.academic_year == data.academic_year.strip(),
    )
    existing = await db.scalar(stmt)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A cohort with this name and academic year already exists in your institution",
        )

    # Auto-generate a unique join code for the class
    cohort_join_code = await _generate_unique_join_code(db)

    cohort = Cohort(
        institution_id=institution_id,
        name=data.name.strip(),
        level_type=data.level_type,
        level_value=data.level_value.strip(),
        department=data.department.strip() if data.department else None,
        academic_year=data.academic_year.strip(),
        is_active=True,
        join_code=cohort_join_code,
        join_code_enabled=True,
    )
    db.add(cohort)
    await db.commit()
    await db.refresh(cohort)
    return cohort


@router.get("/admin/cohorts", response_model=list[CohortOut])
async def list_cohorts(
    is_active: Optional[bool] = None,
    institution_id: uuid.UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """Admin: list all cohorts strictly in their own institution."""
    stmt = select(Cohort)
    stmt = scope_to_institution(stmt, Cohort, institution_id)
    if is_active is not None:
        stmt = stmt.where(Cohort.is_active == is_active)
    stmt = stmt.order_by(Cohort.name.asc())
    result = await db.execute(stmt)
    return result.scalars().all()


@router.patch("/admin/cohorts/{cohort_id}", response_model=CohortOut)
async def update_cohort(
    cohort_id: uuid.UUID,
    data: CohortUpdate,
    institution_id: uuid.UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """Admin: edit a cohort in their own institution."""
    cohort = await get_institution_scoped_entity(
        db, Cohort, cohort_id, institution_id, not_found_detail="Cohort not found"
    )

    if data.name is not None:
        cohort.name = data.name.strip()
    if data.level_type is not None:
        cohort.level_type = data.level_type
    if data.level_value is not None:
        cohort.level_value = data.level_value.strip()
    if data.department is not None:
        cohort.department = data.department.strip()
    if data.academic_year is not None:
        cohort.academic_year = data.academic_year.strip()
    if data.is_active is not None:
        cohort.is_active = data.is_active

    await db.commit()
    await db.refresh(cohort)
    return cohort


@router.patch("/admin/cohorts/{cohort_id}/deactivate", response_model=CohortOut)
async def deactivate_cohort(
    cohort_id: uuid.UUID,
    institution_id: uuid.UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """Admin: deactivate a cohort in their own institution."""
    cohort = await get_institution_scoped_entity(
        db, Cohort, cohort_id, institution_id, not_found_detail="Cohort not found"
    )
    cohort.is_active = False
    await db.commit()
    await db.refresh(cohort)
    return cohort


@router.post("/admin/institution/regenerate-join-code")
async def regenerate_institution_join_code(
    institution_id: uuid.UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """Admin: regenerate the join code for their institution."""
    institution = await db.get(Institution, institution_id)
    if not institution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Institution not found")

    code = await _generate_unique_join_code(db)
    institution.join_code = code
    await db.commit()
    await db.refresh(institution)
    return {
        "institution_id": institution.id,
        "join_code": institution.join_code,
    }


@router.post("/admin/cohorts/{cohort_id}/regenerate-join-code", response_model=CohortOut)
async def regenerate_cohort_join_code(
    cohort_id: uuid.UUID,
    institution_id: uuid.UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """Admin: regenerate the join code for a class in their institution."""
    cohort = await get_institution_scoped_entity(
        db, Cohort, cohort_id, institution_id, not_found_detail="Cohort not found"
    )

    code = await _generate_unique_join_code(db)
    cohort.join_code = code
    await db.commit()
    await db.refresh(cohort)
    return cohort


@router.patch("/admin/cohorts/{cohort_id}/toggle-join-code", response_model=CohortOut)
async def toggle_cohort_join_code(
    cohort_id: uuid.UUID,
    institution_id: uuid.UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """Admin: enable or disable the join code for a class."""
    cohort = await get_institution_scoped_entity(
        db, Cohort, cohort_id, institution_id, not_found_detail="Cohort not found"
    )

    cohort.join_code_enabled = not cohort.join_code_enabled
    await db.commit()
    await db.refresh(cohort)
    return cohort


@router.get("/admin/join-requests", response_model=list[JoinRequestOut])
async def list_join_requests(
    status_filter: Optional[str] = None,
    institution_id: uuid.UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """Admin: list join requests for their institution."""
    stmt = (
        select(JoinRequest, User, Cohort)
        .join(User, JoinRequest.user_id == User.id)
        .outerjoin(Cohort, JoinRequest.requested_cohort_id == Cohort.id)
    )
    stmt = scope_to_institution(stmt, JoinRequest, institution_id)
    if status_filter:
        stmt = stmt.where(JoinRequest.status == status_filter)
    stmt = stmt.order_by(JoinRequest.created_at.desc())

    result = await db.execute(stmt)
    records = result.all()

    out = []
    for req, user, cohort in records:
        out.append(
            JoinRequestOut(
                id=req.id,
                user_id=req.user_id,
                user_email=user.email,
                user_username=user.username,
                user_full_name=user.full_name,
                institution_id=req.institution_id,
                requested_cohort_id=req.requested_cohort_id,
                requested_cohort_name=cohort.name if cohort else None,
                status=req.status,
                decided_by=req.decided_by,
                decided_at=req.decided_at,
                created_at=req.created_at,
            )
        )
    return out


@router.post("/admin/join-requests/{request_id}/decide", response_model=JoinRequestOut)
async def decide_join_request(
    request_id: uuid.UUID,
    decision: JoinRequestDecisionRequest,
    admin_user: User = Depends(require_admin),
    institution_id: uuid.UUID = Depends(get_admin_institution_id),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin: approve (and optionally assign a cohort) or reject a pending join request.
    Strictly isolated: An admin of institution A cannot touch requests of institution B.
    """
    join_req = await get_institution_scoped_entity(
        db, JoinRequest, request_id, institution_id, not_found_detail="Join request not found"
    )

    if join_req.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Join request has already been decided ({join_req.status})",
        )

    student = await db.get(User, join_req.user_id)
    if not student:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Student not found")

    if decision.action == "approve":
        # Resolve cohort: either explicit from decision or the student's requested cohort
        target_cohort_id = decision.cohort_id or join_req.requested_cohort_id
        if target_cohort_id:
            cohort = await get_institution_scoped_entity(
                db, Cohort, target_cohort_id, institution_id, not_found_detail="Specified cohort not found in your institution"
            )
            student.cohort_id = cohort.id
        else:
            student.cohort_id = None

        student.institution_id = institution_id
        join_req.status = "approved"
    elif decision.action == "reject":
        join_req.status = "rejected"

    join_req.decided_by = admin_user.id
    join_req.decided_at = datetime.utcnow()

    await db.commit()
    await db.refresh(join_req)
    await db.refresh(student)

    # Fetch cohort name if present
    cohort_name = None
    if join_req.requested_cohort_id:
        coh = await db.get(Cohort, join_req.requested_cohort_id)
        cohort_name = coh.name if coh else None

    return JoinRequestOut(
        id=join_req.id,
        user_id=join_req.user_id,
        user_email=student.email,
        user_username=student.username,
        user_full_name=student.full_name,
        institution_id=join_req.institution_id,
        requested_cohort_id=join_req.requested_cohort_id,
        requested_cohort_name=cohort_name,
        status=join_req.status,
        decided_by=join_req.decided_by,
        decided_at=join_req.decided_at,
        created_at=join_req.created_at,
    )

