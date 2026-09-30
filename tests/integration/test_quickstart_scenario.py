"""Integration test executing the complete quickstart.md scenario walkthrough."""

import uuid

import httpx
import pytest

from src.core.rate_limit import auth_endpoint_limiter


@pytest.fixture(autouse=True)
def reset_limiter() -> None:
    """Reset the sliding window rate limiter before quickstart execution."""
    auth_endpoint_limiter.reset()


@pytest.mark.asyncio
async def test_full_quickstart_scenario(async_client: httpx.AsyncClient) -> None:
    """Execute all 5 scenarios from quickstart.md end-to-end."""
    suffix = uuid.uuid4().hex[:6]
    alice_email = f"alice_{suffix}@example.com"
    bob_email = f"bob_{suffix}@example.com"
    eve_email = f"eve_{suffix}@example.com"
    password = "SecurePassword123!"

    # =========================================================================
    # Scenario 1: User Registration & Authentication
    # =========================================================================
    # 1. Register Alice
    reg_alice_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": alice_email, "password": password, "full_name": "Alice Smith"},
    )
    assert reg_alice_res.status_code == 201
    assert reg_alice_res.json()["email"] == alice_email

    # 2. Login to get token pair
    login_alice_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": alice_email, "password": password},
    )
    assert login_alice_res.status_code == 200
    alice_tokens = login_alice_res.json()
    alice_token = alice_tokens["access_token"]
    alice_refresh = alice_tokens["refresh_token"]
    assert alice_tokens["expires_in"] == 900
    alice_auth = {"Authorization": f"Bearer {alice_token}"}

    # =========================================================================
    # Scenario 2: Organization Creation & Direct Member Addition
    # =========================================================================
    # 1. Alice creates Acme Corp (Alice is OWNER)
    org_res = await async_client.post(
        "/api/v1/orgs",
        headers=alice_auth,
        json={"name": f"Acme Corp {suffix}", "slug": f"acme-corp-{suffix}"},
    )
    assert org_res.status_code == 201
    org_id = org_res.json()["id"]

    # 2. Register Bob
    reg_bob_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": bob_email, "password": password, "full_name": "Bob Jones"},
    )
    assert reg_bob_res.status_code == 201
    bob_id = reg_bob_res.json()["id"]

    login_bob_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": bob_email, "password": password},
    )
    assert login_bob_res.status_code == 200
    bob_token = login_bob_res.json()["access_token"]
    bob_auth = {"Authorization": f"Bearer {bob_token}"}

    # 3. Alice adds Bob as MEMBER
    add_member_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        headers=alice_auth,
        json={"email": bob_email, "role": "MEMBER"},
    )
    assert add_member_res.status_code == 201
    assert add_member_res.json()["role"] == "MEMBER"

    # =========================================================================
    # Scenario 3: Tenant Isolation Verification
    # =========================================================================
    # 1. Register Eve
    reg_eve_res = await async_client.post(
        "/api/v1/auth/register",
        json={"email": eve_email, "password": password, "full_name": "Eve Mallory"},
    )
    assert reg_eve_res.status_code == 201

    login_eve_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": eve_email, "password": password},
    )
    assert login_eve_res.status_code == 200
    eve_token = login_eve_res.json()["access_token"]
    eve_auth = {"Authorization": f"Bearer {eve_token}"}

    # 2. Eve attempts to access Acme Corp projects -> 403 Forbidden
    eve_access_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects",
        headers=eve_auth,
    )
    assert eve_access_res.status_code == 403
    assert eve_access_res.json()["error"]["code"] == "FORBIDDEN"

    # =========================================================================
    # Scenario 4: Work Management (Project & Task Flow)
    # =========================================================================
    # 1. Alice creates Project Alpha
    proj_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects",
        headers=alice_auth,
        json={"name": "Project Alpha", "description": "Core initiative"},
    )
    assert proj_res.status_code == 201
    project_id = proj_res.json()["id"]

    # 2. Alice creates Task assigned to Bob
    task_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{project_id}/tasks",
        headers=alice_auth,
        json={"title": "Implement Auth", "priority": "HIGH", "assignee_id": bob_id},
    )
    assert task_res.status_code == 201
    task_id = task_res.json()["id"]
    assert task_res.json()["status"] == "TODO"

    # 3. Bob queries assigned tasks
    bob_query_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects/{project_id}/tasks?assignee_id={bob_id}&status=TODO",
        headers=bob_auth,
    )
    assert bob_query_res.status_code == 200
    tasks_items = bob_query_res.json()["items"]
    assert len(tasks_items) == 1
    assert tasks_items[0]["id"] == task_id

    # 4. Bob adds comment
    comment_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{project_id}/tasks/{task_id}/comments",
        headers=bob_auth,
        json={"content": "Working on initial schemas now."},
    )
    assert comment_res.status_code == 201
    assert comment_res.json()["content"] == "Working on initial schemas now."

    # =========================================================================
    # Scenario 5: Token Rotation & Reuse Detection
    # =========================================================================
    # 1. Rotate refresh token
    rotate_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": alice_refresh},
    )
    assert rotate_res.status_code == 200
    new_refresh_token = rotate_res.json()["refresh_token"]
    assert new_refresh_token != alice_refresh

    # 2. Adversary replays old refresh token -> 401 Unauthorized with reuse detection
    replay_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": alice_refresh},
    )
    assert replay_res.status_code == 401
    assert "reuse" in replay_res.json()["error"]["message"].lower()

    # 3. Verify family revocation: even the newly rotated token is now revoked
    revoked_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": new_refresh_token},
    )
    assert revoked_res.status_code == 401
