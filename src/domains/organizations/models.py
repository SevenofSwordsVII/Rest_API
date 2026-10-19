"""SQLAlchemy 2.0 models for Organizations and Multi-Tenant Memberships."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, TimestampMixin, UUIDPrimaryKeyMixin
from src.domains.auth.models import User


class RoleEnum(StrEnum):
    """Fixed RBAC roles within an organization tenant."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"


class Organization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Top-level multi-tenant isolation boundary."""

    __tablename__ = "organization"

    name: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=True,
        default=None,
    )

    memberships: Mapped[list["OrganizationMembership"]] = relationship(
        "OrganizationMembership",
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __str__(self) -> str:
        return self.name or str(self.id)


class OrganizationMembership(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Tenant-scoped user membership with assigned RBAC role."""

    __tablename__ = "organization_membership"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "user_id",
            name="uq_organization_membership_user_org",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    role: Mapped[RoleEnum] = mapped_column(
        String(32),
        nullable=False,
        default=RoleEnum.MEMBER,
    )

    organization: Mapped["Organization"] = relationship(
        "Organization",
        back_populates="memberships",
    )
    user: Mapped["User"] = relationship(
        "User",
        lazy="selectin",
    )

    def __str__(self) -> str:
        return f"{self.user_id} ({self.role})"
