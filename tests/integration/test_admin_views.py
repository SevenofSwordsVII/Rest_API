"""Test SQLAdmin endpoints, authentication, list views, and filters."""

import pytest
import pytest_asyncio
import httpx
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.audit.models import AuditLogEntry
from src.domains.auth.models import RefreshToken, User
from src.domains.organizations.models import Organization, OrganizationMembership, RoleEnum
from src.domains.work_management.models import Project, Task, ProjectStatus, TaskStatus, TaskPriority
from src.core.database import utc_now


@pytest_asyncio.fixture
async def admin_client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    client = httpx.AsyncClient(transport=transport, base_url="http://test")

    # Perform admin login
    login_resp = await client.post(
        "/admin/login",
        data={"username": settings.ADMIN_USERNAME, "password": settings.ADMIN_PASSWORD},
        follow_redirects=True,
    )
    assert login_resp.status_code == 200
    yield client
    await client.aclose()


@pytest.mark.asyncio
async def test_admin_list_views_and_filters(admin_client: httpx.AsyncClient, db_session: AsyncSession) -> None:
    # 1. Seed User
    user = User(
        email="admin_test@example.com",
        hashed_password="hash",
        full_name="Admin Test",
        is_active=True,
        is_superuser=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    # Test /admin/user/list and filter
    resp = await admin_client.get("/admin/user/list")
    assert resp.status_code == 200, f"User list failed: {resp.status_code} - {resp.text}"
    assert "admin_test@example.com" in resp.text

    filter_resp = await admin_client.get("/admin/user/list?is_active=true")
    assert filter_resp.status_code == 200
    assert "admin_test@example.com" in filter_resp.text

    # 2. Seed Organization & Membership
    org = Organization(name="Admin Corp", slug="admin-corp")
    db_session.add(org)
    await db_session.commit()
    await db_session.refresh(org)

    membership = OrganizationMembership(
        organization_id=org.id,
        user_id=user.id,
        role=RoleEnum.OWNER,
    )
    db_session.add(membership)
    await db_session.commit()

    resp = await admin_client.get("/admin/organization/list")
    assert resp.status_code == 200
    assert "Admin Corp" in resp.text

    resp = await admin_client.get("/admin/organization-membership/list")
    assert resp.status_code == 200
    assert "OWNER" in resp.text

    # 3. Seed Project & Task
    project = Project(
        name="Admin Operations",
        organization_id=org.id,
        created_by=user.id,
        status=ProjectStatus.ACTIVE,
    )
    db_session.add(project)
    await db_session.commit()
    await db_session.refresh(project)

    resp = await admin_client.get("/admin/project/list")
    assert resp.status_code == 200
    assert "Admin Operations" in resp.text

    filter_proj = await admin_client.get("/admin/project/list?status=ACTIVE")
    assert filter_proj.status_code == 200
    assert "Admin Operations" in filter_proj.text

    task = Task(
        title="Verify Admin Views",
        project_id=project.id,
        created_by=user.id,
        status=TaskStatus.TODO,
        priority=TaskPriority.HIGH,
    )
    db_session.add(task)
    await db_session.commit()

    resp = await admin_client.get("/admin/task/list")
    assert resp.status_code == 200
    assert "Verify Admin Views" in resp.text

    filter_task = await admin_client.get("/admin/task/list?status=TODO")
    assert filter_task.status_code == 200
    assert "Verify Admin Views" in filter_task.text

    # 4. Seed RefreshToken & AuditLogEntry
    token = RefreshToken(
        user_id=user.id,
        token_hash="dummy_hash_for_testing",
        family_id=user.id,
        is_revoked=False,
        expires_at=utc_now(),
    )
    db_session.add(token)

    audit = AuditLogEntry(
        action="USER_ADMIN_LOGIN",
        target_resource="admin_panel",
        actor_id=user.id,
        organization_id=org.id,
    )
    db_session.add(audit)
    await db_session.commit()

    resp = await admin_client.get("/admin/session-token/list")
    assert resp.status_code == 200

    resp = await admin_client.get("/admin/audit-log/list")
    assert resp.status_code == 200
    assert "USER_ADMIN_LOGIN" in resp.text

    # 5. Test Custom View
    resp = await admin_client.get("/admin/system")
    assert resp.status_code == 200
    assert "Operational Info" in resp.text
