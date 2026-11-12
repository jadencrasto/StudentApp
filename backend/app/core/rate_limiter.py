import asyncio
import ipaddress
import logging
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Deque, Optional
from fastapi import Request
from jose import jwt
from slowapi import Limiter

from app.config import settings

logger = logging.getLogger("sais.rate_limiter")


def get_real_client_ip(request: Request) -> str:
    """
    Safely extract real client IP address behind reverse proxies (e.g. Cloudflare, Nginx).
    Only trusts X-Forwarded-For if the immediate peer (request.client.host) is in TRUSTED_PROXIES.
    """
    client_host = request.client.host if request.client else "127.0.0.1"

    trusted_raw = getattr(settings, "TRUSTED_PROXIES", "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16")
    trusted_networks = []
    for item in trusted_raw.split(","):
        item = item.strip()
        if not item:
            continue
        try:
            trusted_networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            try:
                trusted_networks.append(ipaddress.ip_network(f"{item}/32", strict=False))
            except ValueError:
                pass

    def _is_trusted(ip_str: str) -> bool:
        try:
            ip_obj = ipaddress.ip_address(ip_str)
            return any(ip_obj in net for net in trusted_networks)
        except ValueError:
            return False

    if not _is_trusted(client_host):
        return client_host

    # Peer is a trusted proxy: parse X-Forwarded-For from right to left
    xff = request.headers.get("X-Forwarded-For")
    if not xff:
        return client_host

    ips = [ip.strip() for ip in xff.split(",") if ip.strip()]
    for candidate in reversed(ips):
        if not _is_trusted(candidate):
            return candidate

    return client_host


def get_rate_limit_key(request: Request) -> str:
    """
    Key general rate limits by authenticated user ID from cookie if present;
    fall back to verified client IP address for anonymous requests.
    """
    token = request.cookies.get("access_token")
    if token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass
    return get_real_client_ip(request)


# Limiter instance with default general rate limit
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=[f"{settings.RATE_LIMIT_GENERAL_PER_MINUTE}/minute"],
)


async def _async_record_db_event(scope: str, key: str, event_time: datetime | None = None) -> None:
    """Record a rate limit event to rate_limit_events table with failure fallback."""
    from app.database import AsyncSessionLocal
    from app.models.rate_limit import RateLimitEvent
    if event_time is None:
        event_time = datetime.now(timezone.utc)
    try:
        async with AsyncSessionLocal() as session:
            evt = RateLimitEvent(
                id=uuid.uuid4(),
                scope=scope,
                key=key,
                timestamp=event_time,
            )
            session.add(evt)
            await session.commit()
    except Exception as exc:
        logger.warning("Database unavailable for rate limit record (scope=%s, key=%s): %s. Preserved in memory.", scope, key, exc)


record_rate_limit_event = _async_record_db_event


def _record_db_event(scope: str, key: str) -> None:
    """Non-blocking dispatch to record DB event if event loop is running."""
    # On in-memory SQLite (used in local test suite), concurrent background commits
    # on StaticPool corrupt the shared connection. Production uses Postgres.
    if settings.DATABASE_URL.startswith("sqlite"):
        return
    now_dt = datetime.now(timezone.utc)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_async_record_db_event(scope, key, now_dt))
    except RuntimeError:
        pass


class FailedLoginTracker:
    """
    Sliding window tracker for failed login attempts per email address.
    Dual-tracked in DB and in memory.
    """
    def __init__(self):
        self._attempts: dict[str, Deque[float]] = defaultdict(deque)

    def is_locked(self, email: str, limit: int = 5, window_seconds: int = 60) -> bool:
        normalized = (email or "").strip().lower()
        if not normalized:
            return False
        now = time.time()
        history = self._attempts[normalized]
        while history and history[0] <= now - window_seconds:
            history.popleft()
        return len(history) >= limit

    def record_failure(self, email: str, window_seconds: int = 60):
        normalized = (email or "").strip().lower()
        if not normalized:
            return
        now = time.time()
        history = self._attempts[normalized]
        while history and history[0] <= now - window_seconds:
            history.popleft()
        history.append(now)
        _record_db_event("failed_login", normalized)

    def record_success(self, email: str):
        normalized = (email or "").strip().lower()
        self._attempts.pop(normalized, None)


failed_login_tracker = FailedLoginTracker()


class JoinAttemptTracker:
    """
    Sliding window tracker for join attempts per user (default 10 attempts per hour).
    Dual-tracked in DB and in memory.
    """
    def __init__(self):
        self._attempts: dict[str, Deque[float]] = defaultdict(deque)

    def is_rate_limited(self, user_id: str, limit: int = 10, window_seconds: int = 3600) -> bool:
        uid = str(user_id)
        now = time.time()
        history = self._attempts[uid]
        while history and history[0] <= now - window_seconds:
            history.popleft()
        return len(history) >= limit

    def record_attempt(self, user_id: str, window_seconds: int = 3600):
        uid = str(user_id)
        now = time.time()
        history = self._attempts[uid]
        while history and history[0] <= now - window_seconds:
            history.popleft()
        history.append(now)
        _record_db_event("join_attempt", uid)

    def reset(self, user_id: str | None = None):
        if user_id:
            self._attempts.pop(str(user_id), None)
        else:
            self._attempts.clear()


join_attempt_tracker = JoinAttemptTracker()


