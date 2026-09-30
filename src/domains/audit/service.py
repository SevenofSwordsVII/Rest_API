"""Domain service implementing immutable, append-only Audit History and Security Logging."""

import math
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import PaginationMeta, PaginationParams
from src.domains.audit.models import AuditLogEntry


class AuditService:
    """Manages append-only recording and administrative querying of audit events."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record_audit(
        self,
        action: str,
        target_resource: str,
        organization_id: uuid.UUID | None = None,
        actor_id: uuid.UUID | None = None,
        metadata: dict[str, Any] | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditLogEntry:
        """Append an immutable audit log record."""
        entry = AuditLogEntry(
            organization_id=organization_id,
            actor_id=actor_id,
            action=action,
            target_resource=target_resource,
            metadata_=metadata or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.session.add(entry)
        await self.session.commit()
        await self.session.refresh(entry)
        return entry

    async def list_audit_logs(
        self,
        organization_id: uuid.UUID,
        params: PaginationParams,
        action: str | None = None,
    ) -> tuple[list[AuditLogEntry], PaginationMeta]:
        """Query paginated audit logs for an organization, ordered chronologically descending."""
        query = select(AuditLogEntry).where(AuditLogEntry.organization_id == organization_id)
        if action is not None:
            query = query.where(AuditLogEntry.action == action)
        query = query.order_by(AuditLogEntry.created_at.desc())

        count_stmt = select(func.count()).select_from(query.order_by(None).subquery())
        total_items = (await self.session.execute(count_stmt)).scalar_one_or_none() or 0
        total_pages = math.ceil(total_items / params.per_page) if total_items > 0 else 0

        paged_stmt = query.offset(params.offset).limit(params.per_page)
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
