from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque
from uuid import UUID

from fastapi import HTTPException

from app.config import settings


class AIRateLimiter:
    """
    Sliding-window in-memory rate limiter per user.
    Protects AI quota by enforcing maximum requests per hour per user.
    Configurable via AI_RATE_LIMIT_PER_HOUR in .env.
    """

    def __init__(self, window_seconds: int = 3600) -> None:
        self.window_seconds = window_seconds
        self.requests: dict[str, Deque[float]] = defaultdict(deque)

    @property
    def limit(self) -> int:
        return getattr(settings, "AI_RATE_LIMIT_PER_HOUR", 30)

    def check_rate_limit(self, user_id: UUID | str) -> None:
        """
        Check and record a request for user_id.
        Raises HTTP 429 if the user has reached their quota for the current window.
        """
        user_key = str(user_id)
        now = time.time()
        queue = self.requests[user_key]

        # Evict timestamps outside the sliding window
        window_start = now - self.window_seconds
        while queue and queue[0] <= window_start:
            queue.popleft()

        max_limit = self.limit
        if len(queue) >= max_limit:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: You have reached the limit of {max_limit} AI requests per hour. Please try again later.",
            )

        queue.append(now)

    def reset(self, user_id: UUID | str | None = None) -> None:
        """Reset rate limit counter for a specific user or all users (useful in tests)."""
        if user_id is not None:
            self.requests.pop(str(user_id), None)
        else:
            self.requests.clear()


ai_rate_limiter = AIRateLimiter()


def check_ai_rate_limit(user_id: UUID | str) -> None:
    ai_rate_limiter.check_rate_limit(user_id)
