"""FastAPI route dependencies for tenant context resolution and RBAC validation."""

import uuid
from collections.abc import Callable, Coroutine
from typing import Annotated, Any

from fastapi import Depends, Path
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.exceptions import ForbiddenError, NotFoundError
from src.domains.auth.dependencies import get_current_active_user
from src.domains.auth.models import User
from src.domains.organizations.models import Organization, OrganizationMembership, RoleEnum

ROLE_LEVELS: dict[RoleEnum, int] = {
    RoleEnum.VIEWER: 1,
    RoleEnum.MEMBER: 2,
    RoleEnum.ADMIN: 3,
    RoleEnum.OWNER: 4,
}


async def resolve_org_context(
    org_id: Annotated[uuid.UUID, Path(..., description="Organization UUID identifier")],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> tuple[Organization, OrganizationMembership]:
    """Resolve target organization and active user membership, enforcing tenant boundary."""
    # 1. Resolve organization
    org_stmt = select(Organization).where(
        Organization.id == org_id,
        Organization.deleted_at.is_(None),
    )
    org = (await session.execute(org_stmt)).scalar_one_or_none()
    if not org:
        raise NotFoundError("Organization not found.")

    # 2. Resolve membership
    mem_stmt = select(OrganizationMembership).where(
        OrganizationMembership.organization_id == org_id,
        OrganizationMembership.user_id == current_user.id,
    )
    membership = (await session.execute(mem_stmt)).scalar_one_or_none()
    if not membership:
        raise ForbiddenError("You are not a member of this organization.")

    return org, membership


def require_org_role(
    min_role: RoleEnum,
) -> Callable[..., Coroutine[Any, Any, tuple[Organization, OrganizationMembership]]]:
    """Return dependency validating that user membership satisfies minimum role threshold."""

    async def _role_checker(
        context: Annotated[
            tuple[Organization, OrganizationMembership],
            Depends(resolve_org_context),
        ],
    ) -> tuple[Organization, OrganizationMembership]:
        _, membership = context
        user_level = ROLE_LEVELS.get(membership.role, 0)
        required_level = ROLE_LEVELS.get(min_role, 0)

        if user_level < required_level:
            raise ForbiddenError("Insufficient organization permissions.")

        return context

    return _role_checker
