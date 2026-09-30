"""SQLAlchemy 2.0 models for immutable Audit History and Security Logging."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from src.core.database import Base, UUIDPrimaryKeyMixin, utc_now
from src.domains.auth.models import User
from src.domains.organizations.models import Organization


class AuditLogEntry(Base, UUIDPrimaryKeyMixin):
    """Immutable audit record tracking critical security and administrative actions."""

    __tablename__ = "audit_log_entry"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organization.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("user.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    action: Mapped[str] = mapped_column(
        String(64),
        index=True,
        nullable=False,
    )
    target_resource: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
    )
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSON().with_variant(JSONB, "postgresql"),
        default=dict,
        nullable=False,
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45),
        nullable=True,
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        index=True,
        nullable=False,
    )

    organization: Mapped["Organization | None"] = relationship("Organization")
    actor: Mapped["User | None"] = relationship("User")

    __table_args__ = (Index("ix_audit_org_created", "organization_id", created_at.desc()),)
