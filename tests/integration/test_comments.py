"""Integration tests for comment ownership, editing permissions, and moderation."""

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
async def test_comment_permissions_and_moderation(async_client: httpx.AsyncClient) -> None:
    """Verify author-only edit, author/admin delete, and member view permissions."""
    # 1. Setup Org with Owner, Member A, Member B
    _, _, owner_token = await register_user(async_client, "owner")
    user_a_id, user_a_email, user_a_token = await register_user(async_client, "user_a")
    user_b_id, user_b_email, user_b_token = await register_user(async_client, "user_b")

    org_res = await async_client.post(
        "/api/v1/orgs",
        json={"name": "Comment Org", "slug": f"org-{uuid.uuid4().hex[:8]}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    org_id = org_res.json()["id"]

    for email in [user_a_email, user_b_email]:
        await async_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": email, "role": "MEMBER"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )

    # 2. Setup project and task
    proj_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"name": "Project 1"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    proj_id = proj_res.json()["id"]

    task_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        json={"title": "Task 1"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    task_id = task_res.json()["id"]

    comments_url = f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}/comments"

    # 3. User A posts comment
    post_res = await async_client.post(
        comments_url,
        json={"content": "Comment by User A"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert post_res.status_code == 201
    comment_id = post_res.json()["id"]
    comment_url = f"{comments_url}/{comment_id}"

    # 4. User B can view comment
    get_res = await async_client.get(
        comments_url,
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert get_res.status_code == 200
    assert any(c["id"] == comment_id for c in get_res.json()["items"])

    # 5. User B CANNOT edit User A's comment (403 Forbidden)
    patch_fail = await async_client.patch(
        comment_url,
        json={"content": "Tampered comment"},
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert patch_fail.status_code == 403

    # 6. User B CANNOT delete User A's comment (403 Forbidden)
    del_fail = await async_client.delete(
        comment_url,
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert del_fail.status_code == 403

    # 7. User A CAN update their own comment (200 OK)
    patch_ok = await async_client.patch(
        comment_url,
        json={"content": "Author updated content"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert patch_ok.status_code == 200
    assert patch_ok.json()["content"] == "Author updated content"

    # 8. Org Owner/Admin CAN moderate (delete) User A's comment (204 No Content)
    del_ok = await async_client.delete(
        comment_url,
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert del_ok.status_code == 204
