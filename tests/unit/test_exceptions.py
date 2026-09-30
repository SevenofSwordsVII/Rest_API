"""Unit tests for custom domain exceptions and error response builder."""

from src.core.exceptions import (
    NotFoundError,
    RateLimitExceededError,
    build_error_response,
)


def test_custom_exception_properties() -> None:
    exc = NotFoundError("Project 123 not found")
    assert exc.status_code == 404
    assert exc.code == "NOT_FOUND"
    assert exc.message == "Project 123 not found"
    assert exc.details == []


def test_rate_limit_exception_includes_retry_after() -> None:
    exc = RateLimitExceededError(retry_after=42)
    assert exc.status_code == 429
    assert exc.code == "RATE_LIMIT_EXCEEDED"
    assert exc.headers.get("Retry-After") == "42"


def test_build_error_response_conforms_to_openapi_envelope() -> None:
    response = build_error_response(
        status_code=400,
        code="VALIDATION_ERROR",
        message="Invalid input payload",
        details=[{"field": "email", "issue": "Must be valid email"}],
    )
    assert response.status_code == 400
    import json

    data = json.loads(bytes(response.body).decode("utf-8"))
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert data["error"]["message"] == "Invalid input payload"
    assert len(data["error"]["details"]) == 1