class AIExtractionTracker:
    """
    Sliding window tracker for AI extraction attempts per admin (default 5 attempts per hour).
    Dual-tracked in DB and in memory.
    """
    def __init__(self):
        self._attempts: dict[str, Deque[float]] = defaultdict(deque)

    def is_rate_limited(self, user_id: str, limit: int = 5, window_seconds: int = 3600) -> bool:
        uid = str(user_id)
        now = time.time()
        history = self._attempts[uid]
        while history and history[0] <= now - window_seconds:
            history.popleft()
        return len(history) >= limit

    def record_attempt(self, user_id: str, window_seconds: int = 3600):
        uid = str(user_id)
        now = time.time()
        history = self._attempts[uid]
        while history and history[0] <= now - window_seconds:
            history.popleft()
        history.append(now)
        _record_db_event("ai_extraction", uid)

    def remaining_attempts(self, user_id: str, limit: int = 5, window_seconds: int = 3600) -> int:
        uid = str(user_id)
        now = time.time()
        history = self._attempts[uid]
        while history and history[0] <= now - window_seconds:
            history.popleft()
        return max(0, limit - len(history))

    def rollback_attempt(self, user_id: str):
        """Remove the most recent attempt for user (e.g. if request resulted in 503 busy)."""
        uid = str(user_id)
        history = self._attempts.get(uid)
        if history:
            history.pop()

    def reset(self, user_id: str | None = None):
        if user_id:
            self._attempts.pop(str(user_id), None)
        else:
            self._attempts.clear()


ai_extraction_tracker = AIExtractionTracker()


class QuotaCooldownTracker:
    """
    Tracks AI quota cooldown (e.g. 5 minutes) when daily quota (429) is hit anywhere.
    Dual-tracked in DB and in memory.
    """
    def __init__(self):
        self._cooldown_until: float = 0.0

    def set_cooldown(self, seconds: float = 300.0):
        now = time.time()
        self._cooldown_until = max(self._cooldown_until, now + seconds)
        _record_db_event("quota_cooldown", f"cooldown:{int(self._cooldown_until)}")

    def is_in_cooldown(self) -> bool:
        return time.time() < self._cooldown_until

    def reset(self):
        self._cooldown_until = 0.0


quota_cooldown_tracker = QuotaCooldownTracker()


async def hydrate_rate_limiters_from_db() -> None:
    """
    On startup, hydrate active sliding windows from the rate_limit_events database table.
    Gracefully handles database unavailability.
    """
    from sqlalchemy import select
    from app.database import AsyncSessionLocal
    from app.models.rate_limit import RateLimitEvent

    now = datetime.now(timezone.utc)
    cutoff_1h = now - timedelta(hours=1)
    cutoff_login = now - timedelta(seconds=60)

    try:
        async with AsyncSessionLocal() as session:
            # 1. Hydrate failed logins (< 60s)
            res = await session.execute(
                select(RateLimitEvent).where(
                    RateLimitEvent.scope == "failed_login",
                    RateLimitEvent.timestamp >= cutoff_login,
                ).order_by(RateLimitEvent.timestamp.asc())
            )
            for row in res.scalars():
                ts = row.timestamp.replace(tzinfo=timezone.utc).timestamp() if row.timestamp.tzinfo is None else row.timestamp.timestamp()
                failed_login_tracker._attempts[row.key].append(ts)

            # 2. Hydrate join attempts (< 1h)
            res = await session.execute(
                select(RateLimitEvent).where(
                    RateLimitEvent.scope == "join_attempt",
                    RateLimitEvent.timestamp >= cutoff_1h,
                ).order_by(RateLimitEvent.timestamp.asc())
            )
            for row in res.scalars():
                ts = row.timestamp.replace(tzinfo=timezone.utc).timestamp() if row.timestamp.tzinfo is None else row.timestamp.timestamp()
                join_attempt_tracker._attempts[row.key].append(ts)

            # 3. Hydrate AI timetable extractions (< 1h)
            res = await session.execute(
                select(RateLimitEvent).where(
                    RateLimitEvent.scope == "ai_extraction",
                    RateLimitEvent.timestamp >= cutoff_1h,
                ).order_by(RateLimitEvent.timestamp.asc())
            )
            for row in res.scalars():
                ts = row.timestamp.replace(tzinfo=timezone.utc).timestamp() if row.timestamp.tzinfo is None else row.timestamp.timestamp()
                ai_extraction_tracker._attempts[row.key].append(ts)

            # 4. Hydrate quota cooldown
            res = await session.execute(
                select(RateLimitEvent).where(
                    RateLimitEvent.scope == "quota_cooldown",
                    RateLimitEvent.timestamp >= now - timedelta(minutes=10),
                ).order_by(RateLimitEvent.timestamp.desc())
            )
            latest_cooldown = res.scalars().first()
            if latest_cooldown and latest_cooldown.key.startswith("cooldown:"):
                try:
                    cd_until = float(latest_cooldown.key.split(":", 1)[1])
                    if cd_until > time.time():
                        quota_cooldown_tracker._cooldown_until = cd_until
                except ValueError:
                    pass

        logger.info("Hydrated rate limiters from database successfully.")
    except Exception as exc:
        logger.warning("Could not hydrate rate limiters from DB on startup: %s. Using clean in-memory state.", exc)
