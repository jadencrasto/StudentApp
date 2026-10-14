from datetime import datetime, timedelta
from typing import Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.config import settings

# Password hashing context (PBKDF2 SHA256)
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# ─── Password ────────────────────────────────────────────────

def hash_password(plain_password: str) -> str:
    """Hash a plain text password."""
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Check a plain password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


# ─── JWT ─────────────────────────────────────────────────────

def create_access_token(
    subject: Any,
    expires_delta: timedelta | None = None,
    token_version: int | None = None,
) -> str:
    """
    Create a JWT access token.
    subject = user ID (str) stored in 'sub' claim.
    token_version = integer counter to support instant token invalidation.
    """
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {"sub": str(subject), "exp": expire, "iat": datetime.utcnow()}
    if token_version is not None:
        payload["ver"] = token_version
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """
    Decode and verify a JWT token.
    Returns the payload dict or None if invalid/expired.
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None
