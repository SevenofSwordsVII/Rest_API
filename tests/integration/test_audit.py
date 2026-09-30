"""Integration tests for immutable audit logging and role-governed access control."""

import uuid

import httpx
import pytest

from src.core.rate_limit import auth_endpoint_limiter


@pytest.fixture(autouse=True)
def reset_auth_limiter() -> None:
    """Reset the sliding window rate limiter before each test."""
    auth_endpoint_limiter.reset()


async def register_user(client: httpx.AsyncClient, name: str) -> tuple[str, str, str]:
    """Helper: register and login, returning (user_id, email, token)."""
    email = f"{name}_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": name},
    )
    user_id = reg.json()["id"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token = login.json()["access_token"]
    return user_id, email, token


@pytest.mark.asyncio
async def test_audit_log_access_and_event_recording(async_client: httpx.AsyncClient) -> None:
    """Verify admin-only audit log access and audit record creation on lifecycle operations."""
    # 1. Setup Org with Owner (User A), Member (User B), and another Member (User C)
    user_a_id, _, user_a_token = await register_user(async_client, "audit_owner")
    user_b_id, user_b_email, user_b_token = await register_user(async_client, "audit_member")
    user_c_id, user_c_email, _ = await register_user(async_client, "audit_target")

    org_res = await async_client.post(
        "/api/v1/orgs",
        json={"name": "Audit Org", "slug": f"audit-org-{uuid.uuid4().hex[:8]}"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    org_id = org_res.json()["id"]

    # Add User B as MEMBER
    await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": user_b_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    # Add User C as MEMBER
    await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": user_c_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )

    # 2. Member (User B) attempts to read audit logs -> 403 Forbidden
    forbidden_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/audit-logs",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert forbidden_res.status_code == 403

    # 3. Perform auditable operations by Owner:
    # 3a. Update User C role to ADMIN
    role_res = await async_client.patch(
        f"/api/v1/orgs/{org_id}/members/{user_c_id}",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert role_res.status_code == 200

    # 3b. Create and delete project
    proj_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"name": "Audit Project"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    proj_id = proj_res.json()["id"]

    del_proj = await async_client.delete(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert del_proj.status_code == 204

    # 4. Owner reads audit logs -> 200 OK
    audit_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/audit-logs",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert audit_res.status_code == 200
    data = audit_res.json()
    assert "items" in data
    assert "pagination" in data
    items = data["items"]
    assert len(items) >= 2

    # Check member added event
    member_add_audit = next((item for item in items if item["action"] == "org.member_added"), None)
    assert member_add_audit is not None
    assert member_add_audit["actor_id"] == user_a_id
    assert member_add_audit["organization_id"] == org_id

    # Check role update event
    role_audit = next((item for item in items if item["action"] == "org.role_updated"), None)
    assert role_audit is not None
    assert role_audit["actor_id"] == user_a_id
    assert role_audit["organization_id"] == org_id
    assert f"user:{user_c_id}" in role_audit["target_resource"]

    # Check project deletion event
    proj_audit = next((item for item in items if item["action"] == "project.deleted"), None)
    assert proj_audit is not None
    assert proj_audit["actor_id"] == user_a_id
    assert proj_audit["organization_id"] == org_id
    assert f"project:{proj_id}" in proj_audit["target_resource"]

    # 5. Filter audit log by action
    filtered_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/audit-logs?action=project.deleted",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert filtered_res.status_code == 200
    filtered_items = filtered_res.json()["items"]
    assert all(item["action"] == "project.deleted" for item in filtered_items)
