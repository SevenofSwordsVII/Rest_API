"""Integration tests for end-to-end authentication, rotating token lifecycle, and revocation."""

import asyncio
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.rate_limit import auth_endpoint_limiter
from src.domains.auth.models import User


@pytest.fixture(autouse=True)
def reset_auth_limiter() -> None:
    """Reset the sliding window rate limiter before each integration test."""
    auth_endpoint_limiter.reset()


@pytest.mark.asyncio
async def test_full_auth_lifecycle(async_client: httpx.AsyncClient) -> None:
    """Complete lifecycle: Register -> Login -> /me -> Refresh -> /me -> Logout."""
    email = f"lifecycle_{uuid.uuid4().hex[:8]}@example.com"
    password = "LifecyclePassword123!"

    # 1. Register
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Lifecycle User"},
    )
    assert reg_res.status_code == 201
    user_id = reg_res.json()["id"]

    # 2. Login
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_res.status_code == 200
    token_data = login_res.json()
    access_token = token_data["access_token"]
    refresh_token = token_data["refresh_token"]

    # 3. Access /auth/me with access token
    me_res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["id"] == user_id

    # 4. Rotate refresh token
    refresh_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 200
    new_token_data = refresh_res.json()
    new_access_token = new_token_data["access_token"]
    new_refresh_token = new_token_data["refresh_token"]
    assert new_refresh_token != refresh_token

    # 5. Access /auth/me with new access token
    new_me_res = await async_client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {new_access_token}"},
    )
    assert new_me_res.status_code == 200

    # 6. Logout
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {new_access_token}"},
        json={"refresh_token": new_refresh_token},
    )
    assert logout_res.status_code == 204

    # 7. Verify logged-out refresh token is rejected
    after_logout_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token},
    )
    assert after_logout_res.status_code == 401


@pytest.mark.asyncio
async def test_token_reuse_triggers_family_revocation(
    async_client: httpx.AsyncClient,
) -> None:
    """Replaying an already-consumed refresh token must revoke the entire session family."""
    email = f"reuse_{uuid.uuid4().hex[:8]}@example.com"
    password = "ReusePassword123!"

    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token_1 = login_res.json()["refresh_token"]

    # First rotation: Token 1 -> Token 2 (Valid)
    rot_1_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_1},
    )
    assert rot_1_res.status_code == 200
    token_2 = rot_1_res.json()["refresh_token"]

    # Attacker / replay: attempts to reuse Token 1
    reuse_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_1},
    )
    assert reuse_res.status_code == 401
    assert "reuse detected" in reuse_res.json()["error"]["message"].lower()

    # Legitimate client with Token 2 must now also be rejected because family was revoked
    victim_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_2},
    )
    assert victim_res.status_code == 401


@pytest.mark.asyncio
async def test_password_change_globally_revokes_all_sessions(
    async_client: httpx.AsyncClient,
) -> None:
    """Changing password must globally revoke active refresh tokens across all client devices."""
    email = f"global_rev_{uuid.uuid4().hex[:8]}@example.com"
    old_password = "InitialPassword123!"
    new_password = "ChangedPassword456!"

    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": old_password},
    )

    # Session 1 (Device A)
    session_a = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": old_password},
    )
    token_a = session_a.json()["refresh_token"]
    access_a = session_a.json()["access_token"]

    # Session 2 (Device B)
    session_b = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": old_password},
    )
    token_b = session_b.json()["refresh_token"]

    # Device A changes password
    chg_res = await async_client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {access_a}"},
        json={"current_password": old_password, "new_password": new_password},
    )
    assert chg_res.status_code == 204

    # Device B attempts to refresh session -> Must be rejected (globally revoked)
    refresh_b_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_b},
    )
    assert refresh_b_res.status_code == 401

    # Device A's old refresh token must also be rejected
    refresh_a_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token_a},
    )
    assert refresh_a_res.status_code == 401

    # Login with old password fails
    old_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": old_password},
    )
    assert old_login.status_code == 401

    # Login with new password succeeds
    new_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": new_password},
    )
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_concurrent_refresh_requests(async_client: httpx.AsyncClient) -> None:
    """Concurrent requests with same token must execute safely without database deadlocks."""
    email = f"concurrent_{uuid.uuid4().hex[:8]}@example.com"
    password = "ConcurrentPass123!"

    await async_client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    refresh_token = login_res.json()["refresh_token"]

    # Fire 3 concurrent refresh requests with the identical token
    responses = await asyncio.gather(
        async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token}),
        async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token}),
        async_client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token}),
    )

    status_codes = [r.status_code for r in responses]
    # Exactly one request succeeds (200), or due to reuse detection subsequent calls fail with 401
    assert 200 in status_codes
    assert status_codes.count(200) == 1
    assert status_codes.count(401) == 2


@pytest.mark.asyncio
async def test_deactivated_user_cannot_authenticate_or_refresh(
    async_client: httpx.AsyncClient,
    db_session: AsyncSession,
) -> None:
    """Deactivated user account is immediately blocked from login and token refresh."""
    email = f"deactive_{uuid.uuid4().hex[:8]}@example.com"
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
    access_token = login_res.json()["access_token"]

    # Deactivate the user directly in database
    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    user.is_active = False
    await db_session.commit()

    # Login fails
    assert (
        await async_client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": password},
        )
    ).status_code == 401

    # Refresh fails
    assert (
        await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": refresh_token},
        )
    ).status_code == 401

    # Protected endpoint fails
    assert (
        await async_client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    ).status_code == 401
