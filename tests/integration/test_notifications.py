"""Integration tests for asynchronous work event notifications and read/unread lifecycle."""

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
async def test_notifications_dispatch_and_lifecycle(async_client: httpx.AsyncClient) -> None:
    """Verify task assignment, status change, and comment trigger notifications, and read state."""
    # 1. Setup Org with Owner (User A) and Member (User B)
    user_a_id, _, user_a_token = await register_user(async_client, "alice")
    user_b_id, user_b_email, user_b_token = await register_user(async_client, "bob")

    org_res = await async_client.post(
        "/api/v1/orgs",
        json={"name": "Notif Org", "slug": f"notif-org-{uuid.uuid4().hex[:8]}"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    org_id = org_res.json()["id"]

    await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": user_b_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )

    # 2. Create Project
    proj_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects",
        json={"name": "Notification Project"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    proj_id = proj_res.json()["id"]

    # 3. Create task assigned to User B -> should trigger task.assigned notification to User B
    task_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks",
        json={"title": "Implement Feature X", "assignee_id": user_b_id},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert task_res.status_code == 201
    task_id = task_res.json()["id"]

    # 4. Check User B notifications -> should have task.assigned
    notifs_b = await async_client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert notifs_b.status_code == 200
    items = notifs_b.json()["items"]
    assert len(items) >= 1
    assigned_notif = next((n for n in items if n["event_type"] == "task.assigned"), None)
    assert assigned_notif is not None
    assert assigned_notif["is_read"] is False
    assert assigned_notif["payload"]["task_id"] == task_id
    notif_id = assigned_notif["id"]

    # 5. User A updates task status -> should trigger task.status_changed notification to User B
    status_res = await async_client.patch(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}",
        json={"status": "IN_PROGRESS"},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert status_res.status_code == 200

    notifs_b_after_status = await async_client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    items_status = notifs_b_after_status.json()["items"]
    status_notif = next((n for n in items_status if n["event_type"] == "task.status_changed"), None)
    assert status_notif is not None
    assert status_notif["payload"]["task_id"] == task_id

    # 6. User A posts comment on the task -> should trigger comment.created notification to User B
    comment_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/projects/{proj_id}/tasks/{task_id}/comments",
        json={"content": "Please review this feature specification."},
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert comment_res.status_code == 201

    notifs_b_after_comment = await async_client.get(
        "/api/v1/notifications",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    items_comment = notifs_b_after_comment.json()["items"]
    comment_notif = next((n for n in items_comment if n["event_type"] == "comment.created"), None)
    assert comment_notif is not None

    # 7. User B marks assigned_notif as read
    read_res = await async_client.post(
        f"/api/v1/notifications/{notif_id}/read",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert read_res.status_code == 200
    assert read_res.json()["is_read"] is True

    # 8. User B queries with is_read=false -> assigned_notif should NOT appear
    unread_res = await async_client.get(
        "/api/v1/notifications?is_read=false",
        headers={"Authorization": f"Bearer {user_b_token}"},
    )
    assert unread_res.status_code == 200
    unread_items = unread_res.json()["items"]
    assert not any(n["id"] == notif_id for n in unread_items)

    # 9. Isolation: User A cannot read User B's notification
    cross_read = await async_client.post(
        f"/api/v1/notifications/{notif_id}/read",
        headers={"Authorization": f"Bearer {user_a_token}"},
    )
    assert cross_read.status_code == 404
