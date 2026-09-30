"""In-memory sliding window rate limiter and FastAPI dependency."""

import time
from collections import defaultdict, deque
from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Request

from src.core.config import settings
from src.core.exceptions import RateLimitExceededError


class SlidingWindowRateLimiter:
    """Sliding-window request counter maintaining request timestamps per key."""

    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # Mapping key -> deque of monotonic timestamps
        self._history: dict[str, deque[float]] = defaultdict(deque)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Check if request for key is allowed under rate limit.

        Returns:
            (allowed: bool, retry_after_seconds: int)
        """
        now = time.monotonic()
        cutoff = now - self.window_seconds
        queue = self._history[key]

        # Evict timestamps outside the active window
        while queue and queue[0] <= cutoff:
            queue.popleft()

        if len(queue) >= self.max_requests:
            oldest = queue[0]
            retry_after = max(1, int(self.window_seconds - (now - oldest)))
            return False, retry_after

        queue.append(now)
        return True, 0

    def reset(self) -> None:
        """Clear all rate limit history (useful for test suites)."""
        self._history.clear()


# Default limiter instances
default_api_limiter = SlidingWindowRateLimiter(
    max_requests=settings.RATE_LIMIT_PER_MINUTE,
    window_seconds=60,
)

auth_endpoint_limiter = SlidingWindowRateLimiter(
    max_requests=settings.AUTH_RATE_LIMIT_PER_MINUTE,
    window_seconds=60,
)


def rate_limit(
    limiter: SlidingWindowRateLimiter | None = None,
    max_requests: int | None = None,
    window_seconds: int = 60,
) -> Callable[[Request], Coroutine[Any, Any, None]]:
    """FastAPI dependency enforcing rate limits based on client IP."""
    active_limiter = limiter or SlidingWindowRateLimiter(
        max_requests=max_requests or settings.RATE_LIMIT_PER_MINUTE,
        window_seconds=window_seconds,
    )

    async def dependency(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        # Combine endpoint path and IP so limits are isolated per sensitive route
        limit_key = f"{client_ip}:{request.url.path}"

        allowed, retry_after = active_limiter.is_allowed(limit_key)
        if not allowed:
            raise RateLimitExceededError(
                message=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                retry_after=retry_after,
            )

    return dependency
