"""Pydantic v2 schemas for Audit History and Security Logging."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from src.core.pagination import PaginationMeta


class AuditLogResponse(BaseModel):
    """Representation of an immutable audit record."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    organization_id: uuid.UUID | None = None
    actor_id: uuid.UUID | None = None
    action: str
    target_resource: str
    metadata: dict[str, Any] = Field(..., validation_alias="metadata_")
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime


class PaginatedAuditLogsResponse(BaseModel):
    """Paginated envelope for audit log records."""

    items: list[AuditLogResponse]
    pagination: PaginationMeta
