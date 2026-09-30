"""FastAPI router for organization lifecycle and membership administration endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.core.pagination import PaginationParams
from src.domains.auth.dependencies import get_current_active_user
from src.domains.auth.models import User
from src.domains.organizations.dependencies import require_org_role
from src.domains.organizations.models import Organization, OrganizationMembership, RoleEnum
from src.domains.organizations.schemas import (
    AddMemberRequest,
    OrganizationCreateRequest,
    OrganizationMemberResponse,
    OrganizationResponse,
    OrganizationUpdateRequest,
    PaginatedMembersResponse,
    PaginatedOrganizationsResponse,
    UpdateRoleRequest,
)
from src.domains.organizations.service import OrganizationService

router = APIRouter(prefix="/orgs", tags=["Organizations"])


@router.post(
    "",
    response_model=OrganizationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new organization",
)
async def create_organization(
    payload: OrganizationCreateRequest,
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationResponse:
    """Create a new organization with the calling user as sole OWNER."""
    service = OrganizationService(session)
    org = await service.create_organization(current_user, payload)
    return OrganizationResponse.model_validate(org)


@router.get(
    "",
    response_model=PaginatedOrganizationsResponse,
    status_code=status.HTTP_200_OK,
    summary="List organizations for the authenticated user",
)
async def list_organizations(
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[PaginationParams, Depends()],
) -> PaginatedOrganizationsResponse:
    """Retrieve paginated list of active organizations of which the user is a member."""
    service = OrganizationService(session)
    items, meta = await service.list_user_organizations(current_user.id, params)
    return PaginatedOrganizationsResponse(
        items=[OrganizationResponse.model_validate(org) for org in items],
        pagination=meta,
    )


@router.get(
    "/{org_id}",
    response_model=OrganizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get organization details",
)
async def get_organization(
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.VIEWER)),
    ],
) -> OrganizationResponse:
    """Retrieve details for an active organization."""
    org, _ = context
    return OrganizationResponse.model_validate(org)


@router.patch(
    "/{org_id}",
    response_model=OrganizationResponse,
    status_code=status.HTTP_200_OK,
    summary="Update organization (Admin or Owner only)",
)
async def update_organization(
    payload: OrganizationUpdateRequest,
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.ADMIN)),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationResponse:
    """Update organization name and metadata."""
    org, _ = context
    service = OrganizationService(session)
    updated_org = await service.update_organization(org, payload)
    return OrganizationResponse.model_validate(updated_org)


@router.delete(
    "/{org_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Soft-delete organization (Owner only)",
)
async def delete_organization(
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.OWNER)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Soft-delete an organization."""
    org, _ = context
    service = OrganizationService(session)
    await service.soft_delete_organization(org, actor_id=current_user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{org_id}/members",
    response_model=PaginatedMembersResponse,
    status_code=status.HTTP_200_OK,
    summary="List members in organization",
)
async def list_organization_members(
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.VIEWER)),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
    params: Annotated[PaginationParams, Depends()],
) -> PaginatedMembersResponse:
    """Retrieve paginated roster of members in the organization."""
    org, _ = context
    service = OrganizationService(session)
    items, meta = await service.list_members(org.id, params)
    return PaginatedMembersResponse(items=items, pagination=meta)


@router.post(
    "/{org_id}/members",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add member directly by email/ID (Admin or Owner)",
)
async def add_organization_member(
    payload: AddMemberRequest,
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.ADMIN)),
    ],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationMemberResponse:
    """Directly associate an existing user as a member of this organization."""
    org, membership = context
    service = OrganizationService(session)
    return await service.add_member(org.id, payload, actor_id=membership.user_id)


@router.patch(
    "/{org_id}/members/{user_id}",
    response_model=OrganizationMemberResponse,
    status_code=status.HTTP_200_OK,
    summary="Update member role (Admin or Owner)",
)
async def update_member_role(
    user_id: uuid.UUID,
    payload: UpdateRoleRequest,
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.ADMIN)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OrganizationMemberResponse:
    """Change member's role or transfer ownership (Owner only)."""
    org, actor_membership = context
    service = OrganizationService(session)
    return await service.update_member_role(
        org_id=org.id,
        target_user_id=user_id,
        payload=payload,
        actor=current_user,
        actor_role=actor_membership.role,
    )


@router.delete(
    "/{org_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove member from organization (Admin or Owner)",
)
async def remove_member(
    user_id: uuid.UUID,
    context: Annotated[
        tuple[Organization, OrganizationMembership],
        Depends(require_org_role(RoleEnum.ADMIN)),
    ],
    current_user: Annotated[User, Depends(get_current_active_user)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Response:
    """Remove a user from the organization's membership."""
    org, actor_membership = context
    service = OrganizationService(session)
    await service.remove_member(
        org_id=org.id,
        target_user_id=user_id,
        actor=current_user,
        actor_role=actor_membership.role,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
