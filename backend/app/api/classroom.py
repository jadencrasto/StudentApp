import logging
from uuid import UUID

from cryptography.fernet import InvalidToken
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.classroom.oauth import build_google_connect_url, exchange_code_and_store
from app.classroom.security import decrypt_secret
from app.classroom.service import get_courses, get_events, get_materials, sync_all
from app.services.assignment_service import sync_classroom_assignments
from app.config import settings
from app.core.security import decode_access_token
from app.core.dependencies import get_current_user
from app.database import get_db
from app.models.integrations import GoogleToken
from app.models.user import User

log = logging.getLogger(__name__)

# OAuth routes — mounted at app root level (outside /api/v1)
# so the callback matches what's registered in Google Cloud Console
oauth_router = APIRouter(tags=["Google OAuth"])

router = APIRouter(tags=["Classroom"])

# =============================================================================
# DEBUG ENDPOINT
# =============================================================================
# Step 1 — User visits /auth/google/debug-config (optional debug)
#   → Returns debug info about Google OAuth configuration
# =============================================================================
@oauth_router.get("/auth/google/debug-config")
async def google_debug_config():
    """Debug endpoint to check Google OAuth configuration status."""
    client_id = settings.GOOGLE_CLIENT_ID or ""
    return {
        "debug": settings.DEBUG,
        "google_client_id_configured": bool(client_id),
        "google_client_id_suffix": client_id[-8:] if client_id else None,
        "google_client_secret_configured": bool(settings.GOOGLE_CLIENT_SECRET),
        "google_redirect_uri": settings.GOOGLE_REDIRECT_URI,
    }


# =============================================================================
# OAUTH CONNECT FLOW
# =============================================================================
# Step 1 — User clicks "Connect Google" on frontend
#   → Frontend calls /auth/google/connect with user token
#   → Backend generates Google OAuth URL and redirects user to Google
# Step 2 — User authorizes on Google
#   → Google redirects back to /auth/google/callback with auth code
# Step 3 — Backend exchanges code for tokens
#   → Stores access/refresh tokens in database
# =============================================================================
@oauth_router.get("/auth/google/connect")
async def google_connect(
    token: str = Query(..., min_length=20),
    db: AsyncSession = Depends(get_db),
):
    """Initiate Google OAuth flow - redirect user to Google login page."""
    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(status_code=401, detail="Invalid auth token")

    try:
        user_id = UUID(str(payload["sub"]))
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid auth token")

    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    url = build_google_connect_url(str(user.id))
    return RedirectResponse(url=url)


@oauth_router.get("/auth/google/callback")
async def google_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback - exchange auth code for tokens."""
    await exchange_code_and_store(db, code, state)
    # Redirect to whichever frontend port is active
    frontend_url = settings.ALLOWED_ORIGINS.split(",")[0].strip()
    return RedirectResponse(url=f"{frontend_url}/dashboard/classroom?connected=1")


# =============================================================================
# CLASSROOM API ENDPOINTS
# =============================================================================
# These endpoints are called by the frontend to sync classroom data
# =============================================================================

@router.get("/classroom/courses")
async def classroom_courses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await get_courses(db, current_user.id)


@router.get("/classroom/events")
async def classroom_events(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        events = await get_events(db, current_user.id)
    except InvalidToken:
        log.warning("Fernet decryption failed for user %s during events fetch", current_user.id)
        raise HTTPException(
            status_code=403,
            detail="Stored Google credentials could not be decrypted. "
                   "Please reconnect your Google account.",
        )
    # Auto-sync classroom assignments into the assignments table
    try:
        await sync_classroom_assignments(current_user.id, events, db)
    except Exception:
        log.warning(
            "Classroom → assignments sync failed for user %s", current_user.id, exc_info=True
        )
    return events


@router.get("/classroom/materials")
async def classroom_materials(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fetch course materials (documents, drive files, links) from all connected courses."""
    return await get_materials(db, current_user.id)


@router.get("/classroom/sync")
async def classroom_sync(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        data = await sync_all(db, current_user.id)
    except InvalidToken:
        log.warning("Fernet decryption failed for user %s during sync", current_user.id)
        raise HTTPException(
            status_code=403,
            detail="Stored Google credentials could not be decrypted. "
                   "Please reconnect your Google account.",
        )
    # Auto-sync classroom assignments into the assignments table
    try:
        await sync_classroom_assignments(current_user.id, data["events"], db)
    except Exception:
        log.warning(
            "Classroom → assignments sync failed for user %s", current_user.id, exc_info=True
        )
    return data


@router.get("/classroom/status")
async def classroom_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check if the current user has a connected Google account."""
    result = await db.execute(select(GoogleToken).where(GoogleToken.user_id == current_user.id))
    record = result.scalar_one_or_none()
    if not record:
        return {"connected": False}
    # Verify the stored token can still be decrypted
    try:
        decrypt_secret(record.access_token)
    except InvalidToken:
        log.warning("Fernet decryption failed for user %s during status check", current_user.id)
        return {
            "connected": False,
            "error": "Stored credentials could not be decrypted. Please reconnect your Google account.",
        }
    return {
        "connected": True,
        "scope": record.scope,
        "expiry": record.expiry.isoformat() if record.expiry else None,
    }


@router.delete("/classroom/disconnect")
async def classroom_disconnect(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove stored Google credentials — user must reconnect to use Classroom."""
    await db.execute(delete(GoogleToken).where(GoogleToken.user_id == current_user.id))
    return {"disconnected": True}
