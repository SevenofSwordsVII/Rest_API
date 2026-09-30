"""Contract tests verifying /auth endpoints against OpenAPI 3.1 specifications."""

import uuid

import httpx
import pytest

from src.core.rate_limit import auth_endpoint_limiter


@pytest.fixture(autouse=True)
def reset_auth_limiter() -> None:
    """Reset the sliding window rate limiter before each contract test."""
    auth_endpoint_limiter.reset()


@pytest.mark.asyncio
async def test_contract_register_success(async_client: httpx.AsyncClient) -> None:
    """POST /auth/register -> 201 Created conforming to UserResponse schema."""
    unique_email = f"contract_reg_{uuid.uuid4().hex[:8]}@example.com"
    payload = {
        "email": unique_email,
        "password": "StrongPassword123!",
        "full_name": "Contract Test User",
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 201

    data = response.json()
    assert "id" in data
    assert uuid.UUID(data["id"])
    assert data["email"] == unique_email
    assert data["full_name"] == "Contract Test User"
    assert data["is_active"] is True
    assert "created_at" in data
    assert "updated_at" in data
    assert "password" not in data
    assert "hashed_password" not in data


@pytest.mark.asyncio
async def test_contract_register_validation_error(async_client: httpx.AsyncClient) -> None:
    """POST /auth/register with invalid payload -> 400 ValidationError envelope."""
    payload = {
        "email": "invalid-email-format",
        "password": "short",  # < 8 chars
    }
    response = await async_client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 400

    data = response.json()
    assert "error" in data
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "message" in data["error"]
    assert isinstance(data["error"]["details"], list)
    assert len(data["error"]["details"]) > 0
    assert "request_id" in data


@pytest.mark.asyncio
async def test_contract_register_duplicate_conflict(async_client: httpx.AsyncClient) -> None:
    """POST /auth/register with duplicate email -> 409 ConflictError envelope."""
    email = f"conflict_{uuid.uuid4().hex[:8]}@example.com"
    payload = {"email": email, "password": "Password123!"}
    res1 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res1.status_code == 201

    res2 = await async_client.post("/api/v1/auth/register", json=payload)
    assert res2.status_code == 409
    data = res2.json()
    assert data["error"]["code"] == "CONFLICT"
    assert "request_id" in data


@pytest.mark.asyncio
async def test_contract_login_success(async_client: httpx.AsyncClient) -> None:
    """POST /auth/login -> 200 OK conforming to TokenPairResponse schema."""
    email = f"login_{uuid.uuid4().hex[:8]}@example.com"
    password = "CorrectPassword123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )

    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert isinstance(data["expires_in"], int)
    assert data["expires_in"] > 0


@pytest.mark.asyncio
async def test_contract_login_invalid_credentials(async_client: httpx.AsyncClient) -> None:
    """POST /auth/login with wrong credentials -> 401 UnauthorizedError envelope."""
    response = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent@example.com", "password": "WrongPassword!"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "request_id" in data


@pytest.mark.asyncio
async def test_contract_refresh_token_success(async_client: httpx.AsyncClient) -> None:
    """POST /auth/refresh -> 200 OK conforming to TokenPairResponse schema."""
    email = f"refresh_{uuid.uuid4().hex[:8]}@example.com"
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    refresh_token = login_res.json()["refresh_token"]

    response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "Bearer"
    assert data["expires_in"] > 0
    # Rotation must issue a distinct new refresh token
    assert data["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_contract_refresh_token_invalid(async_client: httpx.AsyncClient) -> None:
    """POST /auth/refresh with bogus token -> 401 UnauthorizedError envelope."""
    response = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": "totally-bogus-token"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"
    assert "request_id" in data


@pytest.mark.asyncio
async def test_contract_logout_success(async_client: httpx.AsyncClient) -> None:
    """POST /auth/logout -> 204 No Content."""
    email = f"logout_{uuid.uuid4().hex[:8]}@example.com"
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    login_data = login_res.json()

    response = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {login_data['access_token']}"},
        json={"refresh_token": login_data["refresh_token"]},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_contract_logout_unauthorized_without_bearer(
    async_client: httpx.AsyncClient,
) -> None:
    """POST /auth/logout without Bearer header -> 401 UnauthorizedError envelope."""
    response = await async_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": "some-token"},
    )
    assert response.status_code == 401
    data = response.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_contract_change_password_success(async_client: httpx.AsyncClient) -> None:
    """POST /auth/change-password -> 204 No Content."""
    email = f"chpass_{uuid.uuid4().hex[:8]}@example.com"
    password = "OldPassword123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    access_token = login_res.json()["access_token"]

    response = await async_client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {access_token}"},
        json={"current_password": password, "new_password": "NewStrongPassword456!"},
    )
    assert response.status_code == 204


@pytest.mark.asyncio
async def test_contract_get_me_success(async_client: httpx.AsyncClient) -> None:
    """GET /auth/me -> 200 OK conforming to UserResponse schema."""
    email = f"me_{uuid.uuid4().hex[:8]}@example.com"
    password = "Password123!"
    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Me User"},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    access_token = login_res.json()["access_token"]

    response = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == email
    assert data["full_name"] == "Me User"
    assert data["is_active"] is True
