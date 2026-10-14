from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from uuid import UUID
from app.database import get_db
from app.core.security import decode_access_token
from app.models.user import User

# Extracts Bearer token from Authorization header
bearer_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    FastAPI dependency — use in any route that requires auth:
        current_user: User = Depends(get_current_user)

    Raises 401 if token is missing, invalid, or user not found.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(credentials.credentials)
    if payload is None:
        raise credentials_exception

    user_id_raw: str | None = payload.get("sub")
    if user_id_raw is None:
        raise credentials_exception

    try:
        user_id = UUID(user_id_raw)
    except (ValueError, TypeError):
        raise credentials_exception

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise credentials_exception

    # Invalidate token if token_version has been bumped or password was reset after token issue
    token_ver = payload.get("ver")
    if token_ver is not None and user.token_version is not None:
        if token_ver != user.token_version:
            raise credentials_exception
    elif user.password_changed_at is not None:
        iat = payload.get("iat")
        if iat is not None:
            if int(iat) < int(user.password_changed_at.timestamp()):
                raise credentials_exception

    return user


def require_role(*allowed_roles: str):
    """
    Dependency factory: verifies that current_user has one of the allowed roles.
    The role is always loaded fresh from the database on every request.
    """
    async def _role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Insufficient permissions",
            )
        return current_user

    return _role_checker


# Convenient pre-configured role dependencies
require_admin = require_role("admin")
require_super_admin = require_role("super_admin")


def get_admin_institution_id(
    admin_user: User = Depends(require_admin),
) -> UUID:
    """
    Extracts and ensures the administrator has a valid institution_id.
    Raises 403 if an admin is not assigned to an institution.
    """
    if not admin_user.institution_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin is not assigned to any institution",
        )
    return admin_user.institution_id


def scope_to_institution(stmt, model, institution_id: UUID):
    """
    Shared helper to enforce that any admin query is strictly filtered
    by the admin's institution_id.
    """
    return stmt.where(model.institution_id == institution_id)


async def get_institution_scoped_entity(
    db: AsyncSession,
    model,
    entity_id: UUID,
    institution_id: UUID,
    not_found_detail: str = "Resource not found",
):
    """
    Single entity fetcher strictly scoped to the admin's institution.
    Returns 404 if not found or belongs to another institution,
    ensuring cross-institution data is never revealed or modified.
    """
    stmt = select(model).where(
        model.id == entity_id,
        model.institution_id == institution_id,
    )
    result = await db.execute(stmt)
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=not_found_detail,
        )
    return entity

