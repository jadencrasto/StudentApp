from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import HTTPException
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.classroom.security import decrypt_secret, encrypt_secret
from app.config import settings
from app.models.integrations import GoogleToken

SCOPES = [
    "https://www.googleapis.com/auth/classroom.courses.readonly",
    "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
    "https://www.googleapis.com/auth/classroom.student-submissions.me.readonly",
    "https://www.googleapis.com/auth/classroom.announcements.readonly",
    "https://www.googleapis.com/auth/classroom.courseworkmaterials.readonly",
]


def _ensure_oauth_config() -> None:
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_REDIRECT_URI:
        raise HTTPException(status_code=500, detail="Google OAuth is not configured")


def _state_token(user_id: str) -> str:
    payload = {
        "uid": user_id,
        "purpose": "google_oauth",
        "exp": datetime.utcnow() + timedelta(minutes=10),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def _decode_state(token: str) -> str:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    if payload.get("purpose") != "google_oauth":
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    return payload["uid"]


def build_google_connect_url(user_id: str) -> str:
    _ensure_oauth_config()
    state = _state_token(user_id)
    params = {
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "scope": " ".join(SCOPES),
        "state": state,
    }
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"


async def exchange_code_and_store(db: AsyncSession, code: str, state: str) -> str:
    _ensure_oauth_config()
    if not settings.GOOGLE_CLIENT_SECRET:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_SECRET is not configured")

    user_id = UUID(_decode_state(state))

    payload = {
        "code": code,
        "client_id": settings.GOOGLE_CLIENT_ID,
        "client_secret": settings.GOOGLE_CLIENT_SECRET,
        "redirect_uri": settings.GOOGLE_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    async with httpx.AsyncClient(timeout=25) as client:
        token_resp = await client.post("https://oauth2.googleapis.com/token", data=payload)
    if token_resp.status_code >= 400:
        raise HTTPException(status_code=400, detail=f"OAuth token exchange failed: {token_resp.text}")

    token_data = token_resp.json()

    existing = await db.execute(select(GoogleToken).where(GoogleToken.user_id == user_id))
    record = existing.scalar_one_or_none()
    if record is None:
        record = GoogleToken(user_id=user_id, access_token="", refresh_token=None, expiry=None, scope=None)
        db.add(record)

    record.access_token = encrypt_secret(token_data["access_token"])
    if token_data.get("refresh_token"):
        record.refresh_token = encrypt_secret(token_data["refresh_token"])
    record.scope = token_data.get("scope", "")

    expires_in = int(token_data.get("expires_in", 3600))
    record.expiry = datetime.utcnow() + timedelta(seconds=expires_in)

    await db.flush()
    return str(user_id)


def _build_credentials(access_token: str, refresh_token: str | None, expiry, scope: str | None) -> Credentials:
    return Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.GOOGLE_CLIENT_ID,
        client_secret=settings.GOOGLE_CLIENT_SECRET,
        scopes=(scope.split() if scope else SCOPES),
        expiry=expiry,
    )


async def get_valid_access_token(db: AsyncSession, user_id: UUID) -> str:
    result = await db.execute(select(GoogleToken).where(GoogleToken.user_id == user_id))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Google account not connected")

    access_token = decrypt_secret(record.access_token)
    refresh_token = decrypt_secret(record.refresh_token) if record.refresh_token else None

    creds = _build_credentials(access_token, refresh_token, record.expiry, record.scope)
    if creds.expired and creds.refresh_token:
        try:
            import asyncio
            await asyncio.to_thread(creds.refresh, Request())
        except Exception as exc:
            raise HTTPException(
                status_code=403,
                detail="Google credentials expired or revoked. Please reconnect your Google account.",
            ) from exc
        record.access_token = encrypt_secret(creds.token)
        if creds.refresh_token:
            record.refresh_token = encrypt_secret(creds.refresh_token)
        record.expiry = creds.expiry
        await db.flush()
    elif creds.expired and not creds.refresh_token:
        raise HTTPException(
            status_code=403,
            detail="Google access token expired and no refresh token is stored. Please reconnect your Google account.",
        )

    return creds.token
