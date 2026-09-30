"""Integration tests for project & task lifecycle and cross-tenant invariants."""

import uuid

import httpx
import pytest

from src.core.rate_limit import auth_endpoint_limiter


@pytest.fixture(autouse=True)
def reset_auth_limiter() -> None:
    """Reset the sliding window rate limiter before each test."""
    auth_endpoint_limiter.reset()


async def register_user(client: httpx.AsyncClient, prefix: str) -> tuple[str, str, str]:
    """Register and login user, returning (user_id, email, token)."""
    email = f"{prefix}_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": prefix},
    )
    user_id = reg.json()["id"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token = login.json()["access_token"]
    return user_id, email, token


async def create_org(client: httpx.AsyncClient, token: str, name: str) -> str:
    """Create an organization and return its id."""
    res = await client.post(
        "/api/v1/orgs",
        json={"name": name, "slug": f"slug-{uuid.uuid4().hex[:8]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    return str(res.json()["id"])


@pytest.mark.asyncio
async def test_assignee_must_be_org_member(async_client: httpx.AsyncClient) -> None:
    """Task assignment to a non-member of the project's organization must be rejected (400)."""
    # Org A with Owner A and Member A
    _, _, token_a = await register_user(async_client, "owner_a")
    member_a_id, member_a_email, _ = await register_user(async_client, "member_a")
    org_a_id = await create_org(async_client, token_a, "Org A")

    await async_client.post(
        f"/api/v1/orgs/{org_a_id}/members",
        json={"email": member_a_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # Org B with User B (not in Org A)
    user_b_id, _, _ = await register_user(async_client, "user_b")

    # Create project in Org A
    proj_res = await async_client.post(
        f"/api/v1/orgs/{org_a_id}/projects",
        json={"name": "Project In Org A"},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    proj_id = proj_res.json()["id"]

    # 1. Attempt assigning task to User B (from Org B) -> 400 Validation Error
    fail_res = await async_client.post(
        f"/api/v1/orgs/{org_a_id}/projects/{proj_id}/tasks",
        json={
            "title": "Cross tenant task",
            "assignee_id": user_b_id,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert fail_res.status_code == 400

    # 2. Assigning task to Member A (in Org A) -> 201 Success
    success_res = await async_client.post(
        f"/api/v1/orgs/{org_a_id}/projects/{proj_id}/tasks",
        json={
            "title": "Valid task",
            "assignee_id": member_a_id,
        },
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert success_res.status_code == 201
    assert success_res.json()["assignee_id"] == member_a_id


@pytest.mark.asyncio
async def test_archived_project_task_modification_freeze(
    async_client: httpx.AsyncClient,
) -> None:
    """Archived projects freeze tasks: cannot create new tasks or update existing tasks."""
    _, _, token = await register_user(async_client, "archiver")
    org_id = await create_org(async_client, token, "Archive Org")

    # 1. Create project and task while ACTIVE
    proj_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"name": "Active Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    proj_id = proj_res.json()["id"]

    task_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        json={"title": "Original Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    task_id = task_res.json()["id"]

    # 2. Archive project
    archive_res = await async_client.patch(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}",
        json={"status": "ARCHIVED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert archive_res.status_code == 200
    assert archive_res.json()["status"] == "ARCHIVED"

    # 3. Attempt creating task in archived project -> rejected (400 or 409)
    create_fail = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        json={"title": "Frozen Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_fail.status_code in (400, 409)

    # 4. Attempt updating task in archived project -> rejected (400 or 409)
    update_fail = await async_client.patch(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}",
        json={"status": "DONE"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_fail.status_code in (400, 409)


@pytest.mark.asyncio
async def test_rbac_project_and_task_permissions(
    async_client: httpx.AsyncClient,
) -> None:
    """Verify Viewer and Member RBAC rules on Projects and Tasks."""
    _, _, owner_token = await register_user(async_client, "owner")
    _, member_email, member_token = await register_user(async_client, "member")
    _, viewer_email, viewer_token = await register_user(async_client, "viewer")

    org_id = await create_org(async_client, owner_token, "RBAC Work Org")

    # Add member and viewer
    await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": member_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": viewer_email, "role": "VIEWER"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    # 1. Viewer CANNOT create project (403)
    v_proj_fail = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"name": "Viewer Project"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert v_proj_fail.status_code == 403

    # 2. Member CAN create project (201)
    m_proj = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"name": "Member Project"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_proj.status_code == 201
    proj_id = m_proj.json()["id"]

    # 3. Viewer CANNOT create task (403)
    v_task_fail = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        json={"title": "Viewer Task"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert v_task_fail.status_code == 403

    # 4. Member CAN create task (201)
    m_task = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        json={"title": "Member Task"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_task.status_code == 201
    task_id = m_task.json()["id"]

    # 5. Viewer CANNOT update task (403)
    v_task_patch = await async_client.patch(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}",
        json={"status": "IN_PROGRESS"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert v_task_patch.status_code == 403

    # 6. Member CANNOT delete project (403 - Admin or Owner only)
    m_proj_del = await async_client.delete(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_proj_del.status_code == 403

    # 7. Owner CAN delete project (204)
    o_proj_del = await async_client.delete(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert o_proj_del.status_code == 204


@pytest.mark.asyncio
async def test_soft_deleted_project_cascade_hiding(async_client: httpx.AsyncClient) -> None:
    """Soft-deleted projects and their tasks are inaccessible via standard API endpoints."""
    _, _, token = await register_user(async_client, "softdel")
    org_id = await create_org(async_client, token, "Soft Delete Org")

    # 1. Create project & task
    proj_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"name": "Project To Delete"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert proj_res.status_code == 201
    proj_id = proj_res.json()["id"]

    task_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        json={"title": "Task in Deleted Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert task_res.status_code == 201
    task_id = task_res.json()["id"]

    # 2. Soft-delete project
    del_res = await async_client.delete(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 204

    # 3. GET project returns 404
    get_proj = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_proj.status_code == 404

    # 4. GET project list does not include soft-deleted project
    list_projs = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_projs.status_code == 200
    assert not any(p["id"] == proj_id for p in list_projs.json()["items"])

    # 5. Accessing tasks under deleted project returns 404
    get_tasks = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_tasks.status_code == 404

    create_task = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        json={"title": "Cannot add to deleted project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_task.status_code == 404

    get_task = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_task.status_code == 404
