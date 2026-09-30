"""Integration tests for foundation application factory, middleware, and operational endpoints."""

import httpx
import pytest


@pytest.mark.asyncio
async def test_health_check_endpoint(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_correlation_id_middleware(async_client: httpx.AsyncClient) -> None:
    # 1. Custom correlation ID passed in request
    custom_id = "test-corr-id-12345"
    response = await async_client.get("/health", headers={"X-Correlation-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("X-Correlation-ID") == custom_id

    # 2. Generated correlation ID when not passed
    auto_response = await async_client.get("/health")
    assert auto_response.status_code == 200
    assert "X-Correlation-ID" in auto_response.headers
    assert len(auto_response.headers["X-Correlation-ID"]) > 0


@pytest.mark.asyncio
async def test_not_found_returns_standard_error_envelope(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/api/v1/non-existent-route")
    assert response.status_code == 404
    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "NOT_FOUND"
    assert "message" in data["error"]
