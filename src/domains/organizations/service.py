"""Domain service implementing organization business logic, RBAC, and tenant invariants."""

import math
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import utc_now
from src.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from src.core.pagination import PaginationMeta, PaginationParams
from src.domains.audit.service import AuditService
from src.domains.auth.models import User
from src.domains.organizations.models import Organization, OrganizationMembership, RoleEnum
from src.domains.organizations.schemas import (
    AddMemberRequest,
    OrganizationCreateRequest,
    OrganizationMemberResponse,
    OrganizationUpdateRequest,
    UpdateRoleRequest,
)


class OrganizationService:
    """Encapsulates multi-tenant organization boundaries and member RBAC administration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.audit_service = AuditService(session)

    async def create_organization(
        self, creator: User, payload: OrganizationCreateRequest
    ) -> Organization:
        """Create a new organization and assign creator as its sole OWNER."""
        # 1. Verify slug uniqueness
        existing_stmt = select(Organization).where(Organization.slug == payload.slug)
        existing = (await self.session.execute(existing_stmt)).scalar_one_or_none()
        if existing:
            raise ConflictError(f"Organization slug '{payload.slug}' is already taken.")

        # 2. Create organization entity
        org = Organization(name=payload.name, slug=payload.slug)
        self.session.add(org)
        await self.session.flush()

        # 3. Associate creator as sole Owner
        membership = OrganizationMembership(
            organization_id=org.id,
            user_id=creator.id,
            role=RoleEnum.OWNER,
        )
        self.session.add(membership)
        await self.session.commit()
        await self.session.refresh(org)
        return org

    async def get_organization(self, org_id: uuid.UUID) -> Organization:
        """Retrieve active organization by ID, raising NotFoundError if soft-deleted or missing."""
        stmt = select(Organization).where(
            Organization.id == org_id,
            Organization.deleted_at.is_(None),
        )
        org = (await self.session.execute(stmt)).scalar_one_or_none()
        if not org:
            raise NotFoundError("Organization not found.")
        return org

    async def list_user_organizations(
        self, user_id: uuid.UUID, params: PaginationParams
    ) -> tuple[list[Organization], PaginationMeta]:
        """List active organizations of which the user is an active member."""
        base_query = (
            select(Organization)
            .join(
                OrganizationMembership,
                Organization.id == OrganizationMembership.organization_id,
            )
            .where(
                OrganizationMembership.user_id == user_id,
                Organization.deleted_at.is_(None),
            )
            .order_by(Organization.created_at.desc())
        )

        count_stmt = select(func.count()).select_from(base_query.order_by(None).subquery())
        total_items = (await self.session.execute(count_stmt)).scalar_one_or_none() or 0
        total_pages = math.ceil(total_items / params.per_page) if total_items > 0 else 0

        paged_stmt = base_query.offset(params.offset).limit(params.per_page)
        items = list((await self.session.execute(paged_stmt)).scalars().all())

        meta = PaginationMeta(
            page=params.page,
            per_page=params.per_page,
            total_items=total_items,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
        )
        return items, meta

    async def update_organization(
        self, org: Organization, payload: OrganizationUpdateRequest
    ) -> Organization:
        """Update organization metadata."""
        if payload.name is not None:
            org.name = payload.name
        org.updated_at = utc_now()
        await self.session.commit()
        await self.session.refresh(org)
        return org

    async def soft_delete_organization(
        self, org: Organization, actor_id: uuid.UUID | None = None
    ) -> None:
        """Soft-delete an organization by setting deleted_at timestamp."""
        org.deleted_at = utc_now()
        org.updated_at = utc_now()
        await self.session.commit()
        await self.audit_service.record_audit(
            action="org.deleted",
            target_resource=f"organization:{org.id}",
            organization_id=org.id,
            actor_id=actor_id,
        )

    async def list_members(
        self, org_id: uuid.UUID, params: PaginationParams
    ) -> tuple[list[OrganizationMemberResponse], PaginationMeta]:
        """List member roster with joined user details."""
        base_query = (
            select(OrganizationMembership, User.email)
            .join(User, OrganizationMembership.user_id == User.id)
            .where(OrganizationMembership.organization_id == org_id)
            .order_by(OrganizationMembership.created_at.asc())
        )

        count_stmt = select(func.count()).select_from(base_query.order_by(None).subquery())
        total_items = (await self.session.execute(count_stmt)).scalar_one_or_none() or 0
        total_pages = math.ceil(total_items / params.per_page) if total_items > 0 else 0

        paged_stmt = base_query.offset(params.offset).limit(params.per_page)
        rows: list[Any] = list((await self.session.execute(paged_stmt)).all())

        items = [
            OrganizationMemberResponse(
                id=membership.id,
                user_id=membership.user_id,
                organization_id=membership.organization_id,
                role=membership.role,
                user_email=email,
                created_at=membership.created_at,
            )
            for membership, email in rows
        ]

        meta = PaginationMeta(
            page=params.page,
            per_page=params.per_page,
            total_items=total_items,
            total_pages=total_pages,
            has_next=params.page < total_pages,
            has_prev=params.page > 1,
        )
        return items, meta

    async def add_member(
        self,
        org_id: uuid.UUID,
        payload: AddMemberRequest,
        actor_id: uuid.UUID | None = None,
    ) -> OrganizationMemberResponse:
        """Add registered user directly to organization."""
        # 1. Find user by email
        user_stmt = select(User).where(func.lower(User.email) == payload.email.lower())
        target_user = (await self.session.execute(user_stmt)).scalar_one_or_none()
        if not target_user:
            raise NotFoundError(f"User with email '{payload.email}' not found.")

        # 2. Check for duplicate membership
        mem_stmt = select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == target_user.id,
        )
        existing_mem = (await self.session.execute(mem_stmt)).scalar_one_or_none()
        if existing_mem:
            raise ConflictError("User is already a member of this organization.")

        # 3. Single-Owner invariant: cannot add directly as OWNER
        if payload.role == RoleEnum.OWNER:
            raise ValidationError(
                "Organizations can have only one Owner. Transfer ownership instead."
            )

        membership = OrganizationMembership(
            organization_id=org_id,
            user_id=target_user.id,
            role=payload.role,
        )
        self.session.add(membership)
        await self.session.commit()
        await self.session.refresh(membership)

        if actor_id:
            await self.audit_service.record_audit(
                action="org.member_added",
                target_resource=f"user:{target_user.id}",
                organization_id=org_id,
                actor_id=actor_id,
                metadata={"role": payload.role.value, "email": target_user.email},
            )

        return OrganizationMemberResponse(
            id=membership.id,
            user_id=membership.user_id,
            organization_id=membership.organization_id,
            role=membership.role,
            user_email=target_user.email,
            created_at=membership.created_at,
        )

    async def update_member_role(
        self,
        org_id: uuid.UUID,
        target_user_id: uuid.UUID,
        payload: UpdateRoleRequest,
        actor: User,
        actor_role: RoleEnum,
    ) -> OrganizationMemberResponse:
        """Update role of an existing member, enforcing sole-Owner invariants and transfer."""
        mem_stmt = (
            select(OrganizationMembership, User.email)
            .join(User, OrganizationMembership.user_id == User.id)
            .where(
                OrganizationMembership.organization_id == org_id,
                OrganizationMembership.user_id == target_user_id,
            )
        )
        row = (await self.session.execute(mem_stmt)).first()
        if not row:
            raise NotFoundError("Member not found in organization.")

        target_membership: OrganizationMembership = row[0]
        user_email: str = row[1]

        # Invariant 1: Last active Owner cannot be demoted
        if target_membership.role == RoleEnum.OWNER and payload.role != RoleEnum.OWNER:
            raise ForbiddenError(
                "Cannot demote the last active owner of an organization. Transfer ownership first."
            )

        # Invariant 2: Transferring ownership to another member
        if payload.role == RoleEnum.OWNER:
            if actor_role != RoleEnum.OWNER:
                raise ForbiddenError("Only the current Owner can transfer ownership.")

            if target_user_id != actor.id:
                # Demote actor to ADMIN, promote target to OWNER
                actor_mem_stmt = select(OrganizationMembership).where(
                    OrganizationMembership.organization_id == org_id,
                    OrganizationMembership.user_id == actor.id,
                )
                actor_membership = (await self.session.execute(actor_mem_stmt)).scalar_one()
                actor_membership.role = RoleEnum.ADMIN
                actor_membership.updated_at = utc_now()

                target_membership.role = RoleEnum.OWNER
                target_membership.updated_at = utc_now()
                await self.session.commit()

                await self.audit_service.record_audit(
                    action="org.role_updated",
                    target_resource=f"user:{target_user_id}",
                    organization_id=org_id,
                    actor_id=actor.id,
                    metadata={"new_role": RoleEnum.OWNER},
                )

                return OrganizationMemberResponse(
                    id=target_membership.id,
                    user_id=target_membership.user_id,
                    organization_id=target_membership.organization_id,
                    role=target_membership.role,
                    user_email=user_email,
                    created_at=target_membership.created_at,
                )

        # Invariant 3: Admin cannot modify an Owner's role
        if actor_role != RoleEnum.OWNER and target_membership.role == RoleEnum.OWNER:
            raise ForbiddenError("Admins cannot modify the Owner's role.")

        target_membership.role = payload.role
        target_membership.updated_at = utc_now()
        await self.session.commit()

        await self.audit_service.record_audit(
            action="org.role_updated",
            target_resource=f"user:{target_user_id}",
            organization_id=org_id,
            actor_id=actor.id,
            metadata={"new_role": payload.role},
        )

        return OrganizationMemberResponse(
            id=target_membership.id,
            user_id=target_membership.user_id,
            organization_id=target_membership.organization_id,
            role=target_membership.role,
            user_email=user_email,
            created_at=target_membership.created_at,
        )

    async def remove_member(
        self,
        org_id: uuid.UUID,
        target_user_id: uuid.UUID,
        actor: User,
        actor_role: RoleEnum,
    ) -> None:
        """Remove member from organization, ensuring sole-Owner cannot be removed."""
        mem_stmt = select(OrganizationMembership).where(
            OrganizationMembership.organization_id == org_id,
            OrganizationMembership.user_id == target_user_id,
        )
        target_membership = (await self.session.execute(mem_stmt)).scalar_one_or_none()
        if not target_membership:
            raise NotFoundError("Member not found in organization.")

        # Invariant: Last active Owner cannot be removed
        if target_membership.role == RoleEnum.OWNER:
            raise ForbiddenError("Cannot remove the last active owner of an organization.")

        # Invariant: Admin cannot remove Owner (handled by above check)
        await self.session.delete(target_membership)
        await self.session.commit()

        await self.audit_service.record_audit(
            action="org.member_removed",
            target_resource=f"user:{target_user_id}",
            organization_id=org_id,
            actor_id=actor.id,
        )
