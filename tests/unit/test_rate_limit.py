"""Unit tests for sliding window rate limiter."""

from src.core.rate_limit import SlidingWindowRateLimiter


def test_sliding_window_rate_limiter_allows_under_limit() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=3, window_seconds=60)
    key = "127.0.0.1:/api/v1/auth/login"

    for _ in range(3):
        allowed, retry_after = limiter.is_allowed(key)
        assert allowed is True
        assert retry_after == 0


def test_sliding_window_rate_limiter_blocks_over_limit() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=2, window_seconds=60)
    key = "127.0.0.1:/api/v1/auth/login"

    # Consume quota
    assert limiter.is_allowed(key)[0] is True
    assert limiter.is_allowed(key)[0] is True

    # 3rd request must be blocked
    allowed, retry_after = limiter.is_allowed(key)
    assert allowed is False
    assert retry_after > 0


def test_sliding_window_resets() -> None:
    limiter = SlidingWindowRateLimiter(max_requests=1, window_seconds=60)
    key = "192.168.1.1:/test"

    assert limiter.is_allowed(key)[0] is True
    assert limiter.is_allowed(key)[0] is False

    limiter.reset()
    assert limiter.is_allowed(key)[0] is True
