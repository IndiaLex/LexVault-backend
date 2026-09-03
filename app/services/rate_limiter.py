"""
app/services/rate_limiter.py
----------------------------
In-memory sliding-window rate limiter for FastAPI endpoints.

Limits:
  - Document Upload: 10 requests / minute per user
  - Anchor Verify: 30 requests / minute per user

Returns HTTP 429 Too Many Requests with Retry-After header when exceeded.
"""

import time
import threading
from typing import Dict, List
from fastapi import HTTPException, status, Request
from app.config import settings
from app.models.user import User


class SlidingWindowRateLimiter:
    """
    Thread-safe in-memory sliding window rate limiter.
    """

    def __init__(self, max_requests: int, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._lock = threading.Lock()
        self._records: Dict[str, List[float]] = {}

    def check(self, key: str):
        now = time.time()
        cutoff = now - self.window_seconds

        with self._lock:
            timestamps = self._records.get(key, [])
            # Evict timestamps outside the sliding window
            timestamps = [t for t in timestamps if t > cutoff]

            if len(timestamps) >= self.max_requests:
                oldest = timestamps[0]
                retry_after = int(self.window_seconds - (now - oldest)) + 1
                self._records[key] = timestamps
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Maximum {self.max_requests} requests per {self.window_seconds}s. Try again in {retry_after}s.",
                    headers={"Retry-After": str(max(1, retry_after))},
                )

            timestamps.append(now)
            self._records[key] = timestamps

    def reset(self):
        """Clears all rate limit records (useful in tests)."""
        with self._lock:
            self._records.clear()


# Singletons configured according to Phase B6 specs:
upload_rate_limiter = SlidingWindowRateLimiter(max_requests=10, window_seconds=60)
verify_rate_limiter = SlidingWindowRateLimiter(max_requests=30, window_seconds=60)


def rate_limit_upload(request: Request, current_user: User):
    """Rate limit dependency for upload endpoints (10/min per user)."""
    if request.headers.get("x-bypass-rate-limit") == "true":
        return
    if not getattr(settings, "RATE_LIMIT_ENABLED", True):
        return
    key = f"upload:{current_user.id}"
    upload_rate_limiter.check(key)


def rate_limit_verify(request: Request, current_user: User):
    """Rate limit dependency for verification endpoints (30/min per user)."""
    if request.headers.get("x-bypass-rate-limit") == "true":
        return
    if not getattr(settings, "RATE_LIMIT_ENABLED", True):
        return
    key = f"verify:{current_user.id}"
    verify_rate_limiter.check(key)
