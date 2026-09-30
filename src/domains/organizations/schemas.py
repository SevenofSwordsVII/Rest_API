"""Pydantic v2 schemas for organization management and membership administration."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from src.core.pagination import PaginationMeta
from src.domains.auth.schemas import EmailType
from src.domains.organizations.models import RoleEnum


class OrganizationCreateRequest(BaseModel):
    """Payload for creating a new organization."""

    name: str = Field(..., min_length=2, max_length=128, description="Organization display name")
    slug: str = Field(
        ...,
        min_length=2,
        max_length=64,
        pattern=r"^[a-z0-9-]+$",
        description="URL-safe unique identifier",
    )


class OrganizationUpdateRequest(BaseModel):
    """Payload for updating organization metadata."""

    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=128,
        description="New display name",
    )


class OrganizationResponse(BaseModel):
    """Public representation of an organization."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class AddMemberRequest(BaseModel):
    """Payload for directly adding a user to an organization."""

    email: EmailType = Field(..., description="Registered user's email address")
    role: RoleEnum = Field(..., description="Assigned RBAC role")


class UpdateRoleRequest(BaseModel):
    """Payload for modifying an existing member's role."""

    role: RoleEnum = Field(..., description="New RBAC role")


class OrganizationMemberResponse(BaseModel):
    """Public representation of an organization member."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: RoleEnum
    user_email: str
    created_at: datetime


class PaginatedOrganizationsResponse(BaseModel):
    """Envelope for paginated organization listing."""

    items: list[OrganizationResponse]
    pagination: PaginationMeta


class PaginatedMembersResponse(BaseModel):
    """Envelope for paginated organization members roster."""

    items: list[OrganizationMemberResponse]
    pagination: PaginationMeta
