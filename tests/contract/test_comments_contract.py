"""Contract tests verifying /comments endpoints against OpenAPI 3.1 specifications."""

import uuid

import httpx
import pytest

from src.core.rate_limit import auth_endpoint_limiter


@pytest.fixture(autouse=True)
def reset_auth_limiter() -> None:
    """Reset the sliding window rate limiter before each contract test."""
    auth_endpoint_limiter.reset()


async def setup_org_project_task(
    client: httpx.AsyncClient, prefix: str = "comm"
) -> tuple[str, str, str, str, str]:
    """Helper creating user, org, project, task -> (user_id, token, org_id, proj_id, task_id)."""
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

    org_res = await client.post(
        "/api/v1/orgs",
        json={"name": f"{prefix} Org", "slug": f"comm-org-{uuid.uuid4().hex[:8]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = org_res.json()["id"]

    proj_res = await client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"name": "Comment Project"},
        headers={"Authorization": f"Bearer {token}"},
    )
    proj_id = proj_res.json()["id"]

    task_res = await client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        json={"title": "Comment Task"},
        headers={"Authorization": f"Bearer {token}"},
    )
    task_id = task_res.json()["id"]

    return user_id, token, org_id, proj_id, task_id


@pytest.mark.asyncio
async def test_contract_comment_lifecycle(async_client: httpx.AsyncClient) -> None:
    """POST /comments -> GET /comments -> PATCH /comments/{id} -> DELETE /comments/{id}."""
    user_id, token, org_id, proj_id, task_id = await setup_org_project_task(async_client)
    base_url = f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}/comments"

    # 1. Create comment
    create_res = await async_client.post(
        base_url,
        json={"content": "Initial comment content"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert create_res.status_code == 201
    comm_data = create_res.json()
    assert "id" in comm_data
    assert uuid.UUID(comm_data["id"])
    assert comm_data["task_id"] == task_id
    assert comm_data["author_id"] == user_id
    assert comm_data["content"] == "Initial comment content"
    assert "created_at" in comm_data
    assert "updated_at" in comm_data
    comment_id = comm_data["id"]

    # 2. List comments
    list_res = await async_client.get(
        f"{base_url}?page=1&per_page=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert "items" in list_data
    assert "pagination" in list_data
    assert len(list_data["items"]) == 1
    assert list_data["items"][0]["id"] == comment_id

    # 3. Update comment
    patch_res = await async_client.patch(
        f"{base_url}/{comment_id}",
        json={"content": "Updated comment content"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["content"] == "Updated comment content"

    # 4. Delete comment
    del_res = await async_client.delete(
        f"{base_url}/{comment_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert del_res.status_code == 204
