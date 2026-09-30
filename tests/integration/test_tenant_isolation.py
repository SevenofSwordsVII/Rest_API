"""Integration tests for multi-tenant isolation, 4-tier RBAC, and Owner invariants."""

import uuid

import httpx
import pytest

from src.core.rate_limit import auth_endpoint_limiter


@pytest.fixture(autouse=True)
def reset_auth_limiter() -> None:
    """Reset the sliding window rate limiter before each test."""
    auth_endpoint_limiter.reset()


async def register_and_login(client: httpx.AsyncClient, name: str) -> tuple[str, str, str]:
    """Helper: register user and login, returning (user_id, email, token)."""
    email = f"{name}_{uuid.uuid4().hex[:8]}@example.com"
    password = "SecurePassword123!"
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


async def create_org(client: httpx.AsyncClient, token: str, name: str = "Test Org") -> str:
    """Helper: create org and return org_id."""
    slug = f"org-{uuid.uuid4().hex[:8]}"
    res = await client.post(
        "/api/v1/orgs",
        json={"name": name, "slug": slug},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    return str(res.json()["id"])


@pytest.mark.asyncio
async def test_tenant_isolation_cross_organization_forbidden(
    async_client: httpx.AsyncClient,
) -> None:
    """User in Org A cannot read or mutate resources in Org B (403 Forbidden)."""
    _, _, token_a = await register_and_login(async_client, "user_a")
    _, _, token_b = await register_and_login(async_client, "user_b")

    org_a_id = await create_org(async_client, token_a, "Org A")
    _ = await create_org(async_client, token_b, "Org B")

    # User B attempts to read Org A
    res_get = await async_client.get(
        f"/api/v1/orgs/{org_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_get.status_code == 403

    # User B attempts to list members of Org A
    res_members = await async_client.get(
        f"/api/v1/orgs/{org_a_id}/members",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_members.status_code == 403

    # User B attempts to update Org A
    res_patch = await async_client.patch(
        f"/api/v1/orgs/{org_a_id}",
        json={"name": "Hacked Name"},
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_patch.status_code == 403

    # User B attempts to delete Org A
    res_del = await async_client.delete(
        f"/api/v1/orgs/{org_a_id}",
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert res_del.status_code == 403


@pytest.mark.asyncio
async def test_all_four_roles_permissions(async_client: httpx.AsyncClient) -> None:
    """Verify distinct permission boundaries for OWNER, ADMIN, MEMBER, VIEWER."""
    _, _, owner_token = await register_and_login(async_client, "owner")
    admin_id, admin_email, admin_token = await register_and_login(async_client, "admin")
    member_id, member_email, member_token = await register_and_login(async_client, "member")
    viewer_id, viewer_email, viewer_token = await register_and_login(async_client, "viewer")

    org_id = await create_org(async_client, owner_token, "RBAC Org")

    # Add Admin, Member, Viewer
    for email, role in [
        (admin_email, "ADMIN"),
        (member_email, "MEMBER"),
        (viewer_email, "VIEWER"),
    ]:
        res = await async_client.post(
            f"/api/v1/orgs/{org_id}/members",
            json={"email": email, "role": role},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert res.status_code == 201

    # 1. VIEWER tests: can read org, can read members, CANNOT update org, CANNOT add members
    v_get = await async_client.get(
        f"/api/v1/orgs/{org_id}",
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert v_get.status_code == 200

    v_patch = await async_client.patch(
        f"/api/v1/orgs/{org_id}",
        json={"name": "Viewer Rename"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert v_patch.status_code == 403

    extra_id, extra_email, _ = await register_and_login(async_client, "extra")
    v_add = await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": extra_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {viewer_token}"},
    )
    assert v_add.status_code == 403

    # 2. MEMBER tests: can read org, can read members, CANNOT update org, CANNOT add members
    m_get = await async_client.get(
        f"/api/v1/orgs/{org_id}",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_get.status_code == 200

    m_patch = await async_client.patch(
        f"/api/v1/orgs/{org_id}",
        json={"name": "Member Rename"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_patch.status_code == 403

    m_add = await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": extra_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert m_add.status_code == 403

    # 3. ADMIN tests: CAN update org, CAN add member, CANNOT delete org
    a_patch = await async_client.patch(
        f"/api/v1/orgs/{org_id}",
        json={"name": "Admin Rename"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert a_patch.status_code == 200
    assert a_patch.json()["name"] == "Admin Rename"

    a_add = await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": extra_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert a_add.status_code == 201

    a_del_org = await async_client.delete(
        f"/api/v1/orgs/{org_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert a_del_org.status_code == 403

    # 4. OWNER tests: CAN delete org
    o_del_org = await async_client.delete(
        f"/api/v1/orgs/{org_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert o_del_org.status_code == 204


@pytest.mark.asyncio
async def test_last_active_owner_protection(async_client: httpx.AsyncClient) -> None:
    """Sole Owner cannot be removed or demoted."""
    owner_id, _, owner_token = await register_and_login(async_client, "owner")
    org_id = await create_org(async_client, owner_token, "Owner Protection Org")

    # Attempt to demote sole Owner to ADMIN
    demote_res = await async_client.patch(
        f"/api/v1/orgs/{org_id}/members/{owner_id}",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert demote_res.status_code in (400, 403)

    # Attempt to remove sole Owner
    remove_res = await async_client.delete(
        f"/api/v1/orgs/{org_id}/members/{owner_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert remove_res.status_code in (400, 403)


@pytest.mark.asyncio
async def test_owner_transfer_preserves_single_owner_invariant(
    async_client: httpx.AsyncClient,
) -> None:
    """Owner transfers ownership to another member; original owner becomes ADMIN."""
    owner_id, _, owner_token = await register_and_login(async_client, "original_owner")
    member_id, member_email, member_token = await register_and_login(async_client, "new_owner")
    org_id = await create_org(async_client, owner_token, "Transfer Org")

    # Add new member
    await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": member_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    # Transfer ownership by updating member to OWNER
    transfer_res = await async_client.patch(
        f"/api/v1/orgs/{org_id}/members/{member_id}",
        json={"role": "OWNER"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert transfer_res.status_code == 200
    assert transfer_res.json()["role"] == "OWNER"

    # Check members roster: exactly one OWNER, previous owner is now ADMIN
    roster_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/members",
        headers={"Authorization": f"Bearer {member_token}"},
    )
    assert roster_res.status_code == 200
    items = roster_res.json()["items"]
    owners = [m for m in items if m["role"] == "OWNER"]
    admins = [m for m in items if m["role"] == "ADMIN"]
    assert len(owners) == 1
    assert owners[0]["user_id"] == member_id
    assert len(admins) == 1
    assert admins[0]["user_id"] == owner_id


@pytest.mark.asyncio
async def test_member_lifecycle_add_update_remove(
    async_client: httpx.AsyncClient,
) -> None:
    """Direct member addition -> immediate access -> role changes -> removal -> 403."""
    _, _, owner_token = await register_and_login(async_client, "owner")
    user_id, user_email, user_token = await register_and_login(async_client, "target_user")
    org_id = await create_org(async_client, owner_token, "Lifecycle Org")

    # 1. Before addition: target user gets 403
    before_res = await async_client.get(
        f"/api/v1/orgs/{org_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert before_res.status_code == 403

    # 2. Add member as VIEWER
    add_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": user_email, "role": "VIEWER"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert add_res.status_code == 201

    # 3. Immediately active: can access org
    after_res = await async_client.get(
        f"/api/v1/orgs/{org_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert after_res.status_code == 200

    # 4. Change role to MEMBER then ADMIN
    for new_role in ["MEMBER", "ADMIN"]:
        patch_res = await async_client.patch(
            f"/api/v1/orgs/{org_id}/members/{user_id}",
            json={"role": new_role},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        assert patch_res.status_code == 200
        assert patch_res.json()["role"] == new_role

    # 5. Remove member
    del_res = await async_client.delete(
        f"/api/v1/orgs/{org_id}/members/{user_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert del_res.status_code == 204

    # 6. User loses access -> 403
    removed_res = await async_client.get(
        f"/api/v1/orgs/{org_id}",
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert removed_res.status_code == 403
