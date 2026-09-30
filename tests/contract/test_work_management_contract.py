"""Contract tests verifying /projects and /tasks endpoints against OpenAPI 3.1 specifications."""

import uuid

import httpx
import pytest

from src.core.rate_limit import auth_endpoint_limiter


@pytest.fixture(autouse=True)
def reset_auth_limiter() -> None:
    """Reset the sliding window rate limiter before each contract test."""
    auth_endpoint_limiter.reset()


async def create_user_and_org(client: httpx.AsyncClient, name: str) -> tuple[str, str, str, str]:
    """Helper: register, login, create org, returning (user_id, email, token, org_id)."""
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

    org_res = await client.post(
        "/api/v1/orgs",
        json={"name": f"{name} Org", "slug": f"org-{uuid.uuid4().hex[:8]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = org_res.json()["id"]
    return user_id, email, token, org_id


@pytest.mark.asyncio
async def test_contract_project_lifecycle(async_client: httpx.AsyncClient) -> None:
    """POST /projects -> GET /projects -> GET /projects/{id} -> PATCH -> DELETE."""
    _, _, token, org_id = await create_user_and_org(async_client, "proj_owner")

    # 1. Create project
    create_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"name": "Alpha Project", "description": "Initial description"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_res.status_code == 201
    proj_data = create_res.json()
    assert "id" in proj_data
    assert uuid.UUID(proj_data["id"])
    assert proj_data["name"] == "Alpha Project"
    assert proj_data["description"] == "Initial description"
    assert proj_data["status"] == "ACTIVE"
    assert proj_data["organization_id"] == org_id
    proj_id = proj_data["id"]

    # 2. List projects
    list_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects?page=1&per_page=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert "items" in list_data
    assert "pagination" in list_data
    assert any(p["id"] == proj_id for p in list_data["items"])

    # 3. Get project details
    get_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == proj_id

    # 4. Update project
    patch_res = await async_client.patch(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}",
        json={"name": "Updated Alpha", "status": "COMPLETED"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["name"] == "Updated Alpha"
    assert patch_res.json()["status"] == "COMPLETED"

    # 5. Delete project (soft delete)
    del_res = await async_client.delete(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 204

    # 6. Subsequent GET returns 404
    after_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert after_res.status_code == 404


@pytest.mark.asyncio
async def test_contract_task_lifecycle(async_client: httpx.AsyncClient) -> None:
    """POST /tasks -> GET /tasks -> GET /tasks/{id} -> PATCH -> DELETE."""
    user_id, _, token, org_id = await create_user_and_org(async_client, "task_owner")

    # Create project
    proj_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"name": "Task Container Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    proj_id = proj_res.json()["id"]

    # 1. Create task
    task_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        json={
            "title": "Build initial API",
            "description": "Implement task CRUD endpoints",
            "priority": "HIGH",
            "assignee_id": user_id,
        },
        headers={"Authorization": f"Bearer {token}"},
    )
    assert task_res.status_code == 201
    task_data = task_res.json()
    assert "id" in task_data
    assert task_data["title"] == "Build initial API"
    assert task_data["status"] == "TODO"
    assert task_data["priority"] == "HIGH"
    assert task_data["assignee_id"] == user_id
    assert task_data["project_id"] == proj_id
    task_id = task_data["id"]

    # 2. List tasks
    list_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks?status=TODO&priority=HIGH",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert "items" in list_data
    assert "pagination" in list_data
    assert len(list_data["items"]) == 1
    assert list_data["items"][0]["id"] == task_id

    # 3. Get task details
    get_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 200
    assert get_res.json()["id"] == task_id

    # 4. Update task status and priority
    patch_res = await async_client.patch(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}",
        json={"status": "IN_PROGRESS", "priority": "URGENT"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["status"] == "IN_PROGRESS"
    assert patch_res.json()["priority"] == "URGENT"

    # 5. Delete task
    del_res = await async_client.delete(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 204

    # 6. Subsequent GET returns 404
    after_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert after_res.status_code == 404
