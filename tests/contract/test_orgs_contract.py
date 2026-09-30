"""Contract tests verifying /orgs and /orgs/{org_id}/members against OpenAPI 3.1 specifications."""

import uuid

import httpx
import pytest

from src.core.rate_limit import auth_endpoint_limiter


@pytest.fixture(autouse=True)
def reset_auth_limiter() -> None:
    """Reset the sliding window rate limiter before each contract test."""
    auth_endpoint_limiter.reset()


async def create_user_and_token(
    client: httpx.AsyncClient, email_prefix: str = "contract"
) -> tuple[str, str, str]:
    """Helper creating a user and returning (user_id, email, access_token)."""
    email = f"{email_prefix}_{uuid.uuid4().hex[:8]}@example.com"
    password = "StrongPassword123!"
    reg = await client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    user_id = reg.json()["id"]

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    token = login.json()["access_token"]
    return user_id, email, token


@pytest.mark.asyncio
async def test_contract_create_org_success(async_client: httpx.AsyncClient) -> None:
    """POST /orgs -> 201 Created conforming to OrganizationResponse schema."""
    _, _, token = await create_user_and_token(async_client, "owner")
    slug = f"acme-{uuid.uuid4().hex[:6]}"
    payload = {"name": "Acme Corp", "slug": slug}

    res = await async_client.post(
        "/api/v1/orgs",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201
    data = res.json()
    assert "id" in data
    assert uuid.UUID(data["id"])
    assert data["name"] == "Acme Corp"
    assert data["slug"] == slug
    assert "created_at" in data
    assert "updated_at" in data


@pytest.mark.asyncio
async def test_contract_create_org_validation_error(async_client: httpx.AsyncClient) -> None:
    """POST /orgs with invalid slug or name -> 400 ValidationError envelope."""
    _, _, token = await create_user_and_token(async_client, "owner")
    payload = {"name": "A", "slug": "INVALID SLUG!"}

    res = await async_client.post(
        "/api/v1/orgs",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 400
    data = res.json()
    assert data["error"]["code"] == "VALIDATION_ERROR"
    assert "request_id" in data


@pytest.mark.asyncio
async def test_contract_create_org_unauthorized(async_client: httpx.AsyncClient) -> None:
    """POST /orgs without auth -> 401 Unauthorized envelope."""
    res = await async_client.post(
        "/api/v1/orgs",
        json={"name": "No Auth Org", "slug": "no-auth"},
    )
    assert res.status_code == 401
    data = res.json()
    assert data["error"]["code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_contract_create_org_duplicate_slug_conflict(
    async_client: httpx.AsyncClient,
) -> None:
    """POST /orgs with duplicate slug -> 409 ConflictError envelope."""
    _, _, token = await create_user_and_token(async_client, "owner")
    slug = f"dup-{uuid.uuid4().hex[:6]}"
    payload = {"name": "First Org", "slug": slug}

    res1 = await async_client.post(
        "/api/v1/orgs",
        json=payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res1.status_code == 201

    res2 = await async_client.post(
        "/api/v1/orgs",
        json={"name": "Second Org", "slug": slug},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res2.status_code == 409
    data = res2.json()
    assert data["error"]["code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_contract_list_organizations(async_client: httpx.AsyncClient) -> None:
    """GET /orgs -> 200 OK conforming to PaginatedOrganizationsResponse schema."""
    _, _, token = await create_user_and_token(async_client, "owner")
    slug = f"list-org-{uuid.uuid4().hex[:6]}"
    await async_client.post(
        "/api/v1/orgs",
        json={"name": "Listable Org", "slug": slug},
        headers={"Authorization": f"Bearer {token}"},
    )

    res = await async_client.get(
        "/api/v1/orgs?page=1&per_page=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "pagination" in data
    assert data["pagination"]["page"] == 1
    assert data["pagination"]["per_page"] == 10
    assert data["pagination"]["total_items"] >= 1
    assert data["pagination"]["total_pages"] >= 1


@pytest.mark.asyncio
async def test_contract_get_org_by_id(async_client: httpx.AsyncClient) -> None:
    """GET /orgs/{org_id} -> 200 OK conforming to OrganizationResponse schema."""
    _, _, token = await create_user_and_token(async_client, "owner")
    create_res = await async_client.post(
        "/api/v1/orgs",
        json={"name": "Get Org", "slug": f"get-org-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = create_res.json()["id"]

    res = await async_client.get(
        f"/api/v1/orgs/{org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == org_id
    assert data["name"] == "Get Org"


@pytest.mark.asyncio
async def test_contract_update_org(async_client: httpx.AsyncClient) -> None:
    """PATCH /orgs/{org_id} -> 200 OK conforming to OrganizationResponse schema."""
    _, _, token = await create_user_and_token(async_client, "owner")
    create_res = await async_client.post(
        "/api/v1/orgs",
        json={"name": "Original Name", "slug": f"upd-org-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = create_res.json()["id"]

    res = await async_client.patch(
        f"/api/v1/orgs/{org_id}",
        json={"name": "Renamed Corp"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Renamed Corp"


@pytest.mark.asyncio
async def test_contract_delete_org(async_client: httpx.AsyncClient) -> None:
    """DELETE /orgs/{org_id} -> 204 No Content for Owner."""
    _, _, token = await create_user_and_token(async_client, "owner")
    create_res = await async_client.post(
        "/api/v1/orgs",
        json={"name": "Delete Org", "slug": f"del-org-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {token}"},
    )
    org_id = create_res.json()["id"]

    res = await async_client.delete(
        f"/api/v1/orgs/{org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 204

    # Subsequent GET returns 404
    get_res = await async_client.get(
        f"/api/v1/orgs/{org_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_contract_members_endpoints(async_client: httpx.AsyncClient) -> None:
    """Contract tests for member roster, addition, role update, and removal."""
    owner_id, owner_email, owner_token = await create_user_and_token(async_client, "owner")
    member_id, member_email, member_token = await create_user_and_token(async_client, "member")

    # 1. Create org
    create_res = await async_client.post(
        "/api/v1/orgs",
        json={"name": "Team Org", "slug": f"team-org-{uuid.uuid4().hex[:6]}"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    org_id = create_res.json()["id"]

    # 2. List members (owner is listed)
    list_res = await async_client.get(
        f"/api/v1/orgs/{org_id}/members",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert list_res.status_code == 200
    members_data = list_res.json()
    assert "items" in members_data
    assert "pagination" in members_data
    assert len(members_data["items"]) == 1
    assert members_data["items"][0]["role"] == "OWNER"
    assert members_data["items"][0]["user_email"] == owner_email

    # 3. Add member
    add_res = await async_client.post(
        f"/api/v1/orgs/{org_id}/members",
        json={"email": member_email, "role": "MEMBER"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert add_res.status_code == 201
    member_data = add_res.json()
    assert member_data["user_id"] == member_id
    assert member_data["role"] == "MEMBER"
    assert member_data["user_email"] == member_email

    # 4. Update role to ADMIN
    update_res = await async_client.patch(
        f"/api/v1/orgs/{org_id}/members/{member_id}",
        json={"role": "ADMIN"},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["role"] == "ADMIN"

    # 5. Remove member
    del_res = await async_client.delete(
        f"/api/v1/orgs/{org_id}/members/{member_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert del_res.status_code == 204
