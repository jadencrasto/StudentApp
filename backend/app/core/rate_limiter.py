import time
from collections import defaultdict, deque
from fastapi import Request
from jose import jwt
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.config import settings


def get_rate_limit_key(request: Request) -> str:
    """
    Key general rate limits by authenticated user ID if present;
    fall back to remote IP address for anonymous requests.
    This prevents students sharing one college Wi-Fi IP from throttling each other.
    """
    auth = request.headers.get("Authorization")
    if auth and auth.startswith("Bearer "):
        token = auth[7:].strip()
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass
    return get_remote_address(request)


# Limiter instance with default general rate limit
limiter = Limiter(
    key_func=get_rate_limit_key,
    default_limits=[f"{settings.RATE_LIMIT_GENERAL_PER_MINUTE}/minute"],
)


class FailedLoginTracker:
    """
    Sliding window tracker for failed login attempts per email address.
    """
    def __init__(self):
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

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

    def record_success(self, email: str):
        normalized = (email or "").strip().lower()
        self._attempts.pop(normalized, None)


failed_login_tracker = FailedLoginTracker()


class JoinAttemptTracker:
    """
    Sliding window tracker for join attempts per user (default 10 attempts per hour).
    Prevents brute-forcing institution join codes.
    """
    def __init__(self):
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

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

    def reset(self, user_id: str | None = None):
        if user_id:
            self._attempts.pop(str(user_id), None)
        else:
            self._attempts.clear()


join_attempt_tracker = JoinAttemptTracker()


class AIExtractionTracker:
    """
    Sliding window tracker for AI extraction attempts per admin (default 5 attempts per hour).
    Prevents abuse and quota exhaustion. Failed extraction attempts also count.
    """
    def __init__(self):
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

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

    def remaining_attempts(self, user_id: str, limit: int = 5, window_seconds: int = 3600) -> int:
        uid = str(user_id)
        now = time.time()
        history = self._attempts[uid]
        while history and history[0] <= now - window_seconds:
            history.popleft()
        return max(0, limit - len(history))

    def reset(self, user_id: str | None = None):
        if user_id:
            self._attempts.pop(str(user_id), None)
        else:
            self._attempts.clear()


ai_extraction_tracker = AIExtractionTracker()

